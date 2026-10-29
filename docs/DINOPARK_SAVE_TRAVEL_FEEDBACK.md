# DinoPark native persistence and menu travel: next-release feedback

Status: observed on published fDisBull 0.21.0, 29 October 2026. This is a
documentation PR for the engineer implementing the next release. It does not
change the engine or include licensed game resources, saves, native states,
private project databases, or screenshots. The playable adapter remains in the
user's active DinoPark research checkout.

The requested outcome is a running park that an agent can save, load in a fresh
original-game process, inspect, and continue operating. Every newly discovered
tool or generated-interface friction during this work belongs in this ledger,
with a reproduction, observed result, intended behavior, evidence, and a
testable follow-up. Add later findings to this PR; do not create a background
monitor or infer that a recorded request is already implemented.

## Pinned environment and evidence

- Released core: 0.21.0, source tag `a253600b94f7006f8962ada842eba699279fdbfe`.
- Native backend SHA-256:
  `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
- Original executable SHA-256:
  `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
- Original `VARS.DAT` SHA-256:
  `5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153`.
- Luna's independent native research, including `events.jsonl`,
  `load-events.jsonl`, `analysis.json`, `friction.md` and stored frames:
  `/Users/tiga/Conversions/DinoParkTycoon/save-load-luna-research-20261029-01`.
- Adapter exploratory runs: private sibling directories
  `save-load-main-20261029-01` and `save-load-main-20261029-02`.

These paths identify local evidence retained by the owner. They are not links
that a public CI runner can fetch. Public tests must use synthetic fixtures;
original-game acceptance requires the owner's matching game edition.

## F1: queued save input did not commit the name editor

Reproduce: Escape in the paused office; Save Game at `(217,121)`; edit the name
at `(85,58)`; click the visible OK at `(250,93)`; run 2,000 guest milliseconds.
Luna observed the edit dialog still visible and no `DINOSG.*` file. Enter once,
followed by 1,000 guest milliseconds, returned to the menu and wrote the file.
The adapter's first exploratory run independently stopped at the unmatched
postcondition, with no automatic replay.

Expected: a generated action distinguishes editing, committing a name, and
completing the disk write. Native queued delivery alone must not report a save.
This is an original UI/adapter qualification issue, not a demonstrated backend
regression.

Adapter mitigation: one qualified Enter submission, rendered menu readback,
exact native-file checks, and no retry after an uncertain result.

Next release: add a reusable text-editor/submit action with observed readiness
and an explicit disk postcondition. Test the consumed-click case, Enter once,
interruption after dispatch, and a failed write. Preserve partial results.

## F2: existing native saves can be replaced without visible confirmation

Reproduce: reopen Save Game, select the existing name at `(75,80)`, click OK,
and run 1,200 guest milliseconds. Luna observed return to the menu and changed
native bytes; no overwrite confirmation appeared in the sampled frame.

Expected: the agent knows whether an action creates or replaces persistent
state. The original UI does not supply sufficient overwrite protection here.

Adapter mitigation: unique native labels and immutable named export folders;
duplicate names are refused before navigation or guest input. Earlier native
bytes are retained. No host-side file rewriting or normalization occurs.

Next release: make create/replace policy explicit in persistence actions and
surface a collision as a no-input refusal. Test that old bytes remain intact
after duplicate-name refusal and after an interrupted new export.

## F3: toolbar appearance and stale view assumptions misdirected clicks

Reproduce: office `(145,187)` looked like a disk control but opened inventory.
An early coordinate replay then attempted a plot selection while inventory was
still visible. Delivery was queued, but working cash stayed at 5,000 and no
plot was staged. Closing inventory and checking the actual map allowed the
subsequent plot selection to stage the purchase.

Expected: each action has the correct current scene, modal context, control,
and state outcome. A successful input transport is insufficient.

Adapter mitigation: save uses the freshly recognized Escape menu and save
dialog. Navigation uses original scene actions with destination checks.

The independent food-boundary reproduction encountered the same class of
friction: a Diner click was queued while the prior street capture was black,
and the subsequent view was still street. After the street was visibly
established, a fresh non-transactional navigation opened the Diner. No purchase
was replayed. See `food-commit-luna-research-20261029-01/RESULT.md`.

