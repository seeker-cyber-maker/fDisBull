# Native stopped-control observation gate

## Purpose and scope

The optional `native_stopped_control` capability adds a process-bound native
control identity to the selected stopped-state observer. The identity counts
reviewed ordinary physical RAM write admissions, including same-byte writes,
before their effects. An unsupported control or a lifetime boundary retires the
scope permanently. This lets the observer detect an intervening write even when
the selected bytes return to their original values.

The scope name is `stopped-native-control-admission-v1`. Its generation is a
control-admission counter. It does not represent every device, AIO, DMA, backing
store or internal emulator mutation. A successful bracket remains non-atomic,
and it does not establish whole-machine equality, application drawing completion
or DOSBox phase equivalence.

The default [selected-state observer](QEMU_SOURCE_STATE_OBSERVATION_GATE.md)
retains its existing cooperative contract. Native admission is explicit and is
never silently substituted for that contract.

## Caller sequence

Use one original QEMU owner with the virtual clock, one TCG CPU, no network and
the precise retrace profile. Require the actual advertised command set and
`native_stopped_control` capability; a capability flag alone is not an arm
receipt. The machine must be settled and stopped, with the initial idle input
schedule, a neutral keyboard boundary and no pending native controllers.

First obtain and verify the intended retained raster through the normal source
export. This populates the original owner's immutable RGB cache. Then arm once:

```python
rgba = debug.video_frame_rgba(stream=stream, frame_id=frame_id)
armed = debug.stopped_control_arm(timeout_ms=1000)
observed = debug.video_frame_state_observe(
    ram_ranges=[{"address": address, "length": 2}],
    stream=stream,
    frame_id=frame_id,
    timeout_ms=1000,
    native_control_token=armed["token"],
)
```

The examples assume a caller-selected stopped session, retained stream/frame
identity and valid ordinary physical RAM address. They do not start a guest,
advance a frame or prepare a baseline automatically.

| Interface | Operation |
| --- | --- |
| Python | `stopped_control_arm(timeout_ms=1000)` |
| JSON method | `debug-stopped-control-arm`, with the existing `run` selection and optional `timeout_ms` |
| Script operation | `stopped-control-arm` |
| Scoped observation | Existing `video_frame_state_observe`, `debug-video-frame-state-observe` or `video-frame-state-observe`, plus `native_control_token` |
| Native arm/query | `x-fdisbull-arm-stopped-control` / `x-fdisbull-query-stopped-control` |

Tokens must contain exactly 32 lowercase hexadecimal characters. Script
references may be resolved normally, but their resulting values are validated
before timeout adjustment or dispatch. Whole-route script preflight rejects an
unsupported capability or invalid visible literal before an earlier mutation.
The native route is restricted to the existing `qemu-machine` and `qemu-dos`
backends.

## Boundaries and receipts

The arm preflight checks the current stopped clocks, input state, retained
source and verified cache under the existing passive authority. The effectful
arm occurs after that passive lease ends while the original machine lock is
still held. The host binds the context, machine, process, lock, original QMP/GDB
objects and sockets, authority, selected session state, source and cached RGB.

Each scoped observation checks this binding before installing transport
deadlines. Its first QMP operation queries the native identity; its last QMP
operation queries it again, enclosing the selected CPU/RAM, input, clock and
source reads. Both raw native receipts remain in the observation evidence. The
process identity, token, epoch and generation must agree across this bracket,
and both receipts must be armed and not busy. A generation may increase between
separate observations, but it may not regress below the last accepted value.

The native receipt has API version 1, model `qemu-stopped-control-v1`, a
canonical lowercase process UUID, the armed token, unsigned 64-bit generation
and epoch, an `armed` or `retired` state, and a strict Boolean `busy` value. A
retired receipt may carry a bounded reason. Boolean values are not accepted as
integer counters. A well-formed stale-token query is inert and returns an
error; it does not adopt or repair another scope.

Scoped observations use the already verified immutable RGB bytes. They perform
no new export after arm and identify the source with:

```json
{
  "exported": null,
  "rgb_origin": "previously-verified-immutable-export"
}
```

