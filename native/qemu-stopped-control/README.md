# Native stopped-control admission, API 1

This candidate adds an explicitly armed, process-local control-admission receipt
for a stopped, single-CPU QEMU session. Its scope is
`stopped-native-control-admission-v1`. The host must select this scope explicitly;
the existing cooperative Python source-state observer remains a separate
contract. This package does not establish raster, application-state or legacy
parity.

## Receipt and lifetime

`x-fdisbull-arm-stopped-control` takes exactly one 32-character lowercase
hexadecimal token. Native code creates one canonical lowercase UUID for the
process, binds the supported nonzero virtual-clock epoch at arm, and returns
API version 1, model `qemu-stopped-control-v1`, that process UUID and token,
an unsigned 64-bit generation, admission state and dispatcher-busy flag.

Arm is possible only with this one QMP dispatcher active, one settled stopped
CPU, no earlier unreviewed or overlapping bootstrap control, no pending
runstate/clock/frame control, no replay/migration/checkpoint/dump work, initial
idle input, and a neutral PS/2 boundary. A successful arm consumes the process's
one scope. Unknown control cannot be repaired by retrying arm or changing its
token.

`x-fdisbull-query-stopped-control` requires the exact token. A well-formed stale
token is an inert query error. A matching retired receipt remains readable and
retains the epoch captured at arm, without consulting the current clock.
Identity, taint, retirement and generation have no VMState registration or
reset path. Reloading guest state cannot rewind them.

## Covered admission paths

The hooks count active QMP, HMP and GDB dispatchers before their handlers can
run. Unknown QMP is also inspected when received, before waiting in a monitor
queue, so a successful arm cannot pass work that was already queued. A receipt
is busy while another covered dispatcher remains active. The scope mutex is
never held across a native handler, CPU synchronization or memory-region lookup;
BQL may precede the scope mutex, and the reverse acquisition order is excluded.

After arm the QMP allowlist contains exact empty-argument status/replay/clock/
input/frame-key/video-frame queries, the token-bound receipt query, and exactly
`human-monitor-command` with `command-line: info registers`. Unknown arguments,
other commands and all `exec-oob` forms retire admission. HMP admits the exact
`info registers` command only. Channel closure taints eligibility even before
arm; a channel opening after arm retires it. Instrumented native run/reset
lifetime changes retire the scope before their effects.

GDB admits exact register reads, physical-memory-mode queries/selections and
bounded `m`/`M` packets over ordinary physical RAM. Memory packet grammar is
checked completely, including address/length overflow, data length, hexadecimal
digits and suffixes. Length is 1–2048 bytes. Every covered memory section must
start at the next requested byte and be ordinary writable, volatile RAM;
holes, ROM/ROMD, RAM devices, IOMMU/protected/guest-memfd regions, and readonly or
nonvolatile sections are refused. Region references are released on every
visited section.

An admitted physical RAM `M` increments generation before the real GDB handler,
including a same-byte write or one that later fails or writes only a prefix.
The counter never wraps: another write at `UINT64_MAX` retires admission and
retains that value. Unsupported GDB packets, raw interrupt and unreviewed
control retire the scope before their covered effects. Retirement is sticky
and keeps the first reason, bounded to 128 bytes.

Before arm, the reviewed bootstrap additionally permits exact capability/XML
queries, continue/stop, the bounded retained-video-frame flow and one-byte
hardware execution breakpoints. The DOS bootstrap's virtual `M22be4,1:01` is
admitted only for stopped x86 with no custom debug-memory callback and paging
disabled. It synchronizes the CPU only after marking GDB active, then checks
the actual CPU address space and every translated page against ordinary RAM.
This exception does not continue after arm.

## Interpretation and exclusions

The observation path reads the receipt and an already verified, immutable
retained raster export. It does not resume the guest or export a new image to
make an observation pass. Equal admissible receipts around an observation mean
that no covered ordinary-RAM write admission intervened and the process-local
scope remained usable. They do not assert that all machine state stayed equal.

Uninstrumented device/AIO writers, DMA, backing storage, atomic snapshots,
application frame completion and legacy state revisions are outside this
scope. The receipt is a control-admission identity, not a whole-machine mutation
revision. The host must still bind its original process, transports, source
receipt and owned RGB bytes and refuse replacement or incomplete evidence.

