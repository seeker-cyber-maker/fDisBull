# DinoPark parking purchase: runtime evidence

The available **pmm / DINOSG.001** fixture commits one parking-lot purchase when the game processes the General Store OK/thumbs-up action. The live counter changes before a later attendance update. This observation is bounded to the tested transaction and exact game image; the reported STF7 save was unavailable.

At project `0x471a6`, the four live facility words stayed `[0,0,0,0]` while the pending order buffer at `0x4bb14` held `[0,0,0,1]`. The OK path reaches the byte-verified call at `334b:0aec`, then the writer **`1000:4fcb`, `F3 A5` (`REP MOVSW`)**. It copies eight bytes from `DS:b914` to `ES:6fa6`. Both the pre-call and post-write stops had PIC guest tick **53805**. The parking word at project `0x471ac` becomes `1` during this copy.

An idle control ran 2,023 guest ms without a write. Confirmed Cancel left the counters zero after another 4,102 guest ms. A byte-verified breakpoint on attendance entry `38ff:211f` remained armed when the data watch fired first. A fresh emulator session repeated the parking-specific word watch. The 13-event call-to-write trace is intentionally partial: its final event is the next instruction snapshot at the stop. A separate 128-event continuation completed without a duplicate stop from the overlapping byte watch.

## Evidence and identities

The repository example preserves the [original report](../examples/dinopark/evidence/parking-commit-2026-10-23/RESULT.md), requests/results, traces, three screenshots, and their [SHA-256 manifest](../examples/dinopark/evidence/parking-commit-2026-10-23/evidence-sha256.json). Those files are copied byte-for-byte from the local experiment; their source commit remains `cd13636c5bba6755836cc5a72898661bae41755c`. They are excluded from tool distributions and included separately in the local debugger delivery. Some original helper paths describe the earlier local delivery. Use the parameterized replay below for a new build.

| Input | SHA-256 |
| --- | --- |
| DINOPARK.EXE | `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c` |
| pmm save | `bf7af4fa7b57c96ff67dcd545d4b6873aee70681c0a197844fd73a84c40d32c5` |
| Native backend | `e749b6e50775de2807c2515f83e455dc705cdf6ddcdfb257e781f215d987865a` |

The runtime translated project `0x471ac` / static `4020:6fac` to runtime `3844:6fac` / linear `0x3f3ec`. Addresses in another loading context must be translated by that session. All 192 original game files remained unchanged in the experiment. Native states and the byte-retaining database remain local.

## Replay with a new wheel

`examples/dinopark/replay_parking_commit.py` takes an existing local project containing the pre-OK state. It makes a SQLite backup into a new output directory, starts a fresh emulator, restores the checkpoint, verifies the pending/live values, clicks OK, watches the parking word, exports a 128-event trace and a completed-frame screenshot, and reaps the emulator. It requires the corresponding user-owned game files and compatible backend. It does not construct the private fixture or distribute it.

```bash
python examples/dinopark/replay_parking_commit.py \
  --project /absolute/path/to/local/parking.fdb \
  --checkpoint ce4393d16aff4b4fa81f7fad3c2afb5b \
  --executable /absolute/path/to/compatible/dosbox-x \
  --game-dir /absolute/path/to/matching/game \
  --wheel /absolute/path/to/fdisbull-0.10.0-py3-none-any.whl \
  --output /absolute/path/to/new-local-replay
```

The new output contains a byte-retaining database and must stay local. This experiment establishes the RAM commit timing, not save-file persistence, other purchase types, the revenue formula, or the behavior of STF7. Screenshots show completed video frames; memory, registers, and traces establish writer identity and counter values.