The original source identity and cached bytes must still match. A native
identity change, retirement, busy scope, malformed receipt, replaced binding,
deadline failure or interrupted admitted bracket fails closed. Cleanup uses the
captured original owner and transports. Replacement channels are not adopted
for cleanup or deadline restoration, and a cleanup failure remains secondary to
the original observation failure. Literal or admission refusals before native
dispatch retain the existing typed refusal behavior.

## Native admission coverage

The producer instruments native QMP receive/dispatch, GDB packet dispatch, HMP
dispatch and selected runstate/channel lifetime boundaries. Receive-time QMP
classification prevents unsupported queued work from waiting unnoticed behind
an arm request. Dispatcher counters are balanced across completion paths and
are checked at arm/query. The scope mutex is not held across handlers, CPU
synchronization or memory lookup.

Supported stopped physical `M` writes increment generation before dispatch,
including unchanged bytes and subsequently partial or failed writes. The
bounded interval must resolve entirely to ordinary RAM; device apertures,
readonly/nonvolatile mappings, ROM, ROMD, IOMMU, protected memory and guest-memfd
regions are excluded. Exhaustion retires the scope instead of wrapping.

Before arm, the reviewed DOS bootstrap also admits its exact debugger packet
forms and a restricted stopped nonpaging x86 virtual-memory path. Unknown or
overlapping bootstrap controls taint future admission. Run, reset, load and
channel lifetime changes after arm retire the scope. Process identity, token,
generation, counters and retirement are not restored from VMState.

## Qualification status

The host and public implementation has been reconstructed after workspace
recovery. Fresh host gate03 passed **407 cases with zero failures, errors or
skips**. All 1,716 checked source/runtime entries matched before and after.
The owned worker exited zero, was reaped, and its group was gone without adopted
children or cleanup errors. The complete gate took 68.46672589499985 seconds;
the owned worker took 67.79773946699993 seconds, within its 180-second allowance.
Its final resource sample was 191,398,767 logical / 195,190,784 allocated bytes
within the 512 MiB cap. This is host/public behavior, not native QEMU execution.

JUnit is 62,386 bytes, SHA-256
`a2228d2931363a179c8f149c09577b1cd1ebdb735975f2c6a41e48fb57fda362`.
The identical before/after input inventory is 708,298 bytes, SHA-256
`063bdf1cdfeee332d9aad457d54d1815668f363273c471077dc2690264c64054`.
The selected modules include 55 native-scope host cases, 50 public-route cases,
and 302 existing observation, source-frame, consumer and deadline cases.

Recovered host attempts01 and02 remain failed. Attempt01 used a target-store
path that violated the existing private-storage ancestry check. Attempt02
recorded407 passing cases but exceeded its 2 MiB JUnit cap because automatic
parameter names serialized an8 MiB command and192 KiB byte string. Gate03 used
an explicit private target store and compact names for those parameter cases;
all original parameter values and assertions remain unchanged. No production
behavior or report/storage cap was relaxed to correct either setup failure.

Earlier source-state native evidence remains pinned to its original producer
and is not qualification for this new native module.

The separate native witness is authored but is not yet qualified. It requires
one freshly built producer and an independently journaled raw peer on the
original GDB channel. After one verified export and arm, it must demonstrate:

1. A successful scoped observation of two unchanged ordinary physical RAM bytes.
2. A raw same-byte write with native `OK` and readback, unchanged Python control
   generation, native generation `+1`, and another successful observation.
3. During the next observation, a raw `00 -> 5a -> 00` sequence after an actual
   selected read, with native acknowledgements/readbacks and unchanged Python
   generation. Equal final selected bytes must still produce a native `+2`
   mismatch, an incomplete observation and original-owner disposal.

The raw peer may use the captured channel below Python protocol admission. It
may not clear or replace transport buffers, remove, replace or disable authority
guards, create a second connection, or replay uncertain writes. Its controller
must independently decode the bounded wire transcript, preserve the original
physical-memory mode, reconcile native calls and process identity, verify
loaded-image/input pins and complete owned cleanup within the admitted budget.

Throughout this work `atomic=false`, `native_mutation_revision=null`,
`application_frame_complete=null`, `frame_state_equivalence=null` and
`legacy_phase_equivalence=null` remain explicit. `completed_guest_frames` stays
false, DOSBox stays the default, and the 143 surface, 18 workgroup and seven
campaign promotion obligations remain open.
