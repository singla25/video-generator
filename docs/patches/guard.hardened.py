#!/usr/bin/env python3
"""PROPOSED replacement for .claude/hooks/guard.py (round 4, finding 1). Admin applies it.

Same contract as the current guard: a PreToolUse hook that reads the tool call as JSON on stdin
and exits 2 to block, 0 to allow. What changes is how a Bash command is judged: it is split into
simple commands and tokens (shlex), so option order, long flags, ``git -C`` / ``git -c`` before the
subcommand, ``..`` inside a path, ``.env.*`` files, environment-variable reads and shell writes to
the rules are all seen. Tests: tests/unit/meta/test_guard_hardened.py (one case per bypass).

Install (Admin only, this file lives outside .claude/ on purpose):
    cp docs/patches/guard.hardened.py .claude/hooks/guard.py
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()

# Agents work in git worktrees under .worktrees/<name>/; judge their paths as if at the repo root.
WORKTREE = re.compile(r"^\.worktrees/[^/]+/")

# Regex rules over the whole command text (kept from the old guard; they catch plain forms).
DESTRUCTIVE = [
    r"\bshred\b", r"\bmkfs\b", r"\bdd\s+if=", r"\btruncate\b",
    r">\s*/dev/sd", r"\bchmod\s+-R\s+777\b", r"\bchown\s+-R\b", r"\bsudo\b",
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", r"\bTRUNCATE\s+TABLE\b",
    r"\balembic\s+(upgrade|downgrade)\b",
    r"\b(manage\.py|django-admin)\s+migrate\b",
    r"\bfind\b.*-delete\b", r"\bfind\b.*-exec\s+rm\b",
    r"\bshutil\.rmtree\b", r"\bos\.(remove|unlink|rmdir)\b", r"\bperl\b.*\bunlink\b",
    r"\bPath\([^)]*\)\.(unlink|rmdir)\b",
]
NETWORK_EXFIL = [
    r"\bcurl\b.*(\s-d\b|--data|-F\b|--form|-T\b|--upload-file|-X\s*(POST|PUT|PATCH))",
    r"\bwget\b.*--post",
    r"\b(curl|wget)\b.*\|\s*(ba|z)?sh\b",
    r"\b(nc|ncat|netcat|scp|rsync|sftp|ftp)\b",
    r"\b(urlopen|requests\.(post|put|patch)|httpx\.(post|put|patch))\b",
]
SECRET_NAMES = re.compile(
    r"(^|/)(\.env(\.[^/]*)?|.*\.pem|.*\.key|id_rsa.*|id_ed25519.*|.*credentials.*|"
    r".*secrets?\.(json|ya?ml|toml|txt)|\.netrc|\.pgpass|\.npmrc|\.pypirc)$",
    re.IGNORECASE,
)
SAFE_SECRET_TEMPLATES = re.compile(r"\.env\.(example|sample|template)$", re.IGNORECASE)
SECRET_VARIABLE = re.compile(r"\$\{?[A-Za-z_]*(KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Za-z_]*\}?")
PERSONAL_PATHS = [
    "~/", "$HOME", "${HOME}", "/home/", "/Users/", "/root/", "C:\\Users",
    ".ssh", ".aws", ".gnupg", ".kube", ".docker/config", "Library/",
    "Documents/", "Desktop/", "Downloads/", "Pictures/", "/etc/shadow", "/etc/passwd",
    "/proc/",
]
PROTECTED = re.compile(r"(^|/)(\.claude(/|$)|CLAUDE\.md$|\.git(/|$))")
# Commands that change files: a protected path as any argument of these is a write.
WRITERS = frozenset({"cp", "mv", "tee", "install", "ln", "dd", "rsync", "patch", "touch", "chmod"})
INTERPRETERS = re.compile(r"^(python[0-9.]*|perl|ruby|node|bash|sh|zsh)$")
SAFE_ABSOLUTE = ("/dev/null", "/tmp/", "/usr/bin/", "/bin/")
SEPARATORS = re.compile(r"\|\||&&|;|\||\n|&(?!>)")
MAIN_BRANCHES = frozenset({"main", "master"})

DOMAINS = {
    "backend-dev": ["backend/", "docs/agents/backend-dev/", "docs/html/",
                    "scripts/setup.py", "Dockerfile.backend", ".dockerignore", "docker-compose.yml"],
    "frontend-dev": ["frontend/", "docs/agents/frontend-dev/", "docs/html/", "Dockerfile.frontend"],
    "tester": ["tests/", "docs/test-tree/", "docs/agents/tester/", "docs/html/"],
    "ceo": ["docs/"],
}
GITHUB_WRITES = frozenset({
    "mcp__github__push_files", "mcp__github__create_or_update_file", "mcp__github__delete_file",
})


def block(reason: str) -> None:
    """Stop the tool call with a reason shown to the agent."""
    print(f"BLOCKED by project guard: {reason}. See CLAUDE.md §3. "
          "If this is really needed, report it to the CEO / Admin.", file=sys.stderr)
    sys.exit(2)


def resolve(p: str) -> Path:
    """Absolute, symlink-free form of a path (relative paths are taken from the project)."""
    path = Path(os.path.expanduser(p))
    if not path.is_absolute():
        path = PROJECT / path
    return path.resolve()


def inside_project(p: str) -> bool:
    """True when ``p`` resolves inside the project folder."""
    try:
        resolve(p).relative_to(PROJECT)
        return True
    except ValueError:
        return False


def rel(p: str) -> str:
    """Project-relative form of a path, or the path itself when it is outside."""
    try:
        return resolve(p).relative_to(PROJECT).as_posix()
    except ValueError:
        return p


def is_secret(p: str) -> bool:
    """True for secret-looking file names (templates such as .env.example are fine)."""
    name = rel(p)
    return bool(SECRET_NAMES.search(name)) and not SAFE_SECRET_TEMPLATES.search(name)


def is_protected(p: str) -> bool:
    """True for the rules and git internals (.claude/, CLAUDE.md, .git/)."""
    return bool(PROTECTED.search(WORKTREE.sub("", rel(p))))


def check_path(p: str, writing: bool, agent: str | None) -> None:
    """Judge one file path of a Read/Write/Edit/Glob/Grep call."""
    if not p:
        return
    if not inside_project(p):
        block(f"path outside the project folder: {p}")
    if is_secret(p):
        block(f"secret file: {rel(p)}")
    if writing:
        r = WORKTREE.sub("", rel(p))
        if PROTECTED.search(r):
            block(f"rules and git internals are read-only: {r}")
        if agent in DOMAINS and not any(r.startswith(d) for d in DOMAINS[agent]):
            block(f"{agent} may not write outside its domain {DOMAINS[agent]}: {r}")


def git_parts(tokens: list[str]) -> tuple[str, list[str]]:
    """Split a ``git`` command into (subcommand, its arguments), skipping global options."""
    i = 1
    with_value = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
    while i < len(tokens):
        token = tokens[i]
        if token in with_value:
            i += 2
        elif token.startswith("-"):
            i += 1
        else:
            return token, tokens[i + 1 :]
    return "", []


def has_flag(args: list[str], short: str, *long: str) -> bool:
    """True if ``args`` has the short flag (alone or inside a group like -fd) or a long flag."""
    for arg in args:
        if arg in long or any(arg.startswith(f"{name}=") for name in long):
            return True
        if re.fullmatch(rf"-[A-Za-z]*{re.escape(short)}[A-Za-z]*", arg):
            return True
    return False


def check_git(args: list[str], sub: str) -> None:
    """Block history rewriting, forced or main-branch pushes and discarding work."""
    if sub == "push":
        if has_flag(args, "f", "--force", "--force-with-lease", "--force-if-includes", "--mirror"):
            block("forced or mirror push")
        if has_flag(args, "d", "--delete") or any(a.startswith(("+", ":")) for a in args):
            block("push that deletes or force-updates a remote ref")
        refs = [a.split(":")[-1].removeprefix("refs/heads/") for a in args if not a.startswith("-")]
        if any(ref in MAIN_BRANCHES for ref in refs):
            block("nobody pushes to main directly (CLAUDE.md §4)")
    elif sub == "reset" and has_flag(args, "", "--hard", "--merge", "--keep"):
        block("git reset that discards work")
    elif sub == "clean":
        block("git clean")
    elif sub == "branch" and (has_flag(args, "D") or (has_flag(args, "d", "--delete") and
                                                     has_flag(args, "f", "--force"))):
        block("forced branch deletion")
    elif sub in {"checkout", "switch"} and has_flag(args, "f", "--force", "--discard-changes"):
        block("forced checkout discards work")
    elif sub == "checkout" and "--" in args and "." in args:
        block("discard all changes")
    elif sub == "restore" and "." in args:
        block("discard all changes")
    elif sub == "worktree" and "remove" in args and has_flag(args, "f", "--force"):
        block("forced worktree removal")
    elif sub == "stash" and any(a in {"drop", "clear"} for a in args):
        block("git stash drop/clear")
    elif sub in {"filter-branch", "filter-repo"}:
        block("history rewriting")
    elif sub == "update-ref" and "-d" in args:
        block("git update-ref -d")
    elif sub in {"gc", "prune", "reflog"} and any("prune" in a or "expire" in a for a in args):
        block("irreversible repository clean-up")


def check_rm(args: list[str]) -> None:
    """Block recursive or forced deletion and wildcards (long and short flags)."""
    if has_flag(args, "r", "--recursive") or has_flag(args, "R") or has_flag(
        args, "f", "--force", "--no-preserve-root"
    ):
        block("rm with recursive or force flags")
    if any("*" in a for a in args):
        block("rm with a wildcard")


def check_secret_reads(tokens: list[str], command: str) -> None:
    """Block secret files, environment dumps and secret-looking variable expansions."""
    for token in tokens:
        if token.startswith("-") and "=" not in token:
            continue
        value = token.split("=", 1)[-1] if token.startswith("-") else token
        if value and is_secret(value):
            block(f"secret file: {value}")
    if re.search(r"\b(printenv|export\s+-p|declare\s+-x)\b", command):
        block("reading environment variables")
    if tokens[:1] in (["env"], ["set"]) and len(tokens) == 1:
        block("reading environment variables")
    if SECRET_VARIABLE.search(command):
        block("expanding a secret-looking variable")


def check_protected_writes(tokens: list[str], command: str) -> None:
    """Block shell writes to .claude/, CLAUDE.md and .git/ (any command that changes files)."""
    name = os.path.basename(tokens[0])
    scripting = bool(INTERPRETERS.match(name)) and any(f in tokens for f in ("-c", "-e"))
    touches = [t for t in tokens if t and not t.startswith("-") and is_protected(t)]
    if scripting and re.search(r"CLAUDE\.md|\.claude/|\.git/", command):
        touches.append("a protected path inside an inline script")  # the path is in the code
    if not touches:
        return
    redirect = re.search(r">>?\s*\S*(CLAUDE\.md|\.claude/|\.git/)", command)
    sed_in_place = name == "sed" and any(a == "-i" or a.startswith("-i") or a == "--in-place"
                                         for a in tokens)
    if name in WRITERS or sed_in_place or scripting or redirect:
        block(f"rules and git internals are read-only: {touches[0]}")


def check_tokens(tokens: list[str], command: str) -> None:
    """Judge one simple command."""
    if not tokens:
        return
    name = os.path.basename(tokens[0])
    if name == "git":
        sub, args = git_parts(tokens)
        check_git(args, sub)
    elif name == "rm":
        check_rm(tokens[1:])
    check_secret_reads(tokens, command)
    check_protected_writes(tokens, command)
    for token in tokens:
        parts = token.replace("\\", "/").split("/")
        if ".." in parts:
            block("parent-directory paths ('..') are not allowed")
        candidate = token.split("=", 1)[-1].lstrip("<>")
        if candidate.startswith("/") and not candidate.startswith(SAFE_ABSOLUTE) \
                and not inside_project(candidate):
            block(f"absolute path outside the project: {candidate}")


def check_bash(cmd: str) -> None:
    """Judge a whole Bash command line."""
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
    # A redirect target is judged even when it is glued to the operator (``>/etc/x``).
    for target in re.findall(r">>?\s*([^\s;|&<>]+)", cmd):
        if target.startswith("/") and not target.startswith(SAFE_ABSOLUTE) \
                and not inside_project(target):
            block(f"absolute path outside the project: {target}")
    for part in SEPARATORS.split(cmd):
        try:
            tokens = shlex.split(part, comments=False, posix=True)
        except ValueError:
            block("could not parse the command (unbalanced quotes)")
            return
        check_tokens(tokens, part)


def main() -> None:
    """Read the tool call from stdin and allow or block it."""
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
    elif tool in GITHUB_WRITES and str(ti.get("branch", "")).removeprefix("refs/heads/") in MAIN_BRANCHES:
        block("writing to main through the GitHub tools is not allowed")
    sys.exit(0)


if __name__ == "__main__":
    main()
