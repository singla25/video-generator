# Test tree - M2 Real AI adapters (G3, RED)
Plan: docs/plans/m2-real-ai.md

All tests run on CPU in well under a second each. No model library is imported or loaded: each adapter takes an `engine_factory` (a zero-argument callable that loads the model) and the tests pass a stub. Real-model tests are not part of G3 (the `real_ai` marker is not registered; see open questions).

Proposed seams (the contract G4 must meet): modules under `backend/vidgen/infrastructure/ai/`; common `errors.py` with `ModelLoadError(code, message)` and `AdapterTimeoutError(message)` (both `DomainError`; timeout code `RENDER_TIMEOUT`); constructor keyword `engine_factory` (STT: `model_factory`), `timeout_s`, lazy load on first use, kept warm.

## Scenario 1: Transcribe the template (faster-whisper) - AC2
| ID | Type | Given / When | Then | AC | Test (tests/unit/infra/ai/test_faster_whisper_stt.py) |
|----|------|--------------|------|----|------|
| M2-S1-P1 | Positive | model returns " Krishan", " ji" with times | `Word` list, text stripped, start/end/confidence kept | AC2 | test_stt_adapter_returns_words_with_start_end_and_confidence |
| M2-S1-P2 | Positive | used as `SpeechToText` | satisfies the port | AC2 | test_stt_adapter_satisfies_the_speech_to_text_port |
| M2-S1-P3 | Positive | transcribe | `word_timestamps=True` and language passed | AC2 | test_stt_adapter_asks_the_model_for_word_timestamps |
| M2-S1-P4 | Positive | two calls | model loaded lazily, once | AC10, D-M2-3 | test_stt_adapter_loads_the_model_lazily_and_only_once |
| M2-S1-N1 | Negative | missing file | FileNotFoundError, model not loaded | AC7 | test_stt_adapter_missing_audio_file_fails_before_loading_the_model |
| M2-S1-N2 | Negative | 0-byte file | DomainError STT_FAILED | AC7 | test_stt_adapter_empty_audio_file_is_a_coded_error |
| M2-S1-N3 | Negative | model load fails | ModelLoadError (STT_FAILED), cause chained | AC7 | test_stt_adapter_model_load_failure_is_a_model_load_error |
| M2-S1-N4 | Negative | model raises while transcribing | STT_FAILED | AC7 | test_stt_adapter_model_crash_during_transcribe_is_stt_failed |
| M2-S1-E1 | Edge | Devanagari word | text intact | AC2 | test_stt_adapter_keeps_devanagari_words_intact |
| M2-S1-E2 | Edge | no speech | `[]`, no error | AC2 | test_stt_adapter_returns_no_words_for_silence |
| M2-S1-E3 | Edge | zero-frame WAV | `[]` | AC2 | test_stt_adapter_accepts_a_zero_length_wav |
| M2-S1-E4 | Edge | 5000 words | order kept | AC2 | test_stt_adapter_handles_a_very_long_transcript |
| M2-S1-E5 | Edge | probability -0.2 / 1.7 | clamped to 0..1 | AC2 | test_stt_adapter_clamps_confidence_into_zero_one |
| M2-S1-E6 | Edge | whitespace-only token | dropped | AC2 | test_stt_adapter_skips_blank_words |
| M2-S1-E7 | Edge | model hangs | AdapterTimeoutError (RENDER_TIMEOUT) | AC7 | test_stt_adapter_times_out_instead_of_hanging |

