# One-resume QEMU DOS return witness

## Status and purpose

This is source-only snapshot-retention revision 02, prepared against
`f69a946110fce16bdd3f5d00daf7ad561b374783`. It is not an execution receipt or
permission to start QEMU. The revised test remains staged outside the main
checkout until root integrates the reviewed source at a new clean commit.
Production behavior remains the separately reviewed
`86a5fdb49d17452f9eda8af9380897f4a92ea7cc` implementation.

The question is whether the public asynchronous `resume` route can observe the
selected DOS child's actual return without injecting a GDB stop packet, issuing
an extra continue, or treating a stopped program counter as sufficient evidence.
This is a separate question from the busy-loop strict-pause experiment. Neither
experiment can qualify the other.

The intended node is
`tests/test_qemu_dos_async_return_native.py::test_native_one_resume_observes_verified_dos_exit42`.
It requires the independently admitted controller plugin, serial pytest with
`-x`, and the exact reviewed integrated source. A normal test invocation skips
the native node unless the explicit environment flag is present; supplying that
flag without the original-owner plugin fails admission. Controller reconciliation
rejects skips, missing nodes, native failures and partial receipts.

## Snapshot-retention revision 02

Native attempt 01 remains a failed gate. Its original test body recorded exit42
from one public resume and one status poll, and the original QEMU owner exited
zero and was reaped. Independent reconciliation then rejected the receipt with
`Entry/resume/status evidence differs from original public dispatch replies`.
The final failed phase SHA-256 is
`01cdaf9854a5e3223815723151919be35e783736112c3394d85da9966c4d5d24`.
Body observations and clean cleanup do not promote that whole gate to a pass.

The source cause is a retained mutable reference in the witness. The ordinary
machine session returns `mapping=self.metadata`; subsequent process return and
close update that metadata's process field. The logger already deep-copies each
public dispatch reply immediately. Its public tracing wrapper, however, returned
the original value to the campaign, which stored it as entry, resume and poll
observations. Those separate structures could therefore change afterward.
Read-only comparison of the original receipt found seven changed fields in
both entry and resume and two in the single poll, all below `.mapping.process`.
Entry register and source-byte observations were unaffected.

The revised test changes exactly one line in the public `_trace.call` wrapper:
return `deepcopy(value)` after its existing owner/deadline check. This creates
an independent snapshot for the campaign at the same public-return boundary.
The immediate raw journal snapshots, native wrappers and all actual API/native
operations remain unchanged. No assertion is removed, no comparison is relaxed,
and no old receipt is edited or reconstructed.

The complete original transport validator, worker, owner and cleanup helpers
remain byte-identical to controller 01. All owner counts, public calls, status
polls, waits, deadlines, receipt/log/call caps, total output cap and reserve are
unchanged. The new controller 02 and output attempt 02 require their own clean
integrated host, exact freeze, check-only phase and separate root admission.
Original source, plans, raw capture, native-call ledger, logs, failure receipts
and provenance are retained and pinned as failed-attempt history.

## Authored child and retained producer

The entire child is the literal five-byte COM `b8 2a 4c cd 21`:

```asm
mov ax, 4c2ah
int 21h
```

It requests normal DOS termination with exit code 42. This interpretation comes
from the authored bytes. The runtime stop does not claim that QMP or GDB reported
the causing instruction.

| Input | Exact identity |
| --- | --- |
| COM bytes | `b82a4ccd21` |
| COM SHA-256 | `ef892afebf7fabb6142f6f024536a9c51bc48f3b2158a060c7ba1eae0dcaa956` |
| QEMU SHA-256 | `b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af` |
| qemu-img SHA-256 | `b8687f147c9ac6900e840619196abdec4d5f4890d94be6876eae0c9e09985f03` |
| Retained FreeDOS boot SHA-256 | `552f7cbb0625960c050a3e682a4d2121cc2ffdfa9dc9d592ccd49edf179333dc` |

The fixture writes these bytes directly. It performs no assembly, producer
build, download, dependency installation or new sandbox creation. It reuses the
retained QEMU prefix, qemu-img, firmware, FreeDOS input and mcopy. A private boot
copy and project are prepared inside the bounded original owner context. Both
the retained boot image and the prepared baseline must remain unchanged.

The selected QEMU profile is one 486 CPU, 32 MiB, floppy boot, pipe transport,
virtual clock, precise retrace and audio off. There is exactly one original QEMU
process and no DOSBox launch. The retained conservative interpreter/tool/library
closure still contains the earlier paired runtime's members; retaining those
inputs does not authorize running its other producer.

## Operation sequence

