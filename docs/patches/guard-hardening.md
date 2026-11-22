# Guard hook hardening (round 4, finding 1)

Admin action: copy the proposed file over the hook.

    cp docs/patches/guard.hardened.py .claude/hooks/guard.py

Nothing under `.claude/` was changed by the optimizer. The proposal is tested by
`tests/unit/meta/test_guard_hardened.py` (82 cases: 33 bypass variants that the current guard allows, 22 old protections that must stay,
25 ordinary commands that must still pass, plus the GitHub tool rule). One ordinary command, a safe branch delete,
is wrongly blocked by the current guard. The counts were checked by running the current guard on every case.

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
