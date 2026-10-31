# DinoPark's game story: behavior contracts for the existing UIL owner

## Purpose and boundary

The useful language-independent model is a park whose committed state changes
through ordered transactions, simulation updates, scene interactions, and
external services. Its story includes the intervals between those changes:
an animal can be paid for but not placed; a cancelled hire can remain in a
pending buffer without becoming an employee; a notice can appear before its
announced payment is credited. Representing those intervals is necessary for
faithful reconstruction.

This document turns preserved evidence into authoring requirements and a
finite map of remaining work. It introduces **no UIL grammar, parser,
interpreter, or competing implementation**. The E42 handoff assigned UIL to
the existing PR #3 owner and described draft PR #7 as a linked-interface RFC.
Grammar and implementation stayed with that owner. That is the historical
ownership record, not a claim about either PR's current remote status. The
parent E55 investigation supplies the current remote-contract assessment.
[E42]

The underlying target is the pinned DOS `DINOPARK.EXE`, SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Guide 0.3 consolidates mechanics and live transactions through E46 and the
E47 media handoff. E51, E53 and E54 add bounded interpreter, resource, and
rendering evidence. This map performs **no new original-game executions** and
does not claim complete-game equivalence, an earned winning campaign, or
coverage of other platform versions. [G:PREF] [E51] [E53] [E54]

The accompanying [rule cards][rules] contain 22 research records. They are an
evidence handoff for an existing representation, not executable UIL syntax.
The [source index][sources] binds every local snapshot and preserved source by
hash and retains the Library identities of Guide 0.3 and the E42 handoff.

## 1. Keep five kinds of completion separate

An action contract needs independent observations of the following boundaries.
Their order belongs to the particular action; this is **not** a universal
five-stage pipeline.

| Boundary | Question the contract must answer | Counterexample to collapsing it |
| --- | --- | --- |
| Input dispatch | Did the relevant handler accept this input under its current guards? | Auction BID can be enabled while an active bidder actor prevents acceptance. |
| Semantic effect | Which state changed, and which remained pending or unchanged? | HIRE changes a draft roster; detail OK does not employ it. |
| Control readiness | Are the next action's controls registered, enabled, focused and semantically current? | A pending staff count can change before FIRE becomes enabled. |
| Rendered observation | Does a completed capture show the intended content, rather than an old page or transition image? | The employment scene request changes while the posters remain visible; a loaded DinoMart registry can precede catalogue redraw. |
| Persistence | Which external bytes were written and successfully read back under the claimed restart boundary? | A record-score ending can follow a short write; an emulator restore does not undo mounted host files. |

These distinctions are established by E41–E47 and the score-writing evidence,
not hypothetical API concerns. A screenshot alone cannot prove a ledger
mutation; a changed ledger cannot prove an actionable display; a successful
ending cannot prove a complete score file. A passive capture did not advance
the measured guest state in E42, whereas the explicitly requested settle wait
did. Retrying a purchase because its picture is old can therefore repeat a
state-changing action. [E42] [M47] [G:STAF] [G:AUCT] [G:SALE]

**Required interface linkage:** each named action should link its semantic
event to the interface identity, target role, applicable control predicate,
input acceptance condition, and content-specific observation predicate.
Information pages need the selected species and displayed title to agree;
the common footer alone is insufficient. Mark a nonvisual action explicitly
when no visual-fidelity claim is intended. Do not invent a universal delay,
universal scene-ready flag, or universal screenshot hook from these scoped
examples. [E42] [M47:auction.information_excursion]

## 2. State is divided by ownership and lifetime

Names should express game meaning while retaining their recovered storage and
lifetime metadata. A host language's object layout is not the contract.

