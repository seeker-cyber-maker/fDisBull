# Native DOS save safe-stop selection

This incremental QEMU patch adds an opt-in automatic stop receipt for the existing source-bound FreeDOS save-operations witness. It leaves the legacy witness API v1 and operations API v2 info/query contracts unchanged. The separate `qemu-pc-dos-save-stop-v1` receipt is configured with SET, queried independently, and ACKed only after the host has persisted the settled result.

The stop can be requested only at a matched completed INT 21h AH=0Dh return when the active v2 ledger is valid and ready. It records the exact returned CS:IP/SS:SP and witness event/generation. It does not infer a stop from a preexisting ready ledger. The IRET helper requests `cpu_stop_current()` and notifies the main loop; the main-loop handler attributes a PAUSED stop only when that request wins. A preexisting debugger stop, step, breakpoint at the return PC, active clock budget, or display-frame fence is preserved and reported as preemption.

## Persistence and limits

The N24 witness parent VMState is version 3 with minimum version 3. It saves the opt-in policy, sequence, settled outcome and returned location. A pending main-loop handoff is rejected by `pre_save`; restore rotates native epoch and generation but never reissues an old stop. A repeated eligible flush before the prior attempt is ACKed invalidates only the auxiliary safe-stop control. The existing save ledger remains a separate proof.

Automatic keep is disabled by default. It is intended only for explicit public workspace save-keep runs; scripts, trials and internal history/undo/frame paths do not acquire this behavior. The native tests were root-owned. The bounded 12-case suite passed with no skips; broader preservation qualification is separate. Cross-binary restore, hosted CI and DOSBox parity are unqualified.

## Apply and build

This patch is incremental over the N23 `guest-write-provenance-runtime` QEMU 10.0.13 source and requires the N23 save-operations patch recorded in `source-manifest.json`. Dry-run, then apply it with `patch -p1` to that source. From the N24 runtime directory, configure a fresh build and compile:

```sh
patch --dry-run -p1 -d <N23-qemu-10.0.13> < native/qemu-dos-save-stop/qemu-10.0.13-fdisbull-dos-save-stop-v1.patch
patch -p1 -d <N23-qemu-10.0.13> < native/qemu-dos-save-stop/qemu-10.0.13-fdisbull-dos-save-stop-v1.patch
mkdir -p build-n24 tmp-n24
cd build-n24
TMPDIR=../tmp-n24 ../qemu-10.0.13/configure \
  --target-list=x86_64-softmmu \
  --without-default-features --enable-system --enable-tcg --enable-pixman \
  --disable-user --disable-tools --disable-docs --disable-guest-agent \
  --disable-containers --disable-download --disable-install-blobs \
  --disable-debug-info --disable-qom-cast-debug --audio-drv-list= \
  --firmwarepath=../qemu-10.0.13/pc-bios \
  --prefix="$PWD/install" \
  --ninja=/Users/tiga/miniconda/bin/ninja \
  --python=/Users/tiga/miniconda/bin/python3
TMPDIR=../tmp-n24 /Users/tiga/miniconda/bin/ninja -j4 qemu-system-x86_64
```

The isolated replay receipt confirms all seven touched-file outputs match the N24 source tree. The manifest records the candidate binary hash and bounded native qualification receipt.
