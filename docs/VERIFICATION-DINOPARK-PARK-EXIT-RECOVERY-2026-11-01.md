# Original park exit and read-only recovery — 2026-11-01

This fixes the park-to-street failure recorded in the
[visitor continuation](VERIFICATION-DINOPARK-VISITORS-2026-11-01.md).
Luna performed the bounded original-game trials; separate Luna reviews examined
the source, private fault binding and results. The parent independently checked
the retained input, native inventories, source pins, recovery counters and
committed scene ancestry. These are assisted, prepared-state tests rather than
a complete-playthrough or whole-binary claim.

Final production source is `5a54aafae02ceb3c9208ab7b15579ff37b7bbf92`.
The normal month-rollover control used its immediate predecessor,
`521077c31f2b640513a467e660a1dd8216cd8863`. F6 adds committed-host-scene
recovery handling; each trial retains its own as-launched source identity.
No package, installation, release or merge was performed.

## Problem and change

The original park-exit object inherited a 10-second scene host limit. Returning
to the street loads original MALL assets, and registered native observers can
consume substantial host time while little guest time passes. The earlier
failure queued a real press, then refused an observer prelude for insufficient
allowance. Its old provider did not recognize Park exit as a reconcilable route.

The fix:

- Gives `park.back` the same bounded 40-second scene allowance as business
  loading, with one shared outer deadline covering initial observation,
  pointer preparation, input and destination readback. The original control,
  pointer preparation and single click remain in order.
- Shares the park-exit implementation between the local text scene and Z.
  Navigation records the authoritative queued-input receipt even if scene
  observation raises; an earlier pointer-stage `not_sent` marker is not treated
  as a complete input history.
- Adds source-qualified read-only Park-to-Street reconciliation. It requires
  the original provider, session, run, Park revision, control, accepted queued
  input and before-observation, then qualifies the actual Street frame and
  dispatch selector. A wrong recovery ID cannot grant completion.
- Publishes fresh Street controls from the current selector. Composed business
  journeys retain their shared request deadline and use the newly published
  `text.street` revision for the next queued hop.
- Preserves a published Street revision when a later witness read fails.
  Before publishing again, it reads the actual committed head under the live
  byte version and verifies the scene root. This also handles publication
  committing before the publisher's return readback raises.

Read-only refers to the guest: reconciliation sends no execution, input or
restore. It may update host scene revisions, witnesses and recovery records.
Unqualified reads retain the original root and input, rather than authorizing
the navigation again.

## Normal original-game control: Native05 / F5

The normal trial recreated the known park through original controls, then used
the prepared three-advance baseline plus 32 additional intervals to cross the
first month. Pre-exit status was year/month indices 0/1, day/weekly counters
2/5; cash 6,442, loan 4,885, food 12, one guide, one Coelophysis and hunger zero.
It is a distinct park, not a restoration of Native04's RNG or machine state.

Public ticket **0153** completed Park-to-Street in **12.505 host seconds**, with
one accepted queued Park-exit press, a matched original scene result and a
canonical public Street witness. The parent verified its retained
`navigation_input_result`: control `park.back`, input state revision **7918**,
run `a65f3ef02408414aa29b56a60b54203a`.

Actual inventories **0152**, **0155** and **0157** verified all **97** unresolved
execution probes enabled with `once=False` at their correct runtime addresses.
Their queries had zero execution/input/input-read/restore deltas, including the
later held state.

The subsequent optional return, **0156 `go park`**, failed after 15.338 seconds
with shared host-budget admission expiry. Its return input was queued at state
revision **8888**; consumption, current view and effect remain unknown. Root
`78d0c249fdc3962b45062e652aac6f29` and its provider were retained without retry,
restore or another game action. That return path is a separate recorded issue;
it is not presented as a successful round trip or part of the completed exit.

## Final-source original-game recovery: Native06 / F6

Native06 used all twelve frozen F6 runtime pins and the same original executable
and backend. It performed the diagnostic on its first fresh Park exit, avoiding
the known return-path uncertainty. The private injector waited for the **full
real original scene action to return matched**, retained that actual receipt,
then withheld the host readback once. It changed no guest input, memory or
execution. It is explicitly a diagnostic injection, not a spontaneous failure.
The exit request took **12.346 host seconds**. Wrong-root reconciliation took
0.055 seconds, the first correct attempt 0.107 seconds, the successful retry
0.208 seconds and the idempotent call 0.007 seconds.

The injection is bound to the same new intent, pre-action Park context, source
scene/control, provider session, native PID/session/run and exact input/before
receipt. It does not accept an unrelated Office or DinoMart return as a normal
Park-exit prerequisite. The later witness fault uses immutable action/receipt
identity while allowing the real error handler to append diagnostic events.

| Step | Original-game result |
| --- | --- |
| Exit **0043** | Real original scene action matched first; original queued input state revision **7684** retained. Injected host readback failure produced an incomplete/unknown public result. |
| Wrong-root reconciliation **0045** | Refused completion, retained the actual root and did not consume the witness fault. |
| First correct reconciliation **0046** | Published Street, then encountered the once-only host witness fault. Original root and diagnostic were retained; no completion was claimed. |
| Second correct reconciliation **0048** | Published from the committed first Street head and returned a canonical Street witness for the original exit, with `applied-confirmed`, `read_only=true`, `action_sent=false`. |
| Reconciliation **0049** | Returned `not-needed`; the completed original navigation was not run again. |

