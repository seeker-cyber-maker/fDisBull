# D004 original-navigation evidence

Sanitized source/load identities, exact-coordinate observations and authored
checks. No native game bytes, memory dumps or checkpoints are included.

From the repository root with the installed Player available:

```sh
python docs/evidence/syndicate-navigation-2026-11-01/tools/verify_navigation.py \
  --scene-root examples/syndicate_z_scene \
  --output /absolute/new-private-verification
```

The checker runs the current authored suite and validates the recorded receipts.
The original D004 qualification reported 140 tests and 219 assertions; current
test counts and historical source-hash comparisons are reported separately.
Use `--require-historical-sources` only with the exact D004 source snapshot.
It does not execute native trials or qualify whole-game behavior. Historical
runtime identities remain in `evidence/source-identities.json`.
The [original report](https://chatgpt.com/library?file_id=libfile_586e2ac154f881918aa903ddd94ee97c&account_id=personal)
distinguishes original movement, diagnostic setup and failed or held paths.