| Domain | Examples | Required distinction |
| --- | --- | --- |
| Committed park | Cash, debt, live pens/herds/fences, active staff, food, facilities, calendar, histories | These values drive the qualified simulation and completed transactions. |
| Draft transaction | Working cash, pending pens/roster/stock/facilities/advertising, animal on cursor | A draft can outlive the screen that abandoned it; synchronization can replace it later. |
| Scene and interface | Current/requested context, selected item, control table, modal acknowledgement, action mode | A request, installed controls and visible page can identify different phases of one transition. |
| Presentation actors | Program position, visibility, frame list/index, motion, deadlines, signal words, dirty tiles | “Animation” includes state transitions and shared-RNG consumption, not just optional pixels. |
| Continuing session | Running RNG, session seed, options, day phase/threshold, shared peanut allowance | Ordinary park loading does not restore every session field. |
| External services | Resource handles, pin flags, sample registry/rate/busy state, stream cursor/error, display surface | These have their own lifetimes and completion/error behavior. |
| Persistent artifacts | Park-save records, opaque bytes, `TOPTEN.DAT`, mounted host files | File contents, immediate loaded state and resumed-scene state are different representations. |

The committed/working-cash distinction is especially important. `DS:BAD4` is
working cash, not cumulative admissions. Income can credit both balances while
a draft reservation remains outstanding. Bank callbacks instead update
committed cash and debt immediately, leaving working cash stale until office
entry synchronizes it. One generic “money changed” event would lose those
different meanings. [G:CASH] [G:RNGS]

## 3. Evidence maturity is a vector, not a percentage

Every rule card names its evidence and its remaining boundaries. Use separate
attributes for structural classification, semantic contract, control-path
evidence, presentation evidence, persistence evidence, and experiment scope.

- **Static:** bytes, tables, direct callers or format boundaries inspected;
  ordinary execution and all indirect callers are not thereby established.
- **Bounded original instructions:** the relevant original body executes under
  declared state and service boundaries. The result does not automatically
  establish a full day, a scene, or physical hardware behavior.
- **Connected instruction sequence:** several actual original components run
  in persistent fixture state, with remaining adapters named.
- **Live original interface:** actual input and rendering establish the stated
  route. Other items, timing variants and campaign outcomes remain separate.
- **Artifact or pixel comparison:** exact bytes or indices are compared under
  a particular input/device/storage contract. Timing, color, audible output or
  restart durability require their own observations.
- **Open:** the missing rule or boundary is explicit. Missing evidence is not
  permission to silently supply a plausible implementation.

E49's snapshot had 926 candidate entrypoints. E53 retained the later
927-candidate inventory and 116 scoped contract records, with 152 unresolved
physical indirect sites and 18,480 bytes in its actual undecoded ledger
category. Those are historical inventory measures. Neither candidate count,
contract count, instruction traversal, nor passing-case count is a semantic
completion denominator. E54 deliberately did not reclassify that whole-binary
ledger. [I49] [H53] [E54]

E47's older ACT directory counts also remain historical. E54 inspected all 57
ACT resources, 1,514 sprites, 48 embedded programs and 679 instructions. A
decoded sprite is not a complete animation; a decoded instruction is not an
executed native scene. E51 qualified all opcode routes in bounded fixtures,
while E54's portable runtime intentionally implements the eleven opcode
values used by the eight DinoMart programs. These claims are compatible and
must not be merged into “all game scripts reconstructed.” [E47] [E51] [E54]

## 4. The simulation story

### R01–R03: Time, daily work and quarter transitions

The common loop invokes presentation/update and input work before its calendar
pause test. Commands precede that test; sound service precedes the requested
scene-transition test. A requested new scene therefore need not skip the rest
of the current iteration. Pause uses counted holds, not a universal suspension
of every subsystem. The initialized day threshold is 20 logical loop
iterations, not an established number of seconds or display refreshes. Bank
visitors and the Diner callback demonstrate RNG activity while the calendar is
held. [G:TIME] [M47:scene.common_loop]

The daily parent orders these semantic effects: weekly-counter advancement;
progression and illness/return; closure-countdown decrement; day advancement;
attendance and concessions; month-close history/inventory/finance; due weekly
wages, food, visitor status, events/fees and escapes; risk-week advancement;
later warnings/overeating and the cash ceiling. The large parent corpus used
declared child-call recorders for most economics, so its strength is ordering,
not a claim that every child combination was simulated end to end. [G:TIME]

