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

## Scenario 7: Docker stack, static checks (AC1, P2, P4, P7, P9)
Files: `tests/unit/meta/test_docker_stack.py` (text checks; pyyaml is not a direct dependency), `test_setup_workers.py`.
| ID | Type | Given / When | Then | Test |
|----|------|--------------|------|------|
| D1-P1 | Positive | compose file | postgres/redis have no profile; api, worker, dashboard in `app` | test_postgres_and_redis_keep_no_profile..., test_api_worker_and_dashboard_are_in_profile_app |
| D1-P2 | Positive | ports | `127.0.0.1:${VIDGEN_API_PORT:-n}` and `VIDGEN_DASHBOARD_PORT`; worker has none | test_host_port_is_parameterised_and_bound_to_loopback, test_worker_publishes_no_port |
| D1-N1 | Negative | any app port | never published on all interfaces | test_no_app_service_publishes_a_port_on_all_interfaces |
| D1-P3 | Positive | media | bind mount `${VIDGEN_MEDIA_DIR:-./media}`, storage root = mount path, only pg/redis named volumes | test_media_is_a_parameterised_bind_mount..., test_storage_root_inside_the_container_is_the_mount_path, test_only_postgres_and_redis_use_named_volumes |
| D1-P4 | Positive | wiring | database host `postgres`, redis host `redis`, no 127.0.0.1 | test_containers_reach_database_and_redis_by_service_name |
| D1-P5 | Positive | settings | `env_file` from `VIDGEN_ENV_FILE`; worker gets Modal pair; api/dashboard never (blank only) | test_settings_file_comes_from_a_parameter..., test_worker_receives_the_modal_token_pair, test_api_and_dashboard_never_get_the_modal_tokens |
| D1-P6 | Positive | workers | `scale: ${VIDGEN_DOCKER_WORKERS:-1}`; installer writes 1 / 0 (local) / 1 | test_worker_count_is_a_parameter_defaulting_to_one, test_docker_worker_count_follows_the_mode |
| D1-N2 | Negative | any compose/Dockerfile | no alembic / migration on start | test_nothing_runs_migrations_on_container_start |
| D1-N3 | Negative | ignore file | excludes settings files, .dev, media, .venv, node_modules, .worktrees, .git | test_dockerignore_keeps_secrets_state_and_heavy_folders_out_of_the_build |
| D1-P7 | Positive | backend image | ffmpeg + libfribidi, non-root, no COPY of settings | test_backend_image_* |
| D1-P8 | Positive | dashboard image | production build, api requests forwarded to service `api`, no vite dev server | test_dashboard_image_* |

## Scenario 8: Docker stack, real containers (e2e, skipped without Docker)
`tests/e2e/test_docker_stack_e2e.py`, project `vidgen-t3test`, own ports and temp media, demo settings; teardown `down -v` of that project only.
| ID | Type | Then | Test |
|----|------|------|------|
| D2-P1 | Positive | the health endpoint answers through the dashboard's api forward | test_health_endpoint_answers_through_the_dashboard_api_forward |
| D2-P2 | Positive | `PIL.features.check('raqm')` is True in the worker image (Devanagari) | test_pillow_raqm_layout_is_available_inside_the_worker_image |

## Scenario 9: Installer offers only modes the backend accepts (gap 1, ADR-013)
Accepted modes = `ai_mode: Literal[...]` in `<root>/backend/vidgen/settings.py`, parsed with `ast` (never imported). Offered = MODES intersected with accepted; missing or unusable file means fake and local only. File: `tests/unit/meta/test_setup_mode_gate.py`; the Modal fixtures now write an accepting settings.py (conftest `settings_source`).
| ID | Type | Given / When | Then | Test |
|----|------|--------------|------|------|
| G1-N1 | Negative | modal typed, not accepted | "not available yet" + ADR-013, asked again; no token prompt, browser, `--with` call; no modal keys in file | test_modal_is_refused_..., test_repeated_modal_answers_never_reach_the_token_step |
| G1-N2 | Negative | prompt text | lists only available modes | test_the_prompt_lists_only_the_available_modes |
| G1-P1 | Positive | backend accepts modal | existing Modal flow unchanged | test_modal_works_as_before_when_the_backend_accepts_it |
| G1-N3 | Negative | REAL repo settings.py | modal refused today (T4 flips this on purpose) | test_real_backend_settings_refuse_modal_today |
| G1-E1 | Edge | Literal over several lines / single quotes | parsed correctly | test_literal_written_across_several_lines_is_understood, test_single_quoted_literal_* |
| G1-E2 | Edge | `ai_backend` Literal has modal, `ai_mode` not (and reverse, either order) | only `ai_mode` counts | test_modal_in_ai_backend_does_not_make_ai_mode_accept_it, test_modal_in_ai_mode_is_accepted_... |
| G1-E3 | Edge | file with a top-level raise | parsed, not imported | test_settings_file_is_parsed_not_imported |
| G1-E4 | Edge | missing, syntax error, no ai_mode, not a Literal | fallback fake/local | test_missing_or_unusable_settings_fall_back_to_fake_and_local_only |
| G1-E5 | Edge | unknown mode "cuda" accepted by backend; backend lacks fake | not offered (intersection) | test_a_mode_the_installer_does_not_know_is_never_offered, test_a_mode_the_backend_does_not_accept_is_not_offered_even_if_fake |

## Outline: still to cover later
- Port already in use gives a clear message; arm64 and amd64 build; restart keeps data; local mode (no worker container) plus native worker share the media folder.

## Outline: Modal adapters (T4 held until spike P2-S; no tests written now)
- Positive: mocked remote speech-to-text / voice cloning / lip sync return expected results; `VIDGEN_AI_MODE=modal` selects them.
- Negative: auth error, timeout, remote crash give a coded row failure, one retry, batch continues; cloud confirmation missing means refuse upload.
- Edge: large video streamed, not loaded; concurrent rows; template cached remotely (content-hash Volume), not re-sent per row.
