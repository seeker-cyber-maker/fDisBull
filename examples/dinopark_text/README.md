# DinoPark text scene: shops, operation and native saved parks

This is a small playable text projection over the original DinoPark executable,
using released fDisBull 0.21.0. It begins at a private new-game office, or loads
a compatible named park through the original OLD GAME menu. It supports `look`,
`go bank`, `repay`, `borrow`, `go street`, `buy desert plot`, `go dinomart`,
`buy coelophysis`, `buy vegasaurus`, `read vegasaurus`, `go store`, `buy wood fence`, `go employment`, `go diner`,
`hire tour guide`, `buy 20 small feeders`, `check inventory`, `open park`,
`go park`, `status`, `advance time`, `acknowledge notice`, `go office`,
`save park NAME`, `list saves`, `load park NAME`, `help`, and `quit`. The original game
executes the clicks. At the bank, cash and loan are read from the running
original game; the player does not see investigation-only working cash.

One qualified shopping route starts with the original $5,000 cash and $5,000
loan. From the office, enter `go street`, `buy desert plot`, `go dinomart`,
`buy coelophysis`, `go street`, `go store`, `buy wood fence`,
`go employment`, `hire tour guide`, `go diner`, `buy 20 small feeders`, and
`open park`. The original game charges $500 for the plot, $1,250 for
the dinosaur, $1,000 for a wood fence, and $500 for 20 small feeders. The
guide's displayed wage is $900 per month; hiring has no up-front charge on
this route. The interface checks the fenced
occupied pen in a reopened placement map, and the inventory view checks one
dinosaur, one pen and one pen in use. This slice supports only one purchase of
that species, plot and fence in the qualified starting state; it refuses
unqualified balances and repeat orders without sending input. Vegasaurus has a separate qualified order described below; other species remain unsupported.
It does not establish indefinite survival, escape behavior, or a viable park.

DinoMart also offers Vegasaurus for $25,000. `read vegasaurus` opens its
original encyclopedia entry and returns to the catalogue. `buy vegasaurus`
(also accepting `buy vegasosaurus`) sends the original BUY once when the
available cash covers its price and no purchase reservation is pending. The
interface reports what the original game does after that action. It does not
supply advance knowledge of the result. A second order in the same guest is
outside this bounded slice and is refused before input.

The hire is checked first in the pending roster and again after the outer
employment confirmation. Each of the 20 food increments is checked before
another input. Food confirmation uses byte-verified original execution
boundaries before the pending-bin copy and after the stock, expense and cash
commit. It checks all nine food bins, the $500 cash reservation and expense
posting, then journals the confirmed 20-unit purchase before letting the
return to the street advance time. The reported current stock is a separate
observation; feeding or spoilage after that commit does not erase the purchase.
`open park` enters the original park view and confirms the day counter has
advanced. A distinct open/closed flag is not established, and entering the
view advances game time and can change money and stock. Once entered,
`status` in the office, street or park reads the live date counters, cash, loan, guide, food bins, dinosaur
pen records and hunger counter without advancing the guest. `advance time`
runs one bounded 1,000-guest-ms interval, then reports the observed state; it
does not promise exactly one game day. Repeated calls allow the player to
monitor the changing park. The older `check inventory` screen action is still
limited to its original fixed-balance cases; use `status` during operation.
The currently recognized winter-quarter or parking notice stops
advancement. `acknowledge notice` handles a uniquely matched quarter notice
in the park view once, without automatically replaying an uncertain input;
parking notices, other seasonal quarter labels and scene changes remain unqualified. Fresh operating tests found a spring-quarter notice missed by the winter-only exact samples, and parking advice appearing over the street after a confirmed food order; both are recorded in feedback PR #15. After the first park entry, return to
the street, visit the Diner, and use `buy 20 small feeders` again to restock;
`go park` revisits the park view. Navigation and shop interactions themselves
can advance days and change finances, stock or staff. The shop checks the
original live/pending stock and cash gap at each staged item, including when
feeding or income happens during an order. These are bounded actions, not an
indefinite survival or full-campaign guarantee. See the
[location audit](LOCATION-AUDIT.md) for tested routes, missing activities and
the boundaries of the current interface. A complete playthrough is not yet
available.