## Recovery and qualification

This is a new candidate reconstructed after a workspace rollback. The recovered
native core, public header and QAPI definition match the prior candidate's
recorded bytes exactly. Surrounding integration is reconstructed against the
hash-checked QEMU 10.0.13 plus 35-patch prerequisite source. Its new manifest must
bind every changed file's actual before/after SHA-256 and the complete new patch.
The historical whole-patch identity is not carried forward as evidence.

The author's integration review checked the actual restored call paths:

- `qapi/qmp-dispatch.c` installs the QMP current monitor in both direct and
  bottom-half dispatch. `qmp_human_monitor_command()` initializes its temporary
  HMP object without changing that current monitor. The HMP wrapper checks it
  before the original handler switches to HMP, preserving the exact nested
  `info registers` exception.
- The generic GDB dispatcher has one return. Enter/leave hooks bracket that
  body, and its new system header, physical-mode dependency and raw-interrupt
  hook remain under `CONFIG_USER_ONLY` exclusions. The patch keeps full context
  for this one file so its exact full source can be reconstructed and checked
  by the user-mode preprocessor falsifier.
- `monitor/qmp.c` belongs to `qmp_ss`/`libqmp`, whose objects also enter
  `qemu-storage-daemon`. Four lazy `libqemuutil` stubs supply the QMP receive,
  enter, leave and channel hooks for non-system consumers. The existing
  `have_block or have_ga` monitor-stub group includes them even in a mixed
  system/tools build. System objects provide the real implementation and
  commands; the stubs cannot arm or return a native receipt.
- The runstate pending predicate reads the vmstop request under its existing
  mutex and atomically inspects the other queued flags without consuming them.
  The main loop retires admission before consuming pending work. Direct reset
  and changed runstate also retire before effects. The host-signal entry point
  receives no scope-mutex call.

The accepted base-source audit verified the 35-patch chain, its 70 input files,
all 92 final touched-file hashes and the complete restored source inventory.
The earlier recovery receipt remains a failed receipt because it used a
different convention for counting the source-root directory; the separate
read-only audit accepted the exact same source without another extraction.
The fresh compiled-source gate passed 107 cases with no failure, error or skip;
all 1,707 pinned inputs remained unchanged and the owned worker was reaped with
its process group gone. Its result SHA-256 is
`100444b7702fe1e0d29a2dc68e67cf757586be3c882bd0f0ef8368d5d3f3f3be`.
These probes used patch
`557da58631c3e0d4ad8a34f395441c3f2094c159ed2d2ddf769a089e89b1a01e`
and the manifest before this qualification-only update
(`6421e649a2f2d3ae784248b922d788e89bd961f8f18f7613c8473dcfd6c47b30`).

The first full build attempt verified the copied source and all 13 patch
projections, then failed during configure before Ninja or QAPI generation.
The private CPython 3.13 runtime lacks `ensurepip`, and QEMU's nested-venv setup
could not initialize its build environment. The failure receipt is preserved
(`cd4658a224b30c587584b7ef3fff66b4aaf21faaa2e0fe61f0243fa1db3375a6`),
the candidate source remained unchanged, and the owned worker and process group
were fully disposed. A separate isolated build-only Python runtime is the next
environment correction; it does not alter the qualified host runtime. No
successful QEMU build, full combined schema parse or new native execution is
claimed.

The authored `tests/test_qemu_stopped_control_source.py` reconstructs the exact
hash-checked native C, replaces only includes with controlled external stubs,
and exercises its real parsers and transitions. Its adversarial cases cover
queued taint, one-shot identity, stale query behavior, active dispatchers,
generation before effects and overflow, memory-map exclusions and the stopped
x86 bootstrap boundary. Such source probes do not execute QEMU's actual
monitor/GDB dispatch, devices, guest or native thread schedule.

The gates remain separate: source/build-graph review; focused compiled-source
falsifiers and full combined QAPI schema parse; a
bounded target build tied to exact prerequisites and output identity; and a
finite native probe that observes direct control, raw retirement, cached-raster
observation and counter behavior on that exact executable. Paired legacy phase
qualification is a further gate. A green source probe cannot satisfy a later
gate.
