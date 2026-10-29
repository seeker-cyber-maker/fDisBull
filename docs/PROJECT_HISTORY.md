# Historical README snapshot

This preserves the previous landing page as a historical development snapshot. Its release-status and future-work statements reflect that snapshot; use the current [README](../README.md) and linked release records for current status.

# fDisBull

An agent-first disassembler with a persistent SQLite analysis database, explicit evidence, bounded analysis, and headless SVG/PNG exports.

> **This tool is not currently suitable for malware analysis or security work.**
>
> Must bring your own weapons. I have only done this once before. Safety not guaranteed.

Requires Python **3.12 or later**.

The **0.23.0.dev0 source candidate** adds an [original-backed DOS UDC](UDC_DOS.md)
and [per-layer ASM/UDL/UIL/C tests](UDC_TESTING.md). The first compiler
definition rebuilds unchanged DOS artifacts from immutable block backings.
A small authored game exercises ASM-backed UDL → UIL → the same UDL backing as
UDC; Z3 checks the declared register boundary, and native original/ASM/C-view
runs agree on that effect. DinoPark and Zork checks qualify byte-preserved
output and bounded observations, with zero recovered game semantic blocks.
This is not generic DOS code generation or a complete C/C++ decompiler.
See [development notes](RELEASE-0.23.0.md) and [verification](VERIFICATION-0.23.md).
The published packages and shared installation remain at **0.22.0**.

Version **0.22.0** adds [room maps and physical, assisted and story policies](SPATIAL_MAPS.md),
a [qualified Z-machine story harness](ZORK_HARNESS.md)
and [shared primitive interaction blocks](INTERACTION_IL.md). UDL and UIL
use the same representation in input and output roles. The bounded Zork I
mailbox recovery is linked to story instructions and compared with the original
DOS interpreter; the parser and turn loop remain outside the extracted slice.
Room maps use game coordinates, actor footprints, separate obstacle/hazard and
object-zone layers, immutable source references and supporting snapshots.
Map-aware movement refuses unknown or hazardous destinations. Story mode uses
qualified, temporary position-test overrides while sending original game input.
The [native spatial verification](VERIFICATION-SPATIAL-2026-10-29.md) records
KQ1's tree and moat probes and PQ1's radio pickup with unchanged actor coordinates.
`fdisbull text-host CONFIG --fair-play` locks physical mode and disables assisted
teleports, room jumps and story waivers for that session. The
[release notes](RELEASE-0.22.0.md) and [release verification](VERIFICATION-0.22.md)
describe source finalization and its exact-commit CI gate. [Version 0.22.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.22.0)
with verified packages and the Linux/DOS offline kit with Z3. The
[publication record](PUBLICATION-0.22.md) documents tag CI, eight-asset
download readback and the active shared Mac installation at 0.22.0.

Version **0.21.0** adds [progressive scene workflows](PROGRESSIVE_SCENES.md),
a [separate text player](TEXT_PLAYER.md), [automatic live-turn saves and resume](PLAYER_LIVE.md),
and [qualified travel assistance](ASSISTED_TRAVEL.md). Live mode checkpoints
after each model turn without a save command. An external agent can choose
commands and narrate their observed results in bounded story sessions. Voice
input/output is planned future work: Qwen TTS is available locally according to
the user; speech recognition and a complete voice interaction are unqualified.
[Version 0.21.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.21.0)
at source `a253600b94f7006f8962ada842eba699279fdbfe`. The exact-source ordinary
workflow passed 1,333 tests with 100 skips; tag-native Linux CI passed 218 stable
backend, 529 layers, 16 PE64, and 13 DOS/QEMU/boot tests with no native failures,
errors, or skips. Eight published assets were downloaded and matched against
GitHub digests. The [publication record](PUBLICATION-0.21.md) documents the
asset readback, Linux offline kit, and shared Mac activation at 0.21.0. The
[candidate scope](UNRELEASED-0.21.md) and [verification record](VERIFICATION-0.21.md)
retain their original evidence boundaries; the pending-status text in the
[release notes](RELEASE-0.21.0.md) is identified as a source-finalization
snapshot by its publication follow-up.

