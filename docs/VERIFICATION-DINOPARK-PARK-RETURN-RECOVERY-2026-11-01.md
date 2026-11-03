# Original park return and read-only recovery — 2026-11-01

This follows the separate return failure recorded in the
[park-exit verification](VERIFICATION-DINOPARK-PARK-EXIT-RECOVERY-2026-11-01.md).
The final source candidate is `64d879535fd85651bf634b1bc9e137f36763ca42`.
The initial implementation `aba00c2ad0111ca0b0441d976181c3bbe7f73d83` and GitLab
source delivery `ce47db66126d20ad21268559c773460ea9244a9f` have identical trees.
The final candidate also supports first Park-scene publication after loading a
native save into a new project. Luna qualified normal return and repeated read-only recovery against the original
game in the separate, source-bound prepared-state Native08 case. Host results
alone do not establish the native gate.

## Failure and fix

Native05 ticket 0156 queued the original return press at state revision 8888,
then failed after 15.338 host seconds with
`Shared debugger host-time budget expired before RPC dispatch`.
Its root `78d0c249fdc3962b45062e652aac6f29` remains unknown and preserved.
The return macro used an 8,000 guest millisecond interval under the generic
15-second run allowance and retained no navigation-specific reconciliation
receipt. Instrumented asset loading can use substantial host time while little
guest time passes.

The fix preserves the original point (201,187), 80 ms hold and continuous
8,000 guest millisecond interval. A shared 40-second host deadline begins before
Z observation, covers the local preparation and readback, and intersects all
nested deadlines. The run no longer creates an earlier 15-second deadline.
The actual queued-input ticket is retained before waiting, with the original
run, Street revision, before-observation and host control identity
`street.park`. This labels the original toolbar macro; it does not claim that
the macro was a native `SceneHandle.act` operation.

The receipt is incomplete on an execution/readback error and matched only after
a unique original Park destination is qualified. It survives later status or
public-witness failure. Existing quarter notices and parking advice remain
explicit partial continuations, without another entry press.

Read-only reconciliation requires the same provider/session/run, original
navigation/action, source revision, before-observation and accepted queued
input. It captures a frame with observation hooks disabled, requires the Park
profile, excludes the two recognized notices and reads the current selector.
It publishes a fresh host Park revision from the actual committed named head,
checking the original scene root and live byte version. A publication/readback
failure can be retried without a stale-parent fork. Native save loading restores qualifications into a fresh project without a prior
Park scene ID. The first qualified return can create that scene; a failed first
publication can follow its already committed named head on retry. Two new cases
failed before this compatibility correction and pass afterward. The operation
sends no guest execution, input or restore.

## Host validation

Independent Luna source review found no material issues in the exact production
diff or the additional plain-timeout integration check. It performed no native
calls and adds no original-game qualification.

- The first new regression run had 11 failures and 7 passes before the fix.
- All 21 new cases pass. They cover original queued-input retention, bounded
  loading, source/run/control/session/input/root guards, read-only qualification,
  committed-head retry, post-publication witness failure, idempotence and both
  recognized notice continuations.
- All 134 affected checks pass, including the prior park-exit, navigation,
  employment, preparation and continuation tests.
- The first full run exposed two notice-continuation regressions caused by
  enrolling `go park` in navigation recovery. The final guard preserves the
  prior recognized partial-notice contract; those checks pass again.
- Final full candidate suite: **2,256 passed, 133 skipped, 12 failed, 23 errors**,
  exit 1 in 51.71 seconds. The same 35 baseline failure/error IDs remain, with
  none added or removed. This is not a green full-suite or release claim.

Private test logs and the baseline comparison receipt are in
`/Volumes/CACHE/fDisBull-native-validation-20261101/park-return-fix`.
No package, installation, release or merge is part of this change.

## Private validation harness findings

Independent Luna review held the native launch for two private harness fixes.
The batch previously checked counter/ownership/diagnostic invariants only after
several reconciliation requests. It now checks every individual response before
issuing another request, including wrong-root refusal. The guard requires zero
run, execution-RPC, input, input-read and restore deltas; stable ownership and
diagnostics; consistent provider/controller roots; and unchanged held intent
after an incomplete read. Twenty-two generated host guard cases pass. They
exercise the AST-extracted guard without operating a guest.

The review also required the controller to check the Park destination and the
confirmed original effect before clearing its hold, rather than accepting any
nonempty witness context or `none-confirmed`. The corrected controller also checks zero input reads and agreement between the
provider and public effect/recovery fields before clearing the hold. Independent
review closed all findings before native launch; the final private preflight
has 60 passing host checks, with all 16 harness files hash-verified.

The initial 45 private preflight checks cover hook orchestration against host
fixtures, including a stub reconciliation service and Park qualifier. They do
not independently exercise production reconciliation or real Park publication;
those claims require the separate original-game receipts. The production host
regressions above are a distinct evidence surface.

## Original-game qualification: Native08

The fresh-setup Native07 case stopped during a separate Coelophysis presentation
problem before reaching the Park test. The original purchase is confirmed, with
its proof retained; root `17c366b9e6a22d5ac592122a24f84c8a` remains held. A
read-only comparison of the last retained frame found 19 of 26 anchors matching
the original `after` profile, below its required 25. That check precedes pointer
state reads and scene publication. No predicate was relaxed, purchase repeated,
or old provider patched. The exact rendering cause remains open. This is new
setup friction, not a Park-return result or evidence of an unused asset.

