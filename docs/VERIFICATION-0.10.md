# 0.10.0 candidate verification — 2026-10-23

Candidate acceptance was performed locally on macOS ARM64 with Python 3.13. The source base is `cd13636c5bba6755836cc5a72898661bae41755c`; the candidate adds the release changes in the working tree. It has not been committed, pushed, tagged, or published. The local delivery identifies its source snapshot by file hashes.

The explicit-seed regression failed before the queue fix: a one-instruction call returned no instruction at the requested address while older work remained. It passes after prioritizing that seed. The seven DOS analysis tests pass, including database restart and subsequent resumption of older work. All twelve debugger tests pass with the real backend selected, including a native breakpoint reached at the seeded address, whole-block `REP MOVSW` observation, no duplicate overlapping-byte stop, state fork/restore, script failure behavior, native traces, screenshot export, timeout, and emulator cleanup. Ten distribution guards reject local database, checkpoint, and game extensions.

## Full suite

```bash
FDISBULL_DOSBOX=/absolute/path/to/patched/dosbox-x python -m pytest -q --tb=short
```

Result: **739 passed, 3 skipped, 2 failed, 23 errors** in 52.60 seconds. Exit status is 1. The complete set of 25 failing/error test identities matches the recorded pre-release baseline. The two failures construct Linux ELF executables in `test_inspection.py` and `test_loading.py`; 23 setup errors construct Linux ELF metadata/call fixtures in `test_elf_metadata.py` and `test_platform_calls.py`. Apple's `/usr/bin/gcc` driver and linker reject their Linux flags. This suite is not globally green, and Linux CI has not been run for the unpushed candidate. Tests were neither skipped nor weakened to hide the platform limitation.

## Real game through the wheel

The parameterized parking replay imported `fdisbull/debugger.py` directly from the **0.10.0 wheel**, using existing dependencies. A SQLite backup kept the original project untouched. A fresh emulator restored the older native pre-OK checkpoint, read live words `[0,0,0,0]` and staged words `[0,0,0,1]`, clicked OK, and caught a width-2 write from project `0x14fcb` to the parking word. Live words became `[0,0,0,1]`. The following 128-event trace completed with zero guest-millisecond advance and no second overlapping-byte stop. A completed-frame PNG was exported after running another guest second. The emulator was reaped.

The final delivery retains `verification/parking-0.10.0/replay.json`, `return.json`, and `after-ok.png`, while the private replay database and native state bytes remain outside the bundle. The backend SHA-256 is unchanged: `e749b6e50775de2807c2515f83e455dc705cdf6ddcdfb257e781f215d987865a`. The runtime result establishes checkpoint compatibility for this exact backend/profile/game manifest; it is not a general cross-version state portability guarantee.

## Package checks

The wheel, sdist, and source ZIP are built from the candidate source with the version set to 0.10.0. `scripts/check_dist.py` validates their tool-only contents, source-test helpers, and exclusions. Every wheel Python module is compared byte-for-byte with the source tree. The delivery manifest records package hashes, source hashes, native backend identity, and selected evidence hashes. The separate native backend and source patch are outside the Python packages. No game files, native state payloads, or SQLite databases are admitted to the bundle.

The historical 0.9.0 and native-state receipts retain their original identities and results. The [parking report](PARKING_COMMIT.md) explains the earlier controlled experiment separately from this candidate replay.