## Scenario 2: Transliterate a name (Qwen3 + common names) - AC3, D-M2-2
File: test_qwen_transliterator.py. LLM stub: `generate(token, target_script) -> (text, confidence)`. New API: `transliterate_checked(text, script) -> result(text, confidence, uncertain, source)`; new code `FailureCode.PRONUNCIATION_UNCERTAIN`.
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| M2-S2-P0 | Positive | code list | `PRONUNCIATION_UNCERTAIN` exists | AC3 | test_failure_code_pronunciation_uncertain_exists |
| M2-S2-P1 | Positive | "Rajesh" in dictionary | dictionary text, LLM never loaded | AC3 | test_dictionary_name_is_used_without_calling_the_llm |
| M2-S2-P2 | Positive | unknown "Anita" | LLM text | AC3 | test_unknown_name_goes_to_the_llm_and_returns_its_text |
| M2-S2-P3 | Positive | "Rajesh Anita" | LLM asked only for "Anita" | AC3 | test_multiword_name_asks_the_llm_only_for_unknown_words |
| M2-S2-P4 | Positive | port | satisfies `Transliterator` | AC3 | test_adapter_satisfies_the_transliterator_port |
| M2-S2-P5 | Positive | dictionary hit, checked | confidence 1.0, not uncertain, source dictionary | AC3 | test_dictionary_result_is_fully_confident |
| M2-S2-N1 | Negative | LLM confidence 0.3 | uncertain=True, text still pre-filled | AC3, R5 | test_low_llm_confidence_is_flagged_uncertain_but_still_prefills |
| M2-S2-N2 | Negative | LLM returns blank | input returned, uncertain | AC3 | test_empty_llm_answer_falls_back_to_the_input_and_is_uncertain |
| M2-S2-N3 | Negative | script "klingon" | ValueError, no model | AC3 | test_unknown_target_script_is_rejected_before_any_work |
| M2-S2-N4 | Negative | load fails | ModelLoadError | AC7 | test_llm_load_failure_is_a_model_load_error |
| M2-S2-N5 | Negative | LLM raises | DomainError TTS_FAILED | AC7 | test_llm_crash_is_a_coded_error |
| M2-S2-E1 | Edge | RAJESH / " rajesh " | case and spaces ignored | AC3 | test_dictionary_lookup_ignores_case_and_surrounding_spaces |
| M2-S2-E2 | Edge | confidence == threshold | not uncertain | AC3 | test_confidence_at_the_threshold_is_not_uncertain |
| M2-S2-E3 | Edge | one uncertain word of two | whole name uncertain | AC3 | test_one_uncertain_word_makes_the_whole_name_uncertain |
| M2-S2-E4 | Edge | empty / blank text | "" without LLM | AC3 | test_empty_text_returns_empty_without_calling_the_llm |
| M2-S2-E5 | Edge | already Devanagari | unchanged | AC3 | test_devanagari_input_for_devanagari_target_passes_through |
| M2-S2-E6 | Edge | 500 words, 1 distinct | one LLM call | AC3 | test_very_long_text_is_handled_and_repeated_words_asked_once |
| M2-S2-E7 | Edge | prompt-injection text | passed as plain data | AC3 | test_prompt_injection_text_is_passed_to_the_model_as_plain_data |
| M2-S2-E8 | Edge | LLM hangs | AdapterTimeoutError | AC7 | test_llm_timeout_is_reported |

## Scenario 3: Clone the voice (Chatterbox) - AC3, AC7
File: test_chatterbox_cloner.py. Model stub: `synthesize(text, voice_sample, language) -> (float samples, rate)`.
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| M2-S3-P1 | Positive | 1.5 s of samples | mono 16-bit WAV written to `out`, returns 1.5 | AC3 | test_cloner_writes_out_and_returns_the_duration |
| M2-S3-P2 | Positive | port | satisfies `VoiceCloner` | AC3 | test_cloner_satisfies_the_voice_cloner_port |
| M2-S3-P3 | Positive | Devanagari text | text, reference path, "hi" reach the model | AC3 | test_cloner_passes_text_reference_and_hindi_language_to_the_model |
| M2-S3-P4 | Positive | two calls | loaded once, lazily | AC10 | test_cloner_loads_the_model_lazily_and_once |
| M2-S3-N1 | Negative | missing voice sample | FileNotFoundError, no out | AC7 | test_cloner_missing_voice_sample_fails_without_output |
| M2-S3-N2 | Negative | "", spaces, newline | TTS_FAILED, no out | AC7 | test_cloner_empty_text_is_tts_failed_and_writes_nothing |
| M2-S3-N3 | Negative | model crash | TTS_FAILED, no partial/temp file | AC7 | test_cloner_model_crash_is_tts_failed_with_no_partial_file |
| M2-S3-N4 | Negative | load failure | ModelLoadError (TTS_FAILED), no out | AC7 | test_cloner_model_load_failure_is_a_model_load_error |
| M2-S3-E1 | Edge | samples +-1.5 | clipped, not wrapped | AC3 | test_cloner_clips_samples_outside_minus_one_to_one |
| M2-S3-E2 | Edge | stale `out` from a crashed try | replaced | AC7 retry | test_cloner_overwrites_a_stale_out_file_on_success |
| M2-S3-E3 | Edge | success | no stray temp files | AC7 | test_cloner_leaves_no_stray_temp_files_on_success |
| M2-S3-E4 | Edge | model returns 0 samples | TTS_FAILED, no out | AC7 | test_cloner_zero_length_model_output_is_tts_failed_and_writes_nothing |
| M2-S3-E5 | Edge | text over `max_chars` | NAME_TOO_LONG_TO_SPEAK, model not called | AC7 | test_cloner_rejects_text_over_the_limit_without_calling_the_model |
| M2-S3-E6 | Edge | text exactly at limit | accepted | AC7 | test_cloner_accepts_text_exactly_at_the_limit |
| M2-S3-E7 | Edge | model hangs | AdapterTimeoutError, no out | AC7 | test_cloner_timeout_raises_and_leaves_no_output |
| M2-S3-E8 | Edge | out folder missing | STORAGE_ERROR | AC7 | test_cloner_unwritable_output_folder_is_storage_error |