For the target test, a distinct guest used the supported native-save load path.
The selected bundle was previously qualified by an original save/load test; its
`DINOSG.000` SHA-256 is
`7d4cc0dcdb1689540fbfbb0f4834a927a8b75efc1ddf565db9c2e65c6254fd3d`.
The current reader accepted all 184 original resource hashes, including the i64
resource. The original engine then loaded all 20 recorded fields exactly before
ordinary movement. That state has $3,224 cash, a $5,000 loan, one guide, 19 food
units and one dinosaur in pen 10. It is a native disk load into a new guest,
not recovery of Native07 or equality with an older guest's RAM/PC/RNG.

The loaded case starts with no host Park scene ID. Its first successful normal
return therefore also exercises the new first-scene branch against the original
game. The guarded initial Office-to-Street trip precedes probe installation;
all 97 probes are installed and checked before the first target return. Bootstrap,
load and that initial trip are outside this case's 97-probe coverage. The final
loaded-harness preflight has 68 passing host checks; the reviewed return fault,
certificate and immediate-counter guards are retained.

| Step | Original-game result | Provider dispatch-to-return time |
| --- | --- | ---: |
| Normal return **0017** | Canonical Park witness, one accepted original queued press at revision **292**. | **17.980 s** |
| Second return **0024** | Full real `revisit_park` returned first. One host-only readback fault then caused an incomplete public result while preserving its matched receipt and confirmed effect; queued revision **2790**. | **17.253 s** |
| Wrong-root read **0026** | Refused completion; retained the actual root and did not consume the witness fault. | **0.0039 s** |
| First correct read **0027** | Real Park publication followed by the planned once-only witness failure; root and diagnostic retained. | **0.0357 s** |
| Correct retry **0029** | Canonical Park witness, `applied-confirmed`, `read_only=true`, `action_sent=false`, same original action/root. | **0.0513 s** |
| Idempotent read **0030** | `not-needed`, `none-confirmed`; no action replay. | **0.0024 s** |

The original root is `133b81d43cd28bdd95992013c3884213`, run
`77bc39defeb94e25b006aaa1ee09aa30`. Both normal and injected-fault calls exceed
the old 15-second helper allowance but complete under the new bounded deadline.
The complete finite native batch took 57.872 host seconds after harness launch;
that excludes source development, host preflight and review time.

The parent independently checked all four reconciliation receipts. Every call
has zero run, execution-RPC, input, input-read and restore deltas; identical native
ownership before/after; and unchanged original diagnostic hashes. The input ticket
and original navigation receipt are preserved, with exactly one navigation-result
event for that held return. The injected fault does not fabricate an unknown
effect: the real matched return remains `applied-confirmed` while public completion
is held for a fresh witness.

The parent also queried the actual project database read-only. The successful
retry's Park revision `6b649c1e539b4bb4ba5ffce785f21ab3` extends the revision
`ff0d81a58ee845e0bff4ce62a60fb644` published before the first witness failure,
under the same Park root. The publisher-commit/return-readback failure is covered
by host regressions; that additional edge was not injected in the native case.

Actual inventories **0015, 0016, 0021, 0025, 0028 and 0031** contain all **97**
enabled execution probes with `once=False`, before the normal/faulted returns,
while held and after recovery. Their queries have zero execution/input/restore
deltas. The parent checked every physical target against the previous authoritative
97-entry list and this run's actual load segment `0824`, relative to static `1000`.
No unresolved-entry probe fired. All 97 entries and 13 asset candidates remain
open; no cumulative coverage ledger was rebuilt.

The current controller/worker/native processes are **95357 / 95403 / 95412**.
The final public scene is Park with no hold or pending request. Actual launch
records show SDL dummy audio, mixer `nosound=true` and MIDI `mididevice=none`.
All twelve current runtime files match the final source freeze. Final owner
immutability/liveness receipts and the selected evidence manifest are retained
privately with the case.

Owner closeout at **2026-11-01 21:10:36 UTC** rehashed all **192 original files**,
**184 prepared resources**, the original/private save pair, twelve as-launched
runtime/data files and sixteen private harness files without a content change.
The older owners remained alive, their held roots/known-idle context were
unchanged, and all 17 specifically protected Native04 files still matched.
The last retained trace sequence is 2431. No further guest actions, probe queries,
replay, restore, close, package or installation followed the acceptance batch.

The parent verified all 37 owner-selected artifact hashes, then retained a
separate immutable copy of **60 files / 2,661,238 bytes**, including the final
test logs, independent audit, source reviews, six actual inventories and the
Native07 presentation checkpoint. Its manifest is
`/Volumes/CACHE/fDisBull-native-validation-20261101/park-return-fix/verified-receipts-20261101-park-return/EVIDENCE-MANIFEST.json`,
SHA-256 `9d4e96a028798cf061d25cd71c26da211670474e6b1c8f86a92999db072047e0`.
The snapshot contains no databases, images, original game files or distribution
package. Live roots remain writable in place; their providers remain retained.
The latest user instruction to disregard space warnings superseded the earlier
reserve stop for this bounded task. Outputs stayed in the authorized CACHE
workspace, without moving or deleting older work.

Native04's unknown exit, Native05's unknown return, Native06's qualified Street
context and Native07's held purchase remain separate, retained contexts. The new
case does not hot-reload or rebind them, replay their inputs or claim them recovered.
