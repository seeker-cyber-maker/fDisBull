# Native input-schedule refusal and original-owner reuse

## Accepted result

The separately supervised **Native03 passed one test with zero failures, errors,
or skips** on source `c3bc62302340e879b21e9cd5862c82036045d5f5`, tree
`e9e0f61d60129ca19b985ebab0b58ebf2f53d46d`. The full controller completed its
independent protocol reconciliation, original-owner cleanup, process-absence,
resource, and input-integrity checks. This qualifies the authored mode-13
armed/cancelled refusal slice described below.

The witness is
`tests/test_qemu_input_schedule_observation_native.py::test_native_input_schedule_refuses_armed_and_cancelled_source_state_observation`.
Its SHA-256 is
`77f2bc18c05e2e29120ca1998a8f8656bca6215642bcf55e3dfd6ae988e25850`.
The [machine-readable verification](evidence/qemu-input-schedule-observation-2026-11-21/verification.json)
records the exact source, producer, limits, outcome, and evidence hashes.

## What the native run established

One original QEMU owner parks the unchanged authored 503-byte COM, starts one
source stream, and completes one retained source raster through one fence and
one continuation. One successful ordinary `video_frame_state_observe` exports
that raster and verifies its independently authored RGB oracle, selected
registers, two physical RAM bytes, native clocks, and initial input state.

The existing Python input-bookkeeping object is empty and remains the same
unchanged object throughout the witness. The test neither creates replacement
bookkeeping nor clears or reconciles it to hide native input state. Direct calls
through the original bound QMP channel then arm one future `a` key-down event and
explicitly cancel the same token while the guest remains stopped. The scheduled
deadline is one billion virtual nanoseconds after the stopped time. Cancellation
retains that time as its terminal time, with reason `caller` and no dispatch.

In both the armed and cancelled states, ordinary selected-state observation
raises `VideoFrameStateRefusal`, code `native_schedule_not_initial`, at
`input-before`. Each refusal retains the actual native scheduler receipt and
performs exactly these five QMP reads:

1. `query-status`
2. `query-status`
3. `query-replay`
4. `x-fdisbull-query-clock`
5. `x-fdisbull-query-input`

There is no GDB operation, source export, continuation, repair, input dispatch,
or native control arm inside either refusal. The original process and both
bound channels remain live when each typed error returns.

### State-specific health evidence

The retained producer deliberately rejects frame-key queries while an input
schedule is armed or failed. The witness therefore records the armed keyboard
as unavailable; it obtains the actual keyboard receipt after cancellation.

| Health check | Armed | Cancelled |
| --- | --- | --- |
| Ordered QMP reads | Status, input, clock, replay, monitor registers, source raster | Status, input, frame keys, clock, replay, monitor registers, source raster |
| QMP count | 6 | 7 |
| Keyboard evidence | `null`, `keyboard_read=unavailable_active_schedule` | Actual unchanged neutral receipt, `keyboard_read=observed` |
| GDB evidence | Register read and two-byte physical RAM read | Register read and two-byte physical RAM read |
| Physical mode handling | Observed mode `0`; select `1`, read, restore `0` | Observed mode `0`; select `1`, read, restore `0` |
| Selected RAM | `0000` | `0000` |

Both health blocks verify unchanged native time, replay counter, selected
registers, monitor reply, source raster, genuine host bookkeeping, breakpoints,
and original-owner identity. The complete arm/refusal/health/cancel/refusal/health
sequence contains exactly **25 QMP calls and 10 GDB exchanges**, with no hidden
operations between its retained intervals. The owned wrapper rejects a
frame-key query after arm until it has verified the original channel's actual
cancellation reply.

## Execution and preservation

