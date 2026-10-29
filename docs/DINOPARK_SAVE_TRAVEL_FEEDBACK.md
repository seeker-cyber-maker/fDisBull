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

Current status: unresolved operating-interface gap. Save/load acceptance does
not establish every possible food-order/calendar phase.

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

## Acceptance record

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
