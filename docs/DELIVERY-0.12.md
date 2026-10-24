# Published 0.12.0 delivery — 2026-10-24

The [GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.12.0) targets `7f8c9d48e01c60a289834ad289282b572c0adad1`. Its wheel, source distribution and tool ZIP are the unchanged outputs of [tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40045173566). `SHA256SUMS` and `VERIFICATION-0.12.0.json` are attached. All five uploaded assets were downloaded again and verified against local SHA-256 hashes and GitHub's asset digests.

The user-designated DeepSeek delivery is:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.12.0-7f8c9d4/
```

Start with `README-DEEPSEEK.md`. `packages/` contains the exact published assets. `tool/` is an unchanged extraction of the published wheel, keeping the guest C/broker/launcher resources accessible as ordinary files. `fdisbull_delivery.py` activates that package and supplies `wine_options()` for Python agents; `fdisbull_from_delivery.py` runs its CLI using an existing Python 3.12+ dependency environment. No existing agent environment was replaced.

The separately supplied backend includes the tested Mac ARM64 QEMU **11.1.2**, selected x86 boot firmware, Linux **6.1.0-50** kernel and pristine **Wine 9.0** boot runtime, plus source recipes, provenance, license notices and direct library identities. The launcher selects the copied firmware explicitly. QEMU uses this Mac's existing Homebrew libraries; those libraries are not bundled. This is a tested delivery for this Mac, not a portable runtime for arbitrary hosts. Other hosts can build the documented recipe using QEMU >=9.1.

The local copied package/backend pair passed **6 PE64 tests with no skips in 265 seconds**, using two fresh offline VMs. The actual workflow verified a counter edit from 7 to 41, clicks reaching 42 and 43, rearmed disassembly breakpoints, completed instruction traces, timeout stopping, original/static patch isolation, restart, and screenshot/trace exports after emulator exit. Evidence is under `verification/mac-delivery/`; tag CI reports are also included. Test executables and temporary project databases stayed outside the delivery.

The sibling bundle is:

```text
fdisbull-wine-debugger-0.12.0-published-2026-10-24-7f8c9d4.zip
```

SHA-256:

```text
7001ae55d6a6f5aed4a0bff1149a32215facb52fabc848b99626ce22c4226fae
```

The ZIP is **662,837,993 bytes**, with **143 verified entries**. Its CRCs, every entry's SHA-256 against the ready-to-use directory, and both launcher/native executable permissions were checked. `DELIVERY.json` records all payload identities except itself; the sibling `DELIVERY-0.12.0-published-7f8c9d4.json` records the ZIP and manifest identities. The matching `.zip.sha256`, `LATEST.json` and `README-LATEST.md` are beside it. Earlier deliveries and the DinoPark 7,500-price evidence remain intact.

Backend input SHA-256 identities:

| Input | SHA-256 |
| --- | --- |
| Native QEMU executable | `a8ee5cdeaa1b04fa6fcfbaf210c03209ab7c91357ce2b6eb4dff10c2b7bc7816` |
| Linux kernel | `d8808aa4ca188560da1e6d749dcb930c87a5fd8b11ebff1f3fa6d728af35203d` |
| Wine boot runtime | `4d9f342d84eea9b307f015901e614201a9b7f106f94177ec0fcc3f20ffc205ea` |

The boot image's member audit is included; it contains the prepared OS/runtime rather than a captured game session. Game inputs, game saves, emulator checkpoints, Wine prefixes, local project databases and compiled test executables are excluded.

DinoPark's original executable is DOS. The 0.12 Python tool can continue using the [existing tested DOS layers backend](DELIVERY-0.11.md); its delivery remains unchanged. The new Wine/QEMU path is for native PE64 Windows EXEs. Arbitrary Windows game compatibility, DirectX/fullscreen capture, PE states, PE code layers and PE data watchpoints remain outside qualification. See [release verification](VERIFICATION-0.12.md) and [PE64 usage](WINE_DEBUGGER.md).
