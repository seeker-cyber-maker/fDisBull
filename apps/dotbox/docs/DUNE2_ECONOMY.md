# Dune II economy, campaign progression and recovery

Status: 19 November 2026. An earlier original Dune II v1.0 run built a Windtrap and
Refinery, completed a full field-harvesting and refining cycle, exercised
separate Harvest and Return commands, and reached the original first-mission
success modal. The run then completed the result presentation, statistics and
local Hall of Fame entry, and reached the campaign's next-region selection map.
This is an authored operational knowledge slice backed by private
captures and original-code analysis. The [evidence receipt](evidence/dune2-economy-2026-11-19.json)
records provenance and the scope of each check. A subsequent separate slice
verified production Hold/Resume, bare-rock Windtrap placement, limited Repair
and ordinary same-process Save/Load. Its [repair and save/load receipt][next-checks]
keeps those tests distinct from the earlier complete-foundation mission win.
A later [Refinery and camera receipt][refinery-camera] covers bare Refinery
placement, one paid repair increment and a specific unit-mode right-click
outcome. That receipt stops before the separately reviewed further win and
recovery below. The [campaign and recovery receipt][campaign-recovery] records
that later mission-one win, region choice, scenario-two entry and one fresh
process ordinary Load of the new `m2` save.

The public [RTS primitives](RTS_PRIMITIVES.md) remain generic contracts. This
contribution adds no public Dune II provider, memory reader, live input route or
desktop-ownership integration. The observed scope now reaches Atreides scenario
two and one fresh-process ordinary-load trial. The earlier complete-foundation
run remains bounded at its campaign-map frontier; full-campaign completion and
scenario-two victory remain unqualified.

## Source and edition boundary

The original executable is identified by SHA-256
`d49f45729babd298fd72d0f623cc3cfaa4c3d144ab38e53f24355f2208b4e5a0`.
An executable hash anchors compatibility but does not identify every resource,
loaded overlay or runtime allocation. New installations still need their own
resource and mapping checks.

