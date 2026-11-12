# Test tree — Docker app stack, installer and Modal cloud mode
Plan: docs/plans/docker-and-cloud-setup.md

Status: Installer = complete, red tests written (T1). Docker stack = outline (tests come with T3). Modal adapters = outline only (T4 held until spike P2-S; no adapter tests yet).

Installer seams (all injectable, so no real Docker, uv, network, terminal or browser is touched): `Seams(which, run, getpass, ask, open_url, echo, is_interactive)`; `main(argv, seams)`; `--root`.
Files: `tests/unit/meta/conftest.py` (fakes), `test_setup_installer.py`, `test_setup_modal.py`.

## Scenario 1: Installer: prerequisites (AC2)
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| I1-P1 | Positive | all tools present, Docker answers | continues, first call is `docker info` | AC2 | test_prerequisites_pass_when_every_tool_is_present_and_docker_runs |
| I1-N1 | Negative | docker / uv / node / ffmpeg missing (4 cases) | that tool is named, non-zero exit, nothing written, no prompt | AC2 | test_missing_tool_is_named_and_nothing_is_written |
| I1-N2 | Negative | Docker installed, daemon down | "docker ... running" message, nothing written | AC2 | test_docker_installed_but_not_running_says_docker_is_not_running |
| I1-E1 | Edge | several tools missing | all are named in one run | AC2 | test_several_missing_tools_are_all_named_in_one_run |
| I1-N3 | Negative | no terminal (stdin not a tty) | "terminal" message, non-zero, no call/prompt/file | AC2 | test_without_a_terminal_the_installer_refuses_and_writes_nothing |
| I1-E2 | Edge | installer imports | only stdlib modules (AST vs `sys.stdlib_module_names`) | AC2/P3 | test_installer_imports_only_the_standard_library |

## Scenario 2: Installer: mode choice
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| I2-P1 | Positive | fake / local | `VIDGEN_AI_MODE` written | AC2 | test_chosen_mode_is_written_as_ai_mode |
| I2-E1 | Edge | "FAKE", "  Local  " | case and spaces ignored | AC2 | test_mode_answer_ignores_case_and_surrounding_spaces |
| I2-N1 | Negative | "", "gpu", "9" then "fake" | asked again, 4 prompts | AC2 | test_invalid_mode_answers_are_asked_again_until_valid |
| I2-P2 | Positive | fake or local | no Modal token prompt, no browser, no modal call | AC3 | test_fake_mode_never_asks_for_modal_tokens, test_local_mode_never_asks_for_modal_tokens |

## Scenario 3: Installer: settings file (`.env`)
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| I3-P1 | Positive | fresh install | mode 0600 | AC2 | test_settings_file_is_owner_only |
| I3-P2 | Positive | fresh install | random 64-hex keys, DB and Redis URLs | AC2 | test_settings_file_has_fresh_random_secrets_and_local_services |
| I3-E1 | Edge | two installs | different secrets | AC2 | test_two_installs_generate_different_secrets |
| I3-P3 | Positive | write | temp file in same folder + `os.replace`, no leftover | AC2 | test_settings_file_is_written_atomically_with_a_same_folder_temp_file |
| I3-E2 | Edge | Ctrl-C during swap / at a prompt | no file, no temp leftover | AC2 | test_ctrl_c_during_the_final_swap_..., test_ctrl_c_at_a_prompt_writes_nothing |
| I3-N1 | Negative | file exists, user declines (n, "", no, maybe) | bytes and mode unchanged, no password asked | AC2 | test_existing_settings_file_is_not_overwritten_when_the_user_declines, test_anything_but_y_keeps_an_existing_settings_file |
| I3-P4 | Positive | file exists, user types y | replaced, 0600 | AC2 | test_existing_settings_file_is_replaced_only_after_an_explicit_y |
| I3-E3 | Edge | re-run, overwrite declined | byte-identical | AC2 | test_rerun_with_overwrite_declined_is_idempotent |
| I3-E4 | Edge | project path with Cyrillic, CJK, emoji, spaces | full flow works | AC2 | test_unicode_project_path_works_end_to_end |

## Scenario 4: Installer: admin login (P3)
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| I4-P1 | Positive | password typed twice | `uv run ... dev_setup.py hash-password`, password on stdin | AC2/P3 | test_admin_hash_is_delegated_to_dev_setup_... |
| I4-P2 | Positive | any run | password in no argv or child variable | AC2 | test_password_never_appears_in_any_argv_or_child_variable |
| I4-P3 | Positive | hash returned | stored single-quoted, password not in file | AC2 | test_hash_returned_by_dev_setup_is_stored_single_quoted_not_the_password |
| I4-P4 | Positive | prompts | password via hidden input only | AC2 | test_password_is_read_with_hidden_input_only |
| I4-N1 | Negative | "", short, 11 chars | refused (12 min), nothing written, no hashing | AC2 | test_too_short_password_is_refused_and_nothing_is_written |
| I4-N2 | Negative | confirmation differs | refused, nothing written | AC2 | test_mismatched_confirmation_is_refused_and_nothing_is_written |
| I4-N3 | Negative | hashing subprocess fails | clear message, nothing written | AC2 | test_failed_hashing_reports_clearly_and_writes_nothing |

