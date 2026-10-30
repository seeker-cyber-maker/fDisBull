# DinoPark Z continuation on v0.24.0

The core opening, operating and native-resumption routes are usable through Z.
This follow-up starts from main `031b53e`; PRs #18 and #19 are merged and left
unchanged. Current runtime is `f07d219da52239e4009070148b74ff98e61a8364`.
Core/player metadata report 0.24.0; these are private branch candidates, not a
new published release. The real DOS UDC emits the unchanged executable and
explicit resources. Original game code supplies every business effect.
Qualification remains `original_bytes_only`, with **zero semantic blocks**.

## Accepted evidence and its limits

| Installed evidence | Actual coverage | Boundary |
|---|---|---|
| Candidate 5, runtime `7d2a5f7`, core wheel `2db348b8…` | 30 public commands: cold-facing encyclopedia/Coelophysis, fence, guide, initial food, opening, replenishment, navigation/status | A separate funded guest stopped at parking advice before submitting food. This is earlier evidence, not a current whole-module pass. |
| Candidate 10, runtime `3d93388`, core wheel `2d7a20c2…` | Two guests: funded Vegasaurus, repeat refusal, catalogue exit, quarter acknowledgment/re-entry, all 20 food increments, native save and public `load zpark`; all 20 native fields equal on fresh load | Core proof was frozen before the optional parking continuation, which returned unknown on its transitional post-thumb frame. That optional result remains unknown. |
| Candidate 11, current runtime | Two guests, 16 public commands, zero incomplete commands: parking interruption, one visible-thumb input, bounded destination observation, park/status/time, `save park`, public `load zpark-002`, 20-field equality, status/inventory, `save park` to zpark-003 | No Vega/cold-opening replay and no third load. Mid-food parking/reconciliation was not encountered in these final native orders. |
| Retained Candidate 2, runtime `edb8599`, core/player 0.23 | Four primary guests/132 commands, natural Winter notice after 74 advances, acknowledgment, three backup/fresh-load cycles; 20 fields equal on each load | Funded exit failed separately. Different packages/audio/input adapters; its evidence is not upgraded to final-candidate parity. |

These are warm verifier runs and bounded presentation checks, not a cold model
benchmark or full-game coverage. The parked one-Coelophysis layout is qualified;
other park layouts, unobserved notices and other dinosaur orders remain unknown.
Native disk saves are accepted here. The separate live-engine checkpoint restore
that later lost its scene qualifier remains an open diagnostic finding.

## Current artifact identities

| Artifact | SHA-256 |
|---|---|
| Core wheel | `b5fcdb61a2672ec1e0b0bb68db9bc8d6540134181165635639bca1b4f6cc87bf` |
| Player wheel | `99e5deaa0a5ab48bacfda0adaa675fd37f3856c8dff7fc48eb1e5a4cce34eddb` |
| Retained native backend, 0.22 prefix | `1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277` |
| Original EXE | `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c` |
| Original VARS.DAT | `5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153` |
| C10 native zpark, final-test input | `f661ecac96ae84803af19901def0669d8032ecb8b2b12814ca4832dcf78f576e` |
| C11 native zpark-002, fresh-loaded | `9c30dcc7f0a64d450075dfe8c92a604d1df78537640de6d526fc5de502fadcf4` |

All 148 runtime payloads equal manifest, wheel, committed source and installed
files. Actual worker imports came from fresh isolated environments; inherited
PYTHONPATH/PYTHONHOME were unset. Every 184-file emitted/compiled closure and
both final native working games were compared directly with original files.
The canonical 192-file game, including eight old saves, and all input bundles
remain unchanged. Original bytes were not edited to grant cash, food or time.

## Final original-game observations

The C10 food order reserved exactly quantities 1–20, with matching native cash
reservations and pending-minus-live food at each stage. One original confirmation
input reached the protected boundaries: cash **27,732 → 27,232**, stock **7 → 27**,
expense **0 → 500**. The final live view and post-load reports were checked
separately. Ordinary business may change cash, loan, food and calendar outside
those protected instruction boundaries.

C11 started from C10's verified native backup. Park entry returned accepted with
partial effects and `park-entry.parking-notice`; fresh look exposed acknowledgment
only. One original thumb input dismissed the advice. Five logged return frames
followed: four unqualified transitional views, then one uniquely matching park
with no known modal. Every return observation records `following_input:not_sent`.
The final image SHA is
`8fcf22ad9251c900488c11e56ba30ca4df1cf3cc4635f02896ecc8971f5e347f`.
The actual park-entry result was completed; no second click or Enter was sent.
The exact internal palette/restoration mechanism remains unproved.

