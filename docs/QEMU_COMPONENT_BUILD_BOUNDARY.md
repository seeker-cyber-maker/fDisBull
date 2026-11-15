# QEMU component build and delivery boundary

This is a source/build-graph inspection of the retained macOS arm64 candidates
on 2026-11-13. It gives the package owner a bounded rebuild recipe. No new native
build, timing benchmark, CI, installation or default change was performed for
this inspection. DOSBox-X remains the default and retained fallback.

## What is modular today

The DOS and CHIP-8 implementations use the same QEMU 10.0.13 foundation, with
in-house architecture, machine and instrumentation source. They currently
produce separately selected **target executables**. A source module is not a
dynamically loadable CPU module:

| Component | Current boundary |
| --- | --- |
| QEMU common engine | Shared upstream source for QMP, GDB, TCG execution, object model, VMState, block images and utility code; compiled into each selected target executable. This is source reuse, not one resident shared engine process. |
| CHIP-8 CPU | `target/chip8/{cpu,gdbstub,helper,translate,vmstate}.c`, selected by `target/chip8/meson.build`; target objects in `libqemu-chip8-softmmu.a`. |
| CHIP-8 machine | `hw/chip8/chip8-test.c`, selected by `CONFIG_CHIP8_TEST_MACHINE`; a minimal machine with no optional PC peripherals. |
| CHIP-8 QMP adapter | `system/qmp-chip8.c` is in the common source set of the CHIP-8 source/build tree. It compiles into `libcommon.a`, rather than a runtime plugin. |
| DOS CPU/machine and instrumentation | The N24 candidate has a separate source/build tree configured only for `x86_64-softmmu`. It has no CHIP-8 CPU, machine or QMP source in its compile commands. |
| fDisBull host | Python adapters and common orchestration are delivered with the tool. A Python-only change does not require compiling either native executable. |
| Checkpoint image tool | An explicitly selected external `qemu-img`; its exact binary hash is included in CHIP-8 debugger identity. The native target recipes disable tools rather than rebuilding this helper. |

The retained CHIP-8 v6 `config-host.mak` selects only
`TARGET_DIRS=chip8-softmmu`. Meson records `modules=disabled`, and its target
inventory contains no shared-module or shared-library target. `default_library`
being `shared` does not override that observed inventory. The only system
executable is `qemu-system-chip8` (via an unsigned link and macOS signing custom
command). No CHIP-8 `.so`/`.dylib` CPU artifact is produced or loaded.

The CHIP-8 compile database contains no `target/i386/` CPU or PC machine source.
It does include the common `hw/i386/kvm/xen-stubs.c`; the presence of that stub
does not mean the x86 CPU was selected. Conversely, N24 selects
`TARGET_DIRS=x86_64-softmmu`, with no CHIP-8 compile entries. Enabling QEMU's
optional module setting is not an implemented CHIP-8 CPU-plugin design. Such a
design would need its own ABI, target-state and compatibility work.

## What a change rebuilds

| Change | Required native work in the present layout | Relevant qualification |
| --- | --- | --- |
| fDisBull Python-only source mapping, storage or orchestration | No native rebuild. Reuse frozen executables by identity. | Focused behavior checks; exercise both adapters when shared code changes. |
| `target/chip8/helper.c` only | Ninja's direct graph maps this source to `libqemu-chip8-softmmu.a.p/target_chip8_helper.c.o`, then the CHIP-8 archive/link and signing output. | Changed instruction/effect and preservation witnesses on the resulting CHIP-8 candidate. |
| CHIP-8 CPU header, translator or VMState | Recompile dependent CHIP-8 objects according to Ninja's recorded dependencies, then link/sign. A header may affect several objects. | Affected CPU/device/checkpoint contracts; exact candidate identities. |
| CHIP-8 machine or `system/qmp-chip8.c` | Recompile its dependent object(s) and link the CHIP-8 target. | Machine launch or QMP protocol/adapter behavior as applicable. |
| `qapi/misc.json` | Regenerate QAPI; changed generated headers may recompile common and target consumers before link/sign. This is broader than one CPU object. | Changed command/receipt schema and consumers. |
| Shared QEMU source changed in both candidates | Deliberately apply and rebuild each affected target tree; an edit in one isolated tree does not propagate to the other. | Both affected native consumers. |
| Tool-only packaging with unchanged native files | Repackage the selected compatible components; do not recompile them merely to create a new tool archive. | Payload identity, dependency availability and a bounded launch/cold-restore check on the delivery host. |

