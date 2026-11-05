# PARTIAL HANDOFF 000: baseline checkpoint

**Date:** 2026-11-01 (America/Toronto)
**Parent:** `COMPLETE_HANDOFF.md` in this ZIP.
**Scope:** Baseline for future partial handoffs; not a new code change.

## Verified state now

- GitLab main `498c0887` (exact full SHA in snapshot JSON).
- Release tag `v0.29.0` at `09a82095`; ten files in existing package groups, not locally downloaded by us.
- Helpers on `main`: exact readback and local SHA-256 match.
- MR !26 merged; 33 project MRs: 24 opened, 3 merged, 6 closed.
- No GitLab pipelines listed.
- Critical missing-from-main work is on preserved branch `pr/32/zork-scene-uil-20261030` at `4be05579`; no associated GitLab MR in current inventory.
- KQ1 TAS movie ZIP available separately in Library; baseline 29.891690004 seconds, `BOW` 29.506450680 seconds. Not independently replayed in this turn.

## New changes since complete handoff

None. This file intentionally establishes the partial/delta schema.

## Next delta trigger

Issue `DELTA_001_YYYY-MM-DD.md` only after a material change (new push, merge, uploaded package with hash, completed test, blocker resolution or new reproducible finding). Do not resend the entire history.