Next release: generated interfaces should expose named semantic controls and
modal state, and invalidate stale routes before input. Include the inventory
overlay as a negative route test. Do not classify this research mistake as an
emulator regression.

## F4: a native park load is narrower than a runtime checkpoint

Reproduce: save in the paused office; close the original backend; boot a new
backend and use OLD GAME. Tracked money, calendar, food, staff, species and pen
data matched disk and live memory. The pause-hold word was 1 before save and 2
after load. A further 3,000 guest milliseconds in the office did not advance
the date. Returning to the street cleared the observed pause fields and
resumed time.

Expected: persistence declares which state is restored. The E55 handoff also
records incoming-session RNG, preferences and day phase as separate concerns;
those were not independently proven equal by this trial.

Adapter mitigation: use the original native save and fresh loader, compare
qualified park fields before restoring adapter capabilities, and describe the
result as native park persistence. The ten-byte geometry prefix of each pen is
rebuilt by the original loader; the checked saved pen suffix is separate.

Next release: typed persistence contracts should distinguish native park
saves, mounted disk state, emulator checkpoints, and adapter metadata. Resume
must validate identities and live postconditions before offering actions.
Test corrupt and incompatible saves, fresh-process load, and a later original
day advance. Do not claim deterministic continuation from field equality.

## F5: opaque bytes after the native name's first NUL change hashes

Reproduce: compare Luna's first and repeated paused-state saves. Both names
begin `luna\0`, but nonzero trailing bytes differ. Tracked park data remained
the same. The meaning of those trailing bytes remains unknown.

Expected: parse the bounded name using its terminator and preserve all original
bytes. A changed whole-file hash need not mean changed gameplay state.

Adapter mitigation: retain the entire 4,153-byte native file; compare both
whole-file identity and declared park ranges. Do not zero name padding.

Next release: lossless codecs should keep opaque bytes and report semantic
comparisons separately from byte identity. Test embedded NULs and nonzero
suffix bytes without reserializing unknown fields.

## F6: feeding during the food-order confirmation causes a bounded refusal

Reproduce: the second adapter exploratory run staged 20 additional feeders,
with live stock 18 and pending stock 38. After the single confirmation and
6,000 guest milliseconds, committed stock was 37. This is consistent with
ordinary feeding during the interval; the precise internal writer was not
independently traced in this failure. The street and synchronized cash were observed, but the adapter's
exact pending-stock expectation rejected the result. Evidence is the final
`food_stock_reservation`, `shop_input_sent`, `food-committed` and
`resource_observation` records in that run. The failure is preserved.

Expected: a valid purchase remains distinguishable from ordinary feeding or
spoilage during the same operation. Rejecting ambiguity is preferable to
silently assigning every stock difference to the purchase.

Status at the original save/load handoff: unresolved operating-interface gap.
The subsequent correction and fresh original-game verification are recorded
below; the initial failure remains retained rather than rewritten as a pass.

Next release: observe the original commit boundary and independently attributed
stock-consumption transitions. Check the order's quantity and cost exactly once
while reporting subsequent feeding/spoilage separately. Do not simply accept
any lower final stock. Test a weekly feed during staging, during confirmation,
and across a month boundary, plus interruption with no duplicate purchase.

## F7: navigation required users to spell out intermediate menu exits

Reproduce: the earlier text slice required `go street` before a shop command,
and `go office` before `go bank`, even when the target was connected by known
original transitions.

Adapter mitigation: bounded route planning expands a named destination into at
most four qualified original menu transitions. Closed businesses and invalid
save destinations are refused before travel. A failed hop clears following
steps. No direct scene-selector or financial memory write is used.

The 0.21 assisted-travel implementation requires qualified actor-field edits;
its room-jump form places an actor at a portal and then uses original input.
DinoPark's menu scenes do not provide that walking-actor contract. Adapt the
fresh-context, original-transition and destination-verification principles,
not PQ/KQ actor addresses or a room-byte write. The published 0.21 verification
names PQ1 and KQ1; SQ was not independently tested in this work.

Next release: support graph composition of qualified menu transitions with no
mandatory actor writes. Pin each edge, preserve intermediate outcomes, stop on
an unknown/modal destination, and report actual guest time. Test park-to-Diner,
Diner-to-bank and office-to-park after native load. Fewer agent commands must
not be described as equivalent elapsed time or a proven teleport speedup.