A quarter transition can acquire a hold while the current daily call still
finishes due weekly work. Quarter processing can be deferred in designated
shop contexts; the pending flag and cached progression must survive that
deferral. The quarter handler increments the progression computed earlier in
the day rather than recomputing it with later revenue, debt payment or the new
month. Annual handling adds tax/breeding/history and office routing, with
additional hold ownership. The final street arrival release is a distinct
step from clicking Leave. [G:TIME] [G:STAF]

**Authoring implication:** retain logical clock domains, call order, pause
ownership, pending transitions and cached values. Do not make a fresh event
handler recompute a value whose historical calculation is itself state.

### R04–R07: Revenue, staff, feeding and hazards

| Rule group | Recovered invariant worth preserving | Observation and remaining boundary |
| --- | --- | --- |
| R04 — Revenue and reporting | Attendance applies ordered capacity/reach, advertising, grade, price, terrain/season, staffing and hunger/closure effects with intermediate truncation. Actual daily receipts and monthly reported ticket income can disagree. | A graph, profit statement and cash delta are different observables. Full rendered reports are not implied by arithmetic tests. |
| R05 — Workforce | Payroll pays one person per role in repeated role-order passes; each payment needs cash **strictly greater** than that wage. Wages precede feeding. One shared sick-leave timer governs one absent worker; return precedes revenue. | Draft staff, active staff, temporarily available staff and advisory text are separate. Maximum-count and every live interruption remain unqualified. |
| R06 — Food and population | Meat/plant needs aggregate by diet; bins substitute one for one in order. Any active employee satisfies the generic feeding gate. Failed feeding adds seven to shared hunger; successful feeding resets it. Monthly growth precedes seed decay. | Warning absence does not prove feeding success. Predation follows its own hunger/progression gate and ordered victim selection. |
| R07 — Events and losses | Weekly wealth-gated events and visitor-status lotteries use different masks. A selected bit can be consumed without a visible outcome. Escape handling separates unfenced losses, random fence failure and maintenance neglect. | A no-message trace still needs mask/RNG checks. Annual breeding and losses are bounded mechanisms, not optimal long-run policies. |

These are summaries of Guide sections VISI/STAF/FOOD/FENC/EVNT/BRED and their
scoped original corpora. They do not replace those detailed formulas. The map
identifies what a language-independent rule must retain: input domain,
strictness, iteration order, truncation points, state lifetime, and output
meaning. [G:VISI] [G:STAF] [G:FOOD] [G:FENC] [G:EVNT] [G:BRED]

Two useful regression discriminators are already available. Exactly 624 cash
does not retain two 312-wage guards, whereas 625 does. A silent event can set a
mask value of 384, so neither “no message means no transition” nor an eight-bit
mask is faithful. These should be expressible without mentioning Python,
Swift, C or an x86 instruction syntax. [G:STAF] [G:EVNT]

## 5. The transaction story

### R08–R10: Shop drafts, ordinary arrivals and the special refund

There is no universal shop commit rule. General Store/food/land/fence changes
usually stage working cash and pending inventory, then commit on the relevant
confirmation. Their exact cancellation, modal and synchronization routes
differ. Land can continue calendar progress; fence placement holds it. A
fence upgrade charges the full selected fence price and retains electricity
with the slot in the tested route. Advertising activates at quarter transition,
and gift/scenery progression has separate state and RNG effects. [G:SHOP]
[G:FENC] [G:VISI] [M47:park.vegetation]

An ordinary DinoMart purchase is a particularly useful story contract:

| Phase | Cash/herd/history meaning | Required separate observation |
| --- | --- | --- |
| Eligible BUY | Reserve working cash and post the animal expense; committed cash/herd are not yet final. | Selection, stock, funds and room checks; some rejection occurs before debit. |
| Arrival | Native presentation progresses and normal days can pass. | Animation mode, callbacks, sample requests and date progression. |
| Placement | A hold is acquired; an animal is on the cursor or in a pending pen. | Placement controls and actual displayed placement page. |
| Confirm | Commit pens/cash and consume ordinary stock without posting the expense twice. | Commit boundary separately from street readiness. |
| Cancel | Refund and reverse expense against the **current** month; no animal committed. | Pending cleanup and later synchronization remain explicit. |