After acknowledgment: cash 28,085, loan 4,290, month index 6/day 29, food 25,
one guide, one dinosaur, hunger zero. One ordinary time interval reached day 30
and cash 28,130. Original save navigation later progressed to month index 7.
After fresh load: cash 28,199, loan 4,167, month 7/day 1, food 19, one guide,
one Coelophysis, hunger zero. All 20 saved ranges matched exactly.

Both final native receipts and the outer receipt completed, both children and
the worker returned zero, and cleanup found no owned survivors. These lifecycle
facts are separate from action results; they do not change earlier unknowns.
C11 public commands summed to 11.551 seconds; the two guest lifetimes summed to
16.243 seconds. These timings exclude verifier reasoning/install/audit overhead.
An earlier Candidate 6 source replay checked 21 public commands in 25.05 seconds;
that timing is not promoted to the final runtime or a model ranking.

## Corrections and reproducible findings

**Catalogue intent versus last page.** Reading the encyclopedia leaves the
catalogue on its last page. Coelophysis now pans back using original mouse input
and qualifies its first page. Static label/price/control samples replace animated
portraits. Before BUY the original species word must be 4 and price must be
1,250. Instructions at `334b:2066..2087` index 26-byte records using `DS:68a5`
and read prices from `DS:4550`; native readback and cash debit establish 1,250.
Misreading the tiny bitmap as 1,500 was an observation error, not a price rule.
The cold-facing Vegasaurus listing does not reveal an unobserved outcome.

**Static catalogue observations.** Software cursors and enabled button bevels
invalidated earlier toolbar probes. The final 48 exact samples use fixed
capital-label and shelf pixels, excluding widgets, moving artwork, cash/calendar
numbers and cursor footprints. All 170 retained catalogue frames match. In a
separate 778-frame corpus it matches eight, introduces no new match, and ceases
to match two dinosaur-arrival views. Pan entry still requires its qualified
parent, unchanged pending scene-request word, no known modal, and final page
qualification. Failed pan conditions now retain their exact frame and reasons.

**Input preparation.** Confirmed Vegasaurus orders were followed by failed exit
inputs. One direct macro and an installed Oracle-OFF case passed; that correlation
does not prove the backend cause. Optional native witness reads were removed
from protected commit callbacks and deferred until command completion. A later
Oracle-ON case still failed with only 150 ms of pointer settling. The tested
DinoMart exit now prepares the saved target for 1,000 guest milliseconds, sends
one 80 ms click, runs a continuous 2,000 ms interval and verifies the street.
Park exit later timed out on a clear 32/32 park with both selectors `ffff`;
its saved target now receives the same 1,000 ms released-pointer preparation
before its single original scene click. Bank controls retain 150 ms. These
bounds passed the stated cases; they are not a universal readiness detector or
proof that diagnostic reads are observationally neutral.

**Occupied-pen observations.** C7 observation
`2d2c0fddbb2a40509bc160cada488a2f` rejected a clear park at 39/40 anchors:
(15,160) changed from ground RGB (186,150,101) to (170,93,117). Its producing
instruction is unproved. The current runtime excludes the entire occupied
first-pen sample region, retains 32 exact anchors and preserves modal rejection.
The raw 40-anchor operating file is unchanged for historical/native-save
identity. Applied variant and predicate digest are in each run receipt.
A portable regression retains all 410 actual probes from frame 7289, bound to
image SHA `3d71fb9e5c42e18b8e1c9acc0330575a6c1d7e6144330a349788d2976f37850b`.
The old guard rejects it; the current guard accepts it. Missing pixels raise
rather than being invented. In 778 retained frames matches change 441 → 442;
the sole additional match is a visually checked clear park-entry-13 image.

**Notices and partial travel.** Known quarter or parking interruptions have
separate public contexts and accepted/partial outcomes only after the native
interruption and fresh modal observation. Acknowledgment can return to the
street before travel occurs, or complete the park entry after a longer original
transition. Z qualifies the actual destination and never replays the earlier
travel click automatically. After one notice input it polls at most twelve
additional 500 ms intervals; an exhausted budget is still unknown. A direct
original-game probe and the final independent C11 run both required four such
extra intervals. A transitional street drawing is not a completed destination.

