# Native QEMU virtual clock extension, version 1

This directory contains an explicit source patch for **QEMU 10.0.13**. It adds
passive `QEMU_CLOCK_VIRTUAL` observation and a native virtual timer that requests
a stop during one caller-owned GDB continue. It is an experimental private
extension, not an upstream QMP API or a supported TCG plugin ABI.

The `standard` and `instruction` fDisBull profiles retain their existing stock
runtime behavior. The `virtual` profile requires this separately built runtime.
Runtime inputs, source archives, build dependencies, build output and firmware
remain outside the repository and tool packages.

## Reproduce the source changes

Use a pristine QEMU 10.0.13 source tree and apply
`qemu-10.0.13-fdisbull-clock-v1.patch` with `patch --batch --forward -p1`.
`source-manifest.json` records SHA-256 values for every modified upstream file,
every resulting source file, and the patch. It also identifies the upstream
tag. Verify the base file hashes before applying and the patched hashes afterward.
An existing patched tree must not receive the patch a second time.

The tested [official source archive](https://download.qemu.org/qemu-10.0.13.tar.xz)
is 141,718,608 bytes, with observed SHA-256
`4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa`.
This pins the downloaded bytes; it is not a publisher-signature claim. The
unrelated EDK2 `X11IncludeHack` absolute symlink was excluded during safe
extraction; this route does not rebuild EDK2 firmware.

From a checkout of this repository, verify, apply, and verify again:

```sh
export FDB_QEMU_SOURCE=/private/qemu-10.0.13
export FDB_QEMU_BUILD=/private/qemu-clock-build
export FDB_QEMU_FIRMWARE=/private/qemu-pc-firmware
python3 - "$FDB_QEMU_SOURCE" native/qemu-clock/source-manifest.json <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys
source, manifest = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
record = json.loads(manifest.read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert (source / 'VERSION').read_text().strip() == record['qemu_version']
patch = manifest.parent / record['patch']
assert digest(patch) == record['patch_sha256']
for item in record['files']:
    path = source / item['path']
    if item['base_sha256'] is None:
        assert not path.exists(), path
    else:
        assert digest(path) == item['base_sha256'], path
subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)],
               cwd=source, check=True)
for item in record['files']:
    assert digest(source / item['path']) == item['patched_sha256'], item['path']
print('All native source hashes verified')
PY
mkdir -p "$FDB_QEMU_BUILD"
cd "$FDB_QEMU_BUILD"
"$FDB_QEMU_SOURCE/configure" --target-list=x86_64-softmmu \
  --without-default-features --enable-system --enable-tcg --enable-pixman \
  --disable-user --disable-tools --disable-docs --disable-guest-agent \
  --disable-containers --disable-download --disable-install-blobs \
  --disable-debug-info --disable-qom-cast-debug --audio-drv-list= \
  --firmwarepath="$FDB_QEMU_FIRMWARE" --prefix="$FDB_QEMU_BUILD/install"
ninja -j6 qemu-system-x86_64
```

The observed Linux dependency set used GLib/gmodule 2.84.4, Pixman 0.44.0,
Meson 1.7.0, Ninja 1.12.1, PCRE2 10.46, libffi 3.4.8 and zlib 1.3.1.
Private extracted dependencies need their own pkg-config and runtime-library
paths supplied before configuring; explicit `--python`, `--ninja` and linker
rpath options can select that prepared prefix. No `ninja install` or global
package installation is required. Supply matching PC firmware explicitly at
runtime and select the project's `pipe` transport where Unix sockets are
unavailable. Source distributions and tool-source ZIPs carry this patch;
Python wheels do not contain an emulator executable.

Build a private `x86_64-softmmu` runtime with TCG and the usual PC/Pixman support.
The native build receipt owns exact configure arguments, dependency identities,
compiler output and the resulting binary hash; this directory does not install
or replace a system QEMU. The authored patch introduces six source changes:

- `system/fdisbull-clock.c`: QMP commands, timer and budget lifecycle.
- `include/system/fdisbull-clock.h`: narrow internal hooks.
- `qapi/run-state.json`: generated command and response schema.
- `system/meson.build`: source registration.
- `system/runstate.c`: consume the private stop request; invalidate on reset
  and unsupported runstate transitions.
- `accel/tcg/icount-common.c`: register the supported fixed-icount configuration
  and suppress further idle warping while a budget stop is pending.

The unarmed extension does not advance the clock, schedule a timer, or stop the
guest. Configuration registration and an empty pending-stop check do not enable
the feature. A query initializes an inactive timer and a state observer only.

## QMP contract

All commands are ordinary, in-band, non-coroutine QMP commands under the big
QEMU lock. They are available after normal QMP capability negotiation.

| Command | Arguments | Behavior |
| --- | --- | --- |
| `x-fdisbull-query-clock` | None | Read the native virtual clock and latest budget record. Stable observations require the VM to be stopped. |
| `x-fdisbull-arm-clock-budget` | `delta-ns`: integer, `token`: string | Arm a single native virtual timer while stopped. This does not resume execution. |
| `x-fdisbull-cancel-clock-budget` | `token`: string | Disarm and acknowledge the matching budget while stopped, preserving its firing and stop observations. |

Each successful command returns the same versioned record:

| Field | Type | Meaning |
| --- | --- | --- |
| `api-version` | integer | Exactly `1`. |
| `epoch` | unsigned 64-bit integer | Starts at `1`; reset or unsupported state invalidation changes it. |
| `virtual-ns` | integer | `qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)` at observation. |
| `running` | boolean | Whether native runstate is `running`. |
| `status` | QEMU runstate string | Native runstate at observation. |
| `budget-supported` | boolean | Supported icount configuration, one vCPU, replay disabled, no active migration, and no invalidation. Arm has additional stopped-state checks. |
| `pending-stop` | boolean | The extension's own stop request has not yet been consumed or satisfied. |
| `budget-state` | string | `idle`, `armed`, `fired`, `stopped`, `cancelled`, or `invalidated`. |
| `budget-token` | optional string | Token for the most recent budget. |
| `budget-start-ns` | optional integer | Native virtual time at arming. |
| `budget-deadline-ns` | optional integer | Absolute deadline, calculated once as start plus delta. |
| `budget-fired-ns` | optional integer | Time observed in the timer callback. Absent for an early stop or cancellation before firing. |
| `budget-stopped-ns` | optional integer | Native time after CPUs stopped, or at cancellation before any execution. |

Absent optional fields are omitted, not set to JSON null. The token/start/deadline
fields appear together after the first successful arm. After cancellation, the
latest record remains available until a new budget is accepted.

### Supported execution profile

Budget execution initially requires:

```text
-accel tcg,thread=single -smp 1 -icount shift=7,align=off,sleep=off
```

Record/replay and migration are unsupported. The first successful arm installs
a process-lifetime migration blocker. Reset, restore, save/migration states,
suspend, shutdown and other unsupported runstates invalidate this extension
instance. An invalidated process may still be observed, but must be closed
before further budget execution. A new emulator process supplies a fresh epoch.

`delta-ns` must be an integer from 1 through 60,000,000,000 and must not overflow
the signed native clock. A token contains 1 through 128 UTF-8 bytes and must
differ from the latest budget token. The host supplies a fresh unpredictable
token for each operation and binds it to the epoch. Arming over an active budget,
arming an unsupported profile, and cancelling the wrong token are errors.

## Stop and cancellation ordering

The controller arms while stopped, sends exactly one GDB continue, and observes
the original GDB stop. It then queries and cancels the matching budget. It may
also cancel immediately after arming, before any continue. Successful cancellation
returns `budget-state: cancelled`, `running: false`, and `pending-stop: false`.
Repeating cancellation for that same stopped budget is safe.

The ordinary virtual timer has attributes zero, so it participates in icount's
native deadline selection and HLT idle warping. Its callback runs in the vCPU
thread under the big QEMU lock. On firing it records the native clock, sets a
private pending flag, requests the current CPU to stop, and wakes the main loop.
It does not disable its own clock or synchronously pause all CPUs from within
timer dispatch.

The main loop processes already-pending native debug requests first, then consumes
the private budget stop. A budget's own stop uses `RUN_STATE_PAUSED`, yielding
GDB SIGINT (`T02`); real debugger stops retain SIGTRAP (`T05`) and their original
watchpoint details. A coincident debug stop can satisfy the budget's pending
request while still retaining a timer-fired observation. The GDB stop reason
must not be replaced merely because `budget-fired-ns` is present.

The VM-state observer runs after the CPUs pause. It removes the timer, records
the stopped clock, and clears the private pending request. Because that request
never enters QEMU's shared VM-stop request slot, it cannot remain there to stop
a later continue. Cancelling while running, while a private stop remains pending,
or after invalidation is rejected. The host closes the emulator on an uncertain
operation instead of retrying a continue or reusing a possibly armed process.

## Precision and qualification boundaries

These are native virtual nanoseconds, including icount idle warping. They are
independent of the separately observed `query-replay.icount` instruction counter.
No host elapsed time, BIOS tick count, or scaled instruction count substitutes
for the virtual-clock reading.

The timer requests a stop at a native deadline; version 1 does **not** promise
an exact arbitrary-nanosecond cutoff. Fixed shift 7 has a 128 ns instruction
quantum, and QEMU may process other due device timers at the same boundary.
The receipt preserves requested, fired and stopped times for direct comparison.
The extension suppresses additional HLT idle warping while its stop is pending.
While a budget is armed, it also suppresses warping when a CPU has a debugger
stop pending or is already stopped. QEMU can otherwise reach its main-loop
idle-warp check before consuming a debug request, artificially moving an early
break/watchpoint's clock to the budget deadline. A merely halted CPU remains
eligible for native idle warping. The early-stop witnesses require the actual
short instruction interval and then run past the cancelled deadline to check
that no deferred stop survived.
Guest IRQ ordering at an identical deadline is not a new guarantee.

Schema parsing and patch application/byte-for-byte roundtrip are source-level
checks only. The separate native qualification must establish stopped stability,
busy-loop progress, HLT virtual-time progress independent of instruction count,
IRQ behavior, early breakpoint/watchpoint preservation, cancellation before
execution, cancellation followed by another continue without a phantom stop,
and reset rejection. Build success alone does not qualify these behaviors.

Virtual time does not establish completed video frames, audio delivery, guest
input consumption, or saved-state compatibility. Those retain independent
witnesses and qualification gates.