The recorded April-to-May Coelophysis cancellation leaves +1,250 expense in
April and −1,250 in May while refunding cash and delivering no animal. A rule
that “undoes every field to its before image” would erase original behavior.
The test is a controlled date/phase fixture, not a cross-year or every-species
claim. [G:DNOS]

Vegasaurus is a distinct contract: reserve 25,000, complete the gag or execute
the Animation-off alternative, refund cash, disable the gag, and deliver no
animal. Its tested expense entry remains 25,000. Suppressing pixels must not
suppress that completion/refund. Sound FX and Animation are different inputs.
[G:DNOS] [G:OPTS]

### R11–R13: Auction buying, selling and information visits

Auction buying has a paid-but-unplaced state. BID starts a hand-raising actor;
a later updater accepts the bid; the hammer charges the accepted amount;
another phase exposes placement; Confirm commits pending pens. The current
visit's spending field `DS:585A` changes, while the fifteen checked monthly
financial-history arrays remain unchanged in the qualified purchase route.
This corrects the earlier animal-expense label. Control-enabled, bidder-idle,
bid-accepted, paid, placed and pen-committed are different predicates.
[G:AUCT] [M47:auction.bid_and_hammer]

Seller preparation removes one offered animal per qualified mark before
payment. Watched hammer settlement credits `floor(accepted * 90 / 100)`.
Ordinary early exit instead draws one percentage per outstanding species in
catalogue order, truncates each estimate, sums them and subtracts
`floor(total / 10)`. For gross 7,007 that pays 6,307; replacing it with
`floor(gross * 90 / 100)` would pay 6,306. The live early-exit notice appears
before the credit instructions; acknowledgement is part of completing the
transaction. Cleared sale flags prevent a second payment. [G:AUCT]

Information visits preserve the tested lot/bid state at their exact
reconstruction boundary but advance the continuing RNG across entry, paging,
return and reinitialization. A settled information idle interval is different
from waiting in an active auction. Equal immediate prices do not imply equal
future competition or RNG state. The interface contract needs a content-aware
page predicate and a return/reconstruction boundary. [G:AUCT] [M47]

### R14–R15: Bank and employment

Bank borrowing/repayment commits immediately. Working cash synchronizes later;
the scene owns pause holds and nonfinancial visitor callbacks. Automatic loan
settlement is another event: full calculated payment is debited before the
debt clamp, and foreclosure is tested between them. A debt of 1 with cash 164
can therefore yield cash −1 and debt −164 before the failure route. That route
stops before month increment and later weekly/quarter work; ordinary control
with cash 165 clears the debt. These semantics require ordered effects and an
explicit failed exit, not an atomic “pay min(debt,cash)” rule. [G:CASH]

Employment has nested drafts. Detail OK retains the draft; outer OK commits
it. Detail Cancel resets all role drafts, including edits from another panel.
Outer equal-cash Cancel compares balances rather than roster dirtiness,
preserves active staff, can retain stale pending staff on the street, and
reentry synchronizes the pending roster. The authentic post-helper screenshot
can still show employment posters. The accepted condition and readiness for
the next action must therefore be separate claims. [G:STAF] [E42]

## 6. Numerical and randomness requirements

The export should carry concrete widths and operations, not just prose labels
such as “number,” “flag,” or “random choice.” The following examples are already
source-backed; unlisted fields need their own annotation rather than inference.