## Scenario 4: Lip-sync the slot (MuseTalk, 25 fps path) - AC5, R1
File: test_musetalk_lipsyncer.py. Model stub `run(video, audio, out)` writes a 25 fps video; ffmpeg and the 64x64 clips are real and tiny.
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| M2-S4-P1 | Positive | 60 fps template | model sees 25 fps; output 60 fps, same duration and frame count (+-2) | AC5 | test_lipsync_output_is_back_at_the_template_frame_rate |
| M2-S4-P2 | Positive | 24 / 25 / 30 fps | template fps restored | AC5 | test_lipsync_restores_other_template_frame_rates |
| M2-S4-P3 | Positive | port | satisfies `LipSyncer` | AC5 | test_lipsync_satisfies_the_lip_syncer_port |
| M2-S4-P4 | Positive | two calls | loaded once | AC10 | test_lipsync_loads_the_model_lazily_and_once |
| M2-S4-N1 | Negative | missing video | FileNotFoundError, no out | AC7 | test_lipsync_missing_video_fails_without_output |
| M2-S4-N2 | Negative | missing audio | FileNotFoundError, no out | AC7 | test_lipsync_missing_audio_fails_without_output |
| M2-S4-N3 | Negative | not a video | CORRUPT_VIDEO, no out | AC7 | test_lipsync_corrupt_video_is_a_coded_error_without_output |
| M2-S4-N4 | Negative | model crashes leaving a half file | LIPSYNC_LOW_QUALITY, nothing left | AC7 | test_lipsync_model_crash_leaves_no_partial_output |
| M2-S4-N5 | Negative | model writes garbage | DomainError, nothing left | AC7 | test_lipsync_unreadable_model_output_is_an_error_without_output |
| M2-S4-N6 | Negative | load failure | ModelLoadError | AC7 | test_lipsync_model_load_failure_is_a_model_load_error |
| M2-S4-E1 | Edge | (covered by P2: 25 fps needs no resample) | | AC5 | |
| M2-S4-E2 | Edge | success | 25 fps working copy removed | AC5 | test_lipsync_leaves_no_intermediate_files_on_success |
| M2-S4-E3 | Edge | zero-frame audio | LIPSYNC_LOW_QUALITY, model not called | AC7 | test_lipsync_empty_audio_is_rejected_and_writes_nothing |
| M2-S4-E4 | Edge | retry after crash | succeeds | AC7 | test_lipsync_retry_after_a_crash_succeeds |
| M2-S4-E5 | Edge | model hangs | AdapterTimeoutError, no out | AC7 | test_lipsync_timeout_raises_and_leaves_no_output |

