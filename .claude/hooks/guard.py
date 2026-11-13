#!/usr/bin/env python3
"""Safety guard for every agent (ceo, backend-dev, frontend-dev, tester).

Runs as a Claude Code PreToolUse hook. It reads the tool call as JSON on stdin
and exits with code 2 (block) when the call would:
  * destroy code (rm -rf, git reset --hard, git clean, force push, ...)
  * touch files outside the project folder (Admin's personal data)
  * read or write secrets (.env, keys, credentials)
  * modify the rules (.claude/, CLAUDE.md, .git/)
  * send data to the internet from the shell (curl/wget uploads, curl | sh)
  * write outside the agent's own domain (when the agent name is available)

Exit 0 = allow. Exit 2 = block; stderr is shown to the agent as the reason.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()

# Agents work in git worktrees under .worktrees/<name>/; judge their paths as if at the repo root.
WORKTREE = re.compile(r"^\.worktrees/[^/]+/")

DESTRUCTIVE = [
    r"\brm\s+(-[a-zA-Z]*[rRf][a-zA-Z]*\s+)+",      # rm -r / -rf / -f
    r"\brm\s+.*\*",                                 # rm with wildcard
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bgit\s+push\b.*(--force|-f\b|--force-with-lease)",
    r"\bgit\s+push\b.*\s\+\S+",                     # git push origin +branch
    r"\bgit\s+branch\s+-D\b",
    r"\bgit\s+checkout\s+--\s+\.",                  # discard all changes
    r"\bgit\s+restore\s+(--staged\s+)?\.\s*$",
    r"\bgit\s+filter-(branch|repo)\b",
    r"\bgit\s+update-ref\s+-d\b",
    r"\bfind\b.*-delete\b",
    r"\bfind\b.*-exec\s+rm\b",
    r"\bshred\b", r"\bmkfs\b", r"\bdd\s+if=", r"\btruncate\b",
    r">\s*/dev/sd", r"\bchmod\s+-R\s+777\b", r"\bchown\s+-R\b",
    r"\bsudo\b",
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", r"\bTRUNCATE\s+TABLE\b",
    r"\balembic\s+(upgrade|downgrade)\b",           # migrations need Admin approval
    r"\b(manage\.py|django-admin)\s+migrate\b",
]

NETWORK_EXFIL = [
    r"\bcurl\b.*(\s-d\b|--data|-F\b|--form|-T\b|--upload-file|-X\s*(POST|PUT|PATCH))",
    r"\bwget\b.*--post",
    r"\b(curl|wget)\b.*\|\s*(ba|z)?sh\b",
    r"\b(nc|ncat|netcat|scp|rsync|sftp|ftp)\b",
]

SECRET_NAMES = re.compile(
    r"(^|/)(\.env(\.[^/]*)?|.*\.pem|.*\.key|id_rsa.*|id_ed25519.*|.*credentials.*|"
    r".*secrets?\.(json|ya?ml|toml|txt)|\.netrc|\.pgpass|\.npmrc|\.pypirc)$",
    re.IGNORECASE,
)
SAFE_SECRET_TEMPLATES = re.compile(r"\.env\.(example|sample|template)$", re.IGNORECASE)

PERSONAL_PATHS = [
    "~/", "$HOME", "${HOME}", "/home/", "/Users/", "/root/", "C:\\Users",
    ".ssh", ".aws", ".gnupg", ".kube", ".docker/config", "Library/",
    "Documents/", "Desktop/", "Downloads/", "Pictures/", "/etc/shadow", "/etc/passwd",
]

PROTECTED_WRITES = re.compile(r"(^|/)(\.claude/|CLAUDE\.md$|\.git/)")

# Write domains per agent (used only if Claude Code passes the agent name).
DOMAINS = {
    "backend-dev": ["backend/", "docs/agents/backend-dev/", "docs/html/",
                    "scripts/setup.py", "Dockerfile.backend", ".dockerignore", "docker-compose.yml"],
    "frontend-dev": ["frontend/", "docs/agents/frontend-dev/", "docs/html/", "Dockerfile.frontend"],
    "tester": ["tests/", "docs/test-tree/", "docs/agents/tester/", "docs/html/"],
    "ceo": ["docs/"],
}


def block(reason: str) -> None:
    print(f"BLOCKED by project guard: {reason}. See CLAUDE.md §3. "
          "If this is really needed, report it to the CEO / Admin.", file=sys.stderr)
    sys.exit(2)


def resolve(p: str) -> Path:
    path = Path(os.path.expanduser(p))
    if not path.is_absolute():
        path = PROJECT / path
    return path.resolve()


def inside_project(p: str) -> bool:
    try:
        resolve(p).relative_to(PROJECT)
        return True
    except ValueError:
        return False


def rel(p: str) -> str:
    try:
        return resolve(p).relative_to(PROJECT).as_posix()
    except ValueError:
        return p


def is_secret(p: str) -> bool:
    name = rel(p)
    return bool(SECRET_NAMES.search(name)) and not SAFE_SECRET_TEMPLATES.search(name)


def check_path(p: str, writing: bool, agent: str | None) -> None:
    if not p:
        return
    if not inside_project(p):
        block(f"path outside the project folder: {p}")
    if is_secret(p):
        block(f"secret file: {rel(p)}")
    if writing:
        r = WORKTREE.sub("", rel(p))
        if PROTECTED_WRITES.search(r):
            block(f"rules and git internals are read-only: {r}")
        if agent in DOMAINS and not any(r.startswith(d) for d in DOMAINS[agent]):
            block(f"{agent} may not write outside its domain {DOMAINS[agent]}: {r}")


def check_bash(cmd: str) -> None:
    # Paths inside the project are fine even if the project lives under /home or /Users.
    cmd = cmd.replace(str(PROJECT), ".")
    for pat in DESTRUCTIVE:
        if re.search(pat, cmd, re.IGNORECASE):
            block(f"destructive or approval-required command ({pat})")
    for pat in NETWORK_EXFIL:
        if re.search(pat, cmd, re.IGNORECASE):
            block("sending data out of the project is not allowed")
    for marker in PERSONAL_PATHS:
        if marker in cmd:
            block(f"command touches personal/system location '{marker}'")
    if re.search(r"(^|[\s'\"/])\.env(\s|$|['\"])", cmd) or re.search(r"\b(printenv|env)\s*($|\|)", cmd):
        block("reading secrets or environment variables")
    for token in re.findall(r"(?:^|\s)(/[^\s;|&'\"]+)", cmd):
        if not token.startswith(("/dev/null", "/tmp/", "/usr/bin/", "/bin/")) and not inside_project(token):
            block(f"absolute path outside the project: {token}")
    if re.search(r"(^|\s)\.\.(/|\s|$)", cmd):
        block("parent-directory paths ('..') are not allowed")
    if re.search(r">\s*(CLAUDE\.md|\.claude/)", cmd):
        block("rules are read-only")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        block("could not read tool call")
        return
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    agent = data.get("agent_type") or data.get("subagent_type") or data.get("agent_name")

    if tool == "Bash":
        check_bash(ti.get("command", ""))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_path(ti.get("file_path") or ti.get("notebook_path", ""), True, agent)
    elif tool == "Read":
        check_path(ti.get("file_path", ""), False, agent)
    elif tool in ("Glob", "Grep"):
        check_path(ti.get("path", "") or str(PROJECT), False, agent)
    elif tool == "WebFetch" and re.search(r"[?&](data|token|key|secret)=", ti.get("url", ""), re.I):
        block("URL looks like it carries data out")
    sys.exit(0)


if __name__ == "__main__":
    main()
