# Finite native named keyboard-action gate

**Prepared, not executed.** This gate starts from source
`14aa3cf5deb5348a3cda39e1e899ae60c76a58e9` and requires the separately reviewed
named-action implementation and exact final source/test pins. It defines two
authored DOS cases and at most two native VM lifetimes. Source preparation and
host checks do not establish a native pass.

The new explicit profile is `fdisbull-scene-3`, with
`observation_profile: {"kind": "runtime-memory", "version": 1}` and
`action_profile: {"kind": "qemu-virtual-keyboard", "version": 1}`. Each selected
object declares one finite keyboard press. Existing passive scene-2 definitions
do not gain action authority. This gate leaves frame-backed scenes, pointer
actions, navigation, general game compatibility and DOSBox retirement open.

## Cases and maximum owner count

The native source is `tests/test_qemu_scene_act_native.py`. Select only these
two cases, stop on the first failure, and create no replacement or retry owner.

| Test suffix | Entry route | Maximum VM lifetimes | Required evidence |
| --- | --- | ---: | --- |
| `test_native_named_action_saved_script_consumption_and_effect` | JSON saved script ID | 1 | Initially ready object and false outcome; one accepted press; complete make/break delivery; independently observed guest consumption and position effect; canonical/public/exported/saved/reopened result |
| `test_native_named_action_json_refusal_and_first_stop` | JSON action calls | 1 | False readiness refuses without input or execution; a fresh admitted action then stops at the first IRQ fence with a retained make prefix, pending break and unknown unpolled effect |

The second case contains one passive refusal followed by one deliberately
interrupted attempt on the same fresh owner. They have separate attempt and
declaration identities. The refusal does not authorize the later attempt.
There are no restores, retries, screenshot probes, automatic releases or extra
post-action guest runs. Offline cold Project reopen creates no VM.

## Guest oracle

Reuse `movement_guest` in `tests/support/observed_movement_fixture.py` unchanged.
It runs as an original COM under real DOS, installs an IRQ1 handler, records
actual keyboard-controller bytes and increments a position word in its main
loop when a BIOS tick occurs while the key is held. Its RAM ledger and position
are independent of Python's input receipts. No host RAM edit creates readiness,
key consumption or the outcome.

Stop at its exported `ready` symbol. Obtain the physical state address from the
verified process mapping as `runtime_base + symbols['state'] - 0x100`. Bind 29
bytes using the explicit `MV01` byte witness and authored source hash.

| Offset from state | Field | Initial state | Successful single press |
| ---: | --- | --- | --- |
| 0..3 | Magic | `MV01` | Unchanged |
| 4..5 | Unsigned little-endian position | 0 | Greater than 0 |
| 6..7 | Guest tick count | 0 | Measured separately |
| 8 | Held key | 0 | 0 |
| 9 | Settled flag | 1 | Not an acceptance predicate |
| 10 | Make count | 0 | 1 |
| 11 | Break count | 0 | 1 |
| 12 | Recorded edge count | 0 | 2 |
| 13..14 | Actual scancodes | `0000` | `1e9e` |

The action declaration is exactly
`{"kind":"press","key":"a","modifiers":[],"hold_ms":80,"gap_ms":80}`.
The object also declares `guest_ms: 500`, `timeout_ms: 5000` and
`outcome_phase: "state"` as immutable caps. Initial readiness requires position
zero, no held key and no recorded edges.
The outcome requires the exact five-byte ledger `0101021e9e` at offset 10,
held zero and position greater than zero. The typed position comparison uses
the existing unsigned 16-bit RAM scalar grammar. Do not assume an exact number
of position increments: the BIOS timer phase is observed guest state.

The successful action polls its destination outcome independently of the old
readiness predicate. Once the guest changes position, the original readiness
can become false without invalidating a correctly observed outcome.

## Separate acceptance, completion and effect

The `fdisbull-scene-action-1` result retains its immutable `plan`, consumed
non-replaying `intention`, fresh `before` readiness, `input` and `effect`, and
the measured `action_wait` journal. It must preserve three distinct facts:

- An exact accepted native arm proves admission of the finite declared input
  plan on the selected owner. It does not prove a dispatched or consumed key.
- A complete native callback prefix proves delivery of the declared make and
  break edges. The release delay starts at actual make dispatch, not its nominal
  deadline. `gap_ms` is not an inferred executed tail timer.
- A fresh, bounded outcome observation proves only the declared RAM effect.
  The independent fixture additionally checks its actual `1e9e` consumption
  ledger and positive position.

Keep the underlying input receipt's `guest_consumed` and
`device_queue_accepted` unknown. Do not rewrite them from the fixture-specific
RAM oracle or equate input completion with a matched effect.

Pin the immutable action plan, selected scene/object revision and hashes,
source/version, run, original owner/process, runtime/capture epoch and fresh
readiness through dispatch and persistence. A saved declaration or observation
alone is not live execution authority. Whole-script preflight must reject an
unsupported known profile or invalid literal before an earlier step acts.

## Refusal and first-stop evidence

The passive refusal selects an explicitly false readiness predicate while the
guest is stopped and input is clear. Require no native keyboard arm, no GDB
execution, no guest-clock/counter change, no RAM mutation and no changed input
ownership. Retain the actual readiness observation and refused action result.

For interruption, use a fresh valid declaration and an execution breakpoint at
the guest's exported `irq_fence`. This fence follows the make counter and held
state stores. The first real breakpoint must win over another outcome poll.
Require one actual execution interval, one dispatched make, the original
pending break and owned hold, and the exact original stop receipt. The action
must neither release nor resume the guest or replay input. Its completion is
false and its unobserved effect remains unknown.

