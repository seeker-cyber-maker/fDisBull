# One-resume QEMU DOS return witness

## Status and purpose

This is an authored source proposal for one finite native observation. It is not
an execution receipt or permission to start QEMU. The test is staged outside the
main checkout until the existing paired gates are complete and root integrates
the reviewed source. The production implementation reviewed for this proposal is
`86a5fdb49d17452f9eda8af9380897f4a92ea7cc`.

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
transport calls. The original test and guest-call sequence remain byte-identical
through this oracle correction. No extra native query, wait or execution is
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
`/var/fdbg-cbd38/fdisbull-qemu-async-return-native-20261121-attempt-01`.
Before admission, `/tmp` was rejected for insufficient free space, the proposed
`/workspace/fdisbull-private-gates-20261121-cbd38b3ee98d` parent was rejected for
Git ancestry, and `/var/tmp` resolved to the full `/tmp` filesystem. The selected
`/var/fdbg-cbd38` parent must be checked again for writability, no links, no Git
ancestor, exclusion from all inputs, and at least the complete output cap plus
reserve. No previous evidence is deleted or moved.

## Source and runtime admission

The new controller derives from `controller-pause-01`, retaining the original
worker, child and full-log helpers byte-for-byte from `controller-consumers-02`.
Its source proposal preserves the exact old 209-member ELF closure from
`controller-paired-01/elf-closure.proposed.json`, twelve loader metadata records,
five optional-loader absent paths and explicit preload absence. Full current
source/test trees, interpreter and tool trees, accepted producer records and
all executable mappings remain subject to preflight and postflight checks.

The paired strict-pause attempt subsequently discovered a late DOSBox
`libudev.so.1.7.10` mapping outside that old closure. This QEMU-only proposal does
not reinterpret or erase that failure. Its runtime metadata remains incomplete
and unadmitted. Root may adopt the separately reviewed closure extension before
freezing this attempt; it must update the exact proposal path, count, hash and
metadata consistently, then review the final frozen inputs. No launch is
authorized by retaining the old closure here.

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
