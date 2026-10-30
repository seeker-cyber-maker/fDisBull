# Z batch recovery and action continuation verification

The later [funded26k/native-provider recovery acceptance](VERIFICATION-FUNDED26K-RECOVERY-2026-10-30.md)
resolves the exercised older-seed return and tests a recovery-only provider.
The earlier outcomes below remain preserved under their original runtime.

Runtime candidate: `381fb93e1dd24b73357aebaf4f566ae4d2c2716e`, core/player
0.24.0 private branch packages. See [the public interface and recovery limits](Z_BATCH_RECOVERY.md).
This follows the [earlier DinoPark continuation record](VERIFICATION-DINOPARK-Z-CONTINUATION-2026-10-29.md);
its prior outcomes remain separate and unchanged.

## Implemented contract

- A fixed public command plan has durable per-step attempts, effect results,
  explicit pause reasons and opaque provider-session identity. Dispatch is
  journaled before execution; a returned effect is journaled before subsequent
  observation. A recovered `running` marker is unknown, never implicitly pending.
- Pending steps can run without replaying completed steps. Accepted partial
  actions require an explicitly declared continuation in a freshly qualified
  public context. The same continuation command runs at most once per step.
  Destination mismatch remains distinct from a notice requiring acknowledgment.
- Explicit named checkpoint recovery verifies the provider, original native
  values and scene before creating a new branch. Superseded attempts remain in
  history. Uncertainty, foreign sessions and incomplete recovery block dispatch.
- Park/quarter and food-advice acknowledgments share a one-shot original-input
  and bounded destination-observation implementation. Input queueing, arrival
  and independently confirmed effect are separate records. Waiting never sends
  another input or renews an exhausted observation budget.
- DinoPark restore compares all 20 saved native ranges before input-free frame
  preparation, requalifies the original scene and invalidates old action tokens.
  Checkpoint witnesses are flushed to the private service receipt before the
  checkpoint response. Mounted-file compatibility remains enforced by the native
  state loader; live memory snapshots do not undo disk effects.

## Artifact binding

| Artifact | SHA-256 |
|---|---|
| Core wheel | `6cd9885dd03b95e1d542773481abe189d267e9f9f6684c394c9719f574986dc3` |
| Player wheel | `196256fbe5af2e642047fba9520b9d2f583edf8087c262a5286f0ccad6aa5173` |

The candidate manifest binds 150 payloads to committed source and both wheels.
Candidate 3 changes only `fdisbull/dinopark_z.py` and
`fdisbull_player/batch.py` from Candidate 2. The shared native action code and
recognition profiles are unchanged across those candidates.

## Original-game acceptance

Luna's final installed-Candidate-3 run used the exact verified C10 `zpark`
native backup, SHA `f661ecac96ae84803af19901def0669d8032ecb8b2b12814ca4832dcf78f576e`.
It reused the previously isolated C3 environment read-only, rechecking all 150
payloads, import paths and dependency identities before/after the run. The genuine
native backend remains the retained 0.22 prefix, SHA
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.

| Requirement | Original-game observation | Result |
|---|---|---|
| Shared action continuation | The earlier installed C3 run encountered a natural quarter on park entry; one original acknowledgment traversed shared continuation stages through qualified arrival/effect. Its completed journal reopened without dispatch. The final zpark run entered without that notice; none was fabricated. | Confirmed for observed notice/route |
| Lost purchase reply | One original food order committed; a transparent client wrapper discarded its successful response. Both run and resume left provider-action counts at 5. | Unknown step retained; no replay |
| Failed following observation | A second order returned applied-confirmed, then the client wrapper failed its next read. The journal kept that returned effect; run/resume left action counts at 6. | Confirmed effect retained; no replay |
| Explicit live recovery | Both discarded branches were followed by explicit recovery. Each immediate on-disk receipt contains all 20 saved/restored ranges equal, Dino Diner requalified, no following input and 100 ms input-free frame preparation. | Two certified recoveries |
| New retained branch | After the second rewind, one normal original order completed. Superseded attempts remained in history. | Confirmed |
| Native save and named load | Public save produced zpark-002, native SHA `532a6f0a47843668a394e4beefe34dcdc3189e12c44e90063f1eb2eba1d7cf2d`; public load zpark-002 started the second guest with a verified session handoff. Save/live and fresh-load readbacks matched all 20 ranges. Reopening the load journal did not resend load. | Confirmed |
| Lifecycle and preservation | Both original guests and the worker exited zero; native/service receipts completed and cleanup found no owned survivor. The canonical game and exact seed remained unchanged. Actual argv/environment/logs confirmed SDL dummy, mixer silence and MIDI none. | Confirmed |

The two client faults were deliberate test injections while the native guest
remained alive. They are not original-game crashes or proof of recovery from a
dead provider. The original engine performed each purchase and both restores.

Protected original commit values were:

