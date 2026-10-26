# Published 0.16.0 release and DeepSeek delivery — 2026-10-26

[fDisBull 0.16.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.16.0)
is published, not draft or prerelease, at immutable source commit
`e1e3fb4913d6d8fae7893c2c9b8edf364d144953`. Its seven assets are the unchanged
tag-CI wheel, source distribution and tool ZIP, `SHA256SUMS`,
`VERIFICATION-0.16.0.json`, the updated Linux/DOS offline ZIP and its checksum.
All seven were downloaded again and matched by size, SHA-256, GitHub digest
and original local bytes. All 95 wheel entry contents match the wheel used
by installed native acceptance; all 90 tool files match the source tag.

Both workflows passed before tagging and again on the tag.
[Tag ordinary CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40384806706)
passed **1,077 tests, 61 skipped** and audited all three package formats.
[Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40384806769)
passed **32 stable DOS, 312 layers, 16 PE64 and 10 DOS/QEMU/boot checks**,
with no native skips. Layers acceptance used Python **3.13.5**. These test
counts include each suite's unit/contract checks, not hundreds of game runs.

## Ready folders

The full delivery is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.16.0-e1e3fb4/
```

It contains the exact published assets, extracted tool, tested Mac ARM64
DOSBox and QEMU 11.1.2 with firmware, the exact tag-CI Linux DOSBox ELF,
source patches/licenses/recipes, and audited pristine DOS/Wine boot filesystems.
These are runtime inputs, not captured target states. Mac QEMU uses this Mac's
existing Homebrew libraries. Linux QEMU remains a separate host dependency;
the optional IDA runtime, vendor server and keys are not included.

The compact delivery is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-linux-dos-offline-0.16.0-e1e3fb4/
```

Its [public ZIP](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.16.0/fdisbull-linux-dos-offline-0.16.0-e1e3fb4-2026-10-26.zip)
and [checksum](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.16.0/fdisbull-linux-dos-offline-0.16.0-e1e3fb4-2026-10-26.zip.sha256)
give Pro/DeepSeek the genuine offline dependency wheels and 63 private
loader/shared libraries, including SDL2_net, without requiring a previous kit
or replacing system libraries. It uses the exact unmodified tag-tested ELF,
including guest keyboard input and the native-state CRC correction. Wheels for
Linux x86-64 Python 3.12/3.13 and Mac ARM64 Python 3.13 are retained; clean
kit acceptance used Linux **3.13.5** and Mac **3.13.14**.

From the selected directory:

```bash
/opt/pyvenv/bin/python3 VERIFY-DELIVERY.py
/opt/pyvenv/bin/python3 INSTALL-OFFLINE.py --venv ../fdisbull-016-venv --with-tests
../fdisbull-016-venv/bin/fdisbull --help
../fdisbull-016-venv/bin/python fdisbull_delivery.py
```

Use this Mac's Python 3.13 on Mac. The installer uses only hash-locked local
wheels and refuses an existing destination. The externally reported Pro/DeepSeek
environment itself was not accessed; it should run its own acceptance. Native
checkpoint compatibility binds the backend hash, so capture new compatible
states. Keep private projects outside the sealed delivery folders.

## Fresh copied-pair acceptance

An independent Linux x86-64 CPython **3.13.5** guest with no network interface
installed the exact wheel from the kit and passed **312 native-gate checks**.
All 90 installed tool entries match the wheel. **16 save and 30 load archive
checks** passed ZIP CRC validation, with no corrupt archive accepted.
An initial file-list check failed because the reused qualification image already
contained an older `/opt/delivery` tree. That result remains intact. Verification
under a new unique guest path then passed the complete manifest, installation,
helper and **14 keyboard/state checks**, with no failures or skips. A test-image
path-mapping attempt between those probes is retained privately; it did not
execute the kit. No product bytes were substituted or rewritten to pass.

The copied Mac package/backend pair passed **312 selected native checks**.
The rebuilt DOS/QEMU runtime doctor passed execution breakpoints, an execution
layer, actual clicks/screenshots, a data watch, bounded trace, native restore,
temporal promotion and offline exports. The copied Wine runtime doctor passed
its PE64 counterpart, including guarded memory editing and native restoration.
The first overlapping Wine cold start timed out in `wineboot` after 180 seconds;
the same copied files passed in the isolated run. The failed receipt remains
alongside the accepted one. This is finite copied-pair qualification, not a full
ordinary Mac-suite pass, arbitrary-host portability or timing-parity claim.

The earlier actual [DinoPark keyboard replay](VERIFICATION-GUEST-KEYBOARD.md)
typed/edited a save-dialog name and restored it in a fresh native session. It
does not qualify a durable leaderboard entry.

## Integrity and exclusions

The full folder contains **453 payload files**, the compact folder **332**,
excluding `DELIVERY.json` itself. Both copied standalone verifiers passed.
Their sibling ZIPs passed CRC, every-member SHA-256 and executable-mode checks.
`LATEST.json`, `LATEST-LINUX-DOS.json` and `README-LATEST.md` select the verified
new delivery only after those checks. Earlier versioned deliveries remain intact.

Compact ZIP: `fdisbull-linux-dos-offline-0.16.0-e1e3fb4-2026-10-26.zip`

- Size: **99042209 bytes**.
- SHA-256: `41044d06aa641ccac28b355961edf343af8da6a999b715d9a2477182f4eea6be`.

Full local ZIP: `fdisbull-unified-debugger-0.16.0-published-2026-10-26-e1e3fb4.zip`

- Size: **1568262961 bytes**.
- SHA-256: `7f564208670b477c8dbda7ae98a6a599acf325717aca37caae605f0f113f5ac7`.

Game files, saved games, captured emulator/native states, project databases,
compiled target fixtures and vendor IDA binaries/keys are excluded. Audited
hash-bound static OS/compiler `.state` support files inside pristine boot
filesystems are OS package inputs, not captured emulator states. Public Python
packages also exclude emulator binaries and boot images.

[Publication and delivery receipts](../experimental/remote-debugger/evidence/2026-10-26-published-0.16/)
preserve asset readback, exact identities, offline installation/CRC evidence and
both Wine results. Frozen package documents retain the source-tag status;
this later publication record does not alter the tag or package bytes.