## F8: strict scene-pattern binding makes older bundles incompatible

An exploratory process saved while the independently authored pattern file was
being extended with load guards. That process correctly refused its older
bundle after the pattern identity changed, without loading it. This is a
concurrent-development artifact, not a product save-corruption finding.

Expected: a released interface gives a clear compatibility error and preserves
the old native save; deliberate migrations require new qualification.

Adapter policy: pin resources and pattern identities; refuse mismatch without
input. No silent manifest rewrite or native-file conversion.

Next release: distinguish native-save format compatibility from adapter action
qualification compatibility. Test unchanged native bytes across a pattern
revision, explicit refusal, and an independently verified migration path.
Keep the original bundle and report what was requalified.

## F9: a food-word watch can stop partway through REP MOVSW

A new native probe watched the two-byte small-feeder field during the Diner's
stock copy. At the stop, the causing instruction and resume PC both identified
`1000:4fcb` (`F3 A5`, REP MOVSW), with `CX=5`, `SI=b9ec`, `DI=6f9c`. The small
feeder word had already changed, but five words remained in the nine-word copy
and committed cash had not yet changed. The following native trace observed
the remaining iterations, return to `2d0a:2815`, expense posting, and the cash
stores at `2d0a:2836/2839`.

The current normalized stop reported `instruction_completed: true` and
`registers_stage: after-instruction` for that partial-repeat stop. The raw
native reply says after-access and the observed registers preserve the partial
state. A consumer must not promote that normalized completion flag to proof
that the whole REP or the transaction finished.

Evidence: `food-commit-main-research-20261029-01/events.jsonl` and its
`after-write-0.json`, under the private parent above. The trace is bounded to
256 fetched observations; it is not exhaustive execution coverage.

Adapter mitigation: use separately byte-verified original execution boundaries
before the copy (`2d0a:2810`) and after the stock, history and cash commit
(`2d0a:283d`). Do not infer completion from a changed first word or a fixed
number of trace records. These are observation breakpoints, not guest edits.

Next release: distinguish a completed memory access, a partial repeated
instruction and a completed instruction in normalized stop semantics. Retain
the raw reply, causing and resume PCs, count/index registers and backend
qualification. Test a data watch during a multiword REP copy where the first
word changes before the remainder, and a watch after the full repeat ends.
Do not change the underlying native evidence to fit a completion label.

## Food-confirmation correction

The user subsequently requested a fix to F6. The active DinoPark adapter now
observes the original transaction before advancing through the return view:

1. Analyze the original entry traversal with a bounded budget, then seed the
   two trace-established Diner instruction addresses. Preserve budget-exhausted
   status; do not describe that analysis as stable.
2. Arm both byte-verified execution breakpoints before sending one original
   confirmation click. An unverified boundary withholds that input.
3. At `2d0a:2810`, check pending minus live food is exactly 20 small feeders and
   zero in the other eight bins, with a $500 committed/working cash gap. Read
   the current calendar and month's food-expense history at this point, so
   ordinary simulation before the commit is not mistaken for order contents.
4. At `2d0a:283d`, require all nine live bins to equal that pending snapshot,
   pending bins to remain unchanged, cash to equal the prior working balance,
   the loan and calendar to remain unchanged within this span, and food-expense
   history to increase by exactly $500 modulo the original 32-bit storage.
5. Flush a `food_purchase_committed` event before allowing the return to the
   street to advance time. Report stock at the commit separately from current
   stock, cash and staff. A later feeding, spoilage or other stock change does
   not turn this proven purchase into unknown or trigger a second order.

Unexpected stops or accounting mismatches before proof still stop without
claiming success. A later display/status failure retains the proven purchase
in the error and failure receipt, while the follow-up remains unknown. Unit
regressions cover one confirmation input, wrong stock/cash/expense rejection,
unverified boundary refusal, unexpected stops and late display failure.

The adapter change is local research code; the reusable framework boundary
contract and F9 normalization correction remain next-release engineering work.

## F10: sampled waits are not equivalent to one exact guest interval

Luna's independent reproduction advanced 24 intervals of 250 requested guest
milliseconds after one original confirmation click. Requested total: 6,000;
observed elapsed total: 6,975. The first 13 intervals requested 3,250 and
observed 4,030. A separate fresh single-run reproduction requested 6,000 and
observed 6,100. These are different runs under uncontrolled host timing, not
identical complete-world trajectories or a performance benchmark.

