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

The separate native witness passed in fresh Native02 against the corrected
producer. Native01 remains a retained failed attempt, described below. The
witness uses an independently journaled raw peer on the original GDB channel.
After one verified export and arm, its complete acceptance contract requires:

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

### Native attempt01: unexpected event refusal (2026-11-21)

The corrected producer build and static 150-ELF dependency closure passed.
The retained producer SHA-256 is
`cec82b2b2e8c76ba749bbd4f518d226e831b439d35b2480241ae46541e329c81`.
Freeze02 passed in 42.640 seconds, retaining the original 45-second worker and
70-second aggregate limits; the earlier Freeze01 timeout remains failed.
The separate check-only phase passed in 16.290 seconds. These preparation
results did not execute the native test.

Native01 then ran the exact witness at source
`0cacf582e5c5679ea4a842b2f27dc55887e5fc69`, tree
`9e4f7e518849f8b8d3673c9a4c266258795c21ac`. JUnit records **one failed test,
zero errors and zero skips**. Pytest took 3.08 seconds, its owned worker
5.287 seconds, and the complete controller 19.614 seconds. This was an actual
failed execution, not a timeout or a passing partial gate.

| Witness step | Retained observation |
| --- | --- |
| Setup and arm | One original QEMU owner, one stream/raster, one verified export, one explicit native arm at generation 0 |
| First observation | Complete; native generation 0 before and after |
| Same-byte raw write | Physical byte `00 -> 00`, acknowledged and read back; Python generation unchanged within the transaction |
| Second observation | Complete; native generation 1 before and after, with the same selected state and clock |
| Third observation and ABA | Initial native generation 1; acknowledged `00 -> 5a -> 00` writes/readbacks after the first selected RAM read; both selected reads returned `0000` |
| Actual refusal | Call 298, `x-fdisbull-query-input`, during `input-after`: `Observation authority invalidated: QMP event during stopped observation` |
| Final generation and expected refusal | Not reached; generation 3 and the intended `native-control-after` mismatch remain unobserved |

The independent journal retains 12 raw packets and three acknowledged one-byte
writes, with the original physical-memory mode, pipe endpoints and Python
guards preserved. All six selected two-byte reads returned `0000`. Only five
of the expected six stopped-control queries ran; the controller accepted no
expected observation refusal. The later count-reconciliation failure is
secondary to the QMP event refusal.

The original QEMU owner was reaped with exit zero and no cleanup errors. The
worker exited one, was reaped, and its process group was gone. No adopted or
selected native processes remained. Preflight and postflight matched all
5,968 selected files and six trees. Final output was 4,865,264 logical /
4,890,624 allocated bytes, plus the separate 4,194,304-byte open-log reservation,
within the unchanged 64 MiB cap. Disposal before the unexpected public error
returned was not separately recorded; final cleanup alone does not prove that
earlier timing boundary.

The exact QMP event name and payload were lost by the witness instrumentation.
The observer attached its lease events to the exception, but the controller
persisted full failure evidence only for the expected native-counter refusal.
The test's exception-message check then failed before copying that attached
evidence, leaving `refusal=null`. Neither the native journal nor the retained
QEMU log identifies the event. No specific event or native mutation defect is
inferred from this result.

This failure established the need for bounded attached-evidence retention
before expected-error classification, including the actual event and original
owner/channel disposition. Controller02 implements that diagnostic correction
with the existing event refusal, acceptance assertions and finite limits intact.
Its separately reviewed fresh Native02 is recorded below. Native01 is retained
unchanged and is not promoted or automatically retried.

| Retained artifact | SHA-256 |
| --- | --- |
| Frozen native plan | `2c9a8f3d379ebb6189d0c38f99f7f1441cdf8a166d64f4a10c94a0486df54011` |
| Native test source | `f0ce56bd3baa712f16bd4e2206201802a0726aa1108c4feee145ad10c80e9359` |
| Complete phase result | `542d494bd944c0b1216a7bb052d575f323191aecfcd1305ae77502f5451ddc18` |
| Independent native journal | `40139bcd8407de5f2b9edd5957266823bd8c3cbe79093015ff21dbe3accc5321` |
| Test observation receipt | `ec1036d724231bb3fce6f700fef6548e7a22a4648a04025a632182a7b26e0f3b` |
| JUnit result | `a32d19d0f2bb724b58fa18d71d86b4ecc2f9ae072ead77e9748366e962b87540` |