These are dependency-graph statements, not newly measured elapsed build times.
The earlier v4 correction receipt already records a **five-step incremental
Ninja relink** for its guarded replacement candidate. It also records why the
first candidate's file was lost when the mutable build output was overwritten.
Freeze every candidate before the next build; retain earlier checkpoint owners.

A CHIP-8-only build command targets `qemu-system-chip8` explicitly. It neither
enters the separate N24 directory nor invokes DOSBox-X. It does not justify
rebuilding or requalifying unrelated x86/DOS components. This does not make a
common-QAPI or shared-host-code change local to one architecture.

## Exact compatibility inputs

The checked-in package manifests are the authoritative build-chain recipes;
the names below do not replace their hashes or after-file checks:

1. QEMU 10.0.13 source archive SHA-256
   `4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
2. Replay the incremental CHIP-8 [v1 CPU](../native/qemu-chip8/source-manifest.json),
   [v2 devices](../native/qemu-chip8-devices/source-manifest.json),
   [v3 classic/RNG](../native/qemu-chip8-classic/source-manifest.json),
   [v4 layers](../native/qemu-chip8-layers/source-manifest.json),
   [v5 frames](../native/qemu-chip8-frames/source-manifest.json), then
   [v6 frame keys](../native/qemu-chip8-frame-keys/source-manifest.json).
   Check each declared parent patch/manifest and touched-file before/after hash.
   The v6 patch SHA-256 is
   `5f9162d7e88ae2bf0aaae6fc9c03504e7321d605e8124a252533cf4749aa15b3`;
   its manifest SHA-256 at inspection is
   `b012861ebb902fec62c282734d52678697791239e18aa8ad31c33cee14c9df91`.
3. The retained v6 executable SHA-256 is
   `4c06e9426b581dc889f35f980b3bced1b92742e2b23cd28f8118924469f08ee5`
   (6,304,584 bytes). Its protocol identities are:
   `chip8-classic-pilot-default-v1`, machine `chip8-test`, CPU subset
   `fdisbull-chip8-frame-keys-6`, environment
   `fdisbull-chip8-display-keypad-timers-rng-layers-frames-keys-5`, frame model
   `fdisbull-chip8-native-frame-sample-1`, and key model
   `fdisbull-chip8-frame-keys-1`.
4. Native VMState is version 6/minimum 6. Host checkpoints also bind source,
   selected project version, exact QEMU binary/version and checkpoint-tool hash;
   see `QemuChip8Debugger.__init__` in `src/fdisbull/qemu_chip8.py` and the
   validators in `chip8_history.py`, `chip8_frames.py` and `chip8_keys.py`.
   Matching a profile label or VMState number alone does not admit a checkpoint
   made by another binary. Retain v1-v5 runtimes for their existing artifacts.
5. The independently retained [DOS N24](../native/qemu-dos-save-stop/source-manifest.json)
   binary SHA-256 is
   `8af033a259892808dd5b15b524f64145aa17a6dcf3a774dc6e8d2985c31e4d27`.
   Its patch SHA-256 is
   `468f3bf0f1adb8f7d9f1dc11b822e983e180d892cbe1573a09a2f91dc583d195`,
   applied over the separately pinned N23 save-operations chain. It is not a
   dependency of a CHIP-8-only build.

G1 ISA/environment definition identities describe declared compatibility.
They do not prove that a delivered native binary matches or qualifies it; the
runtime inspection and binary pins above remain separate.

## Owner-consumable rebuild and delivery recipe

For an authorized native change, first admit the estimated external allocation
under the current storage policy. Use an isolated external candidate source and
build directory; keep the accepted frozen candidate intact. Replay and verify
the exact manifest chain before configuration. From a fresh build directory
under the candidate source, the retained v6 recipe is:

```sh
TMPDIR="$candidate_tmp" ../configure \
  --target-list=chip8-softmmu --without-default-features \
  --enable-system --enable-tcg --enable-pixman \
  --disable-user --disable-tools --disable-docs --disable-guest-agent \
  --disable-containers --disable-download --disable-install-blobs \
  --disable-debug-info --disable-qom-cast-debug --audio-drv-list= \
  --firmwarepath=../pc-bios --prefix="$candidate_build/install" \
  --ninja="$ninja" --python="$python"