The segmented run first observed live/pending stock 38/38 and synchronized
charged cash while its last-completed frame still displayed a transition.
Later, the weekly counter reset and stock became 37/37. A rendered frame,
native commit and requested duration are separate observations.

Evidence: `food-commit-luna-research-20261029-01/RESULT.md`, `events.jsonl`, and
the preserved `single-run/` sibling data. This reproduces F6 with both sampling
styles without attributing the discrepancy to screenshot calls alone.

Adapter mitigation: exact execution boundaries prove the purchase; observed
current stock and actual guest progress describe subsequent simulation. The
action sends one confirmation input, regardless of how many observations occur.

Next release: expose requested versus actual guest progress prominently in
generated wait/observe operations. Do not treat a loop count as an exact
calendar duration. Test overshoot and sampled/single-run reporting separately,
and preserve completion/render boundaries in transaction results.

## Food-correction acceptance on 0.21.0

The frozen corrected script SHA-256 is
`199de30c8a36b5b7db8fb18fb63314a03e52e7222417b8d01c12159bf1fbe511`.
Scene-pattern identities are unchanged, so the previously verified native
`first` bundle remains compatible without conversion or manifest edits.

Luna independently exercised three successful native-game cases:

| Private directory suffix | Commit calendar (year/month/day/week) | Live before | Proven stock at commit | Stock after return | Purchase |
| --- | --- | ---: | ---: | ---: | --- |
| `food-commit-luna-acceptance-20261029-01` | 0/0/21/0 | 17 | 37 | 37 | 20 for $500 |
| `food-commit-luna-acceptance-20261029-02` | 0/0/19/5 | 18 | 38 | 37 | 20 for $500 |
| `food-commit-luna-acceptance-20261029-04` | 0/0/28/0 | 16 | 36 | 27 | 20 for $500 |

The first includes food use before the commit; the second crosses a weekly
boundary during confirmation; the third crosses month end during the return.
In the third case the later loan was 4,885, distinct from the 5,000 loan at
commit. The confirmed purchase remains separate from that monthly settlement.
The public result reports stock at confirmation and stock now, with the change
while returning; it does not label every negative stock delta as feeding.

The coordinator independently verified all three receipts and journal equality,
current code hash, source inventory equality, exactly one confirmation per
purchase, both byte-verified native stops, all nine stock bins, the exact cash
and expense changes, and all 147 exported PNG/database byte matches. Evidence
audit: `food-commit-main-research-20261029-02/acceptance-audit.json` under the
private parent. Luna's failed preparatory case `-03` is retained separately;
it is not counted as successful food confirmation.

The coordinator also completed a normal restock followed by native save and
fresh load at `food-commit-main-acceptance-20261029-01` and its `resume-001`.
A bank regression at `food-commit-bank-regression-20261029-01` passed payoff,
reborrowing, project reopening, stored overlay export and patched scene
isolation. Focused tests: 52 passed. Required active research-checkout full
suite: 1,154 passed, 102 skipped, 24 failed, 23 errors, with the prior
failure/error counts unchanged. The PR checkout's required full-suite baseline
was 1,282 passed, 115 skipped, 13 failed and 23 errors. Neither local full suite
is represented as green.

## F11: an animated street frame can fail the current scene samples

During preparatory case `food-commit-luna-acceptance-20261029-03`, a street
`advance time` requested 1,000 guest milliseconds and observed 1,125. The next
scene check rejected a visibly valid street frame at 28/32 matching samples,
below its 29-sample threshold. Three sample locations were covered by a
passing vehicle and one by the animated upper sign. The stored scene result
reported ready/enabled true and visible false from the pixel predicate.

The differing samples were `(56,162)`, `(23,159)`, `(38,162)` and `(152,9)`.
The exported `advance-after-14.png` and database-only diagnostic have identical
SHA-256 `77cfeed89e05f91c45003b1dae39f95a7b7554eac009831af096660eeb953f2c`,
frame ID 3141, captured guest tick 57432 and state revision 98. Scene
observation `4dee2c7ed52c41cdab9133d79f937f73` retains the actual mismatch.
The coordinator inspected that stored observation and the exported image.