Only after proving no post-stop action poll may the caller separately inspect
the stopped guest's make counter and scancode. That caller observation is not
retroactively attached as an effect poll performed by the action. The normal
bounded context close ends this owner without a guest cleanup input sequence.

## Public routes and persisted evidence

Success executes `debug-script` through real JSON with a saved script ID. The
four script steps contain one `scene-act` and three result assertions. Capture
the real canonical action and script returns once with wrappers that preserve
and invoke the actual bound methods; do not replace behavior or execute again
for comparison. The script's retained action result and the full stored
observation must match that canonical result. Compare the complete exported
JSON response with the public projection of the complete canonical script
result, including nested process addresses. The reusable script declaration
and its route-copy artifact retain separate identities and exact hashes.

The interrupted action uses the real JSON route and checks the complete error
envelope. If output is spilled, export the existing artifact and compare the
whole envelope, its byte count and hash without another action or guest run.
Canonical Python/FDB/error receipts retain canonical address types; successful
JSON uses the existing full public address projection. Never drop nested
process fields or compare canonical integer addresses directly with the
hexadecimal public presentation.

The canonical observation stored in `debug_scene_observations` omits only the
returned top-level `observation` identifier; its public retrieval method
reattaches that exact identifier. The stored byte count must equal
`action_wait.evidence_bytes`. The stored script result similarly omits only its
returned top-level artifact identifier. Error output remains canonical and
retains the complete `SceneError.result`. An interrupted action has
`effect.matched: null`, `effect.observation: null` and no effect-only
`action_wait.polls`; its initial readiness remains in `before`.

Both cold Project reopens must retrieve exact historical canonical evidence
without creating live authority or an additional VM. The raw controller's
SQLite reader must distinguish inline values from external-object descriptors
and verify resolved bytes, sizes, hashes and private-store containment.

Observers retain original methods and actual returned receipts. Instrument the
guarded public method binding, including `MachineContext.keyboard_press`, rather
than a mixin function already captured by an alias. The controller and tests
must not inject an extra input, predicate read or guest interval to make their
evidence complete.

## Native inputs and finite bounds

Use the existing virtual-clock DOS lane: `FDISBULL_QEMU_CLOCK`,
`FDISBULL_QEMU_DOS_BOOT_IMAGE`, `FDISBULL_QEMU_DOS_MCOPY`, `NASM`, and explicit
firmware through `FDISBULL_QEMU_CLOCK_FIRMWARE` or
`FDISBULL_QEMU_DOS_FIRMWARE`. Set `FDISBULL_REQUIRE_QEMU_CLOCK=1`. Missing inputs
are an open gate, not a passing skip. Preserve the multicall `mcopy` invocation
name. Pin the compiler, pristine authored fixture and produced COM bytes.

The candidate sealed QEMU producer has SHA-256
`b82342e48ab014d6a0526675492d9b0bbfe6844d8eb8848570e93b961bbc589c`.
Use the full FreeDOS input with SHA-256
`552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc`, which
contains the configured command interpreter. The minimal root-shell image is
not interchangeable. Neither existing producer verification nor earlier scene
wait results count as execution of this gate.

The profile is one active DOS COM process, explicit virtual clock, standard
retrace, audio off and pipe transport, with no layers, hooks, selected task view
or file workspace. No QEMU rebuild or checkpoint tool is required by these
cases if the pinned producer exposes the existing required commands.

| Bound | Maximum |
| --- | --- |
| Selected cases / native owners | 2 / 2 |
| Cumulative case duration, including startup and cleanup | 60 host seconds: at most 50 work plus 10 cleanup |
| Startup allowance | 15 host seconds, intersected with the original case end |
| Individual action allowance | 5 host seconds, intersected with inherited bounds |
| Action guest allowance / polling slice | 500 ms / 25 ms |
| Shared phase, starting before common preparation | 150 host seconds |
| Outer supervisor, including termination and reap | 180 host seconds |
| Private working/evidence size | 128 MiB total |
| Native logs | Four complete logs, at most 2 MiB each |

One absolute action deadline covers readiness, arming, execution, observation
and publication. The initial execution interval may include the whole fixed
input span plus the poll tail; it still consumes the same total guest budget.
Clock progress is the difference between actual observed virtual nanoseconds.
Preserve any measured overshoot; do not import the exact timing from an earlier
fixture run. No inner operation receives a new full allowance after work has
already consumed part of the inherited deadline.

The fixture's work end is fixed at its original start plus 50 seconds. Normal
owner cleanup, input-hash verification and offline cold reopen must finish by
that same original start plus 60 seconds; they do not start a new ten-second
allowance. The controller also enforces the case and shared outer limits.

Root's separately reviewed controller must enforce the shared limits, finite
subprocess preparation, exact owner count, bounded close/terminate/kill/reap,
complete capped logs and output membership. A limit crossing is a failed run,
never a successful truncated receipt. Record PID/start-time identities, source
and input preflight/postflight, both XML results, full raw native receipts,
canonical/public exports and cold FDB evidence. Private runtime inputs, raw
FDBs, external stores and logs stay outside Git.

This document does not admit execution. Root owns final source/host review,
native admission, deliberate execution and reconciliation. Host race/refusal
coverage remains required for owner/epoch/manifest replacement, deadline expiry,
consumed intention replay and uncertain native failures. This finite authored
gate does not qualify those adversarial cases merely because two ordinary
native owners finish cleanly.