| Value or operation | Required semantics | Source |
| --- | --- | --- |
| Committed/working cash, debt, monthly/annual cash baselines | Signed 32-bit storage in the inherited save-field overlay; preserve the operation's original intermediate widths separately. | [S49] |
| Active staff, month/year/quarter, risk-week counter | Signed 16-bit storage in that overlay; normal-range rules do not imply arbitrary malformed values are supported. | [S49] |
| Event mask, counted holds, pause flag, weekly-day counter | Unsigned 16-bit storage; a mask is not necessarily eight bits and a hold count is not Boolean. | [S49] |
| Shared PRNG | `s = (s * 0x015A4E35 + 1) mod 2^32`; output `(s >> 16) & 0x7FFF`. Seed setter accepts 16 bits and clears the upper half. | [G:RNGS] |
| Random mapping | Preserve modulo versus scaled selection and every draw's order/eligibility. F6 uses `floor(rand15 * length / 32768)`, not modulo. | [E51] |
| Signal store | 32 little-endian 16-bit words; addition wraps; consumers can test exactly 0, exactly 1 or another supplied value. | [E51] |
| ACT time and coordinates | Explicit uint32 logical time, original signed comparisons/wrap/sentinels, word coordinates, and the recovered update/scheduler order. | [R54] |
| ACT encoding | Container words are little-endian; instruction word operands use big-endian signed decoding. Read extent can exceed consumed extent. | [E54] |
| Money reporting | Keep actual cash, monthly report, visit spending and history category distinct; preserve intermediate floor/truncation and posting month. | [G:OFFC] |
| Late-year land valuation | Signed-16-bit intermediate followed by truncation toward zero; do not apply its overflow to the different facility formula. | [G:SALE] |
| Raster coordinates | World x differs from scrolled draw x; original word arithmetic and dirty-page Boolean inversion remain observable. | [K54] |

Order is part of random behavior. Illness consumes conditional draws and does
not try again on a return day; birth's second draw occurs only after its first
test succeeds; an early actor's signal write can affect a later actor's branch
in the same scheduler sweep, but does not retroactively rerun wait release for
an earlier blocked actor. Animation-off can remove some draws and add another
in a different branch. Equal images, equal dates, or equal saved park bytes are
not sufficient replay identities. [G:STAF] [G:BRED] [G:RNGS] [E51]

## 7. Persistence and endings are part of the story

### R16: Save bytes, loaded state and resumed scene

The lossless park codec accounts for 75 records / 4,153 bytes; the ordinary
payload map has 71 constant-address chunks / 4,011 bytes. Keep the 48-byte
record at save offset 582 / `DS:C00B` opaque and preserved. The final 100 bytes
are consumed without becoming modeled game state. These coordinates must not
be confused with initialized-EXE file offsets. [G:RNGS] [I49] [S49]

An ordinary load restores some park fields, preserves live session values,
resets others, and then requests reconstruction of the saved scene. Running
RNG/session seed, options, day accumulator/threshold and peanut allowance are
retained at the qualified load boundary. Incoming live-pen geometry and saved
pending geometry differ; some pending buffers survive until synchronization.
The selected auction species is read and then reset. Subsequent scene setup
can acquire holds, synchronize cash and consume RNG. A faithful continuation
therefore needs explicit incoming session state, not invented defaults.
[G:RNGS]

The original loader's accepted short reads and ignored version-comparison
result are documented behavior, not a recommendation for a modern importer.
A safe host can validate into temporary state and commit only a complete
accepted artifact, provided that policy is labelled as a deliberate boundary
from original invalid-input behavior. It must preserve unknown bytes in
lossless round trips and keep unsupported/incomplete continuation explicit.
The E45 restore-associated stall remains a tool/runtime discrepancy, not a
new game rule. [G:RNGS]

### R17: Park sale, score insertion, file write and ending progress

Confirmed sale computes valuation and subtracts debt; ranking uses resulting
cash. Equal existing scores retain priority over an equal new score. The
selected ending state is distinct from later click/countdown transitions and
from actual file persistence. `TOPTEN.DAT` contains ten 25-byte records:
21-byte name plus signed 32-bit score. Missing-file initialization, existing
file reads, short I/O, real DOS score entry, and fresh-process reads have
different evidence scopes. [G:SALE]

A reconstructed ending should expose the sale result, ranking decision,
score-entry acceptance, write result, displayed ending phase, and return-to-
title transition as linked observations. Do not infer a complete write from
the record-score scene. Do not infer a new winning campaign from an existing-
save sale route. External mounted files require their own reset/version
policy when testing emulator restores. [G:SALE]