Impact: the interface stopped before any food purchase in this run. The
advance was not replayed and the failed process was not resumed. A separate
fresh native-load case advanced in the park and completed the month-end food
test. There is no per-failure before/after source-inventory receipt for `-03`;
the separately recomputed inventory matching successful receipts does not
retroactively establish that missing pair.

Status at the food-correction handoff: documented recognition gap. The user
subsequently requested the street fix described below. The original failed
advance remains preserved and was never replayed into a passing result.

Next release: qualify stable scene samples outside animated/occluded areas,
retain modal/control readiness separately, and support a bounded fresh-view
recheck without replaying an already-delivered advance or purchase. Test both
this passing-vehicle/sign frame and genuinely wrong scenes/notices. Evidence
and exact expected/actual RGB values are in
`food-commit-luna-acceptance-20261029-02/FINAL-FRICTION.md`.

## F12: the foreground animation path extends above the road

The first street candidate used 40 exact samples outside the road, changing
upper signs and Diner train. It fit 52 retained street frames and rejected 305
retained non-street frames, including the original failed advance. An
independent 180-frame capture then rejected 50 valid street frames at 37–39
matching samples. All seven independently captured negative views were rejected.
The threshold was not lowered to hide these failures.

The changed pixels were on lower storefronts: a walking dinosaur reaches
above the road and crosses those facades. For example, `street-sample-104.png`
in `street-luna-research-20261029-01` shows the foreground walker covering the
office frontage, including sample points `(205,148)`, `(213,141)` and
`(195,141)`. Other affected points included `(17,144)` and `(15,132)` at the
left frontage. The coordinator inspected actual original-game frames and
retained `heldout-results.json`; the rejected candidate SHA-256 is
`3688bce3de5cc1bcfa72b770521e32872853982e034139ba0649acf199bd3676`.

Impact: a static-looking building area is not necessarily free of foreground
actors. A fit-only result, even with strict thresholds and many wrong scenes,
does not establish animation resilience. The first 180-frame capture became
development diagnostics after this failure; it cannot also serve as independent
validation of the revision selected using those frames.

Correction: exclude the complete lower foreground region (`y >= 100`), the
train and upper changing signs. The revised 40-sample guard uses fixed upper
Diner trim/header, Employment facades and the DinoMart side column. It still
requires 40/40 exact matches. Known quarter/parking notices and main/save/load
dialogs are excluded explicitly in both image matching and compiled scene
predicates. Existing selector, video, control and destination checks remain.

Next release: qualify stable scene masks against full observed actor extents,
not just their ground/contact line. Maintain separate development and fresh
validation corpora; include tall/wide foreground actors, train/sign phases,
wrong locations, dialogs and notices. Keep failed candidates and field-level
recognition evidence. Do not replay purchases or prior time advances during
recognition recovery.

## Street correction and saved-park compatibility

The corrected local adapter loads a separate `street_patterns.json`; it leaves
the original main, shop and save pattern files unchanged. New native-save
bundles additionally bind the street-profile hash. An explicit incompatible
street binding is refused before guest launch.

Older three-pattern bundles remain supported only when their original three
identities and full game-resource inventory match. Original native and manifest
bytes are preserved. The original loader's declared native fields are checked,
the journal records a `street_guard_binding`, and a newly recognized live
street creates a new scene revision with `street_guard_live_qualified` evidence.
No historical scene revision is reused or silently converted. An old native
park is not a proof that its former visual guard still applies.

The final profile SHA-256 is
`cce87b5c4da70adccb1364142106c4b8669768619a8f878edcb33a4b9e7e4c6a`;
script SHA-256 is
`0454e27c8bcbba7cf23e36c46e6f31f9be55035a4d3e00e447727c2bdee4dc40`.
Coordinator routes `street-main-acceptance-20261029-01` and `-02` used the
first and second profiles and are superseded. The final new-game route is at
`street-initial-regression-20261029-02`; its final independent validation is
recorded separately below. Pattern-selection metadata describes the frozen
development step, not a claim that the later validation had already passed.

## F13: closed and open shop panels need separate qualification from trim

