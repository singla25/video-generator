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
MAIN_BRANCHES = frozenset({"main", "master"})

DOMAINS = {
    "backend-dev": ["backend/", "docs/agents/backend-dev/", "docs/html/",
                    "scripts/setup.py", "Dockerfile.backend", ".dockerignore",
                    "docker-compose.yml"],
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


SCRIPT_DANGER = [
    r"\bshutil\.rmtree\b", r"\bos\.(remove|unlink|rmdir|removedirs)\b", r"\bperl\b.*\bunlink\b",
    r"\bunlink\s*\(", r"\.(unlink|rmdir)\(",
    r"\burlopen\b", r"\brequests\.(post|put|patch)\b", r"\bhttpx\.(post|put|patch)\b",
    r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b", r"\bTRUNCATE\s+TABLE\b",
]
SQL_CLIENTS = frozenset({"psql", "mysql", "sqlite3", "mariadb"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash"})
WRAPPERS = frozenset(
    {"env", "nohup", "time", "command", "exec", "nice", "xargs", "stdbuf", "timeout"}
)
NET_TOOLS = frozenset({"nc", "ncat", "netcat", "scp", "rsync", "sftp", "ftp"})
SHELL_OPERATORS = ("||", "&&", ";", "|", "&", "\n")


def strip_heredocs(cmd: str) -> str:
    """Remove here-document bodies (they are data, never commands)."""
    pattern = re.compile(
        r"<<-?\s*(['\"]?)(\w+)\1(?P<rest>[^\n]*)\n.*?\n[ \t]*\2[ \t]*(?=\n|\)|$)", re.S
    )
    return pattern.sub(lambda m: m.group("rest"), cmd)


def scan(cmd: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Quote-aware pass over a command line.

    Returns (segments, substitutions): the simple commands with the operator that follows each,
    and the text of every ``$( )`` or backtick substitution (which runs even inside double
    quotes). Operators inside single or double quotes or inside a substitution do not split.
    """
    segments: list[tuple[str, str]] = []
    subs: list[str] = []
    buf: list[str] = []
    quote = ""
    depth = 0
    sub_start = 0
    tick_start = -1
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if ch == "\\" and quote != "'" and i + 1 < len(cmd):
            buf.append(cmd[i : i + 2])
            i += 2
            continue
        if quote == "'":
            quote = "" if ch == "'" else quote
        elif ch == "'" and not quote:
            quote = "'"
        elif ch == '"':
            quote = "" if quote == '"' else ('"' if not quote else quote)
        elif ch == "`":
            if tick_start < 0:
                tick_start = i + 1
            else:
                subs.append(cmd[tick_start:i])
                tick_start = -1
        elif cmd.startswith("$(", i):
            if depth == 0:
                sub_start = i + 2
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
            if depth == 0:
                subs.append(cmd[sub_start:i])
        elif not quote and depth == 0 and tick_start < 0:
            op = next((o for o in SHELL_OPERATORS if cmd.startswith(o, i)), "")
            if op and not (op == "&" and cmd[i - 1 : i] in {">", "<"}) and not (
                op == "|" and cmd[i - 1 : i] == ">"
            ):
                segments.append(("".join(buf), op))
                buf = []
                i += len(op)
                continue
        buf.append(ch)
        i += 1
    segments.append(("".join(buf), ""))
    return segments, subs


def without_single_quotes(text: str) -> str:
    """The text with single-quoted spans removed (what the shell may still expand)."""
    return re.sub(r"'[^']*'", "", text)


def is_data(token: str) -> bool:
    """A token with whitespace is a sentence or script argument, not a path."""
    return any(c.isspace() for c in token)


def check_path_token(token: str) -> None:
    """Judge a path-like token: personal locations, secrets, parent paths, outside the project."""
    value = token.split("=", 1)[-1] if token.startswith("-") and "=" in token else token
    value = value.lstrip("<>&")
    if not value or value.startswith("-") or is_data(value):
        return
    for marker in PERSONAL_PATHS:
        if value.startswith(marker) or f"/{marker.strip('/')}/" in f"/{value}":
            block(f"command touches personal/system location '{marker}'")
    if is_secret(value):
        block(f"secret file: {value}")
    if ".." in value.replace("\\", "/").split("/"):
        block("parent-directory paths ('..') are not allowed")
    if value.startswith("/") and not value.startswith(SAFE_ABSOLUTE) and not inside_project(value):
        block(f"absolute path outside the project: {value}")


def redirect_targets(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split tokens into (arguments, redirect targets); ``>file``, ``> file`` and ``2>file``."""
    args: list[str] = []
    targets: list[str] = []
    take_next = False
    for token in tokens:
        if take_next:
            targets.append(token)
            take_next = False
            continue
        match = re.fullmatch(r"\d*(>>?|<)(&?\S*)", token) if not is_data(token) else None
        if match:
            if match.group(2):
                targets.append(match.group(2))
            else:
                take_next = True
        else:
            args.append(token)
    cleaned = [t.lstrip("&") for t in targets]
    return args, [t for t in cleaned if t and not t.isdigit() and t != "-"]


def check_script(text: str, label: str) -> None:
    """Judge inline code (python -c, perl -e, SQL): deletes, sends and writes to the rules."""
    for pat in SCRIPT_DANGER:
        if re.search(pat, text, re.IGNORECASE):
            block(f"{label} contains a destructive or data-sending call ({pat})")
    if INTERPRETERS.match(label) and re.search(r"CLAUDE\.md|\.claude/|\.git/", text):
        block("rules and git internals are read-only: named in an inline script")


def check_command(tokens: list[str], next_op: str, following: str) -> None:
    """Judge one simple command (already split into words)."""
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0]):
        tokens = tokens[1:]  # leading VAR=value assignments
    args, targets = redirect_targets(tokens)
    for target in targets:
        check_path_token(target)
        if is_protected(target):
            block(f"rules and git internals are read-only: {target}")
    if not args:
        return
    name = os.path.basename(args[0])
    rest = args[1:]
    if name in {"sudo", "doas", "shred"} or name.startswith("mkfs") or name == "truncate":
        block(f"destructive or approval-required command ({name})")
    if name == "env" and not rest:
        block("reading environment variables")
    if name in WRAPPERS:
        skip = 0
        while skip < len(rest) and (rest[skip].startswith("-") or rest[skip].isdigit()):
            skip += 1
        check_command(rest[skip:], next_op, following)
        return
    if name == "printenv" or (
        name in {"export", "declare"} and any(a in {"-p", "-x"} for a in rest)
    ):
        block("reading environment variables")
    if name in SHELLS and "-c" in rest and rest.index("-c") + 1 < len(rest):
        check_bash(rest[rest.index("-c") + 1])
        return
    if name == "git":
        sub, git_args = git_parts(args)
        check_git(git_args, sub)
    elif name == "rm":
        check_rm(rest)
    elif name == "dd" and any(t.startswith("if=") for t in rest):
        block("destructive or approval-required command (dd if=)")
    elif name == "chown" and has_flag(rest, "R", "--recursive"):
        block("chown -R")
    elif name == "chmod" and has_flag(rest, "R", "--recursive") and "777" in rest:
        block("chmod -R 777")
    elif name == "find" and ("-delete" in rest or any(
        a == "-exec" and rest[i + 1 : i + 2] == ["rm"] for i, a in enumerate(rest)
    )):
        block("find that deletes")
    elif name in NET_TOOLS:
        block("sending data out of the project is not allowed")
    elif name in {"curl", "wget"}:
        if has_flag(rest, "d", "--data", "--data-raw", "--data-binary", "--data-urlencode") or \
                has_flag(rest, "F", "--form") or has_flag(rest, "T", "--upload-file") or \
                any(a.startswith("--post") for a in rest) or re.search(
                    r"-X\s*(POST|PUT|PATCH)", " ".join(rest), re.IGNORECASE):
            block("sending data out of the project is not allowed")
        if next_op == "|" and re.match(r"\s*(ba|z|da)?sh\b", following):
            block("piping a download into a shell")
    if "alembic" in args and any(a in {"upgrade", "downgrade"} for a in args):
        block("migrations need Admin approval")
    if "manage.py" in " ".join(args) and "migrate" in args:
        block("migrations need Admin approval")
    if name in SQL_CLIENTS:
        check_script(" ".join(rest), name)
    if INTERPRETERS.match(name) and any(f in rest for f in ("-c", "-e")):
        check_script(" ".join(rest), name)
    check_protected_writes(args, name)
    for token in rest:
        check_path_token(token)


def check_protected_writes(args: list[str], name: str) -> None:
    """Block commands that change files and name .claude/, CLAUDE.md or .git/ as an argument."""
    touches = [t for t in args[1:] if not t.startswith("-") and not is_data(t) and is_protected(t)]
    if not touches:
        return
    sed_in_place = name == "sed" and any(
        a == "--in-place" or re.fullmatch(r"-[A-Za-z]*i[A-Za-z]*", a) for a in args
    )
    if name in WRITERS or sed_in_place:
        block(f"rules and git internals are read-only: {touches[0]}")


def check_bash(cmd: str) -> None:
    """Judge a whole Bash command line (quote-aware; here-document bodies are data)."""
    cmd = strip_heredocs(cmd.replace(str(PROJECT), "."))
    segments, subs = scan(cmd)
    for inner in subs:
        check_bash(inner)
    if SECRET_VARIABLE.search(without_single_quotes(cmd)):
        block("expanding a secret-looking variable")
    for index, (segment, op) in enumerate(segments):
        try:
            tokens = shlex.split(segment, comments=False, posix=True)
        except ValueError:
            block("could not parse the command (unbalanced quotes)")
            return
        following = segments[index + 1][0] if index + 1 < len(segments) else ""
        check_command(tokens, op, following)


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
    elif tool in GITHUB_WRITES and (
        str(ti.get("branch", "")).removeprefix("refs/heads/") in MAIN_BRANCHES
    ):
        block("writing to main through the GitHub tools is not allowed")
    sys.exit(0)


if __name__ == "__main__":
    main()