The complete failed output and exact controller are preserved in the private
recovery checkpoint. The current `fdb-qemu-parity` record on the
[Agent BBS](https://agent-bbs-native.tiga-rce.chatgpt.site) supplies the recovery
catalog under job `qemu-parity-20261118`.

### Native attempt02: complete same-byte/ABA witness (2026-11-21)

A fresh sibling controller and private output ran the unchanged native test at
source `03102d0aae38480aa6deb4a082ba2659c9552c4d`, tree
`8d5bcbdb13ada02265b5a908cc7e79e678987697`. JUnit records **one passed test,
zero failures, zero errors and zero skips**. Pytest took 2.942 seconds, its
owned worker 5.101746 seconds and the complete controller 21.951035 seconds.
The producer and native test hashes remain those recorded above.

| Witness step | Actual retained observation |
| --- | --- |
| Setup and arm | One original QEMU owner, one stream/raster, one verified export, one arm at generation 0 |
| First observation | Complete; native generations 0 and 0 at calls 212 and 238 |
| Same-byte raw write | Physical `00 -> 00`, `OK` and readback; Python generation 89 unchanged |
| Second observation | Complete; native generations 1 and 1 at calls 244 and 270; selected state, source and clocks unchanged |
| Third observation | Native generation 1 at call 271; raw `00 -> 5a -> 00` between its actual selected RAM reads; Python generation 91 unchanged |
| Final native query | Generation 3 at call 304, with the same native process UUID, token and epoch, armed and not busy |
| Required refusal | `Native stopped-control identity changed across the source raster bracket`, stage `native-control-after` |
| Original-owner disposal | PID 42 reaped with exit zero; both captured sockets closed before classification and before the public error returned |

The independent journal reconciles all 304 native calls, including exactly six
native stopped-control queries. The two raw transactions used 12 packets and
three one-byte writes, 221 sent / 82 received wire bytes, and 8,604 journal
bytes. Both transactions finished within their original one-second deadlines.
The original physical-memory mode `0`, pipe endpoints and Python guards were
preserved. All six selected two-byte RAM reads returned `0000`; the ABA was
between the two reads of the third observation. The controller accepted exactly
two successful observations and one native-control refusal, with no row errors.

Controller02 retains every exception caught by the observation's existing try
block before checking whether it is the expected refusal. Earlier admission
checks remain outside that block. Full bounded evidence goes into the existing
journal; a compact reference goes into the reserved owner receipt. Actual
exception authority is used as a fallback when its main attachment omits it.
Disposition reads only the original captured process and sockets, without live
admission, reconnect, native work or cleanup. Missing observations remain
unknown. A retention failure stays secondary to the original error and blocks
qualification. Diagnostic storage uses the original limits.

Ten focused host-only cases verified unexpected-event retention through the
same mismatching test assertion, both attachment sources, authority fallback,
unchanged expected-refusal acceptance, journal-write failure, malformed/oversized
attachments, unknown process disposition and missing evidence. The first two
regression attempts each recorded two test-harness failures and eight passes;
they are preserved. Correcting how the tests captured the original exception
made all ten pass without a controller or acceptance change.

In Native02 the new diagnostic retained the complete actual expected refusal,
with no omissions, notes, secondary errors or disposition-read errors. Its
actual authority event list was empty. The Native02 observation receipts contain
no QMP events; Native01's missing payload is still unknown. No event was ignored
or drained, and no production observer, transport, native producer or guest
change was made.

Fresh metadata Freeze passed in 43.326623 seconds and the separately reviewed
Check-only phase in 12.292897 seconds. The reviewed 150-ELF closure and its
historical derivation metadata were reused unchanged. The fresh frozen plan
binds current source and controller bytes; all 5,969 file pins and six full
trees matched before and after native execution. The original 180-second
aggregate, 75-second worker and 60+10-second case envelope remains unchanged.

The worker exited zero without timeout, was reaped and its process group was
gone. No adopted or selected native processes remained; native logs and cleanup
receipts were complete without errors. Final output was 4,998,018 logical /
5,025,792 allocated bytes plus the separate 4,194,304-byte open-log reservation,
within the original 64 MiB output cap.

| Retained artifact | SHA-256 |
| --- | --- |
| Frozen native plan | `e717876fbea77c7e1c6fddd835fb28192d9656c41fbdbc3631bc03e2843a020a` |
| Native root review | `c2a833bc9de37190f45756b355ac891de0537e23eee7542f2890d35c03b03ca4` |
| Complete phase result | `c174bc312717cd5896d29ee7993576e6dc65f0e6e91561dc29114ce79a235097` |
| Worker result | `35c4b30f0fdae56594e7d7729b75e4ae0d0be3207246591aead68c6ca33e3f7c` |
| Independent native journal | `44e5726064902edd6932f4ab042416e4776dab4d2111f1f74b9aba56b7d01318` |
| Test observation receipt | `400d8459caa34e5cc6569b819a1f2fb5fe6c563faae514f329905a810c1f9499` |
| JUnit result | `297655c14b6091ef03f2a11279bcfec5ff6ae83b939cd2b57b1c107a00bc987d` |
| Complete 70-file recovery archive | `c9ce6cc7a3cd84678beb047db0ed1ed07cd7265a5326c5e9ea15c3cdd5f0e8e0` |

The archive is `QEMU-Stopped-Control-Native02-Passed-2026-11-21.tar.gz`,
792,781 bytes. Every retained member's path, mode, size and SHA-256 was checked
against the source. The board recovery catalog retains the full controller,
plans, reviews, regression history and native output, alongside Native01.
This qualifies the narrow stopped native control-admission witness; the next
separate qualification is native scheduler refusal with empty host bookkeeping.

Throughout this work `atomic=false`, `native_mutation_revision=null`,
`application_frame_complete=null`, `frame_state_equivalence=null` and
`legacy_phase_equivalence=null` remain explicit. `completed_guest_frames` stays
false, DOSBox stays the default, and the 143 surface, 18 workgroup and seven
campaign promotion obligations remain open.