| Branch | Cash before -> after | Small feeders before -> after | Confirmation inputs |
|---|---|---|---|
| Discarded reply | 28,914 -> 28,414 | 17 -> 37 | 1 |
| Discarded following read | 29,054 -> 28,554 | 17 -> 37 | 1 |
| Final retained branch | 29,054 -> 28,554 | 17 -> 37 | 1 |

Each has a 500 expense increase and unchanged protected calendar. Whole-command
cash endpoints also include original running-park income. All three attempts
encountered and handled original parking advice during food preparation; this
qualifies the observed advisory path, not every possible reconciliation case.
The final saved/loaded park has cash 28,784, loan 4,167, 37 small feeders, one
guide, one Coelophysis and hunger zero. The discarded purchases are separate
rewound branches, not three purchases in the retained park.

Accounting is **12 player command attempts**, comprising ten current-journal
attempts and two superseded ones. There were eleven provider act requests; look
was passive. The verifier's initial ten-attempt summary omitted superseded
branches; an offline reconciliation corrects it. Current and archived copies of
the same history must not be counted twice. These are warm verification runs,
not model rankings.

## Reproductions and corrected friction

1. Candidate 1's verifier expected the diner after a successful food order; the
   original returned to the street. The confirmed purchase stayed recorded and
   the declared destination goal paused the batch. The verifier also inspected
   a protocol envelope where the Python API supplies a flat action, preventing
   its planned reply-drop injection. Both verifier mistakes are preserved.
   The product now reports `destination-mismatch` separately from
   `continuation-required`.
2. Candidate 2, using the older funded26k seed, executed the original purchase, deliberately discarded its
   returned reply, blocked run/resume replays and returned from explicit live
   recovery to a usable diner. Its verifier stopped because the checkpoint
   witness was not yet on disk. The service held that event in memory until
   another receipt or shutdown. Candidate 3 flushes checkpoint save/restore/
   failure evidence before responding. The original restore is separate from
   that evidence-publication defect.
3. A focused regression demonstrated that a confirmed action response could be
   lost from the batch journal when its following observation raised EOFError:
   the old code failed with `KeyError: result`. Candidate 3 persists the returned
   effect before that read. The step remains unknown while its confirmed effect
   is retained; resume sends no repeat action.
4. The standalone-player distribution allowlist and three archive/offline test
   fixtures required the new `batch.py` module. All were updated, including a
   missing-batch-module rejection check. Earlier intermediate packaging failures
   are retained separately from the final results.
5. A private verifier's indefinite hold loop had no supported continuation
   control. Verification drivers should retain a bounded command/control path
   or finalize owned receipts at a stop. The public batch CLI offers bounded
   run/resume/checkpoint/recover/inspect operations; it does not require that
   private hold-loop design.
6. A verifier treated the public checkpoint label as its opaque provider handle.
   The private journal contains their mapping; the corrected selector was tested
   offline against real earlier evidence before the final launch. A future
   receipt API should expose explicit correlation references so verification
   does not need to discover that mapping in a private journal.
7. An additional run used the older funded26k native backup
   (`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`),
   going directly to the diner. Its original purchase committed 500/20 once,
   but thirteen later street-view observations did not qualify. The provider
   exited with a failed/incomplete action; DOSBox itself exited zero. The batch
   retained applied-confirmed and sent no repeat purchase. **This older-seed
   return-view failure remains open.** A future recovery-only provider state
   could retain the paused guest for explicit rewind after such a failure.
   The final test used the exact qualified zpark backup; the older failure was
   preserved and is not promoted to success.

## Source checks and boundaries

Focused recovery, continuation, player, original-backed bridge, distribution and
offline-kit checks: **155 passed**. The new lost-following-observation regression
was observed failing before the fix. Native-checkpoint boundary checks cover
durable witnesses, input-free frame preparation and mismatch refusal.

Required `python -m pytest -q`: **1,597 passed, 118 skipped, 13 failed,
23 errors**. All 36 failure/error identities match the recorded fresh 0.24 main
baseline; no new identities were added. The local full suite remains red.
Remote CI is reported against its actual head rather than inferred from this
baseline comparison.

The same 155 focused checks also pass from the extracted source distribution.
All four final distribution forms pass tool-only archive policy: core wheel
149 entries, player wheel 11, source tarball 483 and tool ZIP 475. Source and
distribution runtime payloads equal the accepted candidate; later documentation
edits do not change accepted runtime bytes.

Private evidence is under `Conversions/DinoParkTycoon/dinopark-z-batch-recovery-20261029-01`
and the separate Luna candidate directories. No game executables, resources,
native saves, databases or private screenshots are included in the PR. Original
game effects still run through the original-backed DOS UDC with
`original_bytes_only` qualification and zero recovered semantic blocks.

Live checkpoints require a surviving native guest and unchanged mounted files;
native park saves remain the durable resumption mechanism. Preparation advances
original simulation time. This is bounded harness verification, not whole-game
equivalence or a cold model benchmark.