For example, after opening the park:

```text
status
advance time
status
go street
go diner
buy 20 small feeders
status
go park
```

If the park view displays the recognized quarter notice, use
`acknowledge notice` before advancing again. A notice with an unqualified
handler, an unrecognized scene, or an uncertain acknowledgment stops the
bounded route; do not blindly repeat the input.

The original controls offer full payoff or the full available loan quote; this
slice does not support choosing an arbitrary amount. To avoid extrapolating
beyond live tests, repayment is qualified only at cash $5,000 / loan $5,000,
and borrowing only at cash $0 / loan $0. At the $5,000 credit ceiling or with
zero debt the interface explains the condition and sends no input. Other
balances are explicitly unqualified and also receive no input. The original
executable and `VARS.DAT` must have the tested hashes.

## Save, load and travel

After preparing and entering the park, use:

```text
save park first
list saves
go park
advance time
load park first
status
go park
advance time
save park second
```

`save park NAME` takes the verified original menu route back to the office,
opens Escape → Save Game, edits a unique native name and submits Enter once.
The original name editor consumed a mouse OK click without committing in the
observed trial. The adapter checks the native file against live park fields,
then exports the complete, unchanged 4,153-byte `DINOSG` file and a checksummed
qualification manifest to the printed `saves/NAME` folder. Earlier names are
never overwritten. Names contain 1–32 lowercase letters, numbers, underscores
or hyphens. Duplicate or invalid names are refused before travel or input.

`load park NAME` closes the current guest and launches a fresh private game
copy and project, imports the named native file, and uses OLD GAME. It checks
cash, loan, calendar, weekly counter, hunger, all food and staff words, species
counts and the saved suffixes of all ten pens before restoring text actions.
The original loader rebuilds each pen's geometry prefix. This is native disk
persistence; it does not preserve a complete emulator continuation or establish
equal RNG, preferences or day phase. The office is paused; use `go park` or
`go street` before advancing time. The initial loaded status is available in
the office without guest execution.

For a later process, add `--load-save /absolute/path/to/saves/first` to the run
command below and choose a new work directory. `list saves` then uses that
bundle's parent as the library. An optional `--save-library` chooses another
private library. A missing, corrupt or incompatible bundle stops before guest
launch; it never silently starts a new park. Compatibility currently requires
matching original resources and scene-pattern identities. The manifest is an
integrity check and carries route qualification, not an authenticity signature.
New bundles also bind `street_patterns.json`. Earlier bundles with the original
three matching pattern identities keep their native and manifest bytes intact:
the loader verifies their native fields, records the current street guard, and
requires fresh live street recognition before its controls become available.
An explicit incompatible street binding in a newer bundle is refused.
Only saves created after this adapter's qualified running-park setup are
supported; arbitrary original save imports remain unqualified.

You can now name a connected destination directly. For example, `go diner`
from the park crosses the street automatically, and `go bank` from the Diner
crosses the street and office. Every hop uses the original menu action and a
checked destination; an unsuccessful hop stops the remaining route. This
adapts the context and destination checks from 0.21 assisted travel to menu
scenes. It does not write a scene selector or reuse PQ/KQ actor addresses.
Fewer agent commands do not imply identical guest time or a measured teleport
speedup. Shops remain closed before land purchase.

