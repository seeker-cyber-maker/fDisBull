# Published 0.17.0 release and DeepSeek delivery — 2026-10-26

[fDisBull 0.17.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.17.0)
is published, not draft or prerelease, at immutable source commit
`4f736f27fed30b4277c931428a675a692e457e76`. All seven assets were downloaded
again and matched by size, SHA-256, GitHub digest and original local bytes.
They are the unchanged tag-CI wheel, sdist and tool ZIP, `SHA256SUMS`,
`VERIFICATION-0.17.0.json`, and the updated Linux/DOS offline ZIP and checksum.
All **99 wheel entry contents** match the native-tested installed wheel, and
all **94 tool files** match the source tag.

## Tag qualification

Both required workflows passed before tagging and again on the tag.
[Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40438615862)
passed **1,079 tests, 65 skipped** and audited all three package formats.
[Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40438615842)
passed **38 stable DOS, 318 layered DOS (Python 3.13.5), 16 PE64 and 10
DOS/QEMU/boot checks**, with zero native failures, errors or skips. These are
suite test counts, including contract/unit checks, not hundreds of game runs.
Raw GitHub artifact ZIPs matched their recorded GitHub SHA-256 digests.

## Ready deliveries

The full local folder is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.17.0-4f736f2/
```

It contains the exact published assets, extracted tool, bundled agent skill,
scene scripts/documentation/evidence, tested Mac ARM64 DOSBox and QEMU 11.1.2
with firmware, the exact tag-CI Linux DOSBox ELF, complete backend patches and
licenses, and audited pristine DOS/Wine boot filesystems. The full bundle also
includes the separately labeled initial [DOS decompiler investigation](DOS_DECOMPILERS_RESEARCH.md).
No decompiler integration is implied by that research.

The compact local folder is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-linux-dos-offline-0.17.0-4f736f2/
```

Its [public ZIP](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.17.0/fdisbull-linux-dos-offline-0.17.0-4f736f2-2026-10-26.zip)
and [checksum](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.17.0/fdisbull-linux-dos-offline-0.17.0-4f736f2-2026-10-26.zip.sha256)
let Pro/DeepSeek obtain all genuine dependencies from GitHub. It has 63 private
loader/shared libraries, including SDL2_net, and requires no previous kit or
system-library replacement. The Linux backend is unchanged from tag acceptance.
Wheels cover Linux x86-64 Python 3.12/3.13 and Mac ARM64 Python 3.13; copied
acceptance used Linux **3.13.5** and Mac **3.13.14**.

From the selected directory:

```bash
/opt/pyvenv/bin/python3 RESTORE-MODES.py
/opt/pyvenv/bin/python3 VERIFY-DELIVERY.py
/opt/pyvenv/bin/python3 INSTALL-OFFLINE.py --venv ../fdisbull-017-venv --with-tests
../fdisbull-017-venv/bin/fdisbull agent-skill
../fdisbull-017-venv/bin/python fdisbull_delivery.py
```

Use this Mac's Python 3.13 instead of `/opt/pyvenv/bin/python3` on Mac.
`RESTORE-MODES.py` checks every file hash before restoring executable bits that
Python ZIP extraction can discard. The installer refuses an existing location,
uses only local hash-locked wheels and leaves existing environments unchanged.
Keep private project data outside these sealed folders. Native checkpoint
compatibility includes the backend hash, so use compatible checkpoints.

## Copied-pair checks

A separate Linux guest with no network interface verified the manifest,
installed the kit and passed **318 checks on Python 3.13.5**, with zero failures
or skips. All **49 state-archive CRC checks** passed: **17 saves and 32 loads**.
All 94 installed tool entries matched the exact tag wheel. The actual sealed
ZIP then passed Python extraction, permission restoration, manifest verification,
installation, startup and **20 keyboard/scene checks** in another fresh guest.
That guest's recorded ZIP hash matches the published offline asset. The external
Pro/DeepSeek environment itself was not accessed or modified.

The copied Mac pair passed **318 selected DOS checks**, **seven boot/GDB checks**,
a DOS-in-QEMU doctor and an isolated Wine/QEMU doctor. Both runtime doctors
verified real input/screenshots, breakpoints, a data watch, a bounded trace,
native restoration and stored evidence; the Wine path also exercised guarded
memory edits. These are finite checks on this Mac with its existing Homebrew
libraries, not arbitrary-host portability or a full ordinary Mac-suite pass.
Linux QEMU is a separate host dependency. The compact kit is direct Linux DOS.

The [DinoPark scene receipts](VERIFICATION-SCENES.md) retain their original
`0.17.0.dev0` identity. Release promotion retained the scene/runtime source hashes;
those original-game runs are not relabeled as fresh Linux gameplay. The fixed
0.17.0 tag and package bytes do not change when later publication notes appear
on main. Native scene probing currently targets direct DOSBox; a pixel match
alone does not prove control readiness.

## Integrity and exclusions

The full folder has **598 payload files**; the compact has
**335**, excluding each top-level `DELIVERY.json`.
Both copied standalone verifiers passed. Their ZIPs passed CRC, every-member
SHA-256 and executable-mode checks. Latest pointers were updated only after
publication readback and copied-delivery verification. Older deliveries remain
intact.

Public compact ZIP: **99201694 bytes**.

SHA-256: `5e624e6289fe6a2be83467db0a8e9ba4c5115b22b49a1a90c767b07048680b34`.

Full local ZIP: `fdisbull-unified-debugger-0.17.0-published-2026-10-26-4f736f2.zip`,
**1571164911 bytes**.

SHA-256: `88c5b342234ee21ed3802b52c17e3c84a046d03b3e997cb0507babdffee7b29f`.

Game files, saved games, captured emulator/native states, project databases,
compiled target fixtures and vendor IDA servers/keys are excluded. The full
bundle's boot filesystems are pristine OS/runtime inputs; the hash-bound static
OS/compiler support files inside them are not captured sessions. Public Python
packages exclude emulator binaries and boot images.

[Publication receipts](../experimental/remote-debugger/evidence/2026-10-26-published-0.17/)
retain exact identities, published-asset readback, copied qualification and CRC
metadata. No native state bytes or project databases are in those receipts.