The second candidate removed the complete observed foreground path, but a
fresh NEW GAME route exposed a different source of state-dependent pixels.
Before land purchase, DinoMart's closed door differs from its later open
panel. The first `go street` transition sent one input, then timed out waiting
for the second candidate's destination predicate at 35/40 matching samples.
The original street was already visible, with the expected buy-land tutorial
and closed businesses. No second transition input was sent.

Evidence: `street-initial-regression-20261029-01/failure.json`, stored scene
observation `03bbdd914da2422f89a47e18d57163ff`, and the exported original
`failed-scene-stored.png` diagnostic. The differing samples were `(208,74)`,
`(211,70)`, `(204,68)`, `(205,76)` and `(209,84)`, all in the state-dependent
bay. Rejected second profile SHA-256:
`df313d9448bd065008e718c92523f09890e18684fea0e003ff426cfd7a556bd5`.

Correction: the final profile uses the left exterior trim (`x=109..119`,
`y=60..91`) in place of the bay-panel region. All 40 samples remain at `y<100`,
and all must match exactly. The independently collected second 180-frame
animation corpus was not inspected or used to select those replacement points;
the fresh pre-land failure and earlier development frames supplied that change.

Next release: stable-region qualification must vary both animation phase and
game state: closed/open businesses, tutorial overlays, first entry and later
returns. Distinguish architectural trim from a panel or sign that represents
state. A successful operating-park save is not a sufficient fixture for a new
game's first street entry. Preserve failed candidates and input counts.

## F14: General Store navigation pins a balance while the park keeps running

The final street-profile legacy acceptance run reached the store after 25
successful street advances, then stopped during `go street` from General
Store. `leave_store` snapshots current balances and passes them to
`store_fences_tab`; that path opens the catalogue and waits 5,000 guest
milliseconds before requiring the exact earlier cash/loan/working-cash values.

The recorded balance before opening the catalogue was 5,697 / 5,000 / 5,697.
The next catalogue observation was 6,358 / 5,000 / 6,358. The strict comparison
rejected the view even though the catalogue pixels matched. The park was
already operating; the precise writer of that cash increase was not traced
in this failure. This is a frozen-balance assumption in the existing shop
navigation, not a new street-recognition mismatch or proof of a purchase.

Evidence: `street-luna-acceptance-20261029-02-legacy/failure.json` and the last
`store-current`, `shop_input_sent` and `general_store` observations. One
catalogue-opening input was sent; there was no purchase and the final store
exit input had not been sent. The failed session was preserved without replay.
It is excluded from completed-route acceptance, while its earlier successful
street advances remain individually evidenced.

Current status: unresolved existing shop-navigation gap, outside the requested
street fix. A separate fresh legacy-load run tests the remaining street,
Diner, bank, office and saved-park route without that unqualified store exit.

Next release: keep transaction reservation/delivery checks separate from view
navigation. Observe current balances after time advances; do not require them
to stay constant merely to open or leave a catalogue. Independently qualify
the original page-specific exit controls, preserve one-input outcomes, and
test a running park with ordinary cash changes and monthly debt settlement.
Do not weaken a purchase's price or stock checks to fix a navigation guard.

## Final street acceptance on 0.21.0

The final profile was frozen before evaluating the second independent capture.
All 180 newly captured native street frames passed 40/40 exact samples; all
eight fresh non-street views were rejected. The coordinator independently
verified all 188 exported images against stored bytes and evaluated both the
adapter's inline matcher and the installed fDisBull scene predicate evaluator.
Actual native winter-quarter notices over both the park and street were also
rejected; an actual parking notice was not acquired in this work. Parking
exclusion remains covered by the declared guard and synthetic overlay test.

In `street-luna-live-guards-20261029-01`, Luna created a live street revision
then tested `scene_assert` and `scene_click` against actual office, main-menu,
inventory, Diner and quarter-over-street views. All ten operations returned
mismatch. The coordinator checked unchanged guest ticks, full mouse state and
recorded click counts for each rejection. These checks establish withholding
for those observed contexts, not arbitrary unknown overlays.

Completed adapter routes:

- `street-luna-acceptance-20261029-01-newgame`: first NEW GAME street with closed
  businesses, land purchase, DinoMart entry and return.
- `street-luna-acceptance-20261029-03-legacy`: original older native save,
  bank/office/street route, 16 street advances to day 18, Diner round-trip,
  new-profile native save and fresh load in its `resume-001`. The saved/loaded
  values were cash 4,791, loan 5,000, 18 feeders, one guide and one Coelophysis;
  all 20 native ranges matched. The new bundle binds the fourth pattern hash.