| Evidence | Observed result |
| --- | --- |
| Pytest / JUnit | 1 passed; zero failures, errors, or skips; JUnit suite 2.696 seconds |
| Owned worker / complete controller | 4.846191868 / 19.297043205 seconds |
| Native journal | 252 calls: 114 bootstrap and 138 post-setup; 16 source-video calls |
| Source operations | One stream, fence arm/release, continuation, completed raster, and export |
| Observations | One success and two typed, reusable `input-before` refusals |
| Input transitions | One native arm, one explicit cancellation, zero dispatched events |
| Other mutations | Zero guest writes, raw packets, or stopped-control operations |
| Cleanup | Original QEMU exited zero and was reaped; worker reaped and group gone; no adopted children or cleanup errors |
| Input integrity | Same 5,970 file pins and six trees before and after; full producer source/prefix provenance retained |
| Output | 4,694,716 logical / 4,726,784 allocated bytes, plus separate 4,194,304-byte open-log reservation |
| Native receipt | 382,014 bytes, below the 2 MiB cap |

The fresh controller is `frame-parity-20261120/controller-input-schedule-03`;
the raw attempt is
`/tmp/fdisbull-input-schedule-observation-native-20261121-attempt-03`.
Separate metadata Freeze and Check-only phases passed in 38.403288610 and
8.253488188 seconds. Each retained its 45-second worker and 70-second aggregate
limit, verified unchanged inputs, and completed cleanup before native admission.

Native limits remain 180 seconds aggregate, 75 seconds for the worker, 60 seconds
case work plus 10 seconds original-owner cleanup, 64 MiB private output plus
256 MiB free-space reserve, 2 MiB native receipt, and 2,048 native / 32 video
calls. No limit was exhausted or raised for Native03. The producer, retained
baseline, fixture, 150-ELF closure, and 18 loader metadata inputs were reused
without a producer rebuild, assembly, or runtime modification.

| Artifact | SHA-256 |
| --- | --- |
| Producer | `cec82b2b2e8c76ba749bbd4f518d226e831b439d35b2480241ae46541e329c81` |
| Frozen plan | `c2dc70e6662f6c1242c34f743731e44a9df28dc5f39af31e4321fe8589d098d9` |
| Exact root review | `1dd077530ca17db886b5ec2d00b170f8b284a7fc82c2e8e22f4c2771808af19c` |
| Complete phase receipt | `7f10b20d3ff3593062b82517027ba422df90f4a4e668d7e5b7ba2ab980e8b30a` |
| Worker receipt | `6083fe4475281b4770bd30162d394288f19bf888cf80a6c12f8aad5b2718b5f4` |
| Owner receipt | `7c3beda61f69343d1702dd04dda5b3cb7ddd198452224e6b306dfb8149c75127` |
| Independent native journal | `2cb89ac350cd51398ea8802986d3216c83417371bef70fbfa67313e4cf1f2dd8` |
| Native observation JSON | `231ea7e3916a6edec681171389a5bcb227568a00e8798cfe2a0cd869f3dc6988` |
| JUnit | `cfc506999b63152293396623bf0bbb26ef8c4902c37c3bd37fe3f858ca706f88` |

## Earlier attempts remain failed

**Controller01 Freeze** exhausted its 45-second worker limit. It retained three
tree manifests but no frozen plan; no native test ran. A fresh controller02
removed duplicate initial producer-baseline hashing and repeated hashing of
identical selected records. Every unique pin, full tree scan, and late fresh
producer-baseline verification remained required. The failed inputs, partial
outputs, and cleanup are preserved separately.

**Native02**, on `f54d773edfa79f191280c4e226a27952427374cb`, passed its baseline
observation and armed refusal but failed during armed health when the witness
queried frame keys. QEMU returned its documented active-schedule exclusion.
Cancellation and the cancelled refusal were not reached. The original owner
was reaped with return code zero, and complete input postflight matched. The
source correction respects that producer contract and retains all other
readbacks. Native02 remains failed and its complete evidence is preserved.

The corrected test's exact node collected successfully. The earlier 194 related
host tests remain separately attributed host evidence. The existing pytest
`record_property`/xunit2 compatibility warning is retained in the native log.

## Scope

This result adds actual armed/cancelled scheduler coverage to the
[selected-state observer](QEMU_SOURCE_STATE_OBSERVATION_GATE.md). It does not
qualify scheduler dispatch or guest consumption, mouse/global device neutrality,
atomic frame/CPU state, external/native mutation exclusivity, application drawing
completion, legacy raster sampling equivalence, other modes, or real games.
Those fields and obligations retain their existing unknown or unqualified state.
DOSBox remains the default backend.