## Scenario 5: Installer: migrations (P3)
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| I5-P1 | Positive | y / Y / " y " | exactly one `uv run alembic ... upgrade` call, after the file exists | AC2 | test_migrations_run_once_only_after_an_explicit_y_... |
| I5-N1 | Negative | n, N, "", spaces, yes, maybe, ok, 1 | no migration call | AC2 | test_any_other_answer_applies_no_migration |
| I5-N2 | Negative | migration fails | message, non-zero, settings kept | AC2 | test_failed_migration_is_reported_and_keeps_the_settings_file |
| I5-P2 | Positive | success | prints `docker compose --profile app up -d` | AC2 | test_next_commands_are_printed_at_the_end |

## Scenario 6: Installer: Modal accounts and tokens (AC3, AC5, P4)
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| I6-P1 | Positive | modal mode | `uv run --with modal ...` validates | AC3 | test_modal_mode_validates_the_token_pair_through_uv_run_with_modal |
| I6-P2 | Positive | validation call | tokens via MODAL_TOKEN_ID / MODAL_TOKEN_SECRET child variables, never argv or stdin | AC3/P4 | test_token_pair_reaches_the_modal_subprocess_only_through_child_variables |
| I6-P3 | Positive | prompts | both tokens hidden input | AC3 | test_both_tokens_are_read_with_hidden_input |
| I6-P4 | Positive | success | mode + both tokens in 0600 file | AC3 | test_modal_settings_file_holds_mode_and_both_tokens_owner_only |
| I6-P5 | Positive | account steps | https modal.com links opened (mock) and printed | AC3 | test_account_links_are_opened_in_the_browser_and_printed |
| I6-P6 | Positive | notice | sign-up steps and "names, voices, faces sent to Modal" printed | AC3/AC5 | test_modal_steps_and_privacy_notice_are_printed |
| I6-N1 | Negative | empty ID or secret | message, no modal call, nothing written | AC3 | test_empty_token_is_refused_without_calling_modal_and_writes_nothing |
| I6-N2 | Negative | modal rejects pair | clear message, nothing written | AC3 | test_rejected_token_pair_gives_a_clear_message_and_writes_nothing |
| I6-N3 | Negative | rejected while a confirmed old file exists | old bytes unchanged | AC3 | test_rejected_token_pair_leaves_a_confirmed_existing_file_unchanged |
| I6-N4 | Negative | modal package missing / offline (rc 127) | reported, nothing written | AC3 | test_missing_modal_package_or_network_is_reported_not_crashed |
| I6-N5 | Negative | stderr contains the tokens | never shown or logged | AC3 | test_failed_modal_validation_never_echoes_stderr_that_contains_a_token |
| I6-E1 | Edge | tokens with spaces, tabs, newline | stripped in subprocess variables and file | AC3 | test_tokens_with_surrounding_spaces_are_stripped_everywhere |
| I6-E2 | Edge | order | validation happens before the file exists | AC3 | test_modal_validation_runs_before_the_settings_file_is_written |
| I6-E3 | Edge | whole modal run with migration y | no password, token ID/secret or hash in stdout, stderr, logs | AC2/AC3 | test_no_secret_is_ever_printed_or_logged_in_modal_mode, test_clean_run_prints_and_logs_no_secret |
| I6-E4 | Edge | Ctrl-C while validating | nothing written | AC3 | test_ctrl_c_while_validating_tokens_writes_nothing |
| I6-E5 | Edge | re-run, overwrite declined | byte-identical | AC2 | test_modal_rerun_with_overwrite_declined_keeps_tokens_file_byte_identical |
| I6-X1 | Edge (not testable here) | first template upload in modal mode needs explicit consent | belongs to T4 / API tests (AC5), not the installer | AC5 | N/A in T1 |

## Outline: Docker stack (tests with T3, AC1)
- Positive: `docker compose --profile app config` valid; health endpoint answers; restart keeps data (named volumes for PostgreSQL/Redis, bind mount for media); Devanagari label renders correctly in the Linux image (P7); dashboard served as a production build with `/api` forwarded (P9); no container runs migrations on start; `dev_up.sh` unchanged.
- Negative: port already in use gives a clear message; missing media folder; local mode starts the `app` profile without the worker container.
- Edge: arm64 and amd64 build; API container plus native worker share the media folder; ffmpeg and libfribidi present.

## Outline: Modal adapters (T4 held until spike P2-S; no tests written now)
- Positive: mocked remote speech-to-text / voice cloning / lip sync return expected results; `VIDGEN_AI_MODE=modal` selects them.
- Negative: auth error, timeout, remote crash give a coded row failure, one retry, batch continues; cloud confirmation missing means refuse upload.
- Edge: large video streamed, not loaded; concurrent rows; template cached remotely (content-hash Volume), not re-sent per row.