- Coordinator `street-initial-regression-20261029-02`: complete opening setup,
  guide/food/fence route, park/street operation, new-profile save/load and a
  later street advance.
- Coordinator `street-main-final-legacy-20261029-01`: older native save, 30
  street advances past the original failure period, Diner/office route,
  new-profile save/load and another street advance.

The coordinator checked the three successful Luna receipts/journals, current
script and profile hashes, native readback equality, original resource
inventory equality, and all 62 exported screenshots from those completed
adapter sessions. The 25 street advances in failed batch `-02-legacy` remain
individually recorded but are not counted as a completed route. Its General
Store failure is F14, with no independent per-failure source-preservation pair.

Final-profile scene reopening, stored overlay export and patched-child
isolation passed at `street-main-final-restart-20261029-01`. Focused tests:
55 passed. Required active research-checkout full suite: 1,157 passed, 102
skipped, 24 failed and 23 errors; failure/error counts match the prior food
correction. The PR checkout baseline remains 1,282 passed, 115 skipped, 13
failed and 23 errors. Neither local full suite is claimed green.

Private evidence: `street-luna-research-20261029-02/heldout3-results.json`, its
`notice-results.json`, `street-luna-live-guards-20261029-01/events.jsonl`, and
`street-main-corpus-20261029-01/final-heldout-audit.json` plus
`final-native-acceptance-audit.json`, under the private parent already named.
The first capture and failed candidates remain preserved. The generic scene
authoring/qualification recommendations and unrelated F14 navigation defect
remain next-release work; the tested local street fix is available now.

## Native-save acceptance before the food correction

The final adapter was independently tested by Luna on pinned 0.21.0. Its script
SHA-256 is `b58cb41aee44497edb6d67e541615cb1fdd8b08b1c75c0754780a1993acf0409`;
save-pattern SHA-256 is
`71537783f8aebee49a75c5edfb314fed938daed811aa8cbfec75a0dcfd8aa55f`.
The shop and base route patterns retain SHA-256
`56b840fdd0a4a21b7e4223cdd922459aac4e1bbb019f472f64bc4be209ad5046` and
`5b2acae80d3ddf6a83af9e76c1e4154f5466014be8dd310189fe8a197094c9a4`.

Private acceptance directories:

- `save-load-luna-acceptance-20261029-01`: fresh setup, save `first`, duplicate
  and invalid-name refusals, day advance, native reload request.
- Its `resume-001`: new private copy/project/backend, exact checked-field
  restoration, office-to-Diner automatic travel, successful restock, park entry,
  further advance and save `second`.
- `save-load-luna-acceptance-20261029-02-external`: separate Python process,
  `--load-save` of `first`, inherited library listing, exact initial restoration
  and further park operation.

All are under `/Users/tiga/Conversions/DinoParkTycoon/`. Three distinct run IDs,
matching current code/pattern hashes, source inventory equality, four native
file/live comparisons of 20 ranges, both bundle hashes, journal/receipt equality,
and all 125 exported PNG/database byte matches were independently checked by
the coordinator after Luna's report.

The `first` save and both loads agree on day 6, cash 3,165, debt 5,000, one
guide, 20 small feeders and one Coelophysis. Before loading, the park had reached
day 7 and 19 feeders. The successful resumed order committed 38 feeders;
`second` was saved at day 24 with cash 5,574 and 37 feeders. That successful
order does not erase F6. The coordinator separately loaded its own second save
in a new Python process and checked Diner-to-bank and bank-to-park travel.

Focused local tests: 44 passed. Required active-checkout `python -m pytest -q`:
1,146 passed, 102 skipped, 24 failed, 23 errors. The failure/error counts match
the previous operating-slice run; they include existing fixture/platform,
managed dependency and distribution failures. This is not a green full-suite
claim. A separate pinned-0.21 bank regression passed repayment/reborrowing,
project reopening, original scene overlay export from stored state, and patched
child scene isolation.

This PR documents observed adapter mitigations and next-release acceptance
requirements. The framework requests remain implementation work; neither this
PR nor the finite game tests establish whole-game coverage or indefinite park
survival.