The former final-confirmation stock gap is fixed for the qualified food order.
For example, the original game can commit 38 feeders and return with 37 after
time advances. The interface now confirms the purchase, reports both stock
values, and sends no repeat purchase. Unexpected execution before commit
still stops without inventing a successful outcome. If the later display or
status fails after a proven commit, the error and failure receipt retain that
confirmed purchase and explicitly prohibit repeating it. The original failure
and this correction are recorded in [release-feedback PR #15](https://github.com/seeker-cyber-maker/fDisBull/pull/15).
Add later tool or generated-interface friction to that PR with a reproduction,
expected/actual result, impact, retained evidence and a next-release acceptance
case. Distinguish adapter mitigations from framework work still to implement.

## Run

Use your own original game directory and choose a new private work directory
outside both the game directory and the repository:

```sh
/Users/Shared/fDisBull/releases/0.21.0-a253600/venv/bin/python examples/dinopark_text/scene.py \
  --game-dir /Users/tiga/Conversions/DinoParkTycoon/dinopark \
  --backend /Users/Shared/fDisBull/releases/0.21.0-a253600/backend/native-macos-arm64/dosbox-x \
  --work-dir /Users/tiga/Conversions/DinoParkTycoon/my-new-text-session
```

The program creates a separate game copy, omits source `DINOSG.*` saves, and creates
a fresh project. Without `--load-save`, it performs the previously investigated new-game startup route
to the office. The recognized office uses independently authored pixel samples
from `examples/dinopark/routes/newgame-pixel-patterns.json`. It captures a
reference, records the observed dispatch selector and creates a scene revision.
On `go bank`, fDisBull checks the office and the named control, injects the
original mouse input, and verifies the bank predicate. A separately captured
bank frame creates the return and financial actions; `go office` checks that
scene and verifies the office predicate. `look` rechecks the current scene
without guest execution. `repay` and `borrow` check the bank, input and the
appropriate confirmation view, record intermediate values, then acknowledge
the confirmation and verify the original cash and loan changes. The driver
waits 1,200 guest milliseconds after the confirmation appears, rechecks the
modal and its intermediate balances, sends Enter once, and waits for the bank
scene to become ready. This is a bounded timing qualification, not a universal
proof that every modal is ready. They retain
the working-balance observation separately. Native persistence is checked by
the dedicated save/load path described below.
Scene identities and the live video mode are checked, and unexpected debugger
stops or missing/mismatched observations stop the session.

Pixel matching is an authored, partial view recognition. The selector value is
a calibrated correlation, not proof of universal control readiness. A
successful transition proves the observed view in this run; it does not prove
money, save-file, audio, or campaign state. The finance actions additionally
compare original runtime balance fields; the save action separately compares
native file ranges with the live park.
The program binds the executable,
backend, pattern file and full source/copy inventories by hash in the private
receipt. The guest copy may write files; checkpoints do not revert those files.
Scene evidence and PNGs remain in the private work directory. Before each
action, a flushed `events.jsonl` records an intent, and finance actions also
record the modal and intermediate balances before acknowledgment. The completed
scene result is recorded afterward. An intent without a result leaves the outcome unknown: do not
blindly replay a command after an error or interruption.

For an automatic bounded check, add `--verify` and select a fresh work path.
That run checks office-to-bank, full payoff, maximum borrow, and return to the
office. It exports real screenshots, reopens the
project, exports the office overlay from stored state, and tests that a patched
child version cannot inherit the original scene. It does not operate a GUI.
The default interactive run can repeat both transitions and uses the same
checks. The separate native-save route qualifies saved-park restart behavior.

## Research and local evidence

The current street correction binds script SHA-256
`0454e27c8bcbba7cf23e36c46e6f31f9be55035a4d3e00e447727c2bdee4dc40`
and street-profile SHA-256
`cce87b5c4da70adccb1364142106c4b8669768619a8f878edcb33a4b9e7e4c6a`.
Luna's fresh independent `street-luna-research-20261029-02` capture accepted
180 street frames at 40/40 and rejected eight other views. Actual native
quarter notices over street and park were rejected; an actual parking notice
was not acquired. Ten live negative scene/assert-and-click tests withheld
input and guest time in office, main menu, inventory, Diner and quarter-over-
street contexts. The coordinator independently checked the 188 held-out
exports and both inline and installed scene evaluation, then the 62 exports
from the completed new-game/legacy-load/save/reload acceptance sessions.
The private paths share `/Users/tiga/Conversions/DinoParkTycoon/` as parent.
Final original-game acceptance is in `street-luna-acceptance-20261029-01-newgame`,
`street-luna-acceptance-20261029-03-legacy` and its `resume-001`. The coordinator
also completed the full opening setup and a separate 30-advance legacy route,
plus stored-scene reopening, overlay export and patched-version isolation.

A separate legacy batch, `street-luna-acceptance-20261029-02-legacy`, completed
25 street advances then stopped during General Store exit because its old
navigation guard required cash to stay constant while the catalogue opened.
No purchase or exit input was replayed. This remaining shop-navigation issue
is F14 in PR #15; it is separate from street recognition and is not fixed by
this change. That street-only delivery passed 55 focused tests; local full suites remained
non-green with their existing failure/error counts, as recorded in that PR.

The earlier food-confirmation correction was verified with script SHA-256
`199de30c8a36b5b7db8fb18fb63314a03e52e7222417b8d01c12159bf1fbe511`.
The original commit trace and execution-boundary probes are in private sibling
directories `food-commit-main-research-20261029-01` and `-02` under
`/Users/tiga/Conversions/DinoParkTycoon/`. The first data watch caught a partial
`REP MOVSW`, illustrating why observing one changed food word alone is not a
complete transaction check. Native execution at `2d0a:2810` starts the pending
bin copy; `2d0a:283d` follows the full stock, expense and cash commit. These
points are qualified to this executable, not inferred universal game hooks.
The coordinator's normal restock and subsequent native save/reload passed at
`food-commit-main-acceptance-20261029-01`. The older save evidence below remains
unchanged; its statement of an unresolved food gap describes the earlier code.

Luna's corrected-interface runs are `food-commit-luna-acceptance-20261029-01`,
`-02` and `-04` under that same private parent. They proved delivery of 20 units
and a $500 cash/expense commit, with stock at commit/current stock of 37/37,
38/37 across a weekly boundary, and 36/27 across month end. The coordinator
independently checked all 147 exported frames against stored artifact bytes,
the three receipts and journals, source preservation, one confirmation per
order and both native boundaries. The preparatory failed `-03` run is retained
and excluded from successful acceptance. The current focused checks pass 52
tests; neither local full-checkout suite is green, as recorded in PR #15.
That failed preparatory run exposed F11 in PR #15. The subsequent street fix
replaces the old samples with 40 strict, exact samples on upper structural
facades. All are above the complete observed foreground-actor region; the
Diner train and changing upper signs are also excluded. The inline image
check and stored scene predicates use the same profile and explicitly reject
recognized quarter/parking notices and main/save/load dialogs. Scene-selector
readiness, video mode and per-action destination checks remain required.
The first candidate covered the road but still sampled lower storefronts;
Luna's independent capture exposed a tall walking dinosaur crossing those
points. That failed candidate is retained, and its frames are diagnostic
development data rather than final validation. A fresh new-game check also
exposed a closed/open door-panel difference, so the final guard uses exterior
trim rather than that panel. Its independent validation uses a new original
capture, separate from those diagnostics. No input or time advance is replayed
to make an animated frame pass.

Native save/load acceptance on pinned 0.21.0 is at
`/Users/tiga/Conversions/DinoParkTycoon/save-load-luna-acceptance-20261029-01`,
its `resume-001`, and the separate Python process at
`/Users/tiga/Conversions/DinoParkTycoon/save-load-luna-acceptance-20261029-02-external`.
All three receipts bind final script SHA-256
`b58cb41aee44497edb6d67e541615cb1fdd8b08b1c75c0754780a1993acf0409`
and save-pattern SHA-256
`71537783f8aebee49a75c5edfb314fed938daed811aa8cbfec75a0dcfd8aa55f`.
Four original file/live comparisons of 20 ranges and all 125 stored/exported
PNGs were independently checked. `first` saved day 6, cash $3,165, loan
$5,000, one guide, 20 feeders and one Coelophysis; both loads restored those
checked fields. The successful resumed route restocked to 38 feeders,
advanced again, and saved `second` at day 24 with cash $5,574 and 37 feeders.
This successful order does not resolve the final-confirmation stock gap above.
Luna did not independently reload `second`; a separate coordinator run loaded
its own second save in a new process and resumed operation. The original game
directory remained unchanged throughout these runs.

The independent native UI research is at
`/Users/tiga/Conversions/DinoParkTycoon/save-load-luna-research-20261029-01`.
The coordinator's accepted round trip is at `save-load-main-20261029-03` under
the same parent, and its later-process load is `save-load-main-fresh-20261029-01`.
The older research below predates native-save support; its stated save limits
apply to those historical runs.

An operating route with repeated time advances is preserved in
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-quarter-20261028-01`.
It reached the next quarter, stopped on the original winter-quarter notice,
acknowledged it explicitly, and observed a later day. That particular run did
not restock and ended with one small feeder; it is not a survival claim. A
separate replenishment run is at
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-operations-20261028-04`.
There, 19 live feeders became 18 during the order, while the pending/live
gap reached 20; confirmation recorded 38 live feeders. Cash also changed
during the order, so the receipt records the two balances and staged gap
rather than claiming the net cash movement is the purchase price.

Luna's independent original-game investigation is preserved at
`/Users/tiga/Conversions/DinoParkTycoon/operating-luna-original-20261028-02`.
An earlier full text-interface acceptance on pinned fDisBull 0.20.0 is at
`/Users/tiga/Conversions/DinoParkTycoon/operating-luna-adapter-acceptance-20261029-03`.
Its receipt binds script SHA-256
`73ff0ecb784f71c36a199aad91869db89a6370af0cac1023c12dfa15029f1b6f`
and pattern SHA-256
`56b840fdd0a4a21b7e4223cdd922459aac4e1bbb019f472f64bc4be209ad5046`.
The run crossed a weekly feeding, restocked, returned to the park, crossed a
quarter notice with explicit acknowledgment, and advanced again. Its original
game source inventory remained unchanged. The park state, outcomes and
timestamps are specific to that finite run; they do not prove indefinite
survival, every popup, all possible shop states, or saved-game persistence.
After correcting the older inventory refusal message, Luna repeated the
operating route on pinned 0.20.0 at
`/Users/tiga/Conversions/DinoParkTycoon/operating-luna-adapter-acceptance-20261029-04`.
Its receipt binds the final script SHA-256
`e1315c6127698b348aec4c01f06899be2800fb9df79e41cfed681b57ba8feccf`
and the same pattern hash above. The run confirmed the week, restock, quarter
notice, subsequent advance, inventory refusal and live `status` route.

The independent original-game guide, food, and park-view research is at
`/Users/tiga/Conversions/DinoParkTycoon/guide-food-luna-research-20261028-01`.
The pending guide word changed from zero to one before the active guide word;
the latter changed only after the outer employment confirmation. Each food
increment reduced working cash by $25, while the committed food word remained
zero. Confirmation produced 20 small feeders and $1,750 committed cash. The
original park view then showed an advancing day counter; the run did not
identify an independent open/closed flag. A local text-interface route using
the then-current fDisBull 0.21.0 is at
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-guide-food-20261028-04`.
Luna independently ran the final adapter on pinned fDisBull 0.20.0 at
`/Users/tiga/Conversions/DinoParkTycoon/guide-food-luna-adapter-acceptance-20261028-04-020`.
Its receipt records script SHA-256
`c10d51ff459d28eac6b0d23a59716dcf75a4e5ef92082e90822f8f5591cc88b2`
and shop-pattern SHA-256
`56b840fdd0a4a21b7e4223cdd922459aac4e1bbb019f472f64bc4be209ad5046`.
The pending and committed guide states, all 20 food increments, committed
stock, park day advance and source inventory were checked. An earlier
acceptance discovered that the Diner can reopen on the meat menu rather than
the cover; that failure was preserved and the final run verifies re-entry.

Luna first bought and placed a wood fence in the original game on a fresh
private copy at
`/Users/tiga/Conversions/DinoParkTycoon/wood-fence-luna-research-20261028-01`.
The occupied pen's wood border was visible after reopening the placement map.
The completed text-interface acceptance is at
`/Users/tiga/Conversions/DinoParkTycoon/wood-fence-luna-adapter-acceptance-20261028-03`.
Its script SHA-256 is
`fc6574d6755717b01f7558963883d61ec716410ef9f1b440f4c7e9ec548f00f8`
and its pattern SHA-256 is
`da56bfc0110d5020b62b5354aef20d43a25379c2f5f9678d5dac5ca6efd41001`.
Placement changed working cash from $3,250 to $2,250 while committed cash
remained $3,250; confirmation committed $2,250. The subsequent reopened map
showed `1 COELO` in the wood-bordered pen. The run checked inventory, repeat
purchase refusal, General Store re-entry, employment, Diner and the bank.
The original game directory was unchanged. The observed border is a
same-session visual readback; it is not a save/reload test.

The DinoMart route is pinned to visual samples independently matching the
earlier 0.16.0 original-game route and a fresh Luna-run 0.20 original-game
session. The samples live in `shop_patterns.json`; they are partial visual
recognition, not proof of universal input readiness. The land selection stages
working cash at $4,500 while committed cash remains $5,000; confirmation
commits $4,500. The dinosaur order stages working cash at $3,250 while
committed cash remains $4,500. After arrival, the adapter waits for the
placement view without repeating any input, checks the staged placement view,
and confirms it once. It then checks committed cash at $3,250. Inventory is a
separate original-game view and reads the three displayed counts via qualified
pixel samples. The game may advance its calendar during the arrival.

Each shop input is journaled before and after dispatch, and each important
view and balance observation is recorded. If an observation fails or a command
is interrupted, its outcome is unknown; do not blindly replay it. These checks
are limited to the supplied executable, configuration, observed new-game path,
and one dinosaur. The inventory check does not prove save/reload persistence.

Luna's independent original-game route, with unmodified game code and no
memory edits, is recorded at
`/Users/tiga/Conversions/DinoParkTycoon/dinomart-luna-research-20261028-01`.
A successful text-interface route including a return visit and inventory check
is recorded at
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-shop-20261028-06`.
The recorded staged placement named Coelophysis; the separate inventory view
confirmed the counts but did not itself display the species name.

Luna independently tested the earlier DinoMart-only text interface on another
fresh private copy at
`/Users/tiga/Conversions/DinoParkTycoon/dinomart-luna-adapter-acceptance-20261028-07`.
Its receipt binds script SHA-256
`21d6f31f8dc3b67e0b9ad6be2ac7b7264f8b6dd5f6e0b0895e37cf63e75846ac`,
and shop-pattern SHA-256
`9bc04fb2818cb90118f049e89f1540f8ea3493c088d0b723d58beffd820cd392`,
reports the source unchanged, and records the same staged and committed
balances. It also checks the inventory twice, returns to DinoMart, and verifies
that repeat land and dinosaur purchases receive no input. Separate earlier
private attempts retain the discovered placement-readiness and scene-revision
failures. A further preserved run stopped after committed cash changed because
the catalogue pattern sampled an animated sign. Those samples were removed;
the revised predicate matches that captured frame and distinguishes the
pre-confirmation selected view. That acceptance is a bounded fresh run,
not a claim of save/reload persistence.

The E55 handoff separates interface readiness and rendered content from
semantic effects and persistence, and records that bank operations can affect
committed and working balances differently. The bank slice measures both
committed balances and working cash, while treating persistence as unknown.
The original handoff archive SHA-256 is
`e6f9da13a3ab1d1de485a496f5d807121bcd929ba67bd87256b449870aa718ea`.
The supported executable SHA-256 is
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
The supported `VARS.DAT` SHA-256 is
`5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153`.

In the final finance verification, run `6ed3b97911c044679adc914b489911e6`,
payoff went from cash/debt/working-cash `5000/5000/5000` to a confirmation
with `5000/5000/5000`, and then to `0/0/5000`. Borrow went from `0/0/5000`
to a confirmation with `0/5000/5000`, and then to `5000/5000/5000`. Both
post-action views displayed balances agreeing with the committed memory reads.
The private evidence and receipt are at
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-bank-20261028-final-r4`.
The exact script SHA-256 was
`59da792fa8cfaec5b14a2b6795b5077f30a5e0094fae0d88c6b636a0952f66ed`.
The source inventory was unchanged, the project was reopened, its saved
overlay was exported and a patched child could not inherit the scene.

An independently run Luna agent-facing scenario used that same script hash in
`/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-bank-agent-acceptance-20261028-04`.
It checked ceiling borrowing and zero-debt repayment were refused without
sending input, then completed repayment and borrowing, returned to the office,
re-entered the bank, and observed the same cash and loan values on `look`.
Its private receipt and event log preserve the separate modal and final reads.

An earlier run stopped with the repayment confirmation still displayed after
the initial Enter; the outcome was recorded as unknown and that input was not
automatically retried. The recorded diagnostic motivated the modal-settling
qualification above. Another earlier startup captured a blank frame and stopped
before any bank command. The startup check now waits for a bounded number of
fresh office observations without repeating prior input. Both failed private
runs are retained; the cause of the blank frame is not established.

For the earlier navigation-only prototype, on 28 October 2026 an actual-game verification completed in a private
copy at `/Users/tiga/Conversions/DinoParkTycoon/dinopark-text-scene-e55-20261028-final-r3`.
The run `d9805e95b59e45dc968e3b672f7d8bf1` observed both transitions and
the original game directory's complete file inventory was unchanged. The
bank screenshot SHA-256 is
`47575807c7f5a5d0eb94585fc55a9f4953ca4946dd5974fdb6961779fe2d3914`.
The reopened project retained its office scene, exported a stored overlay, and
refused that scene in a patched child. A separate player run repeated each
transition twice and checked `look` in both scenes. These are bounded
observations, not a full DinoPark reconstruction or a finance test.

<details>
<summary>Vegasaurus developer verification — contains story spoilers</summary>

Ordinary mouse movement pans the original wide catalogue; the adapter checks
static labels and the actual printed encyclopedia entry. No camera, asset or
story memory is edited. Four byte-verified execution boundaries observe the
complete reservation, expense posting and release, including both halves of
the native 32-bit writes. The $25,000 working reservation is released, no animal is added, and the
expense history retains $25,000. Balances and calendar are checked within
each native instruction pair. Ordinary simulation can change cash, debt and
the month during the animation; the result reports those separate observations. The listing becomes NOW EXTINCT. A confirmed result is journaled
before later view settling, and failure.json retains confirmed dinosaur orders.
The optional entry reproduces the original Era, Diet, Length, Weight and
Climate text. Native screenshots, execution stops and a player test are
preserved separately from the earlier research notes. Owning or placing this
species is not implemented or implied by this test.

</details>

Current Store/Vegasaurus verification (29 October 2026): frozen adapter
`0fd84f33f655f3326e141c1ec939967057d9fc7cc1a9d055ef4fcbbf7fa3c91c`
and mart observations `e5da3e3f68e6cacf1db788b4327eb127b2151a7d0c619d0fb85392985ac39378`.
The DinoPark and Zork focused tests pass 67 checks. The required full command
in the occupied implementation checkout reports 24 failed, 1,169 passed,
102 skipped and 23 errors; all 47 failure/error identities match the earlier
Store-only run. Bounded native 0.21.0 macOS Store and DinoMart acceptance is
separate from that non-green full suite. A final bank verification also
reopens the project, exports stored images and checks patch isolation.
The park-view fingerprint also rejected a visibly valid desert park during
longer operation (14/32 samples, threshold 28). That recognition gap remains
recorded with the seasonal notices in feedback PR #15; no complete-playthrough
claim follows from these bounded scenes.