**Food drafts and advice.** C5 stopped before food submission under parking
advice. C9 instead encountered it while requesting quantity 12: the stored cash
reservation was 275, representing 11 units. A queued click alone did not establish
its requested effect. Pre-order interruption exposes explicit acknowledgment
and requires a new purchase intent. During a draft, one known advisory is
acknowledged through its original thumb; the resumed selected view and both
cash-reservation and pending-minus-live food counts are checked. If both encode
the requested quantity, no increment repeats. If both encode the immediately
preceding quantity, one newly qualified increment may complete that state goal.
Disagreement stays unknown. UI qualification permits unrelated loan progression;
the protected 500-debit/20-unit native commit proof remains mandatory.
The consistency rules have regression tests using retained native values.
**The mid-draft advisory/reconciliation path was not encountered in the final
native orders and remains natively unqualified.** No old failed draft is retried.

**Native titles and public backups.** Public saves create zpark, zpark-002 and
later revisions without overwriting. Load park chooses the latest saved or
explicitly loaded backup; load zpark-002 selects a named one. The selected resume
bundle is validated and copied into the owned library. Up to 64 named backups
are exposed; reaching that limit removes new-save availability, not navigation.
Native file slot, native title and public name are separate identities. The
save adapter chooses a title unused in the active native files, not a globally
monotonic title across separate immutable backups. C11 actually loaded agent001
and wrote agent002, then loaded agent002 and wrote agent001 into another backup.
Both active slot pairs are distinct; both writes matched all 20 file/live fields.
A verifier helper's assumed literal agent001/agent002 sequence had the wrong
seed offset; its failed assertion is preserved, with independent actual-byte
readback. This is not a failed native save or a claim of global title uniqueness.
C2 independently covered three complete save/fresh-load cycles. Legacy three-,
four- and five-profile manifests require exact original identities; new saves
bind all six. Imported and adapted TextScene hashes are kept separately.

**Sound.** The Mac output was muted at the user's request. Actual headless child
arguments/environment and logs independently confirm SDL dummy audio, mixer
nosound and MIDI device none. This disables host MIDI output that can bypass
SDL audio. Z uses this silent headless mode; opt-in visible-debugger audio
behavior is unchanged. No original game sound/configuration file was edited.

## Source and distribution gates

- Focused continuation, scene/player, package and audio-launch checks:
  **134 passed, 2 skipped**.
- Required full command, python -m pytest -q: **1,579 passed, 118 skipped,
  13 failed, 23 errors**. A fresh main 0.24 export had 1,539 passed, 118 skipped,
  the same 13 failures and 23 errors. All 36 identities match; the local full
  suite remains red. Earlier-head remote test-and-package CI passed; final-head
  checks are reported on the PR rather than inferred from earlier heads.
- Extracted source-package focused checks: **134 passed, 2 skipped**, including
  the original RGB-probe regression. Core/player wheels, source tarball and
  tool ZIP pass archive policy (148/10/477/469 entries respectively). Runtime
  payloads match the accepted wheels; documentation-only edits do not change
  accepted runtime bytes.

## Friction for the next compiler release

1. Make input consumption, effect application and eventual scene arrival separate
   facts. A matching picture or queued input establishes neither of the latter.
2. Provide non-interfering bounded observation batches and checkpoint recovery
   that retains scene qualifiers. Keep effects separate from cleanup receipts.
3. Support cursor, actor, widget-state and transitional-palette exclusions with
   explicit evidence/variants, preserving raw observations and unknowns.
4. Represent interrupted travel and its actual post-notice destination explicitly.
   Allow declarative modal substeps without replaying an uncertain transaction.
5. Express state goals such as draft quantity separately from a plus-button click.
   Original native counters can qualify a new increment; disagreement cannot.
   An RTS build queue or spreadsheet edit interrupted by a dialog is a plausible
   analogous use case, not a tested Dune2/Warcraft/office-application result here.
6. Carry elapsed simulation/presentation effects through optimization contracts:
   input preparation and waiting can change calendar, food, income and loan.
7. Distinguish native disk slot/title/public backup identity and portable named
   load grammar. Do not hardcode an assumed seed-title offset in acceptance.
8. Keep silent headless SDL/mixer/MIDI initialization explicit.

All earlier failed receipts, unknown actions and verifier mistakes are retained
separately. No game executables, resources, full images, saves, databases or
native binaries are in this PR. Only bounded observation/profile data and tool
source are included. This is original-backed playability evidence, not full-game
semantic recovery, a synthetic DinoPark implementation or a model ranking.
