# Claims ledger

Every claim in the README, and what backs it. "manual" = checked by hand in a browser, not by an automated test.

| Claim | Evidence |
|---|---|
| Starts with no API keys and no `.env` | `app/config.py` (every variable has a default); `test_no_demo_seed_when_off` starts with only a data dir |
| 191 tests (181 unit/API/golden + 10 e2e) pass | `make test`, `make e2e` outputs pasted in README "Testing" |
| 95% line coverage of `app/` | `make coverage` output |
| 128-case golden set passes | `make eval` output; `tests/test_scoring_golden.py::test_golden` |
| Silent child → pause screen (A1) | `tests/e2e/test_practice_flow.py::test_silent_child_gets_pause_screen` |
| Recogniser offline → kind message + record-only (A2, B20) | `test_record_only_when_recogniser_offline` |
| IST day boundaries (A3) | `tests/test_time_and_migration.py::test_today_counts_roll_over_at_ist_midnight`, `test_local_day_around_ist_midnight`, `test_day_start_utc` |
| No scoring/saving after exit (A4) | `test_exit_mid_try_stops_everything` |
| Every therapist route needs the token (A5) | `tests/test_api.py::test_therapist_routes_need_token` (10 routes) |
| PIN lockout after 5 failures (A5) | `test_pin_lockout_after_five_failures` |
| Forged/tampered token rejected (A5) | `test_tampered_token_rejected` |
| Audio type sniffed; text rejected (415); oversize rejected (413) (A6) | `test_clip_upload_sniffs_type`, `test_upload_rejects_text_and_oversize` |
| No outbound requests except the app's own server (A7, B22) | `tests/e2e/conftest.py` `page` fixture assertion, applied to every e2e test |
| Summary counts only scored tries (A10) | `test_summary_counts_scored_only` |
| Override history is append-only; Pesu's first pass is kept (A11) | `test_override_audit_trail_and_agreement` |
| v0.1 database migrates in place (A12) | `test_migrates_v01_volume_in_place` |
| Delete removes rows and audio files (A14) | `test_delete_cascades_rows_and_files` |
| Export ZIP contents (A14) | `test_export_zip_contents` |
| Demo data only with PESU_DEMO=1 (A15) | `test_no_demo_seed_when_off`, `test_demo_remove_and_fast_forward` |
| Recogniser confidence used (A17/E3) | golden `low_conf` cases; `test_stubbed_recogniser_path` stores 0.82 |
| One sticker per finished session, never more (B13) | `test_one_sticker_per_finished_session` |
| Mistake → tilt (no shake), retry, next picture (B10) | `test_t_error_twice_then_next_picture` |
| Parent decides with two voices (C4) | `test_parent_decides_when_two_voices` |
| Noise gate before listening | `test_noise_gate_pauses_before_listening` |
| Multi-child isolation (C9) | `test_multi_child_isolation` |
| Backup/restore round trip (F7) | `tests/test_backup.py` |
| Audio retention (F6) | `test_retention_removes_old_audio_keeps_rows` |
| No inline handlers; JS parses | `scripts/check_static.py` |
| Latency / footprint numbers | `scripts/measure.py` output pasted in README |
| Prevalence and DEIC staffing facts | linked sources in README "The problem" |
| Refresh resumes a session (A18) | manual |
| Reduced motion honoured (B4) | manual (CSS media query in `styles.css`) |
| Docker build + healthcheck | not verified in the build sandbox (no Docker daemon); CI job written |