TMPDIR="$candidate_tmp" "$ninja" -C "$candidate_build" -j4 qemu-system-chip8
```

For a matching existing candidate build, reuse its configure/dependency state
and issue only the second command. Review `config-host.mak`, Meson options and
the selected target before reuse. Do not run an unqualified `ninja all`, restore
stale build outputs from another source tree, or mutate a sealed accepted tree.

The package handoff should carry the tool commit and payload hash; component
target/host platform; exact source archive and patch/manifest chain; configure
options and compiler/tool identities; frozen native binary hash; protocol and
checkpoint identities; checkpoint-tool hash; dependency paths/versions/hashes;
and the named behavior exercised. Changed components get new identities and
focused qualification. Unchanged components retain their existing identities
and evidence, with a delivery-integrity check rather than a gratuitous rebuild.

The retained macOS v6 executable is **not yet a self-contained offline runtime
component**. `otool -L` reports absolute Homebrew Pixman and GLib dependencies
in addition to system libraries/frameworks. At inspection they resolve to
Pixman 0.46.4 and GLib 2.90.1. The selected external `qemu-img` is Homebrew
11.1.3, SHA-256
`f04beba959b1576c2955924a4f7a5189292537a172301e05df61da8af994e3f2`;
that is an observed dependency identity, not a promise for every host or future
Homebrew version. A ChatGPT delivery must either use a qualified matching
runtime environment or bundle/relocate and freshly verify the complete dynamic
dependency closure with its licenses. Copying only the executable would leave
an unproved last-mile dependency. No such relocation was performed here.

## Inspection evidence

The private roots used for this read-only inspection are the established study
workspace `QEMU-DOSBox-Parity-20261110` and the external
`chip8-frame-keys-runtime-20261112` source/build tree. The useful records are:

- `build-frame-keys/config-host.mak`,
  `meson-info/intro-buildoptions.json`, `intro-targets.json`,
  `compile_commands.json` and `build.ninja`; `ninja -t query` confirms the
  helper-object, target-link and signing edges without building.
- N24 `build-n24/config-host.mak`, Meson options and compile database, confirming
  the separate x86-only selection and absence of CHIP-8 compile sources.
- `chip8-layers-build-correction-01.json`, recording the earlier incremental
  relink and candidate-retention limitation.
- The checked-in native manifests linked above and the fresh retained baseline
  receipt `chip8-g2-retained-baselines-01.json`.

The source/build boundary is therefore concrete enough to avoid unrelated
native rebuilds now. A dynamically loadable CPU ABI, a unified multi-target
binary, self-contained offline packaging and cross-binary saved-state migration
remain separate proposed work, not properties established by these candidates.

## Subsequent bounded input-checkpoint fix

The [completed-input checkpoint patch](../native/qemu-input-checkpoint-completion/README.md)
closes an observed N24 failure in the original ATTT workflow: a completed
keyboard-press descriptor was mistaken for pending work. Its separate candidate
changes one C file, reuses copied N24 objects/generated inputs, compiles that
object, links and signs. The three replayed commands took about 1.01 seconds;
copying the retained build inputs took about 1.14 seconds. These are local
incremental observations, not a matched clean-build or guest-speed benchmark.
No configure/generator, CHIP-8 or DOSBox-X build occurred. Accepted N24 source,
object and binaries remain unchanged. Exact commands, source edges, patch,
candidate hash and native workflow result are recorded in the new package's
manifest. Existing saved states retain their exact earlier component identity.