The semantic reference is OpenDUNE commit
[`ebea79aeba025be2fe9004570e9255044aacc0be`](https://github.com/OpenDUNE/OpenDUNE/tree/ebea79aeba025be2fe9004570e9255044aacc0be),
whose README requests version 1.07 data. Original instructions and coherent
captures established the v1.0 field meanings used here. A concrete difference
is the original 80-slot structure pool versus the reference's 82 slots; modern
structure layouts and pointer sizes cannot be transplanted. Original refining
also uses a fixed non-player multiplier where the reference varies it. This
study was informed by source analysis and earlier control research.

Public content contains authored facts and hashes. Original game files,
images, saves, RAM, disassembly and private analysis records remain excluded.
No OpenDUNE source code is copied into this contribution.

## Construction is a set of independent operations

The observed route uses construction-yard selection, catalogue interaction,
production, placement arming, target preview, placement submission and explicit
tutorial responses. The planner chooses each operation from current state;
these milestones do not become an unconditional input sequence.

| Milestone | Evidence needed before claiming it |
| --- | --- |
| Product selected | Current catalogue choice and producer identity |
| Production started | Allocated off-map product, producer link, busy state and changing countdown |
| Product ready | Countdown reaches zero and the producer reports ready; placement remains separate |
| Placement armed | Current placement mode and the coherent active product |
| Target preview ready | Intended tile agrees with stored and rendered preview positions and current validity |
| Building placed | On-map record, footprint occupancy and relevant house totals |
| Gameplay resumed | Current phase and input readiness after any tutorial or other event |

Independent review checked 52 frozen building/delivery captures, 520 memory
chunk receipts and 50 request/response pairs. Four concrete tiles supported the
Windtrap and six supported the Refinery. Their resulting HP/max HP were
200/200 and 450/450. The Windtrap produced 100 power; adding the Refinery left
production at 100, raised use to 30 and established storage of 1005. Those are
observed values for this original scenario. [Evidence receipt](evidence/dune2-economy-2026-11-19.json)
contains the review identity and milestone hashes.

### Placement needs a current preview position

A failed slab attempt exposed an original ordering rule: the PLACE click
handler calculates the new event tile but passes the stored preview position
to placement. A later hover invocation updates that stored position and its
validity. Moving and clicking together can therefore attempt the preceding
preview tile. Concrete placement revalidates the position it receives; this
is not merely a stale validity display.

The retained refusal left the intended tile unchanged. After the new preview
was observed, a separately chosen click succeeded. Original code corroborates
the argument source and return-before-hover ordering; the first call's arguments
were not captured in a breakpoint trace. Later Windtrap and Refinery placements
used matching current/rendered previews before their single placement clicks.

The provider requirement is a target-bound transaction: move the pointer with
no button held, allow a bounded original-loop update, observe the chosen tile's
preview, and then send one click. Keep the active product, camera, ownership,
frame, phase and observation identity coherent. A refusal remains a refusal;
it does not trigger an automatic second click. The reference has the same
ordering in [GUI_Widget_Viewport_Click][viewport].

### Modals and presentation can outlive a state change

Original tutorials appeared after placement had committed. In one concrete
event, a raw placement pointer still named its now-unused terrain-construction
slot while a nested tutorial suspended cleanup. Retain an aligned raw candidate
as an unused slot; do not manufacture an allocated structure from the pointer.
Later event completion cleared it. Invalid, misaligned or out-of-pool pointers
still require refusal.

Other captures show cleared placement pointers and enabled timer bits while a
tutorial remains visible, or rendered selection and building graphics lagging
the committed state. An old refusal banner also persisted after a later success.
Neither a pointer, timer bit, label nor single banner establishes current input
readiness. `respond_to_event` remains an explicit primitive, and confirmed
placement must survive a later presentation gap. Reference context: [gui.c][gui],
[viewport.c][viewport] and [structure.c][structure].

## Costs, foundations, power and storage

| Item in the tested opening | Cost | Footprint | Observed economic role |
| --- | ---: | --- | --- |
| Concrete slab | 5 | One tile | Four slabs for the Windtrap and six for the Refinery cost 50 in total |
| Windtrap | 300 | 2 by 2 | Full foundation; 100 power production |
| Refinery | 400 | 3 by 2 | Full foundation; 30 power use and 1005 current storage |

The reviewed ledger reconciles from the observed gameplay balance:
`999 - 50 - 300 - 400 - 1 = 248`. The additional one-credit debit is strongly
supported as maintenance by the original deadline/debit code and matching
before/after state; the exact debit instruction was not traced. The earlier
scenario allocation of 1000 is a different milestone.

Production spends credits incrementally with a fractional remainder. Original
code ties progress to producer HP and can put production on hold when credits
are insufficient. Do not infer a universal production-rate multiplier directly
from the power ratio. The current action, countdown, actual credits and hold
state are separate observations. The displayed credit counter animates toward
the ledger and can temporarily disagree with it. [Original evidence receipt](evidence/dune2-economy-2026-11-19.json);
reference [structure.c][structure] and [house.c][house].

Own concrete counts for placement adjacency. Original validation returns zero
for invalid placement and can return a negative missing-foundation count for
otherwise valid ordinary buildings. Bare-rock placement can therefore be legal
with reduced starting HP. A generic building adapter must interpret that
condition, rather than treating every negative result as rejection. The earlier
mission-winning run used complete foundations. The subsequent Windtrap and
Refinery tests below directly verify legal bare-rock placements and reduced
initial HP for those two footprints; other buildings and mixed-foundation
arrangements remain separate tests.
[structure.c][structure] provides the reference correlate.

Storage, actual credits, displayed credits and the scenario's initial
no-storage allowance have distinct roles. The observed capacity is scenario
state, not a promise about every Refinery or Silo in every edition.

## Further original checks: Hold, Repair and ordinary Save/Load

These checks cover one Windtrap in Atreides mission one, across two isolated
original processes. Hold/Resume was observed in the first process before its
later terminal timeout. Bare placement, Repair and Save/Load were observed in
the fresh sliced-wait process; no uncertain operation was replayed. The
[bounded-wait report](evidence/bounded-wait-2026-11-19.json) records that runtime
boundary. The [new evidence receipt][next-checks] records each test's scope.

### Hold and Resume have separately observed effects

The producer's Hold flag, production countdown and actual credits establish
whether production stopped. The product's own record is a different object.
The same production panel can offer Hold, Resume or placement according to
current state; it is not a fixed-action button.

| Observation | Producer countdown | Actual credits | Producer Hold |
| --- | ---: | ---: | --- |
| Hold accepted and observed | 11264 | 974 | On |
| After a separate 3,000 guest-ms observation, with 180 game ticks elapsed | 11264 | 974 | On |
| After an independently selected Resume and 2,000 guest-ms observation | 10496 | 956 | Off |

The countdown and credits changed while the initial Hold input was being
consumed, then remained stable during the independent held interval. This does
not establish instantaneous delivery or a universal production rate. Displayed
credits also lagged the ledger: the held capture's displayed-credit memory field
was 979 while actual credits were 974, and that field later caught up. These
last-completed frames are 1–15 guest ms older than stopped RAM, so sampled
displayed-credit fields need not equal the exact frame digits. [Test receipt][next-checks].

### Bare placement and a bounded repair

The separate preview selected a 2-by-2 Windtrap footprint with four missing
concrete cells and matching stored/rendered position. Original validity was
`-4`; one subsequent placement committed the building at **100/200 HP**, with
raw house power production **50**. Placement and the ensuing construction and
Windtrap tutorials were distinct events, each inspected before the next action.
One preview tile retained a partial-fog overlay despite its unveiled flag. The
successful original placement therefore does not qualify current-visible
admission for all four cells. [Test receipt][next-checks].

After the tutorials, a separately selected Repair action set both Repair and
Hold on the Windtrap. A bounded observation increased HP from **100 to 105** and
reduced actual credits from **699 to 685**. An independently selected repair-off
action cleared both flags. During a further **2,000 guest ms**, HP and credits
remained at 105 and 685. The displayed-credit memory field was still 694 after
the debit, illustrating why accounting needs the actual ledger.

Original instruction analysis explains the observed repair price. For positive
values in this tested case, its fixed-point calculation is:

```text
fraction = floor(10 * 256 / nominal_HP)
credits_per_step = floor((fraction * build_price + 128) / 256)
```

With nominal HP 200 and build price 300, the original result is **14 credits per
paid +5 HP step**. The pinned OpenDUNE [structure.c][structure] uses factor **2**
instead of the original **10**; its repair price cannot be substituted. A later
separate repair interval added 10 HP for 28 credits. Neither interval tested
full repair. The original strict-greater-than completion comparison and the
insufficient-credit branch remain source findings, not live qualifications.
Original analysis and executable hashes are pinned in the [test receipt][next-checks].

The visible Windtrap panel showed output **52** at 105 HP while the raw house
power field still read **50**. After the later interval it showed **57** at
115 HP, with the house field still 50. Ordinary loading subsequently restored
105 HP and the house field read **52**. Keep displayed output, building HP and
stored house totals separate; this test does not establish their general refresh
schedule. [Test receipt][next-checks].

### Ordinary Save/Load restores state and creates an observation boundary

The original Options menu, Save This Game entry, empty slot, description field
and Save confirmation were inspected as separate operations. Saving description
`r1` created a **3,884-byte** `_SAVE000.DAT`; its retained digest and description
anchor the tested file. Menu closure alone was not the success criterion.

The saved state had **105 HP**, **685 credits**, and Repair/Hold off. A deliberate
ordinary repair after saving changed it to **115 HP**, **657 credits**, with both
flags on. Selecting `r1` through the original Load A Game menu restored **105 HP**,
**685 credits**, and both flags off. A further independent observation reached
the completed gameplay frame with those restored facts. That trial established
**same-process ordinary game Save/Load**. Its scope did not include cross-process
loading; the later `m2` test below qualifies one fresh-process ordinary load.
Other save formats and native `state.load` remain unqualified.
[Test receipt][next-checks]; reference context:
[save.c][save] and [load.c][load].

The initial load capture already held the restored ledger but still reported
displayed credits **65535** and timer mask 1. That displayed value was a transition
sentinel, not spendable funds or a victory balance. The later completed capture
reported actual/displayed credits 685 and timer mask 3. A timer bit or credit
counter alone does not establish current input readiness.

Loading did not rewind the native or game clocks. At the initial restored
capture, the game clock was 2290 and the scenario-start value became 98,
retaining the saved elapsed mission time of **2192**. The reference's
[scenario-time serialization][save-info] offers a correlate; byte-identical
memory or a rewound runtime clock is not the acceptance condition.

Treat the load as a new observation boundary: discard old object keys, selection
intents, targets and placement previews, then inspect fresh rendering and state
before choosing another action. The test records this boundary explicitly. The
sliced-run reader still reports entity candidates, current visibility false and
action admission false; these results install no public Dune II provider.

## Bare Refinery and context-click follow-up

This follow-up continues the same sliced-wait process after the ordinary load
had returned to normal rendering. The construction and repair review covers
requests 31–52. The later camera check covers requests 57–59, with request 56
used only as its prior camera and selection baseline. These are bounded tests
in the same Atreides first mission. The [Refinery and camera receipt][refinery-camera]
keeps their hashes and scope separate from the earlier mission-winning run.
All observation durations in this follow-up are native guest time.

### Build, move units and place remain separate choices

The fresh catalogue offered **Spice Refinery for 400 credits**, backed by
original structure type 12. Choosing Build This was followed by active
production: an allocated off-map product, a changing producer countdown and
credits falling from 685 to 675. No separate warning acknowledgement or second
Build input was required in this recorded interval. Completion later showed
Place It, countdown zero and **285 credits**, reconciling the full 400-credit
purchase. This does not establish a universal warning-repetition rule or exclude
an uncaptured transient frame. [Test receipt][refinery-camera].

Two Trike moves were independently chosen while production continued: select
the unit, choose Move, then choose its destination. The southern Trike cleared
the future footprint and reached tile (30, 29); the northern scout reached
(34, 24), after which eastern spice-colored terrain was visibly rendered. Their
destination samples before the commands were different: the southern tile was
not unveiled and had full-fog overlay 123; the northern tile was unveiled but
had partial-fog overlay 110. The successful ordinary coordinate moves establish
no pre-command current-visible admission for either destination. Later rendered
terrain supplies the new observed map knowledge. [Test receipt][refinery-camera].

Placement was armed only after production completed. A separate pointer move
then produced matching stored and rendered previews at tile **(30, 27)**,
packed position 1758. The signed placement result was **−6** for the 3 by 2
bare-rock footprint. All six coherent tile samples were unveiled, had clear
overlay zero and had no unit or structure occupant. The next placement click
committed the Refinery at **225/450 HP**, with all six cells naming its structure
slot. House storage became **1005**, power production remained **52** and use
became **30**. [Test receipt][refinery-camera].

The placement capture still displayed the Refinery tutorial. A separate response
returned to normal rendering. A later harvesting hint likewise required its own
response, even though the timer mask already read 3. Those committed state
changes do not promote the tutorial captures to gameplay-input readiness.

### Starter cargo, storage and paid repair have distinct accounting

The newly allocated Harvester began off-map with one cargo unit. Its later
deployment changed cargo from 1 to 0, actual credits from **285 to 292**, and
the allied processed-spice statistic from **0 to 7**. This records conversion
of the initial cargo. The construction/repair slice itself contains no field
cargo gain or completed harvesting-and-return cycle. [Test receipt][refinery-camera].

Selecting the Refinery showed **MAX 1000** on the panel. The coherent house
storage field and current original Refinery type field both read **1005**.
Keep the panel label, storage fields, actual credits and displayed credits as
separate observations; none supplies a universal capacity or refresh rule.

| Repair milestone | Actual credits | Refinery HP | Repair / Hold |
| --- | ---: | ---: | --- |
| Before Repair | 292 | 225/450 | Off / Off |
| After one paid increment | 284 | 230/450 | On / On |
| After stopping, then 2 seconds of observation | 284 | 230/450 | Off / Off |

The stopped interval covered 120 game ticks. The observed **8-credit cost for
5 HP** agrees with the original repair factor 10, base HP 450 and price 400:
`floor(2560 / 450) = 5`, then `floor((5 * 400 + 128) / 256) = 8`.
This tests one paid increment and its stop, with no full repair or insufficient-
credits branch. The ledger reconciles as **685 − 400 + 7 − 8 = 284**.
At the final stable capture the displayed-credit memory sample was still 286;
the ledger was stable before that display sample had caught up. Memory display
samples also need not match the exact digits in the last completed frame.
[Test receipt][refinery-camera].

### One ordinary unit-mode right-click moved the camera

With Harvester slot 39 selected in ordinary unit mode, moving the pointer to
guest pixel **(239, 100)** and observing for one second left the camera at tile
**(23, 21)**. That one edge-hover test supplies no general conclusion about
other scroll inputs, edge positions or modes.

A separately chosen right-click at **(224, 112)**, followed by one second of
observation, changed both requested and rendered camera position to **(30, 20)**.
The actual frames show the resulting view change. Harvester 39 remained
selected; its sampled position **(9856, 6016)** in fixed-point units of 1/256
tile, cargo **15**, and action **5 (Harvest)** were unchanged across that click
interval. Its raw flags and record digest did change, so the claim is limited
to those named fields. [Test receipt][refinery-camera].

After a further 25 seconds without a new input, the view remained at (30, 20)
and cargo reached **32**, with actual credits still 284. This supports continued
field collection in that later interval, without a demonstrated return,
unload or victory in this checkpoint. The rendered status banners read 13%
and later 31%, whereas the stopped cargo samples were 15 and 32. A banner and
a later memory sample are separate evidence.

The observed context-click is one camera outcome in ordinary unit mode. It is
not a universal right-click Move or Cancel binding, and no target-selection,
placement or modal context was qualified by this test. All retained projections
remain candidates with current visibility and action admission false. No public
Dune II provider or runtime behavior is added. [Test receipt][refinery-camera].

## Harvester commands and the observed economy loop

The original Harvester action list is Harvest, Move, Return and Stop. Harvest
and Move arm target selection. Return and Stop issue unit commands without a
second target click; completion can still be deferred by movement or scripts.
Original Harvest targeting uses the fresh clicked tile, unlike building
placement's stored-preview argument. Reference: [actioninfo.c][actions],
[widget_click.c][widget] and [viewport.c][viewport].

The earlier complete-foundation run established these separate outcomes:

| Observation | Result and scope |
| --- | --- |
| Refinery placed | Original game allocated and delivered a Harvester without a separate purchase input |
| Starter cargo processed | One preloaded cargo unit produced 7 credits, then the Harvester deployed; this alone was not field collection |
| First field cycle | Cargo reached 100, automatically returned, entered the Refinery, unloaded to zero and redeployed |
| Full-load accounting | Credits rose 255 to 955 and the allied processed-spice statistic rose 7 to 707: exactly 700 for 100 cargo |
| Explicit Harvest | Selecting Harvest armed its target mode; a separate choice of a currently visible field led to 10 cargo |
| Explicit Return | One Return command produced return travel and Refinery entry with that partial load; no target-click sequence followed |
| Result | The original first-mission success modal appeared with actual/displayed credits 1005, cargo zero and processed-spice statistic 777 |
| Campaign continuation | Explicit result responses led through statistics and local score entry to the next-region selection map; the campaign index advanced from 0 to 1 |

The explicit partial load began at 954 credits. Six cargo units unloaded while
actual credits reached 996 and displayed credits still read 977. Processing the
remaining four brought the processed statistic from 749 to 777 and the ledger
to its observed 1005 storage cap. A nominal 70-credit ten-unit load and a
51-credit balance increase are consistent with 19 credits clipped by that cap;
the cap's exact write was not traced. Do not replace observed accounting with
an assumed `cargo * 7` net balance change. Reference: [RefineSpice][script-structure]
and [house.c][house].

The raw flag called `inTransport` has an overloaded meaning. Original harvesting
itself sets the flag while the unit remains on the map and cargo increases.
It cannot alone prove Carryall occupancy. Physical carrying or Refinery entry
needs coherent links, on-map status and the relevant carrier/building state.
Likewise, action ID Harvest alone does not prove collection; current terrain
and cargo growth matter. Reference: [Script_Unit_Harvest][script-unit].

### Automatic search and player knowledge

The original automatic spice-search helper checks terrain, bounds and occupancy
without a player-visibility filter. Its existence does not expose hidden spice
coordinates to the player. Keep the engine's autonomous choice separate from
explicit targeting based on current permitted observations.

Camera movement changes the view; controlled-unit movement supplies scouting
and terrain reveal. A selected Harvest target must be a player-observed field.
The automatic player search radius/retry cadence and complete EMC script flow
are not recovered by this slice. In particular, the reference's radius-20 AI
Carryall branch is not a general player search rule. References:
[Script_General_SearchSpice][script-general], [Map_SearchSpice][map] and
[Unit_RemoveFog][unit].

## Identity and visibility findings for the world adapter

**A slot is not an entity lifetime.** Reviewed captures show one unit slot
holding an opposing Soldier, then explicitly unused, then an owned Harvester.
This establishes actual slot reuse without assigning a cause or attacker to
the earlier unit's disappearance. Selection, logical-group membership and
pending commands need a qualified incarnation or observation-local identity.
This applies the existing [RTS identity contract](RTS_PRIMITIVES.md) and
[reused-storage guidance](REVERSE_ENGINEERING.md).

**The earlier private candidate projection had a confirmed omission.** Its conservative
requirement of an unveiled tile with overlay zero omitted moving own units
that were visibly rendered over nonzero sand-track overlays. Original rendering
analysis confirms that such background overlays can coexist with visible ground
unit sprites. An independent unchanged-reader replay reproduced the omission.

The next test slice qualified a narrow private correction against the frozen
original captures. It retains the old clear-tile diagnostic rows and adds own,
allocated, on-map ground-unit candidates on verified sand-track overlays, with
exact occupancy, matching requested/rendered cameras and the existing viewport
limits. Original renderer hashes and the tactical icon table guard the extension.
Unknown non-fog overlays do not gain this extension. The conservative fog band
remains excluded. Reference [Tile_IsUnveiled][sprites], [Map_IsPositionUnveiled][map] and
[GUI_Widget_Viewport_Draw][viewport] inform that correction; the original and
reference unit-loop bounds differ.

The same screenshot-derived positive regression fails on the unchanged reader
and passes on the candidate, adding exactly the two witnessed own units in the
original scouting capture. Fifty offline checks and replay of all 113 retained
captures passed; an independent review also checked four additional pointer/debug
negatives. All 111 existing saved world outputs were reproduced by the unchanged
reader, and the candidate removed no legacy rows. Two historical decoder refusals
have no saved world output and are retained as such. See the
[qualification receipt](evidence/dune2-observation-qualification-2026-11-19.json).

This correction does not establish current visibility. The old reader had no
qualified phase, frame-relationship or durable entity-lifetime gate to preserve;
those remain missing. Eight result/map captures retain world rows after tactical
icon resources have changed, and the extension disables itself there. A success
modal can still retain matching tactical resources. Resource checks alone are
therefore insufficient. The candidate explicitly reports current visibility and
action admission as false. Its consumer must retain those qualifications and
call the list entity candidates, without a visible-entities alias.

The correction and raw regression fixtures remain private diagnostic material;
this public guide does not install a Dune II reader or provider. Do not treat
projection omission as absence, promote retained modal rows to current game
objects, or broaden action admission from a screenshot alone. The public
projector continues to consume provider-asserted visibility. See the
[world model](WORLD_MODEL.md).

## Earlier mission-one result

In the earlier complete-foundation run, the visible original success modal
establishes mission-one success. The source also explains why a quota-like
credit number alone was insufficient: original
mission checks have an elapsed-game-time gate and periodic evaluation, and the
quota predicate consumes displayed credits. No tick-rate conversion or win
flag is inferred from a timeout. The private decoder continues to report an
unknown visible-win result; the frame/event witness supplies the success claim.
Reference: [opendune.c][game].

The result presentation was acknowledged explicitly. Proceed opened the results
and advanced the campaign index from 0 to 1. The completed original statistics
show score 89, game-reported time 7 minutes, rank Desert Mongoose, spice totals
777 versus 0, and units destroyed 3 versus 0. These aggregate statistics do not
identify the cause or attacker behind a particular earlier disappearance, and
the game-reported time is not a cold-start or harness-performance measurement.
After local Hall of Fame entry and Resume Game, bounded observation of the
campaign narration reached the next-region selection prompt. That earlier run
stopped at this frontier and did not select a second scenario. The later reviewed
continuation below has its own evidence. Exact success, statistics and campaign
map screenshot hashes from the earlier run are retained in its
[evidence receipt](evidence/dune2-economy-2026-11-19.json).

## Further win and campaign continuation

The [campaign and recovery receipt][campaign-recovery] covers a later mission-one
win, a fresh region choice, scenario-two entry and a separately prepared ordinary
save recovery trial. The earlier receipts keep their original boundaries.

### A balance, a result screen and a battlefield are different boundaries

In the later run, one full field load converted **100 cargo into 700 credits**.
An independently chosen Return with a later eight-unit partial load added 56 to
the processed-spice statistic but only 22 to the treasury, reaching the current
1005 storage cap. The observed ledgers are `284 - 1 + 700 + 22 = 1005` and
`7 + 700 + 56 = 763`. The one-credit decrease and Refinery HP falling 230 to 209
have no established cause. The 34-credit gross/net gap supports the original
storage-clamp interpretation; discarded credits were not traced individually.

Request 0069 had the quota balance but still showed the battlefield. A separate
3,000-guest-ms observation produced the original success modal at 0070. Later
completed statistics showed score 89, game-reported time 6 minutes, Desert
Mongoose, processed spice 763/0 and destruction totals 2/1 units and 0/0
structures. Local Hall of Fame entry was accepted; restart persistence of that
entry was not tested. These statistics belong to this later win.
[Checkpoint receipt][campaign-recovery].

Resource identity also remained separate from phase. The track-resource check
failed during the congratulations presentation, then passed again on statistics
and Hall of Fame screens. A passing resource check does not make a screen
tactical or admit actions against retained entity candidates.

The strategic choice used a fresh binding to the current map, original code,
resources and offered rows. With the selection prompt visible, all 121 pixels
around the inspected click at (92, 84) mapped to region 8; its current REG entry
mapped to scenario 2. One click selected it. This qualifies that choice, not a
general selector. The pictured Rocket Turret question then accepted the ordinary
answer `rocket turret`; no hidden expected-answer buffer was used. The next
briefing gave a **2,700-credit objective** and warned of an Ordos base. The warning
disclosed no tactical enemy positions. [Checkpoint receipt][campaign-recovery].

Scenario ID changed to 2 while prior-mission candidate pool data remained. The
briefing later held the new **1,200-credit** state but still had selection mode 0,
timer mask 1, a displayed-credit sentinel of 65535 and a tactical icon-table
mismatch. After the observed Proceed choice at 0107, the frame showed the new
battlefield: own Construction Yard at (31, 41), 400 HP, camera (24, 37), matching
track/fog table identities, mode 4 and timer mask 3. Old mission keys and intents
were discarded at this boundary; the private fields `current_visibility_established`
and `action_admission` remained false.

### An ordinary save crosses a process boundary

After preserving the earlier `r1` bytes, the original Save menu selected that
existing slot and renamed it `m2`. One Save produced a **4,506-byte** ordinary
save, with 1,200 credits, scenario 2/campaign 1 and 69 elapsed game ticks. Root
then deliberately closed the source host process; its terminal receipt confirms
it was reaped with return code 0. This was host closure, not in-game Quit.
The exact save and completion witness are pinned in the
[checkpoint receipt][campaign-recovery].

A separately prepared process staged those same save bytes and selected `m2`
through the ordinary Load menu once. Startup/menu decoder refusals preserved
raw frames and native receipts without fabricating world entities. Restored
fields appeared at request 0006 while the frame was black; another two-second
observation remained black.
A separate five-second observation reached the tactical view at 0008. The
earlier “tactical-ready” capture label did not establish readiness. Options
then visibly opened, Continue closed it to a dim view, and a further one-second observation
produced the normal final frame at 0011. Those durations are guest time. Mode 4
persisted while Options was open, so mode alone did not establish UI context.
Original instruction and stack evidence links the two black samples to voice and
resource preparation; that finding adds no universal black-screen or phase rule.

The first restored state had 1,200 credits and 69 elapsed game ticks. Its new
absolute game clock was 0 and scenario-start value 4294967227: unsigned 32-bit
subtraction still gives 69. The final observed state had 1,199 credits and
325 elapsed ticks; the one-credit decrease has no established cause. The named
saved fields restore while clocks, rendering and subsequent gameplay advance;
loading does not rewind the previous process or reproduce byte-identical memory.
Fresh object and control bindings must be observed again.
[Checkpoint receipt][campaign-recovery].

The separately declared **prepared-save recovery** profile measured
**169.926726539 host seconds against a 180-second budget**, from before wrapper
preflight and launch through root's final acceptance, including intervening
observations and tool/coordination time. Earlier preparation and save import
were outside this interval; its deadline was not renewed. The earlier prepared
opening result remains **285.051091492 seconds against 180**, a miss. These are
different trials and neither is a general cold-start or recovery-time promise.
[Checkpoint receipt][campaign-recovery]; [earlier timing receipt][wait-evidence].

## Remaining qualification

Building, accounting, campaign and recovery reviews have separate evidence
scopes in their receipts. Full-campaign play, scenario-two objective completion,
other houses, broad combat/NPC behavior, automatic script recovery, current visibility
qualification, reusable provider integration and original-Dot
ownership qualification remain separate work. The next adapter should preserve
independent primitives, current observation fences and explicit event responses
while reusing these learned conditions.

[viewport]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/gui/viewport.c
[widget]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/gui/widget_click.c
[gui]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/gui/gui.c
[actions]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/table/actioninfo.c
[structure]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/structure.c
[house]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/house.c
[unit]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/unit.c
[script-structure]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/script/structure.c
[script-unit]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/script/unit.c
[script-general]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/script/general.c
[map]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/map.c
[sprites]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/sprites.c
[game]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/opendune.c

[next-checks]: evidence/dune2-repair-save-load-2026-11-19.json
[refinery-camera]: evidence/dune2-refinery-camera-2026-11-19.json
[campaign-recovery]: evidence/dune2-campaign-recovery-2026-11-19.json
[wait-evidence]: evidence/bounded-wait-2026-11-19.json
[save]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/save.c
[load]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/load.c
[save-info]: https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/saveload/info.c