Version **0.20.0** integrates [typed input macros and bounded movement](SEMANTIC_INPUT_MACROS.md), [scene geometry and content readiness](SCENE_NAVIGATION.md), explicit DOS COM support, watch-only dot-mode, a partial AGI inspector, and [bounded Z3 model checks](BOUNDED_PROOFS.md). See the [release notes](RELEASE-0.20.0.md) and [offline kit with Z3](OFFLINE_KIT_0.20.md). [0.20.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.20.0) with verified packages and the Z3 offline kit. The [publication record](PUBLICATION-0.20.md) records its tag CI, asset readback and historical activation. The current [shared Mac installation](SYSTEM_INSTALLATION.md) selects 0.22.0. The [candidate history](UNRELEASED-0.20.md) and [Library reconciliation](RECONCILIATION-0.20.md) preserve earlier identities and limitations.

Version **0.19.0** adds guarded DOS filename aliases, persistent screenshot
hooks, callback-safe DOSBox continuation and expanded investigation-skill
references. See the [release notes](RELEASE-0.19.0.md) for behavior and
limits; the [development record](UNRELEASED-0.19.md) retains earlier evidence.
[**fDisBull 0.19.0 is published**](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.19.0)
with CI-verified wheel, source distribution and tool ZIP. The
[publication record](PUBLICATION-0.19.md) records tag CI, asset hashes,
download readback and the [shared Mac installation](SYSTEM_INSTALLATION.md).
This records the earlier 0.19.0 publication. Global commands now select 0.22.0;
retained 0.21.0, 0.20.0, 0.19.0 and 0.18.0 prefixes remain available for guarded
rollback and compatible checkpoints. Existing project environments are preserved. The 0.19.0 publication
did not produce a new DeepSeek delivery or offline bundle.

Persistent scenes share object context, supporting snapshots and composite masks
between overlays and checked named actions. The updated DOSBox backend provides
native RGB probes without PNG transfer. The bundled `fdisbull-investigate` skill
prioritizes expected reward and probe cost alongside confidence.

Version 0.16.0 consolidated [saved experiments and baseline/layer comparisons](DEBUGGER_EXPERIMENTS.md),
[guest keyboard input](GUEST_KEYBOARD.md), [bounded observation waits](OBSERVATION_WAIT.md),
[temporal code interpretations](RUNTIME_CODE.md), [observation semantics](DEBUGGER_SEMANTICS.md)
and the [runtime doctor](RUNTIME_DOCTOR.md). Its
[standalone DOS knowledge](DOS_KNOWLEDGE.md) supplies 182 provenance-bound
runtime signatures, 37 DOS/BIOS service descriptions, reusable catalogs and
richer declared types with near/far Pascal profiles. Comparison captures are
validated before pairing. Compiler overlay loading and a dedicated SYS loader
remain outside this implementation; the current source adds the explicit COM
profile described below, without claiming dynamic overlay coverage.

Version 0.14.0 adds an optional [IDA 9.4 remote-server adapter and matching
DOSBox endpoint](IDA_REMOTE.md). These use a common binary debugger
protocol and keep execution breakpoints out of instruction bytes. The new
adapter's feature and verification limits are separate from the custom Wine
backend; no vendor IDA executable is included. Bounded PE traces run
inside the Linux controller in one host request, preserving fresh code reads,
integer-register snapshots and breakpoint boundaries. See the
[measured trace comparison](IDA_TRACE_PERFORMANCE.md).

The [shared machine controller](UNIFIED_DEBUGGER.md) also runs
DOSBox inside Linux/QEMU using the existing DOS project API. DOS and Windows
sessions expose an explicit outer-machine context, while a raw-image profile
can stop before boot and capture registers, memory, breakpoints, traces and
display artifacts. Real DinoPark has been verified locally. DOS state/layer/input
checks and an authored boot-sector session also passed Linux CI. Typed kernel
objects and a DTrace provider remain future work.

See the [0.14.0 release notes](RELEASE-0.14.0.md) for runtime compatibility,
feature limits and the ordinary/native Linux checks required before tagging.

## Release, branches, and native backend status