## 8. Presentation and services have semantic contracts

### R18: Audio and preference changes

Music, Sound FX, Animation and music volume are separate state. FX-off changes
the game-visible busy/wait contract; it is not merely host volume zero. Toggle
ordering clears the repeating marker, and re-enabling does not automatically
resume it. Lookup, submission, busy, wait, stop and cleanup have separate
boundaries. A silent host must still answer the completion queries that drive
the game. [G:OPTS] [M47]

E47 proves exact ABT decoded samples, and a live DinoMart registry in which
CRACKLE's header rate 22,000 becomes playback rate 30,000. Returning to street
replaces the registry. Decoded bytes are not audible waveform/timing or a
complete trigger map. XMI container checks are not event-stream decoding or
synthesis. Scene resources, selected settings and completion behavior belong
in service contracts, while device details may remain explicit adapters.
[E47] [M47]

### R19–R20: Actor programs and pixels

E51 establishes bounded opcode, signal, reset, construction and scheduler
behavior. Reset preserves identity pointers, sprite/resource information and
suspension; it is not a whole-record zero fill. Recognized high-bit waits can
remain blocked because of the original sign-extension comparison. Unsupported
dispatch, blocked state and scheduler return must stay distinguishable. These
rare-path findings must not be described as observed ordinary scene hangs.
[E51]

E54 provides a real processor adapter, standalone DinoMart interpreter and
portable canvas. Fresh original-code comparison matched 2,491 logical ticks;
the connected rendering experiment reused 16 actor observations and added
308 original draw-wrapper calls across 64 frame batches. Do not add the saved
actor replay to the original tick count. The pipeline establishes ordered
requests, pixel indices and dirty maps within declared surfaces, not one
complete original scene running with reconstructed audio and clocks. [E54]

The wrapper forces kind 3, scrolls x for raster output, and marks dirty tiles
with unscrolled world geometry even after rejection. The planar branch has an
explicit four-plane mode-zero/map-mask device model. Palette, scanout, latches,
original mode initialization and background restoration remain outside that
contract. A complete presentation needs the native signal producer and host
timeline as well as the ACT bytes. E55's ABOUT work is a separate acceptance
slice; this map does not predeclare its result. [K54] [E54]

### R21–R22: Resource lifetime and startup/demo context

Resource identity must survive relocation and replacement without importing
x86 far pointers into the high-level game vocabulary. The underlying service
contract must nevertheless retain ownership, Boolean pinning, reload/dispatch
order, stale pointers and partial mutation on failure. E53 qualifies resident
allocation/draw/free paths and selected stream wrappers; backing-store
eviction/reload, resize, shutdown, real loading and fatal cleanup remain open.
A reference-counted or transactional host implementation is a different policy
unless its observable boundary is explicitly justified. [E53] [H53]

NEW GAME, ordinary load, startup and demo load have different initialization
contracts. NEW GAME does not generically reseed or reset every session field.
The demo initial loader reads a seed and reseeds; its later recorded-input
grammar and complete playback remain separate work. Clock-derived seed
fixtures do not establish physical clock resolution. Title/help/education/
ending resource transitions likewise need native orchestration beyond decoded
actor programs. [G:RNGS] [P49:W06] [E54]

## 9. Information the existing UIL representation must be able to retain

These are schema **requirements**, not a proposed serialization or new grammar.
The existing owner's accepted contract determines their eventual spelling.

1. **Identity and scope:** target/resource hashes, rule identity, original
   anchors, supported domain, configuration and version; distinguish a routine
   contract, game event, interface action and whole-scene claim.
2. **Typed state:** numeric width/signedness/endianness, enum or mask meaning,
   units, identity, alias, owner/lifetime, initialization, persistence policy,
   and preserved unknowns. Keep serialized layout separate from runtime state.
3. **Guards and accepted input:** semantic eligibility plus interface/control
   readiness; record disabled, ignored, cancelled and rejected paths.
4. **Ordered effects:** reads, writes, intermediate states, derived caches,
   iteration order, transaction boundaries and partial failures. Do not force
   every event to be atomic or every cancellation to restore a before image.