1. Construct the ordinary DOS process session and reach its real stopped COM
   entry. Constructor boot and entry work belongs to the original deadline and
   native-call ledger. The one-resume restriction applies to the subsequent
   experiment, not to the documented constructor's work needed to reach entry.
2. Make exactly three public reference observations: `status`, `registers`, and
   a physical five-byte `memory` read at `CS * 16 + 0x100`. Require real mode,
   `IP=0x100`, active process state, a live source mapping, and exact COM bytes.
3. Retain the actual nonce-bound READY report, authored loader bytes and hash,
   launch epoch, child and helper PSPs, and the exact private return-breakpoint
   record. The helper must be the loader for `A:\EXIT42.COM` with an empty tail.
   The only admitted breakpoint is the original private parent-return point.
4. Call public `resume` exactly once. The resume result may already be terminal.
   If it reports running, wait at most 5 ms on the host and call public `status`.
   Repeat only while the preceding reply says running, for at most 32 status
   polls under the same original endpoint. Each wait is requested as 5 ms;
   scheduler delay remains inside the fixed owner deadline and is recorded.
5. Stop polling at the first nonrunning reply. It must report an actual stopped
   machine and a fully qualified `process_stop` for exit 42. Any unrelated stop,
   missing qualification, error, exhausted poll cap or deadline fails this
   attempt. There is no pause, step, second continue, settling operation,
   replacement owner or retry.
6. After that terminal public reply, read only the host project database twice
   to check stable persisted process state and exactly one return event. No
   further public status, guest clock, register or memory read is introduced.
   Then close and reap the original owner and retain its complete logs.

The pre-dispatch controller guard permits only the required post-entry QMP
status/register observations, GDB register/physical-memory reads, and the exact
private breakpoint removal. Its sole QMP continue permission is consumed before
dispatch, so an uncertain response cannot authorize a replay. All native errors
remain sticky, even if a caller catches the exception.

## Return oracle

A parent-helper PC match is necessary context, but is not the return oracle.
The production observer must return the actual 96-byte helper report read from
guest memory and the independently received 96-byte UART record. The test wraps
the original read and receive methods to retain their actual replies; it neither
replaces the serial channel nor supplies a synthetic report.

Success requires all of the following:

- Memory and UART records are byte-identical, framed as the version-one `FDBP`
  TERMINATED report, and contain the original 16-byte launch nonce.
- Helper segment, helper PSP, child PSP, original entry and stack information,
  helper layout, and launch identity remain consistent with the actual READY
  record. For this literal child, READY and TERMINATED bytes differ only in the
  record kind and the DOS return-status word.
- The DOS return status is exactly `0x002a`: normal termination, code 42 and
  nonresident. The returned process is exited and carries the original child
  and parent PSPs.
- Actual returned registers place the machine in real mode at the original
  helper's post-return park address. `process_stop.outcome` and the session stop
  reason are `guest_exit` with the same termination evidence.
- The selected source lifetime is invalidated, its live ranges are empty, its
  epoch changes, and the original private control is absent. The one actual GDB
  removal request for that exact point must receive `OK`.
- The native machine stop retains the actual QMP state while its GDB reply is
  absent, breakpoint IDs are empty, and native classification remains
  incomplete. No `T05`, breakpoint attribution or causing instruction is
  fabricated.
- The host FDB stores the same exited process and exactly one
  `dos-process-return` event, with equal repeated passive observations before
  cleanup.

The raw receipt records the three entry replies, resume reply, every status
reply, every post-entry QMP/GDB transport reply, the actual helper memory and
UART bytes, host wait timestamps, process/epoch/control disposition, and the
passive persistence observations. The external owner ledger independently
captures constructor and transport activity and guards the original process.
An ordinary stopped QMP state without the helper evidence is a failure.

### Binding the return to original transport replies

The independent host validator reads the original controller's
native-calls.jsonl as well as the test receipt. It pairs every attempt and
result by a stable call ID, original PID, lifetime, phase and timestamp, including
nested constructor calls. It then requires a one-to-one ordered match between
all post-entry QMP/GDB rows in the two journals: method, arguments, raw reply and
enclosing public-call interval must agree. Constructor and cleanup records
remain retained, but cannot supply post-resume stopped-state evidence.

For each public resume/status result, the validator identifies the actual
post-continue QMP query within that public call and compares its raw running
state with the result. The terminal call must contain the first stopped
observation after the sole continue. Its subsequent GDB g reply and HMP
info-registers reply must also be inside that same terminal call.