| Track | Source and availability | Verification |
| --- | --- | --- |
| **Latest published and installed release: 0.22.0** | [Verified packages and Linux/DOS offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.22.0), source `75bbd7ee65118c0186844f73ef6c79245854eba0` | [Publication and shared installation](PUBLICATION-0.22.md): 1,458 ordinary (101 skipped), 316 stable, 627 layers, 16 PE64 and 13 DOS/boot checks; zero native skips. |
| **Previous published release: 0.21.0** | [Verified packages and Linux/DOS offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.21.0), source `a253600b94f7006f8962ada842eba699279fdbfe` | [Publication and shared installation](PUBLICATION-0.21.md): 1,333 ordinary (100 skipped), 218 stable, 529 layers, 16 PE64 and 13 DOS/boot checks; zero native skips. |
| **Earlier published release: 0.20.0** | [Verified packages and Z3 offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.20.0), source `4f7791b` | [Publication and retained installation](PUBLICATION-0.20.md): 1,236 ordinary, 109 stable DOSBox, 415 layers, 16 PE64 and 13 DOS/boot checks; zero native skips. |
| **Earlier published release: 0.19.0** | [Verified packages](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.19.0), source `57824bd` | [Publication and shared installation](PUBLICATION-0.19.md): 1,112 ordinary, 66 stable DOSBox, 372 layers, 16 PE64 and 13 DOS/boot checks; zero native skips. |
| **Earlier published release: 0.18.0** | [Verified packages](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.18.0), source `416b64d` | [Publication and shared installation](PUBLICATION-0.18.md): 1,089 ordinary, 54 stable DOS, 335 layers, 16 PE64 and 10 DOS/boot checks passed; zero native skips. |
| **Earlier published release: 0.17.0** | [Packages and updated offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.17.0), source `4f736f2` | [Tag CI and copied-pair verification](DELIVERY-0.17.md): 1,079 ordinary, 38 stable DOS, 318 layers, 16 PE64 and 10 DOS/boot checks passed; zero native skips. |
| **Earlier published release: 0.16.0** | [Packages and updated offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.16.0), source `e1e3fb4` | [Tag CI and copied-pair verification](DELIVERY-0.16.md): 1,077 ordinary, 32 stable DOS, 312 layers, 16 PE64 and 10 DOS/QEMU/boot checks passed; no native skips. |
| **Historical source candidate: 0.15.0** | [Saved debugger experiments](DEBUGGER_EXPERIMENTS.md) on the existing unified debugger | [Candidate notes](RELEASE-0.15.0.md) and [local verification](VERIFICATION-0.15.md). No 0.15.0 tag/release; exact CI packages are additionally available in the GitHub offline asset. |
| **Earlier published release: 0.14.0** | [GitHub release and packages](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.14.0), commit `6a0aeb3` | [Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40222623197): 817 passed, 45 skipped. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40222623209): 15 stable DOS, 38 layers/endpoint, 14 PE64 and 10 DOS/QEMU/boot checks passed, no native skips. |
| **Repository branch** | [main](https://github.com/seeker-cyber-maker/fDisBull/tree/main) is the release branch; feature and RFC branches may exist | Release promotion requires both ordinary and native Linux CI. Use version tags for fixed source snapshots. The old experimental checkpoint is preserved under an archive tag. |

The historical [0.15.0 Linux/DOS offline candidate kit](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.14.0/fdisbull-linux-dos-offline-0.15.0-e91879c-2026-10-26.zip) is now hosted on GitHub, with a [checksum](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.14.0/fdisbull-linux-dos-offline-0.15.0-e91879c-2026-10-26.zip.sha256). It supplies the exact `e91879c` CI packages, genuine Python dependencies, and the corrected Linux backend with private SDL2_net libraries. Its 0.15.0 contents predate the current 0.16.0 work; its URL uses the existing 0.14.0 release as an asset host.

The Python packages do **not** include an emulator. Source builds use the [stable backend patch](../experimental/dosbox-x/README.md); execution layers need the separate [layers backend patch](../experimental/dosbox-x/layers/README.md). Both pin an upstream source commit and require an explicit executable path. Coordinate grids work with either backend.

The [release-status record](RELEASE_STATUS.md) distinguishes tagged source, published packages and historical candidate receipts. Ordinary Python CI may skip native tests; [required native acceptance](DOSBOX_DEBUGGER.md#required-native-acceptance) builds or selects the real patched backend and runs the existing tests against it.

The historical [0.17 DeepSeek delivery](DELIVERY-0.17.md) contains the published packages, scene-capable DOSBox, bundled agent skill, tested Mac QEMU/Wine profiles and audited pristine boot filesystems. Its no-network Linux 3.13.5 kit passed 318 checks and 49 save/load archive CRC checks; the actual ZIP separately passed extraction, permission repair, installation and 20 keyboard/scene checks. Both copied bundles passed complete manifest and ZIP readback.

The [delivered DinoPark leaderboard replay](VERIFICATION-DINOPARK-LEADERBOARD.md)
typed `DeepSeek016`, clicked OK and verified the saved score table through the
original game in a second emulator and separate project. Its Mac evidence
includes clean/8px-grid screenshots, bounded writer/reader traces and unchanged
original-file checks. The [E35 investigation example](../examples/dinopark/notes/INVESTIGATION_E35.md)
adds the latest attributed Library findings and remaining NEW GAME work.

The earlier user-designated [0.14 DeepSeek delivery](DELIVERY-0.14.md) contains the exact published packages, tested Mac ARM64 DOSBox/QEMU backends, Linux DOSBox and matching pristine DOS/Wine/optional-IDA boot runtimes. A smaller Linux/DOS offline kit supplies genuine hash-locked Python wheels and private libraries including SDL2_net. Copied Mac gates and 51 clean-offline checks passed. The additional Linux Python 3.13.5 probe passed installation and 49 native checks, with **2 native-state restore CRC failures**; the external DeepSeek environment remains unverified. See the delivery record for the separate scopes and failed receipts. Earlier deliveries are preserved. Game files, saved states and project databases are excluded.

The direct Linux backend now has a separate [native-state CRC correction and
offline statefix1 kit](LINUX_STATE_CRC_FIX.md). It fixes the empty VGA buffer
write that caused the original probe's two restore failures. Python 3.13.5
acceptance passed 52 clean-build checks, 51 fresh copied-kit checks and 6 repeated
original-case checks, with no failures/skips. The published 0.14.0 package bytes
and original full delivery remain unchanged; the original failed results above
describe that earlier delivery.

## Install and use

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
fdisbull inspect /path/to/program
fdisbull import /path/to/program analysis.fdb
fdisbull analyze analysis.fdb --max-instructions 10000
fdisbull analysis-status analysis.fdb
fdisbull functions analysis.fdb
```

On Windows, activate `.venv\Scripts\Activate.ps1` in PowerShell. Install `.[managed]` for optional .NET metadata and CIL inspection.

## Capabilities

- x86 16/32/64 and ARM64 decoding; DOS MZ, explicitly selected DOS COM, PE, ELF, Mach-O, universal Mach-O slices, and explicit raw images.
- Persistent instructions, control flow, references, annotations, types, and immutable byte versions.
- Explicit PE versus DOS-stub selection and segment-aware DOS instruction identities.
- Bounded analysis with pending work and unresolved targets kept visible.
- Attached resource/save files with typed fields, evidenced code references, and bidirectional shared labels.
- Repairable label links with retained history.
- Disassembly and control-flow graph images generated from stored state.

See the [user guide](USER_GUIDE.md), [API](API.md), [architecture](ARCHITECTURE.md), [platform support](PLATFORMS.md), and [external-file workflow](EXTERNAL_FILES.md). The development [processor decoder seam](PROCESSOR_MODULES.md) does not yet support importing or persisting arbitrary VM projects.

## DOSBox debugging

Launch an original DOS MZ or explicitly selected COM project with `fdisbull debug PROJECT --executable PATH_TO_PATCHED_DOSBOX --game-dir GAME_DIRECTORY`. Import COM with `fdisbull import GAME.COM PROJECT --image com`; a `.COM` suffix alone is not format evidence. The foreground JSON interface can set byte-checked breakpoints from disassembly addresses, click in guest screenshots, run until a breakpoint with a host timeout, and fast-forward a requested number of guest milliseconds. Screenshots and traces are stored inside the project and remain exportable after restart. See [DOSBox debugger usage and acceptance](DOSBOX_DEBUGGER.md).

The current source adds an opt-in dot-mode watch-only window for the **same** native agent-controlled session: append `--dot-mode` (`--window` remains an alias) to the command above. Headless remains the default. This requires a compatible rebuilt backend and an accessible display; see the [window requirements and limitations](DOSBOX_DEBUGGER.md#dot-mode).

Version 0.21.0 also separates [structural MZ eligibility from DOS guest
filenames](DOS_INPUT_NAMES.md), supporting extensionless/long host names
through guarded executable aliases. Published 0.20.0 and its retained system
prefix keep their recorded filename limitation.

Version 0.21.0 includes persistent [screenshot pre/post hooks](SCREENSHOT_HOOKS.md)
for temporarily suspending sprite-render layers, bounded preparation, recorded
capture provenance and automatic restoration of the previous layer stack.

The real DinoPark path was verified through this interface. A ten-second guest skip completed in about 0.45 host seconds on the tested Mac, with actual elapsed values recorded; this is not a speed guarantee. The separately built DOSBox backend is required and is not bundled with the Python tool.

## Persistent scenes (0.17–0.18)

Version **0.18.0** adds per-observation memory-read deduplication,
opt-in compact replies with retained evidence, portable scene bundles, typed
relative outcomes and numbered overlays with legends. See the
[scene improvements guide](SCENE_IMPROVEMENTS.md) and
[development verification record](VERIFICATION-SCENE-IMPROVEMENTS.md).
The [content-recovery design](GAME_CONTENT_AND_PLAYER.md) and
[UIL export boundary](UIL_BOUNDARY.md) describe a future
agent-authored semantic recovery framework. fDisBull would produce a
provenance-bound Universal Interaction Language export and stop there. AEC
cartridges, game runtimes, players and general Python/JavaScript/other language
generators remain independent downstream projects. No UIL exporter is supplied
by this release. Human and agent authors may propose evidence-backed language
amendments through the [UIL RFC process](UIL_RFC_PROCESS.md); acceptance of
an RFC remains separate from implementation or game qualification.

The [scene framework](SCENE_FRAMEWORK.md) saves object context, trigger
provenance, revisions and supporting screenshots in the project database. One
manifest drives native-pixel overlays and named guest actions, with composite
rectangle/polygon masks, separate visible/ready/enabled checks, bounded outcome
verification and saved desynchronization/collision evidence. The updated DOSBox
patch provides sparse RGB probes without PNG transfer. The shared 0.18.0 system
installation and historical 0.17.0 offline kit supply the tested backend;
earlier 0.16.0 binaries do not contain this probe.

The bundled `fdisbull-investigate` agent skill is available with
`fdisbull agent-skill`. It guides evidence-based reverse engineering and scene
authoring, prioritizing expected decision value and cost alongside confidence.
The unreleased skill returns four resources covering the scene API,
claim-specific evidence, action boundaries, failed-probe triage, matched-run
preparation and a capability ladder for runtime navigation and actor-free
observations. The ladder distinguishes current APIs from future resolver and
target-adapter work; it does not implement those capabilities.
The scene runtime currently targets DOSBox; PE64 native pixel probing is not
implemented. [Implementation and limits](SCENE_FRAMEWORK.md).
The [installed-wheel DinoPark verification](VERIFICATION-SCENES.md) exercises
named controls, a popup handler, masks, collisions, restart and debugger stops.
It records the original `0.17.0.dev0` development build. The
[publication/delivery record](DELIVERY-0.17.md) documents the completed
ordinary/native tag CI, exact published packages and copied backend checks.

## Tool packages and examples

The wheel, source distribution, and standalone tool ZIP contain the tool, tests, and relevant documentation. **DinoPark is a repository example and is excluded from tool release packages.**

The [DinoPark example](../examples/dinopark/README.md) contains layouts, investigation notes, and selected renders. Original game executables, resources, saves, and databases retaining those bytes are local inputs. Authored C fixtures are under `examples/synthetic/`.

```bash
python -m pip install '.[test]' build
python -m pytest -q
python -m build
python scripts/check_dist.py
python scripts/build_release.py
```

`MANIFEST.in`, `.gitattributes`, and the standalone ZIP builder exclude repository examples and experimental work from distributable artifacts. Build output goes to `dist/`.

## History and experimental work

Eight saved releases were reconstructed as successive commits: **0.1.0, 0.2.0, 0.3.0, 0.4.0, 0.5.0, 0.8.0, 0.8.1, and 0.8.2**. These are imported release snapshots, not original development commits. Exact 0.6.0 and 0.7.0 source snapshots were unavailable; their later verification notes remain historical documentation. [Import provenance](../history/README.md) records filtering and archive hashes.

The original unfinished DOSBox checkpoint is preserved at tag `archive/dosbox-headless-2026-10-23`; the former experimental and takeover branches have been removed. The continuation contains a complete backend patch and fixture/DinoPark runtime evidence under `experimental/dosbox-x`; the Python integration uses that separately built backend. Neither emulator nor original game assets are included in tool packages.

Version 0.12.0 integrates a [PE64 Wine/QEMU debugger](WINE_DEBUGGER.md): disassembly breakpoints, guarded memory edits, bounded instruction traces, client-window screenshots, 8px grids and mouse clicks, persisted with the project. It requires a separately prepared offline Linux/Wine runtime and QEMU >=9.1. The [earlier Wine/Linux experiment](../experimental/wine/README.md) records why full x86-64 CPU emulation is used on this Mac: Apple container/Rosetta failed the debugger gate. The [published-wheel verification](VERIFICATION-0.12.md) covers real input, memory edits, rearmed breakpoints, traces and offline exports in fresh Linux CI and copied Mac delivery sessions. The runtime and emulator are supplied separately from the public Python packages.

Version 0.13.0 adds PE64 `r`, `w` and `rw` watchpoints, reversible RAM layers, guarded relocated execution layers, and editable native QEMU states. PE execution layers use a private 4 KiB guest allocation and host stepping; the DOS backend's zero-additional-RAM fetch overlay does not apply to Wine. Native PE states capture the Linux/Wine machine and retain a hash-bound private sidecar beside the project. See [usage and exact limits](WINE_DEBUGGER.md#pe64-watches-layers-and-native-states-0130).

## Limits and licensing

Static analysis does not establish runtime execution. A drained queue does not establish complete code coverage. Authored labels and links record interpretations, and unresolved segment/pointer state stays explicit. Native macOS debugger acceptance passes; the full suite still has Linux ELF fixture failures on Apple's compiler/linker. Runtime integration launches original unpatched DOS MZ, explicitly selected COM, or x86-64 PE EXE versions; static child patches are never applied silently. COM support is tested on Linux and on this Mac with the qualified Zork I reference. PE support has its own runtime and acceptance gate. The PE watches, layers and states use different mechanisms and formats from DOS; published 0.12.0 packages do not contain those additions.

Runtime code snapshots preserve and decode observed self-modified or layered bytes alongside earlier views. The 0.16.0 candidate adds explicit offline promotion into a preserved temporal interpretation, fresh traversal/xrefs/CFG and byte/context trace comparisons. Captured bytes do not prove execution; inherited bytes remain unobserved, and no patched disk image is reconstructed. A mapped runtime address alone does not verify equality with static instructions. Headless execution is not security isolation, and restoring a machine checkpoint does not roll back mounted host files.

No first-party distribution license has been selected. Public visibility does not grant an open-source license. See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency provenance. The separate DOSBox-X checkpoint retains its upstream GPL notices.

The debugger also supports [native checkpoints, editable state forks, bounded menu scripts, and CPU data-access breakpoints](DEBUGGER_SCRIPTS.md). See the [0.10.0 release notes](RELEASE-0.10.0.md) and [parking-counter experiment](PARKING_COMMIT.md). Explicit DOS analysis seeds are decoded first within the requested budget, so preparing one execution-breakpoint address is no longer blocked by an older analysis queue.

The 0.11.0 [code layers](CODE_LAYERS.md) distinguish RAM-visible patches from instruction-fetch overlays, preserve observed self-modified code separately from static facts, and support guarded layer stacks, branch theories, and breakpoint-triggered virtual caves. They require the separate layers backend; the published 0.10.0 backend and packages remain unchanged. Zero additional guest RAM bytes does not imply zero host overhead or unchanged guest timing.

Screenshots also support an [optional native-coordinate grid](DOSBOX_DEBUGGER.md#optional-screenshot-coordinate-grid-0110) for writing click scripts. Clean frames remain stored unchanged; annotated images retain the same dimensions and video-mode ID and can be regenerated from the project after restart without operating a GUI. `click-frame` captures, labels and queues a chosen click in one client action.
