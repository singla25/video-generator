# Guard hook hardening (round 4, finding 1)

Admin action: copy the proposed file over the hook.

    cp docs/patches/guard.hardened.py .claude/hooks/guard.py

Nothing under `.claude/` was changed by the optimizer. The proposal is tested by
`tests/unit/meta/test_guard_hardened.py` (122 cases: 33 bypass variants that the current guard allows, 22 old protections that must stay,
15 dangerous commands hidden in substitutions, wrappers, later commands and `-c` strings,
50 ordinary commands that must still pass, plus the GitHub tool rule). One ordinary command, a safe branch delete,
is wrongly blocked by the current guard. The bypass counts were checked by running the current guard on every case.

Revision after the CEO review of this PR: the first version cut the command at `;`, `&&` and newlines even inside
quotes, so commit messages with a body, trailers, `;` or `&&` in the text, heredoc messages, and searches such as
`grep -rn sudo scripts` were blocked. The command is now scanned quote-aware: operators split only outside quotes,
`$( )` and backtick substitutions are judged as commands of their own, here-document bodies are data, shell `-c`
strings are judged recursively, and the danger rules look at the command, its flags and inline scripts (`python -c`,
SQL clients), not at quoted text handed to `grep`, `echo` or `git commit`. 18 more everyday commands from this
session (loops, `$(date)`, pipes, `2>&1`, worktrees, `uv export`) were also checked and all pass.

What changes in behaviour:

- A Bash command is split into simple commands and tokens (`shlex`), so `git -C . push --force`, `git -c k=v push -f`, `rm --recursive --force`, forced checkout and forced worktree removal are seen.
- `git push` to `main` or `master` is blocked, as are `--mirror`, `--delete`, `+ref` and `:ref` pushes. The lower-case safe branch delete (merged branches only) is no longer a false positive.
- `.env.*` files (except `.env.example`), `printenv`, secret-looking variable expansions such as `$VIDGEN_ENCRYPTION_KEY`, and `/proc/` are blocked in shell commands.
- `..` inside a path (`a/../../b`) and absolute redirect targets glued to the operator (`>/etc/x`) are blocked.
- Shell writes to `.claude/`, `CLAUDE.md` and `.git/` (`sed -i`, `tee`, `cp`, `mv`, `dd`, redirects, and inline `python -c` or `perl -e` scripts that name them) are blocked; reading them (`cat`, `sed -n`, `diff`) is still allowed.
- Inline scripts that delete files or send data out (`shutil.rmtree`, `os.remove`, `urlopen`, `requests.post`) are blocked.
- The GitHub MCP write tools (`push_files`, `create_or_update_file`, `delete_file`) may not write to `main` or `master`.

Known limits (a regex or token guard cannot be complete): a command built from variables or from a script file written earlier, `eval`, and base64-decoded commands are not understood. The strongest protection is still a read-only checkout of `.claude/` for the agents, which only the Admin can set up.

Deliberately unchanged: the guard only judges the Bash, file and web tools. `merge_pull_request` is not blocked, because the CEO may merge with the Admin's permission.

Order of work: the hardened file was written first and the tests second, so the first test run was not red. It had one failing case (the inline-script write to `CLAUDE.md`), which was then fixed. Against the current guard, 33 of the bypass cases are allowed (measured).