The validator reconstructs the GDB register layout from the constructor's
already recorded qXfer:features:read replies for target.xml and
i386-64bit.xml. It decodes the actual register packet without using production
register dictionaries or the production register parser as an oracle. The
actual HMP text supplies CR0, CS selector, hidden CS base and EIP/RIP. These
observations must agree on real mode and the original helper's return address;
the public register map and derived PC must match them. The resulting receipt
retains journal indices and XML hashes identifying this evidence.

Both lifetime finalization and outer reconciliation perform that pure host
comparison. Helper memory/serial wrapper rows may legitimately contain nested
GDB rows; the validator does not mistake those nested intervals for overlapping
transport calls. The earlier transport-binding correction left the test and guest-call sequence
byte-identical; snapshot revision 02 preserves that same guest-call sequence. No extra native query, wait or execution is
introduced.

## Finite bounds and ownership

| Bound | Limit |
| --- | --- |
| Test cases / original QEMU owners / maximum simultaneous owners | 1 / 1 / 1 |
| Original owner work / cleanup | 45 s / 10 s |
| Whole case, including fixtures | 60 s |
| Worker work allowance | 70 s |
| Whole controller aggregate | 180 s |
| Preflight / postflight / final receipt reserves | 45 s / 40 s / 5 s |
| Worker TERM / KILL / adopted-child cleanup | 10 s / 5 s / 5 s |
| Initial QEMU startup | At most 15,000 ms and original remaining time |
| Public experiment calls | 36: three entry reads, one resume, at most 32 status polls |
| Post-entry witness native records | 1,024, including helper observation wrappers |
| Full original owner native calls | 8,192 |
| Per native log / worker log / case ledger | 2 MiB / 16 MiB / 16 MiB |
| Native receipt / whole output | 4 MiB / 128 MiB |
| Additional destination free-space reserve | 256 MiB |

The work endpoint is created once by the journal before fixture preparation and
preserved by the controller. Native timeouts intersect that endpoint. Cleanup
has its own fixed bounded tail and permits no guest execution. The external
worker retains its original Popen, PID/start identity, process group, session,
pidfd, executable image, command line and executable mappings. Full log copies
must agree with retained original file descriptors after zero-exit reap.
Adopted-child or fallback cleanup is failure evidence, not success recovery.

The destination is the fresh private path
`/var/fdbg-cbd38/fdisbull-qemu-async-return-native-20261121-attempt-02`.
Before admission, `/tmp` was rejected for insufficient free space, the proposed
`/workspace/fdisbull-private-gates-20261121-cbd38b3ee98d` parent was rejected for
Git ancestry, and `/var/tmp` resolved to the full `/tmp` filesystem. The selected
`/var/fdbg-cbd38` parent must be checked again for writability, no links, no Git
ancestor, exclusion from all inputs, and at least the complete output cap plus
reserve. No previous evidence is deleted or moved.

## Source and runtime admission

Controller 02 derives from the frozen failed controller 01. Its execution,
owner and complete independent transport/evidence validator modules are unchanged.
The original worker, child and full-log helpers still retain their accepted
`controller-consumers-02` bytes. The exact 212-member potential ELF closure from
`controller-loader-02/elf-closure.proposed.json`, all 55 loader metadata records,
ten optional-loader absent paths and explicit preload absence are inherited
unchanged from attempt 01. Full current source/test trees, interpreter/tool
trees, accepted producer records and executable mappings remain subject to the
same preflight and postflight checks.

The earlier source proposal contained the historical 209-member graph. Root
subsequently reviewed its extension after the retained DOSBox/libudev failure;
that history does not authorize any new producer or reinterpret prior failures.
The current source revision's runtime metadata is incomplete and unadmitted
until root integrates it at a new clean host. It must preserve the exact inherited
212-member graph and all optional search/preload checks during that completion.

Root must first integrate the test and this document byte-identically, record a
clean exact host commit, review the source and runtime graph, and admit a fresh
plan after the finite metadata and check-only phases. The unadmitted source
proposal has no automatic next phase. A native failure exhausts its attempt;
any correction requires a new reviewed attempt with retained earlier evidence.

Before the transport-binding correction, the staged/controller source bytes and
hashes were preserved in async-return-source-01/pre-independence-01.
The controller's correction-provenance.json records the independent review
finding and the exact pre-correction identities. Those source snapshots are
historical, unadmitted inputs, not native evidence.

## Scope of a future pass

A pass would establish one native child return after one public asynchronous
resume on this exact retained QEMU, boot image and authored five-byte program.
It would show that the returned process evidence, source invalidation, private
control retirement and passive persistence agree for that one original owner.
It would not establish strict-pause stability, arbitrary DOS process behavior,
indefinite liveness, GDB stop-packet availability, hosted CI, image parity, or
game behavior. Until the separate admitted run completes, all such runtime
observations remain pending.
