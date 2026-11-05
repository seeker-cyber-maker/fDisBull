# Retained damage evidence

Original-game observations and separately measured repeated checks are described
in the [original damage report](https://chatgpt.com/library?file_id=libfile_d0a3b03d35a081918f473f5af63f0edb&account_id=personal). These sanitized receipts are
not a native checkpoint or permission to replay a guessed runtime address.

The complete semantic snapshot remains in the local handoff and is not required
by these public authored tests. The checker skips that optional recorded-Player
check when damage-scene.json is absent. It does not claim native re-execution.

```sh
python -B docs/evidence/syndicate-damage-2026-11-01/verify_damage.py \
  --evidence docs/evidence/syndicate-damage-2026-11-01 \
  --scene-tools examples/syndicate_z_scene/tools \
  --output /private/new-damage-receipt.json
python -B -m unittest discover -s examples/syndicate_z_scene/tests -v
```

The Player package is required for the authored suite; the recorded native
observations used v0.29. Optional exact
private MAIN inspection uses --main-exe; never add that executable to the repo.
The record projection is opt-in, frozen and read-only. It cannot install a live
watch, issue game input, infer guilt from distance or verify arbitrary JSON's
authenticity. The stop-normalization mismatch is reproduced with installed core;
this addendum reports it but does not change core runtime behavior.