## Scenario 5: Separate vocals and music (Demucs, new `VocalSeparator` port) - AC4, D-M2-1
File: test_demucs_separator.py. Stub `separate(audio) -> (vocals, accompaniment, rate)`.
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| M2-S5-P0 | Positive | port + `FakeVocalSeparator` | Protocol exported from `vidgen.ports`, fake in `vidgen.infrastructure.fakes` | AC4 | test_vocal_separator_port_is_exported_from_ports |
| M2-S5-P1 | Positive | fake, 2 s WAV | two valid WAVs of the input length | AC4 | test_fake_separator_writes_two_wavs_as_long_as_the_input |
| M2-S5-P2 | Positive | Demucs | vocals.wav + accompaniment.wav in `out_dir` | AC4 | test_demucs_writes_vocals_and_accompaniment_into_out_dir |
| M2-S5-P3 | Positive | two calls | loaded once | AC10 | test_demucs_loads_lazily_and_once |
| M2-S5-N0 | Negative | fake, missing input | FileNotFoundError | AC4 | test_fake_separator_missing_input_fails_loudly |
| M2-S5-N1 | Negative | missing input | FileNotFoundError, no folder created | AC7 | test_demucs_missing_input_fails_without_creating_files |
| M2-S5-N2 | Negative | 0-byte file | INTERNAL_ERROR, nothing written | AC7 | test_demucs_empty_audio_file_is_a_coded_error |
| M2-S5-N3 | Negative | model crash | INTERNAL_ERROR, no partial stems | AC7 | test_demucs_model_crash_leaves_no_partial_stems |
| M2-S5-N4 | Negative | load failure | ModelLoadError | AC7 | test_demucs_load_failure_is_a_model_load_error |
| M2-S5-E1 | Edge | `out_dir` missing | created | AC4 | test_demucs_creates_a_missing_out_dir |
| M2-S5-E2 | Edge | same out_dir twice | same paths, no extras | AC7 retry | test_demucs_same_input_twice_overwrites_cleanly |
| M2-S5-E3 | Edge | zero-frame WAV | two empty stems or a coded error, never a raw crash | AC4 | test_demucs_zero_length_audio_gives_two_empty_stems_or_a_coded_error |
| M2-S5-E4 | Edge | model hangs | AdapterTimeoutError, no stems | AC7 | test_demucs_timeout_raises_and_leaves_no_stems |

## Scenario 6: Package rules - AC10, D-M2-3
File: test_ai_package.py.
| ID | Type | Given / When | Then | AC | Test |
|----|------|--------------|------|----|------|
| M2-S6-P1 | Positive | import each adapter module | no torch/faster_whisper/demucs/chatterbox/transformers imported | AC10 | test_importing_an_adapter_never_imports_a_model_library |
| M2-S6-P2 | Positive | `ModelLoadError` | is a DomainError with the given code | AC7 | test_model_load_error_is_a_domain_error_with_the_given_code |
| M2-S6-P3 | Positive | `AdapterTimeoutError` | RENDER_TIMEOUT, retryable | AC7 | test_adapter_timeout_error_is_retryable |

## Scenario 7: `ai_backend` setting - G4
File: test_ai_backend_setting.py (guards: the setting already exists, so these pass today).
| ID | Type | Given / When | Then | Test |
|----|------|--------------|------|------|
| M2-S7-P1 | Positive | nothing set | "fake" | test_ai_backend_defaults_to_fake |
| M2-S7-P2 | Positive | "fake", "real" | accepted | test_ai_backend_accepts_fake_and_real |
| M2-S7-P3 | Positive | `VIDGEN_AI_BACKEND=real` | "real" | test_ai_backend_reads_the_environment_variable |
| M2-S7-N1 | Negative | gpu, "", REAL, Fake, " real", mock, none | ValidationError naming ai_backend | test_ai_backend_rejects_anything_else |

## Scenario 8: AI label band >= 10 % - D-M2-4, C2
File: test_label_band_share.py (guards: the code already enforces 10 %; the ~9 % came from the spike code).
| ID | Type | Given / When | Then | Test |
|----|------|--------------|------|------|
| M2-S8-P1 | Positive | 12 frame heights (1 px to 4320) | `label_band_height` / height >= 0.10 | test_label_band_is_at_least_ten_percent_of_frame_height |
| M2-S8-P2 | Positive | default `RenderConfig` | `band_height` / height >= 0.10 | test_render_time_band_with_the_default_config_is_at_least_ten_percent |
| M2-S8-N1 | Negative | share 0.09 | rule rejects it (1080p -> 97 px) | test_a_nine_percent_band_would_fail_the_rule |
| M2-S8-N2 | Negative | label_band_share 0.09 / 0 / -0.1 | ValidationError | test_settings_reject_a_label_share_below_ten_percent |