5. **Clock and scheduling:** logical clock domain, signed comparison, wrap,
   sentinel, wait/release phase, pause ownership, callback order and external
   completion dependencies. State physical timing only when measured.
6. **Randomness:** shared stream identity, incoming/outgoing state, conditional
   draw order, output mapping and scope. A seeded test profile is not proof of
   the native scene's signal or random-event producer.
7. **Outputs and observations:** ordered draws, text/control requests, audio
   requests, errors and return conventions; retain the difference between a
   request, actual service completion and rendered or audible observation.
8. **Interface linkage:** semantic action role, current context/content,
   geometry/focus where known, control guards, scene entry/reentry/cleanup and
   scoped pre/post observation predicates. Allow explicitly nonvisual events.
9. **External artifacts and services:** resource load/unload ownership, file
   byte extents and I/O results, restart boundary, audio busy/stop/cleanup,
   render-surface/palette/timing contract and declared adapters.
10. **Evidence and uncertainty:** source/receipt identities, observed versus
    inferred facts, input fixtures, comparison masks, adapters, unvisited or
    unresolved paths, known contradictions and claim-specific acceptance.

An author should be able to tell the three worked transaction stories above
using these concepts without embedding Python/C/Swift control flow. Exact
arithmetic and control dependencies still need an explicit representation;
“language independent” does not mean “informal enough to omit them.”

## 10. Remaining work, mapped to the preserved plan

| Dependency | Current reusable evidence | Smallest meaningful missing contract |
| --- | --- | --- |
| W01 — Actor language | E51 opcode routes; E54 narrow portable execution | Native signal producers, broader portable subsets and scene-host timing; preserve malformed/error qualifications. |
| W02 — Presentation | E52–E54 qualified drawing and pixel boundaries | Actual background restoration, palette/fade/layering/text and full presentation timeline. |
| W03 — Resources | E53 resident lifetimes and stream wrappers | Backing devices, actual load/replace/free ownership, resize/shutdown and failed cleanup. |
| W04/W05 — Park/shop actors | Known economic state machines and E47 trigger map | Native dinosaur/visitor/vehicle/scenery, arrivals, employee/auction and side-activity phase-to-media contracts. |
| W06 — Startup/help/education/endings/demo | Seed/load and ending rules; ACT programs inspectable | Complete native host orchestration and remaining `INTRO.DMO` recorded-input grammar. |
| W07 — Audio | ABT bytes; selected registry and busy/wait rules | XMI events, actual drivers, every scene trigger and completion timing. |
| W08 — Interfaces | Live readiness counterexamples and named routes | Hit-testing/focus/control lifecycle/text/modal contracts across remaining contexts. |
| W09 — Economics/persistence | Consolidated bounded mechanics and live transactions | Attach existing receipts to uncovered exits/consumers; do not rediscover settled formulas from scratch. |
| W00/W10/W11/W12 — Closure | Historical byte/candidate ledger and service contracts | Aliases, support arithmetic/errors, unknown data/flags, indirect targets and a final finite closure audit. |

The practical next unit is a dependency-connected story, with one declared
initial state and the same external inputs at all compared boundaries. For
ABOUT that means its actual host signal/audio source, actor progression,
ordered drawing, and presentation completion. For a purchase it means its
economic reservation, input/control phases, native arrival and commit/cancel
path. Completing one such unit is useful progress; it is not a reason to
discard the remaining ledger or claim a percentage of the game understood.
[P49] [H53] [E54]

## Source key

- **G** — [Guide 0.3 text-read snapshot][guide], with its original section names
  and E1–E47 evidence index. Original Library item:
  [DinoPark-Tycoon-Mechanics-0.3.md]([private Library link omitted]).
- **E42** — [Interface phases and UIL ownership snapshot][E42]. Original:
  [DinoPark-E42-Report.md]([private Library link omitted]).
- **E47/M47** — [Media report][E47] and [sixteen-record event handoff][M47].
- **I49/P49/S49** — [Inventory report][I49], [ordered work plan][P49] and
  [inherited typed save-field overlay][S49].