The same root, `419c925d5d28bb54cd4bd8c8f1db3f68`, survived both incomplete
attempts. Wrong-root and both correct-root calls had **zero run, execution RPC,
input mutation, input-read and restore deltas**, unchanged native ownership and
unchanged original failure diagnostics. There is one retained navigation-input
result event, with the actual original input unchanged by the injection.

The parent independently verified the committed-host-scene edge: the successful
retry's parent is the Street revision published before the first witness fault.
This is a readback/retry test against original game state, not a model-simulated
navigation effect.
The publisher-commit/return-readback failure was separately covered by a host
regression; it was not additionally injected in the native trial.

Inventories **0040**, **0044**, **0047** and **0050** independently verify **97
actual enabled execution probes**, `once=False`, correct physical addresses and
zero query side effects before the fault, in both held states and after recovery.
No unresolved-entry probe fired. All 97 entries and 13 asset candidates remain
open; this task adds no unusedness claim.

Final checks verified controller **7234**, worker **7260** and native **7261**
alive with no active request or hold and a canonical Street witness; all twelve
loaded/as-launched F6 files match their frozen pins. All 192 canonical original
files were rehashed unchanged. Actual launch records confirm SDL dummy audio,
mixer `nosound=true` and MIDI `none`. Native04/05 protected evidence and original
holds remain unchanged. No further game requests were scheduled. The retained
F6 trace ends at sequence 5058; no cumulative coverage ledger was rebuilt.

## Library check and preserved evidence

The initial accessible Pages listing completed with zero Spaces and nine Pages;
that listing does not cover all uploaded Library files. A read-only Chrome
Library search found DinoPark E53/E54/E55 handoffs and reports, the behavioral
report and game-story map. Thus the earlier Pages-only view missed relevant
Library uploads.

Both user-provided archives are present. Their central directories and selected
text were read without bulk extraction:

| Archive | Bytes / entries | SHA-256 |
| --- | --- | --- |
| DinoPark-E55-UIL-Research-Handoff.zip | 3,760,109 / 296 | `e6f9da13a3ab1d1de485a496f5d807121bcd929ba67bd87256b449870aa718ea` |
| GOG-KQ1-PQ1-Zork-Recovered-Files.zip | 105,923,104 / 522 | `795c7600af1ab967657ebd49f8e8db839425e32eaef8210afd5cb49a17cfc316` |

The E55 source index identifies Guide 0.3 and E42 Library files. Their direct
Library views remained loading, so no live-content parity is claimed. The
available E55 `ABOUT-RUNTIME.md` and `GAME-STORY-MAP.md` were reviewed as bounded
research evidence. They distinguish dispatch, semantic effects, readiness,
rendering and persistence; their standalone ACT runtime is not a replacement
for this DOS original-game test. Newer recovered research also exists in main's
history rather than every older research ref. No game-containing archive or
raw library delivery was added to Git.

## Verification and storage

- **15 new park-exit test cases** and **73 affected checks** pass. The cases
  cover delayed loading with one press, wrong source/run/control/root/input,
  read-only qualification, repeated failed readback, post-publication witness
  failure and publisher-commit/return-readback failure.
- Full exact-F6 source suite: **2,235 passed, 133 skipped, 12 failed, 23 errors**,
  exit 1 in 51.90 seconds. The same 35 baseline failure/error IDs remain;
  none were added or removed. This is not a green full-suite or release claim.
- Source review findings on composed deadlines, stale Street aliases and
  committed-head retry were fixed and re-reviewed. The final private driver
  passed **77 host checks** and its error-to-hold path was independently reviewed.
  Host fixtures are separate from the original-game qualification above.
  The supporting receipt is private
  `park-exit-fix/private-harness-f6/HOST-PREFLIGHT.json`, retained as
  `parent/private-harness-f6/HOST-PREFLIGHT.json` in the selected snapshot.
- The user's bounded CACHE exception retains a 20 GB reserve. Fresh Native06
  admission initially refused to launch below that floor. Under AGENTS.md's
  verified-recovery relocation exception, three completed, unopened test-output
  trees were moved to CODEX: **984,729,760 regular-file bytes / 13,801 verified
  entries**. Every destination file hash/link was checked; original paths remain
  symlinks. No live runtime, active `tmp/native`, original game or sealed receipt
  was moved. CODEX remained above the 20 GB minimum. Fresh 512 MiB Native06
  admission then passed with 20,940,627,968 CACHE pool bytes available.

Native04's original unknown exit remains preserved: loaded providers have no
supported live-code reload or ownership transfer. Native05's later unknown
return is also preserved. Neither is claimed recovered by testing a new guest.
Private receipts are under
`/Volumes/CACHE/fDisBull-native-validation-20261101/park-exit-fix`; the library
scope record is in the parent `publication/LIBRARY-PARK-EXIT-CHECK.json`.
Raw original files, database contents and screenshots remain private.

The selected immutable snapshot contains **53 files / 34,358,310 bytes** at
`/Volumes/CACHE/fDisBull-native-validation-20261101/park-exit-fix/verified-receipts-20261101/EVIDENCE-MANIFEST.json`,
SHA-256 `1f6d86562602da5993fe5cd6355dae26cf2dfcc008389a0686a315bb44cc9a74`.
The parent verified all 29 selected owner-manifest members before copying them,
then verified each snapshot member against its source. The live roots are not
sealed, moved or closed.
