# Published 0.13.0 DeepSeek delivery — 2026-10-24

The [GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.13.0) targets `eabfc2afb772d4cb78401893eebf15c8b0f6ad17`. The wheel, source distribution and tool ZIP are unchanged [tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40099730231) outputs. `SHA256SUMS` and `VERIFICATION-0.13.0.json` bind their identities. All five uploaded assets were downloaded again and verified against local files and GitHub asset digests.

Tag package CI passed **769 tests, 31 skipped**. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40099730260) passed **15 stable DOS, 32 DOS layers and 13 PE64 installed-wheel tests**, with **no native skips**. All 65 wheel entry contents match between the package job and the wheel tested with real PE acceptance.

The ready-to-use directory is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.13.0-eabfc2a/
```

Start with `README-DEEPSEEK.md` and `python VERIFY-DELIVERY.py`. `packages/` holds the exact published assets. `tool/` is an unchanged wheel extraction; the Win32 agent/broker/launcher sources and host QMP/state/layer/watch modules are ordinary files. `fdisbull_delivery.py` activates this package from a fresh Python process, supplies `wine_options()`, and provides `dos_options()` referencing the preserved 0.11 DOS backend. `fdisbull_from_delivery.py` runs the CLI in an existing Python 3.12+ dependency environment. No existing environment was replaced.

The backend includes copied Mac ARM64 QEMU 11.1.2, selected boot firmware, Linux 6.1.0-50 kernel and a pristine prepared Wine 9.0 boot image matching the 0.13 guest resources. The wrapper selects the copied firmware. Existing Homebrew shared libraries on this Mac are required and are identified in provenance; they are not bundled. This is a tested delivery for this Mac. Other hosts can build the included recipe with QEMU>=9.1.

The boot image's **21,521 member** audit confirms the current packaged resource hashes and finds no game, emulator-checkpoint or project-database paths. The audit explicitly identifies two static OS/compiler files named `.state` (shell configuration and GCC plugin type descriptors); they are not captured emulator states. The large `.cpio.gz` is a prepared boot filesystem. Full member audit and source/provenance/license records are included in the delivery.

## Fresh copied-pair acceptance

The exact published package and copied backend passed a **193.22-second real Mac smoke**, independent of the Linux CI runtime. It verified:

- Read and write watches, including a byte watch overlapping a wider read-modify-write store, stopping before the value changed.
- RAM layer self-CRC failure and execution-layer self-CRC success with original source RAM retained; branch inversion and disable.
- 8px click-frame screenshots, real native input and a bounded trace retaining RAM bytes `b801000000` versus execution bytes `b803000000`.
- Checked memory and full-width RAX edits, one native checkpoint and restore in a fresh QEMU process, with saved watch and active layer restored.
- Counter 41 and RAX `0x123456789abcdef0` restored after temporary edits; continued to 44 with the layer and 45 after disabling it.
- Original/static child patch isolation, unchanged fixture source hash and offline screenshot/trace exports after project restart.

This copied-pair smoke uses one checkpoint to bound disk use; the complete native fork/export/asset-allowlist gate is separately covered by the 13-test tag CI. Test EXEs, databases, native machine images and the existing agent's environments stayed outside the delivery. Selected [publication evidence](../experimental/wine/evidence/2026-10-24/published-0.13.0/) is retained in the repository; full copied-pair reports are under `verification/mac-delivery/` locally.

## Bundle and integrity

```text
fdisbull-wine-debugger-0.13.0-published-2026-10-24-eabfc2a.zip
```

The bundle is **662,778,358 bytes**, with **173 verified entries**. SHA-256:

```text
c2c84f2bce9ba44b730f32f69ffb91d59238afc25a7eb83ac2af7a7fee232e38
```

ZIP CRCs, every entry's SHA-256 against the ready folder, and launcher/native executable permissions passed. `DELIVERY.json` binds all 172 payload files except itself. The sibling `DELIVERY-0.13.0-published-eabfc2a.json`, `.zip.sha256`, `LATEST.json` and `README-LATEST.md` record the accepted directory/bundle. Large unchanged runtime files were copied with APFS clone semantics into independent regular files; no symlink back to recovery storage is required.

Game inputs, in-game saves, emulator checkpoints, local project databases and compiled target fixtures are excluded. Earlier 0.10/0.11/0.12 deliveries and DinoPark findings remain intact. DinoPark's original executable is DOS: use the existing 0.11 DOS layers backend with the new Python package. The Wine/QEMU path is for native PE64 EXEs. See [API and limits](WINE_DEBUGGER.md) for scalar guard-page constraints, relocated execution overhead, native sidecars and the authored-fixture claim ceiling.