- **E51** — [Actor/command-set closeout][E51].
- **E53/H53** — [Resource contracts][E53] and [preserved handoff][H53].
- **E54/R54/K54** — [Integrated pilot report][E54], [runtime contract][R54]
  and [original kind-3 rendering contract][K54].

[rules]: ../evidence/story-map/RULES.json
[sources]: ../evidence/story-map/SOURCE-INDEX.json
[guide]: ../evidence/story-map/Guide0.3-read-snapshot.md
[G:PREF]: ../evidence/story-map/Guide0.3-read-snapshot.md#pref-about-this-guide
[G:TIME]: ../evidence/story-map/Guide0.3-read-snapshot.md#time-days-weeks-months-and-quarters
[G:CASH]: ../evidence/story-map/Guide0.3-read-snapshot.md#cash-money-orders-and-the-bank
[G:OFFC]: ../evidence/story-map/Guide0.3-read-snapshot.md#offc-office-desk-reports-and-sale-markers
[G:VISI]: ../evidence/story-map/Guide0.3-read-snapshot.md#visi-attendance-parking-and-ticket-prices
[G:STAF]: ../evidence/story-map/Guide0.3-read-snapshot.md#staf-what-your-employees-actually-do
[G:FOOD]: ../evidence/story-map/Guide0.3-read-snapshot.md#food-feeding-spoilage-and-planting
[G:SHOP]: ../evidence/story-map/Guide0.3-read-snapshot.md#shop-food-stands-gifts-and-restrooms
[G:FENC]: ../evidence/story-map/Guide0.3-read-snapshot.md#fenc-fences-and-escapes
[G:EVNT]: ../evidence/story-map/Guide0.3-read-snapshot.md#evnt-events-rustlers-and-plague
[G:BRED]: ../evidence/story-map/Guide0.3-read-snapshot.md#bred-breeding-and-herd-size
[G:DNOS]: ../evidence/story-map/Guide0.3-read-snapshot.md#dnos-dinosaur-reference-table
[G:AUCT]: ../evidence/story-map/Guide0.3-read-snapshot.md#auct-auctions-stock-and-bids
[G:SALE]: ../evidence/story-map/Guide0.3-read-snapshot.md#sale-selling-the-park-and-reaching-the-leaderboard
[G:OPTS]: ../evidence/story-map/Guide0.3-read-snapshot.md#opts-music-sound-fx-and-animation
[G:RNGS]: ../evidence/story-map/Guide0.3-read-snapshot.md#rngs-randomness-saving-and-reloading
[E42]: ../evidence/story-map/E42-read-snapshot.md
[E47]: ../evidence/story-map/sources/E47-Report.md
[M47]: ../evidence/story-map/sources/E47-Media-Event-Map.md
[M47:scene.common_loop]: ../evidence/story-map/sources/E47-Media-Event-Map.md#scenecommon_loop
[M47:auction.information_excursion]: ../evidence/story-map/sources/E47-Media-Event-Map.md#auctioninformation_excursion
[M47:auction.bid_and_hammer]: ../evidence/story-map/sources/E47-Media-Event-Map.md#auctionbid_and_hammer
[M47:park.vegetation]: ../evidence/story-map/sources/E47-Media-Event-Map.md#parkvegetation
[I49]: ../evidence/story-map/sources/E49-Report.md
[P49]: ../evidence/story-map/sources/E49-Work-Plan.md
[P49:W06]: ../evidence/story-map/sources/E49-Work-Plan.md#w06-startup-title-helpeducation-ending-and-demo-playback
[S49]: ../evidence/story-map/sources/E49-Save-Field-Overlay.csv
[E51]: ../evidence/story-map/sources/E51-Report.md
[E53]: ../evidence/story-map/sources/E53-Report.md
[H53]: ../evidence/story-map/sources/E53-Handoff.md
[E54]: ../baseline/E54/REPORT.md
[R54]: ../baseline/E54/docs/RUNTIME.md
[K54]: ../baseline/E54/docs/KIND3-CONTRACTS.md
