# Native renderer publication stop fence

This patch adds a one-shot QMP fence for a **completed synchronous renderer
publication**. It uses the existing retained display observer and clock owner.
It does not claim a guest application frame, VGA retrace, vertical blank, or
completed guest drawing.

## QMP flow

1. Start the existing headless synchronous standard VGA display observer while
the native clock is stopped.
2. Arm `x-fdisbull-arm-display-frame` with a fresh fence `token` and the current
   `display-token`. Arming does not render, advance time, or run the guest. The
   receipt captures the observer epoch and current `baseline-update-id`.
3. Continue execution through the existing controller. On the next observer
   timer callback that successfully completes `graphic_hw_update()`, copies all
   retained pixels, and captures any selected VGA configuration, QEMU increments
   the display update ID and requests a stop at its next safe CPU boundary.
4. Read `x-fdisbull-query-display-frame` after QEMU stops. A completion is valid
   only when `completed-update-id == baseline-update-id + 1`; `published-ns` is
   the actual renderer publication time. `stop-consumed` is true only when the
   frame handler itself requested the VM stop. The result is the ordinary
   paused/SIGINT stop class, matching clock-budget stops. A preexisting debugger stop may
   supersede the fence and leaves `stop-consumed` false.
5. Call `x-fdisbull-cancel-display-frame` before checkpoint export. Cancellation
   of an incomplete arm creates no update; cancellation after completion keeps
   its actual update ID and timestamp. The existing display checkpoint stores
   the pixels and observer update counter. The fence itself is process-local and
   introduces no new checkpoint state.

The frame fence and virtual-clock budget are mutually exclusive. Display
observation must remain active and retain the same observer token and epoch
through completion. Reset, observer invalidation, a pending debugger stop, or a
renderer/copy/configuration failure cannot produce a completed receipt. In
standard retrace mode, a display checkpoint may retain published RGB pixels
without a precise VGA configuration snapshot. A precise-retrace checkpoint
requires that configuration whenever it contains published pixels.
Instrumented checkpoint export/load refuses while a fence is armed or its stop
is pending; cancel it first. Existing hook/debug/clock stop handling retains
precedence. Only one stopped TCG vCPU and the existing supported virtual-clock
profile are admitted.

The display checkpoint decoder also admits retained standard-profile renderer
pixels without a precise VGA publication configuration. When precise retrace
is admitted, pixels still require that configuration. This preserves both
profile contracts through completed-publication cold restore.

## Commands and receipt

- `x-fdisbull-arm-display-frame {token, display-token}`
- `x-fdisbull-query-display-frame {token}`
- `x-fdisbull-cancel-display-frame {token}`

`FdisbullDisplayFrameFenceInfo` reports `api-version`, `epoch`, `state`, fence
and observer tokens, `baseline-update-id`, `updates`, `stop-pending`, and
`stop-consumed`. A completed receipt also includes the exact
`completed-update-id` and `published-ns`. State is `armed`, `completed`, or
`cancelled`; `updates` does not advance past the actual observer update tied to
the receipt.

## Build

Source is QEMU 10.0.13, based on the N19 native cascade runtime. Configure for
x86_64 TCG with the same bounded feature profile, then build only the system
binary. Example from the isolated `frame-history-runtime` directory:

```sh
mkdir -p build-n20 tmp
cd build-n20
TMPDIR=../tmp ../qemu-10.0.13/configure \
  --target-list=x86_64-softmmu --without-default-features --enable-system \
  --enable-tcg --enable-pixman --disable-user --disable-tools --disable-docs \
  --disable-guest-agent --disable-containers --disable-download \
  --disable-install-blobs --disable-debug-info --disable-qom-cast-debug \
  --audio-drv-list= --firmwarepath=../qemu-10.0.13/pc-bios \
  --prefix="$PWD/install" --ninja=/Users/tiga/miniconda/bin/ninja \
  --python=/Users/tiga/miniconda/bin/python3
TMPDIR=../tmp /Users/tiga/miniconda/bin/ninja -C . -j2 qemu-system-x86_64
```

The recorded source and binary identities, build command, and root-owned guest
qualification status are in `source-manifest.json`. No guest or CI execution
was performed by the patch author.

Root-owned local witnesses subsequently passed recording, branching, offline
PNG export, separate-process cold restore, early debugger/hook stops, native
controller exclusion, and task-private RAM/fetch, hook and IRQ preservation.
These are bounded renderer-publication results; the dated project handoff and
!117 carry final source/test receipts. DOSBox-X remains retained and default.
