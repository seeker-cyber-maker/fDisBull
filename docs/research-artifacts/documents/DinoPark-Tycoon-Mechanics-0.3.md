# DinoPark Tycoon: Mechanics Guide and Evidence Baseline

**DOS edition, 1993 | Mechanics closeout 0.3 | 27 October 2026**

**Author: TiGa / TiGa-RCE, with AI-assisted investigation and writing**

> **READ THIS FIRST:** Mechanics closeout is not complete-game equivalence.
> This edition consolidates the original-DOS mechanics and live transaction
> evidence through E46, plus E47's media handoff and sound-sample decoding.
> Real existing-save sale, ending and score-writing routes are established.
> The opening checklist remains proposed strategy, not an earned first-year
> campaign or globally optimal policy. The JavaScript Lab remains 0.8 and the
> Swift reconstruction is a separate implementation. Media timing, composition
> and some saved/session-state semantics remain explicit qualifications.

## Contents

- [PREF: About this guide](#pref-about-this-guide)
- [FAST: A cautious opening checklist](#fast-a-cautious-opening-checklist)
- [QUIR: Quirks, traps and misleading numbers](#quir-quirks-traps-and-misleading-numbers)
- [TIME: Days, weeks, months and quarters](#time-days-weeks-months-and-quarters)
- [CASH: Money, orders and the bank](#cash-money-orders-and-the-bank)
- [OFFC: Office desk, reports and sale markers](#offc-office-desk-reports-and-sale-markers)
- [VISI: Attendance, parking and ticket prices](#visi-attendance-parking-and-ticket-prices)
- [STAF: What your employees actually do](#staf-what-your-employees-actually-do)
- [FOOD: Feeding, spoilage and planting](#food-feeding-spoilage-and-planting)
- [SHOP: Food stands, gifts and restrooms](#shop-food-stands-gifts-and-restrooms)
- [FENC: Fences and escapes](#fenc-fences-and-escapes)
- [EVNT: Events, rustlers and plague](#evnt-events-rustlers-and-plague)
- [BRED: Breeding and herd size](#bred-breeding-and-herd-size)
- [DNOS: Dinosaur reference table](#dnos-dinosaur-reference-table)
- [SIDE: Peanuts, Window shop and the Diner fly](#side-peanuts-window-shop-and-the-diner-fly)
- [AUCT: Auctions, stock and bids](#auct-auctions-stock-and-bids)
- [SALE: Selling the park and reaching the leaderboard](#sale-selling-the-park-and-reaching-the-leaderboard)
- [OPTS: Music, Sound FX and Animation](#opts-music-sound-fx-and-animation)
- [RNGS: Randomness, saving and reloading](#rngs-randomness-saving-and-reloading)
- [FAQS: Myths and practical questions](#faqs-myths-and-practical-questions)
- [OPEN: What this baseline does not claim](#open-what-this-baseline-does-not-claim)
- [ENGN: Evidence, build identity and methods](#engn-evidence-build-identity-and-methods)
- [CRED: Credits, licence and revision history](#cred-credits-licence-and-revision-history)

## PREF: About this guide

### What changed in the closeout edition

The main mechanics-recovery branch is now a consolidated, bounded baseline.
Later original-interface evidence is integrated instead of leaving thirteen
addenda to contradict old "not yet tested" statements. Historical test counts
still describe their original scopes; this edition did not rerun every corpus.

The important correction is auction accounting: a winning buyer's hammer charge
updates current shopping-visit spending, not the monthly animal-expense history.
Seller proceeds do reach the sale-income history. The guide preserves that
asymmetry. [E44] [E45]

A separate media map records resource identity, triggers, state changes,
completion conditions and RNG/clock dependencies. E47 adds exact decoded ABT
sample-byte comparisons and a live sample-rate observation, not a full renderer
or a competing UIL implementation. [E47]

This project approaches an old management game from two directions: what a
player needs to decide, and what the original program actually does. TiGa's
reverse-engineering approach informs the latter.
The aim is to replace folklore with checkable explanations, not to pretend
that every unknown has already been solved.

The sources are the supplied DOS executable and data, bounded execution of
its original instructions, earlier recorded observations, and clearly
identified player-guide hypotheses. The investigation has revised its own
conclusions several times. The corrections below supersede older statements
about annual escape counters, flat capacity, cumulative "takings," and
first-day-only random events. Edition 0.2d also corrects the earlier
"slow-update gate" name: that field is the Animation preference, not the
simulation-pause control. Edition 0.2f also corrects the old Vegasaurus
"sound-off" label: that test actually varied Animation, not Sound FX.
The historical observations remain valid within their declared scope; the
preference attribution is corrected here.

### How to read the evidence labels

- **Verified mechanics:** original instruction execution in a bounded test,
  with declared inputs and intercepted subcalls. This is not automatically
  an end-to-end game observation.
- **Static finding:** original bytes, tables or control flow inspected without
  executing the complete relevant game interaction.
- **Recorded observation:** an earlier original-game run described by its
  receipt; not newly repeated for this guide.
- **Proposed strategy:** a recommendation inferred from mechanics, not a
  demonstrated optimal or winning playthrough.
- **Open:** the necessary evidence is still missing.

Evidence codes such as **[E3]** lead to the index in [ENGN]. This guide
is deliberately limited to one fingerprinted DOS build. Do not assume the
Macintosh or 3DO versions behave identically.

## FAST: A cautious opening checklist

**Proposed strategy, not a tested victory route.** A management game is not a
fixed adventure-game puzzle. Different random draws and purchase decisions
can change what the next sensible action is.

1. **Preserve an untouched starting save.** Name experimental saves separately.
   The ordinary loader preserves the running random state; it does not
   restore an earlier random sequence. Do not mix an emulator snapshot with the game's own save format.
2. **Inspect the actual starting park.** Check cash, debt, land, occupied pens,
   facilities, staff and food. The supplied research saves are not established
   as the original official QUICKSTART distribution.
3. **Buy only the necessary opening land and enclosure.** The supplied real-
   estate artwork has three normal terrain choices. The alleged fourth terrain
   is not a verified purchase option.
4. **Choose an animal with its feeding requirement in view.** Purchase price
   alone hides the difference between one ration and twenty-seven rations per
   weekly check. The complete inspected catalogue is in [DNOS].
5. **Budget before adding staff.** Weekly wages come before feeding in the
   weekly processing sequence. A full food bin is not useful if no employee
   remains available to perform the relevant feeding check.
6. **Distinguish staff presence from specialist benefits.** A guide can satisfy
   the tested generic feeding-presence gate and removes the no-guide attendance
   penalty. That does not replace maintenance protection or a veterinarian's
   other effects.
7. **Compare $2.50 and $5.00 rather than trusting a universal price rule.** Their
   attendance multipliers differ by a factor of two. Ticket income, concessions,
   staffing thresholds and integer rounding all matter to the comparison.
8. **Check whether demand is actually hitting capacity before expanding.** With
   no parking units the initial reach is twenty times a daily factor. More
   species alone need not increase the number admitted through that bottleneck.
9. **Add concessions with operators, not just buildings.** Food and gifts share
   the operator pool. A stand count is not an unconditional income bonus.
10. **Watch one complete weekly settlement.** Record wages, food use and any
    departures. Leave more cash than the total payroll, and check active maintenance
    against occupied pens: one worker covers three pens against neglect.
11. **Watch the first month and quarter transitions.** Inventory decay, growth,
    finance and quarterly resets occur at different points. They are not one
    interchangeable end-of-month event.
12. **Expand one consequential feature at a time.** Keep the previous save and
    compare actual outcomes. This guide does not prescribe a winning purchase
    sequence that has never been played through.

The safest interpretation of a losing experiment is "this park failed under
these conditions." It is not automatically evidence that the original game
is unwinnable, or that a replica needs more generous balancing.

## QUIR: Quirks, traps and misleading numbers

These are original-program behaviors, not a list of Swift bugs. The evidence
labels in [PREF] still apply. A tested arithmetic oddity is not automatically
a useful or normally reachable exploit.

### Financial traps worth remembering

| Quirk | What it means for a player | Details |
|---|---|---|
| The last automatic loan payment can exceed the debt | Even $1 debt can trigger a $165 debit. Manually clear a balance below $165 before the next installment when feasible. A $5,000 loan's tested 36-payment sequence leaves $24; manually paying it saves $141. | [CASH], E16 |
| Exact payroll cash is insufficient | Paying one worker requires cash strictly greater than that worker's wage. Merely matching the wage can cause dismissals. | [STAF], E11 |
| Concessions have a discontinuity at a load of 400 | The base rate is zero at exactly 400 visitors per stand but becomes 100 above 400. Later staffing modifiers still matter; this is not a universal zero-final-income rule. | [SHOP], E8 |
| A refunded Vegasaurus still leaves an expense entry | Completing the gag returns the cash but retains 25,000 in the tested animal-purchase expense record. It supplies no animal and proves no tax exploit. | [DNOS], E14 |

**Avoid spending the last dollar at auction.** A connected original-routine
purchase that leaves exactly zero cash reaches a zero divisor in auction
exit cleanup. Keeping one dollar completed cleanup in the matched control.
The native bridge raises SIGFPE; the original DOS error display/recovery has
not been recorded. This is a precaution based on a reproduced algorithmic
fault, not a claim of a completed DOS crash test. See [AUCT]. [E21]

### Annual tax was missing from the early lab

Year-end can deduct37% of cash growth over a saved baseline. The baseline resets
to the resulting cash, even after a loss. This recovered original charge is now
implemented in Lab0.4; the earlier0.3 prototype was too generous at year-end.
The signed expense-history overflow described below does not feed this tested
cash-growth calculation. See [CASH], [E28].

### A dinosaur cancellation can move the expense into another month

An ordinary Coelophysis purchase posts its 1,250 expense at BUY, before final
placement. If the original arrival animation crosses month-end and the order
is then cancelled, the refund subtraction uses the new month. A live DOS
fixture retains +1,250 in April and records -1,250 in May, while refunding the
pending cash debit and delivering no animal. The combined expense cancels;
the per-month reports do not. This is a constructed day/phase-only checkpoint
fork, not a money exploit or a test of December/year rollover. [E32]

### Simulation and save surprises

The overeating trigger's apparent pen loop repeatedly inspects the first pen.
Do not infer that it scans every dinosaur independently. A vet clears the
resulting persistent flag; this is separate from ordinary food demand. [FOOD],
E3 and E12.

Ordinary park loading does not rewind the running RNG. Bank visitors, peanut
appearances and the Diner fly are demonstrated menu-side consumers. The same
park save is not a snapshot of the whole DOS machine. This does not establish
a deterministic reload trick for a desired event. [RNGS], E9, E16 and E17.

The peanut game grants at most three feedings per entry from an initial pool
of six. Its tested new-park reset does not refill that pool. A zero initial
countdown can delay the first appearance for 65,536 minigame callback updates;
that is not a measured number of seconds. [SIDE], E17.

The Animation option can change the shared RNG sequence. In the tested Diner
callback, the fly still consumes randomness while the calendar is paused;
turning Animation off suppresses those particular draws. Pausing is not a
universal freeze of every game subsystem. [TIME], [RNGS], E18.

Animation off is not universally "less randomness." One original auction
sprite selector uses a sequence table when on but calls the shared RNG when
off. Other gates use fixed sprites or direct state/position changes instead
of merely suppressing output. These are scoped code findings, not a proven
whole-session increase in randomness. [RNGS], E19.

**A record-score ending is not proof of a complete score-file write.** The
original writer does not reject short writes if closing the file reports
success. An existing empty `TOPTEN.DAT` is not regenerated like a missing file;
unread bytes in the destination remain unchanged. These are original-code
fault-injection results with a host filesystem adapter, not observed DOS disk
failures. Keep score-file backups when moving or researching the game.
See [SALE]. [E22]

**The ticket graph is not a cash-profit graph.** It plots monthly visitors.
The separate financial summary can overstate actual ticket receipts through
monthly-versus-daily rounding, without adding cash. Annual tax can appear in
the prior year's January fee slot after the history shift. See [OFFC]. [E29]

### Accounting and long-run curiosities, not proven strategies

A large food purchase can overflow a signed 16-bit expense-history field
without refunding the actual cash. The recorded 328-large-feeder case spends
32,800 normally while recording -32,736 in that field. Downstream tax benefits
are unverified. [FOOD], E10.

Synthetic late-year tests make the signed land-sale contribution turn negative
starting in displayed Year 24 for Plains, Year 35 for Marsh and Year 57 for
Desert. Those are tested arithmetic inputs, not decades-long completed parks.
The facility valuation uses different arithmetic. [SALE], E13.

Leaderboard ties do not displace an existing equal score: insertion requires
a strictly lower entry. Check the final cash rather than expecting a separate
prestige score. [SALE], E13.

### Save files can be accepted without a complete payload

The loader accepts a recognized DINOSG header even when later reads are short.
The park reset happens before all fields are available. Wrong-magic rejection
also skips the file close. Preserve backups and do not treat a successful load
return as an integrity check. Ordinary loading additionally mixes saved calendar/
hold state with live RNG, preferences and day-counter phase. See [RNGS]. [E23]

## TIME: Days, weeks, months and quarters

### Calendar

The inspected month-length table is:

```text
Jan 31   Feb 28   Mar 31   Apr 30   May 31   Jun 30
Jul 31   Aug 31   Sep 30   Oct 31   Nov 30   Dec 31
```

February is always twenty-eight days in this table. A year is not twelve
thirty-day months. Internally, the game also maintains a separate weekly
counter and a quarterly escape-risk counter. [E1, E4]

### The clock and pause are separate from Animation

In the tested common scene loop, animation and input callbacks run before the
simulation-pause check. When unpaused, a counter advances and triggers a day
when it reaches or exceeds its configured threshold. The initialized threshold
is 20 logical loop iterations, not an established number of seconds or video
refreshes for every configuration. [E18]

Pause uses a count of outstanding holds: two acquisitions need two releases.
The original outer loop does not call the daily routine while paused. Calling
that routine directly is not equivalent: it increments its weekly counter
before its own pause check. That last result is a diagnostic fixture, not a
normal player action. [E18]

**Animation is a different option.** It controls some scene effects, including
the tested Diner fly, rather than being the calendar's pause flag. Those effects
can consume shared randomness even while the date is held. See [RNGS]. [E18]

### Scene entry and paused bank updates still consume randomness

The original common scene setup makes a shared-RNG call before repeating
updates begin. The bank's updater also continues while the calendar is paused,
and the tested path does not consult the Animation preference. In matched bank
runs, Animation on/off produced equal recorded state except for that byte.
Longer bank waits changed the RNG but not cash, debt, date or day-counter phase.
Turning Animation off is not a universal deterministic-replay switch. [E25]

E25 connects the original scene router, full common-loop control flow, bank and
office bodies, and the main-street release prefix. Physical control delivery,
clock pumping and specified presentation/modal services remain adapters. No
real-time or complete DOS-game claim follows from those connected runs.

### What happens during a day

The verified parent routine has this order:

1. Increment the weekly day counter and consult the simulation-pause flag.
2. Compute progression and handle an existing or new employee absence.
3. Reduce an existing closure countdown.
4. Advance the day within the current month.
5. Calculate attendance, then concessions.
6. At month end, record history, perform monthly inventory work and applicable
   financial settlement; set the internal day to zero, advance the month and
   flag a quarter transition where appropriate.
7. When the weekly counter is due, run wages, food, visitor status, events/fees
   and escapes in that order. Increment the escape-risk counter afterward.
8. Process applicable mid-month warnings and overeating logic, then the cash
   ceiling before returning.

**Scope:** the parent ordering was executed across 27,216 cases. Most named
child routines were logging stubs in that experiment. The original event
routine remained executable, so its fee reachability was tested through the
real parent. Monthly inventory was executed in a separate experiment. These
counts are not complete simulated parks. [E1]

### A fee month is not a guaranteed annual bill

The licence and repaving code sits inside the weekly event routine. It sees
the updated month only when a weekly check coincides with month rollover.

| Ending month | Weekly counter before this day | Observed bounded result |
|---|---:|---|
| January | 5 | Month advances; no repaving in this invocation |
| January | 6 | Month advances; eligible repaving can be charged |
| June | 5 | Month advances; no licence fee in this invocation |
| June | 6 | Month advances; eligible licence fee can be charged |

The financial gate and fee-specific conditions still apply. Do not convert
this into a universal "pay every February 1" rule, or a claimed multi-year
avoidance schedule without checking the full caller and load/clock behavior.
The verified fact is the intersection of the two branches. [E1, E5]

### Quarter boundaries

The daily routine flags a quarter transition and acquires a simulation-pause
hold. Due weekly work can still finish within that same daily call. The outer
loop then considers the pending quarter without rechecking the newly acquired
hold inside that iteration. [E18]

Quarter processing is blocked in the land, employee, Diner, General Store,
DinoMart and auction contexts. Window shop follows its previous context.
If blocked, the quarter remains pending and its hold prevents later days.
The tested main-street entry slice has a mode-conditional hold-release loop;
when that path releases the hold, the pending quarter can run on a later loop
iteration without another daily call. This is connected original-code evidence,
not yet a full mouse-driven shop-exit recording. [E18]

The quarter handler clears the escape-risk week counter, escape tally,
visitor-status mask and event mask at **every quarter**, not just New Year.
The ordinary quarter path releases a hold. The annual path additionally calls
annual-account and breeding work, retains its hold, and requests the office
unless already there. The original year-end notice says the stopped clock allows first-quarter
changes and that time resumes when leaving the office. E20 now executes the
original office entry, notice, exit/cleanup and main-street release slice in
persistent state: one incoming hold becomes two on office entry, three after
the notice, two after office cleanup, and zero on the enabled main-street
release path. Reentering with the notice cleared does not add that notice hold
again. The last release belongs to arrival at main street, not just the Leave
button callback. [E18, E20]

These are scripted original-instruction scene sequences with modal/display
services supplied, not a live DOS navigation recording. E18's economic subcalls
were recorded rather than rerun in full. No new complete-quarter economic
acceptance follows. [E1, E4, E18, E20]

### Return days matter

A sick employee whose timer expires is restored before that day's attendance
call. A closure countdown of one becomes zero before attendance too. New
illness is not attempted again on the return-day path. [E1, E3]

## CASH: Money, orders and the bank

### Owned cash versus a pending order

The original maintains both committed cash and a working balance. In the
staged shops, synchronization refreshes the latter from the former. The bank
uses a different immediate-update path, described below. Staging a shop purchase
reduces working cash and changes pending inventory; it does not immediately
commit the purchase. OK commits it. Cancel leaves owned state unchanged; a
later synchronization discards the draft. [E5]

| Example operation | Committed cash | Working cash |
|---|---:|---:|
| Synchronize a $20,000 park | 20,000 | 20,000 |
| Stage a $10,000 purchase | 20,000 | 10,000 |
| Commit it | 10,000 | 10,000 |

The original also has paired income instructions that credit both balances,
maintaining their difference during a pending order. Bounded tests exercised
that arithmetic; they did not prove every possible menu/time interleaving.

**Technical correction:** `DS:BAD4` is the working balance. Calling it
cumulative admission takings caused several incorrect interpretations of
wealth, illness and event eligibility. The corresponding committed cash is
`DS:5C3A`. [E5]

### Annual income tax is based on cash growth

For this build, the year-end annual routine charges **37% of positive committed
cash growth over its stored annual baseline**, rounded down. It is not computed
from the expense-history totals or the value of the dinosaurs and land. [E28]

```text
if cash > saved_annual_baseline:
    tax = floor((cash - saved_annual_baseline) * 37 / 100)
    cash -= tax
saved_annual_baseline = cash
```

The baseline becomes the post-charge cash even when cash fell and no tax was due.
A constructed final-day fixture with cash100000 and baseline5000 ends at64850:
35150 tax is deducted. Original quarter cleanup then synchronizes working cash.
This is original-code evidence, not an earned park or a new real-world tax rule.
An installment due at that month's rollover occurs before this annual charge.

Positive growth of1 or2 rounds the tax to zero but still takes the tax-notice
branch. Lab0.3 omitted annual tax entirely; Lab0.4 now preserves the original
baseline and charge. An old snapshot without that historical baseline cannot
be faithfully upgraded by guessing it from current cash. [E28]

### Midmonth financing advice is conditional, not a universal reminder

At the midpoint of the month, the game estimates half the monthly salaries of
**active** workers, plus the lesser of the automatic loan installment and the
remaining debt. It warns only when this estimate exceeds committed cash and
additional credit is nonzero. At the5000 debt ceiling it does not give this
bank advice. Absence and actual paid payroll retain their separate rules. [E28]

One active guide/no debt:449 cash warns,450 does not. One security employee
contributes625, not624 from doubling the rounded weekly wage. The estimate caps
its final loan contribution to debt, but the actual automatic repayment still
has the165 overcharge trap. The advisory is not a complete safety budget.
Lab0.3 incorrectly emitted it every midmonth; Lab0.4 uses the original gates.

The original monthly cash-change report is computed and its baseline refreshed
**before** the monthly installment. Annual and monthly baselines are different
fields. Detailed multi-year ledger presentation remains separate work. [E28]

### Borrowing and manual repayment

For this exact DOS build and supplied VARS.DAT, the outstanding credit ceiling
is **$5,000**, not $100,000. The original quote reads VARS offset `014C` (5,000),
not `0124` (100,000). The normal-range quote is:

```text
additional credit = min(5000, 5000 - current debt)
manual repayment  = min(5000, committed cash, current debt)
```

After the first automatic installment reduces debt to 4,885, the original
borrow callback can lend another 115, bringing debt back to 5,000. Manual
repayment can use exactly the available cash and does not add an immediate
interest charge. The original bank control-builder now has bounded execution
evidence: Borrow is registered in the enabled mode even when the loan is
already at its ceiling, while Repay requires nonzero committed cash and debt.
The callback rejects borrowing at the cap. Working cash is not the repayment
control's eligibility input. This is native control registration, not live
mouse-hit testing. [E16, E20]

Bank borrowing and manual repayment update committed cash and debt directly,
not as purchases awaiting an OK commit. They leave working cash unchanged at
the callback boundary. In the tested active-game route, bank cleanup requests
the office, whose original entry synchronizes working cash. A persistent
example goes from committed/working 1,000/777 to 6,000/777 after borrowing
5,000, then to 6,000/6,000 on office entry. It is not a cash duplication bug.
[E16, E20]

### Bank visits and pause holds

The actual bank scene adds a counted pause hold and, in the active mode,
releases its own hold on cleanup. Existing holds survive. Its visitor
initialization and control-builder consume shared RNG despite calendar pause.
E20 used a scripted common-loop adapter. E25 now executes the original scene
router and full common-loop control flow through bank and office, ending after
the original main-street release prefix. Borrow, Repay, cleanup, office cash
synchronization and hold releases remain connected in one native sequence.
Physical input and specified services are still supplied, not a graphical DOS
visit or continuous economy. [E18, E20, E25]

### Automatic installments and the final-payment trap

The original installment helper and month-end loan block now have fresh
execution evidence, not just a recorded $5,000 example:

```text
payment = ceil(debt / 5000) * 165
interest term = floor(debt / 100), only when payment < debt
principal reduction = payment - interest term
```

Automatic processing debits the full payment from both cash balances and
records it in the monthly expense bucket. The $5,000 case charges 165 and
leaves debt 4,885. **The cash debit is not capped to the remaining debt.** [E16]

| Remaining debt | Cash before | Automatic charge | Loan-block result |
|---:|---:|---:|---|
| 5,000 | 1,000 | 165 | Cash 835; debt 4,885 |
| 166 | 1,000 | 165 | Cash 835; debt 2 |
| 24 | 1,000 | 165 | Cash 835; debt cleared |
| 1 | 165 | 165 | Zero cash; debt cleared |
| 1 | 164 | 165 | Negative cash; foreclosure dispatch |

Foreclosure is tested after the cash debit and before the nonpositive-debt
clamp. Having enough cash to cover only the small remaining principal does
not protect a park from that automatic charge. The ending screen and actual
score-file write were not executed by this loan probe. [E16]

A persistent original-code finance sequence starting at debt 5,000 leaves
24 after 36 automatic charges. A 37th automatic charge takes another 165,
for a total cash cost of **6,105**. Using the original manual repayment
callback for the final 24 instead makes the total **5,964**, saving **141**.
These are sequential finance calls, not a 37-month recorded game. [E16]

**Mechanics-based advice:** manually clear a remaining balance below 165
before another automatic installment, when feasible. This is not a verified
winning route. Other park costs still apply.

### Foreclosure stops the month transition

A fresh original-DOS test now follows the failure into the actual bank and
ending screens. With $1 debt and $164 committed/working cash, the $165 payment
leaves cash -$1 and debt -$164. The debt clamp occurs only on the successful
path, so that negative loan is visible in the bank. With $165 cash, the payment
instead leaves zero cash and clears the debt without foreclosure at this test.
The branch tests committed cash; a negative working balance alone is not its
trigger. Two mismatched-balance fixtures establish that distinction but are
not proposed player routes. [E33]

The failed installment returns before month increment, weekly payroll/feeding
and quarter processing. Internal day is already zero in the closing month;
the park becomes inactive and acquires a terminal pause hold. A weekly counter
that has reached seven can remain seven. The actual route tested is foreclosure
notice -> bank advice -> Nice Try -> leaderboard -> title. The stored spending
category selects the advice, which is not a comprehensive causal diagnosis.
The nonqualifying negative score does not write a new leaderboard entry. [E33]

Seven controlled finance forks reached their precise original instruction stops.
A separate 320-scenario day/quarter corpus has 96 foreclosures. Lab0.7 advanced
the month in all 96; Lab0.8 now stops at the correct boundary. These are controlled
states, not an earned losing or winning playthrough. Old terminal snapshots
must stay with their matching lab because their calendar/hold state may be
wrong. Original ending artwork is not recreated in the browser. [E33]

### Cash ceiling

The inspected daily tail caps committed cash at 100,000,000 and removes the
same excess from working cash, then clamps the latter at zero where required.
Earlier descriptions that placed the clamp only at a mid-month checkpoint
were corrected. This is a ceiling, not a verified victory condition. It says
nothing by itself about the park-sale score or whether reaching it is feasible
through ordinary play. [E1, E7]

## OFFC: Office desk, reports and sale markers

The pictures on the office calendar are working controls, even though they do
not look like buttons. Original registration and command-handler execution
identify eleven hotspots. Click the objects, not just the bottom action bar.
[E21]

| Desk object | What it opens or reports |
|---|---|
| Ticket stack, upper right | Previous-day visitors |
| Food shopping slip, right | Dinosaur meat/plant inventory |
| Snack package, right | Food concessions and allocated operators |
| Staff note | One staffing advisory |
| Profit-statement reminder, lower left | Previous month's profit, loss or break-even |
| Business-sale card, lower right | Park-sale confirmation path |
| General ledger, center | Financial reports and ledger controls |
| Dinosaur-count note | Herd, unused pens and any hunger warning |
| Dinosaur reference book, upper center | Dinosaur information |
| Small dinosaur object, lower left-center | Gift concessions and allocated operators |
| Bank card, upper left | Bank account and loans |

The [office evidence report](../docs/dinopark-tycoon/office-auction/REPORT.md)
includes the exact original 320x200 rectangles and command IDs. Registration
and callbacks were executed; native mouse hit-testing and rendered dialogs
were not. Park-sale eligibility and final ending acceptance remain separate.

### The staff note reports one problem at a time

Its checks use hired counts, not the complete on-duty staffing model:
maintenance against floor(developed pens/3), vets against floor(animals/5),
guides against occupied pens (also warning if there are no guides), then
security against 50 visitors per guard. Each later failure overwrites the
previous advisory. The displayed priority is security, guides, vets, then
maintenance. [E21]

Several simultaneous shortages therefore produce only one warning. Even an
empty park with zero guides takes the guide-warning path. The note's all-clear
is not a guarantee about every simulation subsystem or absence condition.
Use [STAF] for the actual worker rules rather than treating this note as a
complete staffing audit.

### Marking animals for auction is a pending ledger change

The ledger permits only one marked pen per species. Marking another pen of
the same species clears its earlier mark; marks on different species survive.
These are pending pen flags. Leaving the ledger returns to the desktop;
leaving the office then copies the pending pens to the live table. [E21]

This is a selection/commit rule, not a claim that the entire marked pen is
sold. The quarter's seller setup and auction settlement have their own rules.
The ordinary office report clicks do not award money or feed the herd.

### The ticket graph plots visitors, not monthly cash profit

On the ticket-pricing page, the graph reads completed-month visitor totals.
It does not multiply them by the ticket price. Its annual curves cover the
current year and up to four preceding years. January has no completed-month
segment; February has one. Older-year curves have twelve monthly segments. [E29]

The scale considers all twelve stored values of every available year before
applying visibility choices. Hiding a year therefore does not remove its values
from the y-axis range. A curve can start from the preceding December. These are
original data and line-request tests, not a newly rendered original screen.

Food- and gift-concession graphs instead plot gross sales minus their recorded
costs. The desk's previous-month cash-change field is a third quantity, based
on committed cash and its monthly baseline before the next loan installment.
These numbers should not be treated as interchangeable. [E28, E29]

### Reported ticket income can exceed the actual receipts

The financial summary reconstructs ticket income as monthly visitors times the
stored ticket price, divided by 100 and rounded down. Actual admission cash is
rounded down each day before it is added. The two can disagree even at a constant
price. This discrepancy is in the original game, not extra money credited by
the lab. [E29]

A constructed January with seed 1 and $2.50 tickets produced:

| Quantity | Original value |
|---|---:|
| Visitors | 2,411 |
| Actual admission cash | $6,014 |
| Financial-summary admission | $6,027 |
| Payroll | $900 |
| Month cash-change report | $5,114 |
| Financial-summary profit | $5,127 |

The original daily routines and original summary helper both execute. Across
all19 normal prices and four seeds,36 whole-dollar controls agree;40 half-dollar
cases overreport by $2-$13. These are constructed parks, not an earned winning
route. Annual tax uses actual cash growth, so this reporting difference does
not itself increase or reduce the annual charge. [E29]

### History holds five years; tax appears in an unusual month

The annual routine shifts current data into the previous-year slot, older data
back one slot, and clears the new current year. The fifth-oldest data falls off.
All15 retained history arrays now have native shift/clear comparisons. Repeated
annual calls are not five-year gameplay acceptance. [E29]

The caller has already wrapped the month index to zero when annual tax is
posted. Tax enters that January fee slot before the shift, so afterward it is
recorded in the previous year's January rather than December or the new current
year. The charge is not doubled. This is a reporting-placement quirk. [E29]

### Where the financial categories really come from

Following the original writers corrected two names in our research: C03B is
food/plant purchases, not dinosaur purchases; C12B is advertising, not food.
Dinosaur purchases instead reach the C30B other-expense bucket. The summary
already summed both misnamed buffers, so this is a category correction rather
than newly created cash or a changed total. [E30]

Food and newly confirmed advertising expenses post on successful confirmation,
not just while selecting an order. Cancellation leaves those histories unchanged.
Facility costs share the broader C21B bucket with several fees, loan installments
and annual tax. Native General Store tests start from prepared pending orders;
they do not replay every preceding shop click. [E30]

CA8B, previously unnamed, stores active concession operators. It is a count
snapshot overwritten by daily processing, not monthly income or hired-to-date
staff. Its value can change when an operator is absent. [E30]

### A December payday can be recorded two years back

Month rollover advances the month before a due weekly payroll. January31 wages
therefore post to February. December31 temporarily uses month index12, putting
wages into the previous-year January block; annual shifting then moves them
into the block two years back. [E30]

A controlled park with two vets, one guide and two operators pays1,675. From
200,000 cash it ends with198,325, but its December payroll history is zero and
its two-years-back January entry contains1,675. Matched non-payday controls
produce no such posting. The actual cash is debited only once. This is an
original reporting-order defect, not another hidden fee. [E30]

The installment and annual tax use different timing: the installment posts to
the closing month before month increment; annual tax joins previous January as
described above. Do not treat these three dates as one universal posting rule.

E30 checks all900 retained financial values through112 connected scenarios,
including four constructed2,190-day runs and explicit original street-release
slices at year-end. This is stronger than repeated shift calls, but not earned
six-year gameplay or original office/media timing. Lab0.6 exposes live histories;
missing imported history is unavailable and undefined concession cells remain
marked unknown. It does not invent old ledger data from cash totals. [E30]

## VISI: Attendance, parking and ticket prices

### Parking is not advertising

The initial attendance calculation combines capacity with this reach term:

```text
parking units == 0:  reach = 20
parking units > 0:   reach = 35 * parking units

initial attendance = min(capacity, reach * daily_factor)
daily_factor = 1, 2 or 3
```

The parking counter is `DS:6FAC`. Advertising is a later modifier, not the
source of `35 * units`. Additional capacity can go unused when reach is the
limiting side. Later modifiers can raise the final visitor count above this
intermediate capacity; the game does not simply clamp it again at the end.
[E6]

### Capacity compounds

For the inspected normal arithmetic:

1. Begin with 100.
2. For each species represented, add ten percent of the running amount.
3. For each species with at least two animals, add another ten percent.
4. Apply the extra contribution for each occupied pen, with integer truncation
   at each step.
5. If the amount remains the unchanged base of 100, the no-animals result is
   zero capacity.

The third contribution has an original indexing quirk: it reads a catalogue
field using the **pen's slot number**, not the species ID stored in that pen.
Do not silently repair that quirk and call the result a faithful formula.
Examples such as 121, 133 and 160 refer to particular pen arrangements, not
universal final attendance values. [E6]

### Admission bands

| Ticket price | Attendance multiplier at this stage |
|---|---:|
| Up to $2.50 | 200% |
| Over $2.50 through $5.00 | 100% |
| Over $5.00 through $7.50 | 50% |
| Over $7.50 through $9.75 | 25% |

Normal office controls use fifty-cent steps from **$0.50 through $9.50**.
The $9.75 boundary belongs to the calculation, not to an extra selectable
office price. Externally edited prices above the last band can reach an
unassigned-value path; that is not a supported pricing strategy. [E6, E7]

**Strategy inference:** within one band, a higher price does not incur another
penalty from this particular ladder. At a band boundary it does. Comparing
$2.50 with $5.00 requires considering concessions and staffing as well as
admission revenue. Neither a prototype's profitable $14 park nor an old
unqualified "always charge $5" recommendation settles the original optimum.

### Other modifiers, in order

After initial reach/capacity, the original applies active advertising,
average pen grade, ticket price, terrain/season, staffing, hunger and closure
or staff-presence checks, followed by first-year support. Truncation occurs
along the way. The supplied season table contains **four seasons and three
terrain columns**, not evidence by itself of a fourth terrain. [E6]

The four advertising choices are now mapped to the original shop labels:

| Advertising | Purchase price | Added basis points |
|---|---:|---:|
| Fliers | 750 | 250 |
| Newspaper | 2,500 | 500 |
| Radio | 10,000 | 750 |
| T.V. | 50,000 | 1,250 |

Active choices add their points to a base of 10,000 before one multiplier is
applied. All four together produce 12,750 at this stage, or 127.5% before
integer truncation. Pending campaigns become active at the quarter transition.
The names and prices come from original artwork, controls and tables; a full
interactive advertising purchase/quarter cycle was not newly executed. [E6,
E10]

### Original quarterly price controls and their lock window

Ticket prices form a four-quarter schedule. The original office control builder
allows editing a future quarter, or the current quarter when its internal day
counter is zero. Past quarters are locked. At ordinary April day 5, Winter and
Spring have no Less/More buttons; Summer and Fall do. [E31]

The controls step by 50 cents within 50..950 cents. A live Summer change from
300 to 950 survives leaving the office, while resumed April attendance uses
Spring's 250. Eight explicitly calendar-edited native checkpoints and 64 actual
mouse-control comparisons confirm the eligibility rule. This is not proof of
a universally timed player opportunity at rollover; the exact gate is day zero.

Three separate constructed two-year original daily/quarter sequences confirm
selection and month-close posting of each scheduled price, together with the
RNG and all 900 financial-history entries. Those long runs use the declared
instruction-bridge adapters, not continuous DOSBox gameplay. Lab0.7 adds an
opt-in schedule; its flat diagnostic editor remains a separate mode. [E31]

## STAF: What your employees actually do

### Hiring is a draft until you leave through the outer OK

HIRE and FIRE on a role's detail panel edit the **pending roster**. That panel's
OK keeps the draft and returns to the posters. Only the employment poster
screen's outer OK commits the entire roster and returns to the street. The
salary table shows the draft, not necessarily the active payroll. The tested
ordinary hires have no up-front fee. [E41]

**Detail-panel Cancel discards every uncommitted role edit**, including a hire
accepted on a different panel. Outer Cancel has a different rule: its helper
checks committed versus working cash, not staffing differences. For the tested
roster-only changes, equal balances allow immediate exit without a dialog.
Active staff stay unchanged, while the abandoned pending roster survives until
reentry synchronizes it. Those scratch workers are not employed. [E41] [E42]

A changed pending count can precede the redraw and FIRE-control enable update.
The next action therefore requires current interface readiness, not just the
new number. Maximum-count and quitting/firing timing rumors remain unqualified.

### Wages and availability

The complete original payroll routine now has 2,474 bounded cases. Each
person costs the nominal wage divided by four, rounded down **before** any
headcount total. This is a weekly debit. [E11]

| Role | Nominal wage | Weekly amount per employee |
|---|---:|---:|
| Maintenance | 1,400 | 350 |
| Veterinarian | 1,800 | 450 |
| Security | 1,250 | 312 |
| Guide | 900 | 225 |
| Concession operator | 1,100 | 275 |
| Manager | 2,400 | 600 |

Payroll visits the roles in the table's order, paying one person per role,
then starts another pass if employees remain. It does not pay every maintenance
worker before trying the first guide. Each payment requires **committed cash
strictly greater than that person's weekly wage**. Failure dismisses that
role's still-unpaid people; people already paid remain, and later roles still
get their turn. Both cash balances decrease by the amount actually paid. [E11]

| Two guards; cash before payroll | Paid this week | Guards retained |
|---|---:|---:|
| 1,000 | 624 | 2 |
| 624 | 312 | 1 |
| 625 | 624 | 2 |

Thus two guards cost 624, but 624 cash is insufficient to retain both. Leave
a margin above the total scheduled payroll. Actual monthly outflow depends on
the number of weekly checks, not just the nominal wage label.

**Sick leave is paid.** Payroll temporarily includes the absent employee,
charges their wage if affordable, then restores their unavailable status.
An absent guide still costs 225. If they cannot be paid and leave, their
absence timer is cleared. A sick worker is one unavailable person, not a
number of people equal to the remaining days of leave. Specialist benefits
below depend on active staff where the original reads active counts. [E3,
E11]

### Guides and the attendance calculation

Let N be attendance entering the staffing stage, S guards, G guides, and P
occupied pens. The verified formula is:

```text
points = 100
if 50*S < N: points -= 10
if G == 0:  points -= 10
else:       points += 5 * min(G-1, P)
N = floor(N * points / 100)
```

The first guide removes the missing-guide penalty. Extra guides add five
percentage points each, capped by occupied-pen count. One guard covers the
threshold at exactly fifty incoming visitors, but not fifty-one. Penalties
and guide bonuses combine as points before one multiplication. They are not
separate percentage multipliers. **40,128 isolated original cases matched
the arithmetic.** [E2]

### Managers

A manager protects against a particular quarterly resignation check. After
the progression gate activates, the previous three months' visitors are
compared with:

```text
active managers * 100000
```

Exceeding that coverage can remove one available non-manager employee. This
is not an eight- or fifteen-employees-per-manager rule. The manager does not
buy food, operate stands or eliminate the separate unpaid-wages path. [E3]

The current Swift research snapshot mistakenly called this quarterly check
at every month end. That is a replica defect, not original-game difficulty.

### The quarterly gate uses an earlier stored value

The day computes progression before revenue and month rollover. Quarter entry
adds exactly one to that stored value; it does not recalculate with the new
month or later cash. This is important near the strict 100,000 working-cash
threshold. Management checks the incremented value against six. [E27]

In a constructed end-of-September Year 1 state with working cash 100,001, daily
progression 4 becomes 5 at quarter entry, not 6. At end-of-March Year 2 with the
same cash and debt 5,000, the daily value 8 becomes 9 even though the monthly 165
installment reduces cash below 100,000. Recent positive visits and no manager
therefore cause a departure in the second fixture, but not the first. These
are original-code boundary fixtures, not a proposed economic exploit. [E27]

Lab 0.2 recomputed the value too late and failed 56 of 2,400 new boundary cases.
Lab 0.3 preserves the cache, including deferred quarters. This corrects the
reconstruction without changing the original economy. [E27]

### Sick leave

Once progression is at least eight, with no existing illness, the original
attempts illness when `rand()%30 == 0`. A second draw chooses a starting role;
a cyclic scan finds an occupied role. One employee leaves for seven days.
The original has **one shared absence timer**, not independent simultaneous
leave in every job category. A third draw chooses the message. [E3]

There is no requirement to have five employees. Even one worker can be
selected once progression permits it. Selection is neither uniform among
individual people nor necessarily uniform among the occupied job categories.
During an absence, and on its return day, no new illness attempt is made.
E27 adds 2,824 isolated native comparisons and 96 ten-update sequences linking
illness/return to attendance and concessions. A returning guide can affect
that same revenue pass. The later weekly/monthly body is outside those slices.
These are confirmations, not counts of complete parks. [E27]

### How progression accelerates

Using zero-based calendar values:

```text
q = 4*year + floor(month/3)
if working_cash > 100000: q *= 2
```

The financial test is strict. It does not use lifetime revenue. Thus a
calendar-only rule such as "sickness begins at exactly eighteen months" is
not reliable. Different event branches use different progression thresholds.
[E3, E5]

### A silent visitor outcome still changes state

The six-bit visitor-status lottery can mark a selected bit even when an extra
condition prevents its visible effect. Marked bits skip later lottery draws.
No message therefore does not imply no mask or RNG change. E27 adds 4,608 native
status comparisons, including food loss, guide complaints, mortality and parking
advice. The known empty-herd nonterminating scan is excluded from these native
cases and remains an explicit bounded diagnostic in the browser lab. [E27]

## FOOD: Feeding, spoilage and planting

### What the Dino Diner actually sells

These names and prices are connected to their inventory bins through the
original page artwork, button tables and executed purchase handler. Prices
are per inventory unit. They are not inferred from a replica. [E10]

| Page | Product | Price |
|---|---|---:|
| Meats | Small feeders | 25 |
| Meats | Medium feeders | 75 |
| Meats | Large feeders | 100 |
| Plants | Fungus & moss | 12 |
| Plants | Grass & flowers | 18 |
| Plants | Bushes & trees | 25 |
| Seeds | Fungus spores | 1 |
| Seeds | Flower seeds | 5 |
| Seeds | Tree seedlings | 9 |

More normally adds one unit; the held-repeat branch requests five. Less
reverses pending additions, rather than selling previously owned stock. OK
commits; Cancel preserves owned cash and stock. Unlike payroll, an exact-price
purchase can succeed and leave zero cash. Actual mouse repeat timing was not
part of these callback tests. [E10]

### Weekly feeding and substitution

The original aggregates need into **meat and plants**, then draws from each
diet's bins in the order listed above. Within a diet the units substitute
one for one. A Tyrannosaurus requiring seven units can be fed seven small
feeders, seven medium feeders, seven large feeders, or a mixture totaling
seven. The meat labels do not require matching dinosaur size. Seeds are not
consumed as food by this weekly routine. [E12]

Any one active employee, in any of the six roles, satisfies the feeding
presence check. If nobody is active, feeding fails and the stock is left
untouched. Other specialist duties still matter. Weekly wages happen first,
so an unpaid departure can make an otherwise stocked park fail feeding.
[E1, E12]

The persistent overeating flag adds `floor(aggregated diet need / 2)` to
each diet's requirement. An active veterinarian clears that flag during the
food check. It is not an automatic surcharge whenever visitors are present.
[E3, E12]

**Strategy inference:** small feeders and fungus & moss are the cheapest
direct purchases per immediately usable ration. Their storage behavior can
change the comparison for a long stockpile, especially across month end.
No complete cost-optimal buying schedule has been played through.

### Failed feeding, hunger and predation

With animals present, any diet shortage or lack of an active employee adds
seven to a shared hunger counter. Fully successful feeding resets it to
zero. An empty park takes an early return that leaves the old counter alone.
The absence of a warning message does not prove that feeding succeeded:
warning display has its own random and screen conditions. [E12]

The weekly part of the daily update calls predation when **hunger is greater
than 28 and
progression is at least six**. Starting at zero, four failed checks reach
28; five reach 35. The progression condition must also be met. [E12]

The predator routine scans pens in internal order. A carnivore can remove
one animal from the first eligible neighboring pen containing a strictly
smaller internal size class. Another carnivore can be the victim. The
routine stops after one removal. It makes no random draw and does not check
fences, electricity, guards or vets. Its adjacency list and size classes
are preserved in the survival report. The catalogue below lists the classes;
the numbers are game values, not measurements. [E12]

**The hunger counter is shared.** A fully fed Tyrannosaurus can attack after
an unresolved plant shortage keeps the park hungry. Predation neither clears
hunger nor adds meat to the stores. These findings establish this particular
loss path; they do not establish a universal starvation countdown or prove
that isolated herbivores are immortal. A separate no-vet death branch appears
in [EVNT].

### Why overeating can appear in one park and not another

The mid-month trigger checks February or August, no active vet, sufficient
progression and an animal-count result. Its apparent ten-pen loop never
advances the pointer: it reads **slot zero ten times**. Moving an otherwise
identical animal to slot one or nine changed the bounded result. This is an
original implementation quirk, not proof that every feeding problem comes
from the first pen. [E3]

### Monthly spoilage and U-Plant arithmetic

The earlier 5,184-case monthly experiment verified growth, capping and decay.
The new shop mapping supplies the names. It is not a second execution of
that whole monthly grid. [E1, E10]

| Meat | Monthly units lost, rounded down |
|---|---:|
| Small feeders | 25% |
| Medium feeders | 10% |
| Large feeders | 5% |

| Seed | Plant produced | Terrain for growth |
|---|---|---|
| Fungus spores | Fungus & moss | Marsh |
| Flower seeds | Grass & flowers | Desert |
| Tree seedlings | Bushes & trees | Plains |

Each seed unit on the matching terrain grows one matching plant unit per
monthly update. The plant bin is then capped at 999 and loses the following
fraction, rounded down:

| Plant | Desert | Plains | Marsh |
|---|---:|---:|---:|
| Fungus & moss | 50% | 25% | 0% |
| Grass & flowers | 0% | 25% | 50% |
| Bushes & trees | 25% | 0% | 25% |

All three seed bins then lose `floor(stock*25/100)`. Growth uses the count
before this decay. One to three seeds lose nothing in this monthly operation;
four becomes three. That can support small recurring growth, but it does not
by itself pay wages, feed every animal or prove an indefinite survival route.
[E1, E10, E12]

### Shop boundary quirks

The nominal 999-unit purchase limit has a later comparison bug. A controlled
sequence bought 1,000 large feeders for 100,000 and committed at zero cash.
Another sequence reached an invalid negative-cash draft that OK correctly
refused. This is a callback-level result, not a recommended graphical exploit.
[E10]

Large orders also expose signed 16-bit overflow in food-cost history. Buying
328 large feeders debits the correct 32,800 cash but adds -32,736 to that
accounting field. It does not refund cash or supply free food. Downstream
tax effects are unverified; the recovered sale calculation does not use this
food-expense field. [E10, E13]

## SHOP: Food stands, gifts and restrooms

Food/gift income depends on attendance, stand count and a shared concession-
operator pool. It is not a fixed daily amount per building. The recovered
allocator distributes complete staffing cycles by stand counts, then splits
leftover staff with an odd remainder favoring food. [E8]

For a type's visitor load per stand, the recovered base rate is:

```text
load == 0:       base = 0
0 < load <=400: base = 500 - floor(load/100)*125
load > 400:     base = 100
```

This has an unusual discontinuity: at exactly 400 the base is zero, but above
400 it becomes 100. Staffing, extra operators and variation then modify the
rate. A zero base is not a universal statement that every staffing arrangement
at that crowd level has zero final income. [E8]

The final type rate is bounded from zero through 500. Gross revenue is
`floor(visitors*rate/100)`. Costs are `floor(gross*80/100)`. Net is gross minus
costs, preserving the intermediate rounding. Two ordered random draws alter
nonzero rates. Do not smooth the curve or replace the whole mechanism with a
flat profit per stand. [E8]

During inspection, the original gives operators to gifts without clearing
food's normal allocation. A branch skips food's monthly statistics, not the
final combined income credit. Therefore the account history and actual cash
change can differ without either value being a fabricated UI result. [E8]

Restrooms feed a service-load selector in this routine, not direct revenue.
The service values are not star ratings: a larger visitors-per-capacity
measure is not automatically better. No complete ROI ranking is asserted.

### Inspection is not a whole-park closure

Food inspection shares a countdown with closure events, but its discriminator
keeps attendance open. Normal hunger and staffing penalties still apply. The
concession inspection effect requires **both** the flag and a nonzero timer.
The flag can remain set after expiry without extending the inspection. [E26]

The original decrements that timer **before** attendance and concessions. In
bounded connected revenue sequences starting at 7, six subsequent passes have
an active timer and the seventh reaches zero. Do not interpret the initial
counter as seven further complete revenue days. These tests cover the daily
revenue prefix, not a fully played week with all other processing. [E26]

Algorithm Lab 0.1 got both gates wrong: inspection zeroed admissions, and its
concession effects persisted after expiry. Lab 0.2 fixes the implementation.
This correction is not a newly discovered defect in the original game.

### Building prices and bonus gifts

| Facility | Purchase price |
|---|---:|
| Food Stand | 5,000 |
| Rest Rooms | 1,000 |
| Gift Stand | 7,500 |
| Parking Lots | 10,000 |

The General Store advances its gift level once when a committed visit
contains at least **10,000 in eligible fence/facility spending**. The eligible
subtotal starts over on entry; it is not a lifetime total. Advertising does
not count. Spending 20,000 in one commit still earns only one level. The
state is capped at six. [E10]

| Level | Reward described by the original offer |
|---:|---|
| 1 | Tiki torches for the front walkway |
| 2 | Decorative plant life for the pens |
| 3 | Volcano centrepiece |
| 4 | Ornate dinosaur fountain |
| 5 | Huge dinosaur fountain |
| 6 | Dinosaur carousel |

Later offers promise only a handshake and a pat on the back. These are gift
levels, not six independently purchasable products. Original rendering uses
the levels for torches, plants and centrepiece graphics. **No attendance
bonus or edible-food grant is established for the gifts.** The season
multiplier previously suspected to be a centrepiece effect actually indexes
the park's Desert/Plains/Marsh terrain. [E6, E10]

### Live land selection, undo and cancellation

On the tested existing Plains park, clicking an unowned plot stages a 1,000
purchase. Clicking the same plot again undoes it and refunds working cash.
Only Confirm commits the new owned-but-unfenced pen, debits committed cash and
posts the capital expense. The calendar can keep advancing on this screen.
The test stops at the original commit return to avoid mixing in another day.
[E32]

Cancel exits this land map directly, unlike the General Store's extra modal.
At the following street cash-sync boundary, the live park and both cash
balances remain unchanged, but the pending plot can still be stale until a
full synchronization. That pending field is not owned land. Other terrains
and new-park land selection retain separate acceptance boundaries. [E32]

### Live gift-stand confirmation, cancellation and reentry

The original DOS interface now corroborates the staged-order model. From a
10,781-cash checkpoint, selecting a gift stand and clicking BUY leaves committed
cash at 10,781, working cash at 3,281, one pending stand, no live stand and no
new capital expense. Confirm commits both the stand and its 7,500 expense. [E31]

Cancel first asks for confirmation. Declining preserves the pending order.
Accepting cancellation does not immediately clear every scratch field. At the
next street cash-sync boundary, both balances are 10,781 and no live stand or
expense exists, but the pending stand remains until reentering the store runs
the fuller synchronization. It is not a free asset or a second debit. Matched
fresh-process confirm/cancel routes verify this with real mouse controls and
modal dialogs. Other shop/placement/undo paths remain separate work. [E31]

## FENC: Fences and escapes

### Three fences and a separate electrical upgrade

| Fence | Price per pen | Plain threshold | Electrified threshold |
|---|---:|---:|---:|
| Wood | 1,000 | 104 | 62 |
| Chain Link | 2,500 | 83 | 41 |
| Cement Wall | 5,000 | 62 | 20 |

Electricity costs 1,000 per pen and is a separate flag, not a fourth fence
grade. The last two columns are integer risk increments, not percentages.
Original shop labels identify the grades; the complete weekly processor
has now been executed in 2,008 controlled-draw and 648 original-PRNG cases.
[E10, E11]

### Live fence placement and upgrades

BUY first opens the pen-placement map and pauses the calendar; it does not yet
charge for a fence. Clicking a pen stages the fence and debits working cash.
Clicking it again undoes that pending change and refunds it. Confirm copies
the pending pens, commits cash and posts the expense. [E32]

A new Wood fence costs1,000. The tested upgrade from existing Wood to Chain
Link charges the **full2,500**, not a1,500 trade-in difference. Existing
electrification survives the pending upgrade, undo and final commit. These
live DOS routes do not qualify every grade, downgrade, electricity-purchase
control or affordability boundary. [E32]

### Unfenced animals go first

At progression one or above, the processor scans unfenced occupied pens in
internal order. It empties a pen completely, adds its animal count to the
quarter's escape tally, and stops this pass once the number lost in this
invocation reaches progression. A whole pen can overshoot that stopping
value: progression one does not save the second or third animal in a pen.
There is no random draw in this pass. [E11]

### Random fence failure

The later stages run only when:

```text
quarter escape tally == 0 AND progression >= 5
```

For each occupied fenced pen, the game multiplies the table's increment by
the quarter-reset risk-week counter and compares `rand()%10000` strictly
below the result. It processes weak grades before strong grades, then pens
in internal order within a grade. The first failure loses the **whole pen**,
clears its fence and electricity, and ends this stage. The risk-week counter
increments after the weekly processor. [E4, E11]

Maintenance employees do not suppress this fence-failure test. An original
PRNG case still lost a pen with four maintenance employees present. Stronger
and electrified fences reduce the threshold; they do not guarantee immunity.
Because original output ranges from 0 to 32,767, modulo 10,000 is uneven;
do not treat threshold/10,000 as an exact probability. [E11]

### The separate maintenance check

If no fence failure occurred, a neglect check uses:

```text
threshold = floor(occupied_pens * 100 / 3) - 100 * active_maintenance
neglect occurs if rand()%100 < threshold
```

A successful neglect roll empties the first occupied pen in internal order,
again removing its fence and electricity. The following staffing makes this
specific threshold nonpositive:

| Occupied pens | Active maintenance needed against neglect |
|---|---:|
| 1-3 | 1 |
| 4-6 | 2 |
| 7-9 | 3 |
| 10 | 4 |

For example, four occupied pens and one worker give threshold 33. Draw 32
loses a pen; draw 33 does not. Two active workers prevent this neglect
outcome. Sick leave and unpaid departures can change the active count.
These numbers do not prevent the separate random fence failure. [E11]

Once the quarter's escape tally is positive, the later fence/neglect stages
are skipped for the rest of that quarter. The unfenced pass can still run.
Quarter transitions reset the tally and risk counter. No paid recovery
system appears in the executed loss paths: removed animals are gone and
the land can be restocked. [E4, E11]

## EVNT: Events, rustlers and plague

### The entry gate and lottery

The weekly event routine requires **working cash of at least 100,000**.
Equality qualifies. Its first-day condition selects month-specific fees;
it does not suppress ordinary weekly lottery attempts. Fees, when applicable,
are processed first, with no second check of the original 100,000 threshold
before the lottery. [E5]

The selector picks a starting bit using `rand()%8`, then makes up to eight
attempts while shifting left. It does not wrap and does not stop at `0x80`.
Unused eligible bits receive the shared test `rand()%100 < 5`; progression
must be at least `attempt_number + 5`, counting the first attempt as zero.
The selected bit is set before event-specific feasibility checks. [E5]

Therefore, selecting an impossible or unrecognized outcome may consume a bit
without showing a message. The original can produce a mask of 384. The mask
resets quarterly. Do not describe the system as six independent daily five-
percent rolls, or require its mask to fit in eight bits. [E4, E5]

### Licence and repaving

At an eligible zero-day weekly/month boundary:

- July licence: animal count times 1,000; the amount must be strictly less
  than working cash. A zero amount can still reach its message path.
- February repaving: parking units times 10,000; the computed cost must be
  nonzero. There is no second affordability comparison in this branch.

Both affect committed and working cash. They are not guaranteed unconditional
annual charges; see [TIME] for the verified parent-ordering condition. [E1, E5]

### Plague

After the event is selected, the original requires animals and an additional
successful `rand()%2 == 0` gate. Then:

```text
losses = rand() % total_animals
if active_vets > 0: losses = floor(losses / (active_vets+1))
```

A raw loss of four becomes four with no vet, two with one vet, and one with
two vets. Victims are removed in ascending pen order, exhausting a pen before
moving onward. One animal produces modulo-one losses of zero **in this
branch**. It is not thereby immune to other death branches, predation, escapes or
theft. [E5, E12]

### Rustlers

Once this outcome is selected:

```text
if active_guards > 0 and rand()%active_guards != 0:
    stop the theft
otherwise:
    remove one animal of the highest-priced owned species
```

Zero guards skip the protection draw. One guard consumes it but modulo one
cannot stop the theft. Two or more guards can block it. The most expensive
species is selected by catalogue price; ties keep the earlier pen. It is not
a uniformly random victim. [E5]

This is conditional theft protection, not the overall weekly probability.
The first guard still has its separately verified attendance benefit.

### Closures, inspection and lawsuits

The earlier complete event-deck receipt supports the remaining selected
outcomes below; these are not newly rerun event grids. [E5]

| Selected outcome | Additional condition and effect |
|---|---|
| Lawsuit | Quarter escape tally above zero; charge 10,000-29,000 in 1,000 steps |
| Food inspection | At least one food stand; set inspection flag and seven-day countdown |
| Water shutdown | Set ordinary closure state and seven-day countdown |
| Road repairs | Set ordinary closure state and seven-day countdown |

The lawsuit amount is `(rand()%20 + 10)*1000`; both cash balances are debited.
Inspection has the cash/statistics distinction explained in [SHOP]. Ordinary
closure countdowns can suppress attendance. Their daily decrement happens
before attendance, so a countdown of one expires before that day's admission
calculation. Unhandled selected bits consume a mask entry without their own
visible event. [E1, E5, E8]

### A separate death branch when no vet is active

The weekly visitor/status routine has its own quarterly mask and lottery.
This is separate from the 100,000-cash event deck and from predation. Its
outer test uses `rand()%100 < floor(risk_week*100/12)`. The specific no-vet
death branch additionally requires progression at least ten, no active vet,
and a second `rand()%100` result below 15. Calling it a flat 15% weekly death chance would
omit the outer conditions. [E12]

The branch chooses a starting boundary with another draw, scans pens and
removes one animal. It is not a uniform random choice among all animals.
Hunger is not read: a well-fed park can qualify. An active vet blocks this
particular death path, but does not block the predation routine above.
Its quarterly bit is consumed once the initial lottery selects it, even if
the later vet or progression gate prevents a death. [E12]

The report also records an empty-park scan boundary that failed to return in
a direct fixture. That controlled result does not establish a reachable
freeze during ordinary graphical play; it is retained as a technical
follow-up, not described as a demonstrated player-facing crash.

## BRED: Breeding and herd size

The original birth routine is called at the annual transition, after the
year increments. That timing comes from its original quarter-handler caller;
the controlled birth tests execute the complete birth routine itself. [E11]

For each pen containing more than one animal, the routine tests:

```text
first draw:   rand()%100 < floor(50 / (herd_size - 1))
second draw:  rand()%100 < 25
```

Only a successful first test consumes the second draw. Passing both adds
**one animal** to that pen. The routine continues to later pens; a failed
first pen does not prevent a later one from breeding. [E11]

| Animals already in pen | First threshold | Second threshold |
|---|---:|---:|
| 0-1 | No attempt | No draw |
| 2 | 50 | 25 |
| 3 | 25 | 25 |
| 4 | 16 | 25 |
| 6 | 10 | 25 |
| 11 | 5 | 25 |
| 26 | 2 | 25 |
| 51 | 1 | 25 |
| 52 or more | 0 | Unreachable after first failure |

The larger counts are controlled arithmetic fixtures, not demonstrated
multi-decade herds. They establish that two animals are not an absolute
per-pen cap: a pair can become three, and larger herds can also increase.
The declining threshold limits growth. Multiplying the thresholds as if
the modulo outputs were perfectly uniform independent draws would overstate
the precision of a probability estimate. [E11]

**Strategy inference:** a pair gives access to breeding and the earlier
capacity bonus, while each additional animal adds its normal food demand.
No breeding-based winning route or optimal sell/retain schedule is claimed.

## DNOS: Dinosaur reference table

### Ordinary stock is a quarterly purchase opportunity

A confirmed ordinary purchase consumes that species' shop-stock flag. Leaving
and returning to DinoMart during the same quarter does not restock it. Quarterly
processing refreshes ordinary stock; the calendar may already show the new
quarter while the quarter-end notice still awaits acknowledgement. [E46]

A cancelled ordinary order restores the cash reservation and expense and does
not consume the stock opportunity. After restocking, a second animal can join a
matching single-animal pen even when no owned pen is empty. The live example
bought Hypsilophodon in April and again after July's refresh. [E46]

Stock, money and placement are separate checks. A species can be selectable but
unaffordable, or affordable with BUY enabled but still rejected by the original
no-room notice **before debit**. All twenty selection controls were exercised;
that does not mean twenty purchases were completed. Vegasaurus remains a
separate refunded-gag path, not an ordinary animal. [E46]

**Static catalogue extraction, cross-referenced with the feeding consumer.**
Prices are catalogue amounts; food is normal aggregated need per animal at
the weekly feeding check, before overeating. These are not daily needs or
modern biological claims. Availability and unlocks are not established by a
row's existence. Size class is the original predation comparison value.
[E1, E3, E12]

| Species | Price | Weekly food | Diet | Size class |
|---|---:|---:|---|---:|
| Albertosaurus | 3,400 | 2 | Meat | 1 |
| Allosaurus | 4,250 | 2 | Meat | 1 |
| Ankylosaurus | 5,750 | 3 | Plants | 1 |
| Apatosaurus | 8,750 | 20 | Plants | 2 |
| Coelophysis | 1,250 | 1 | Meat | 0 |
| Corythosaurus | 7,250 | 3 | Plants | 1 |
| Deinonychus | 1,250 | 1 | Meat | 0 |
| Diplodocus | 9,250 | 27 | Plants | 2 |
| Edmontosaurus | 6,000 | 4 | Plants | 1 |
| Hadrosaurus | 3,500 | 2 | Plants | 1 |
| Hypsilophodon | 1,500 | 1 | Plants | 0 |
| Iguanodon | 8,500 | 5 | Plants | 2 |
| Ornithomimus | 1,250 | 2 | Plants | 0 |
| Panaplosaurus | 3,250 | 3 | Plants | 1 |
| Pentaceratops | 1,750 | 3 | Plants | 2 |
| Saurolophus | 5,500 | 4 | Plants | 2 |
| Stegosaurus | 3,250 | 2 | Plants | 1 |
| Triceratops | 7,500 | 6 | Plants | 2 |
| Tyrannosaurus | 9,750 | 7 | Meat | 2 |
| Vegasaurus* | 25,000 | 7 | Meat | 0 |

*Vegasaurus has a catalogue row, but its shop purchase is a special refunded
animation rather than an animal added to a pen. Its table fields must not be
used to plan an ownable herd.* [E14]

### Ordinary DinoMart purchases have a different commit sequence

For the tested Coelophysis, BUY immediately debits working cash and posts the
1,250 animal expense. Committed cash and the live herd wait for confirmation.
The calendar can advance during the arrival animation; placement then acquires
a pause hold. Unlike land/fences, the ordinary animal expense is already in the
history before placement. [E32]

Placing the animal changes the pending pen only. Clicking again picks it back
up without refunding the purchase; it can then be placed elsewhere or cancelled.
An owned, unfenced pen is accepted by the tested placement control, but the
separate unfenced-escape rules still apply. Confirm commits the pen and cash,
without posting the expense twice. Same-month Cancel restores pending cash and
pens, restores shop availability, and reverses the expense. [E32]

Cancellation subtracts from the **current month**, not the remembered purchase
month. In a date/phase-only April28 fixture, the original animation reaches
May2 before placement. Cancel refunds the debit and supplies no animal, but
leaves +1,250 in April and -1,250 in May. It is a month-allocation defect, not a
second cash refund. Cross-year and other-species cases are not established by
that fixture. [E32]

### What happens when you buy Vegasaurus

The normal DinoMart initializer registers twenty selection buttons, including
Vegasaurus as the last catalogue entry. The original registration, hit-test,
selection and purchase paths now have bounded execution evidence; this is
more than an unused database row. [E14]

With at least 25,000 available, BUY charges 25,000 and starts the original
special animation. Completion refunds the same 25,000, resets the selection
and marks that entry disabled. The original hit-test then no longer returns
its button. No pen is needed, and no animal is placed. Ordinary Tyrannosaurus
positive controls instead reach the normal placement path when a usable pen
exists and are rejected when none does. [E14]

There were 72 completed purchase sequences, with four insufficient-cash
controls. **Correction in 0.2f: with Animation off**, the original skip path
refunds immediately during BUY; the next frame clears the selection. The older
probe called its input `sound` but wrote the Animation flag `DS:3DFE` and its
cached value. Sound FX is a different preference, `DS:3DEB`. Twenty-four new
purchase-time fixtures cross Animation, Sound FX and Music independently and
confirm the refund branch follows Animation. Audio services remain supplied;
this is not a claim of complete playback equivalence. [E20]

Including the earlier selection and original UI-registration
controls, the hidden-content receipt covers 254 formal cases with no
mismatches. Graphics/audio calls and sprite width are supplied; the tests
execute the special animation's logic rather than render its appearance.
They do not establish every possible secret or a fourth terrain. [E14]

One accounting quirk remains: the animal-purchase expense retains 25,000
through the refund and tested OK path even though cash is restored. That is
not a demonstrated cash loss, tax strategy or additional sale value. [E14]

## SIDE: Peanuts, Window shop and the Diner fly

These diversions are part of the original game, not required additions to the
Swift reconstruction. The new evidence executes their original logic with
explicit drawing, sound and UI adapters; it is not a live DOS recording. [E17]

### Feeding peanuts

In this DOS build, the peanut interaction belongs to the **Window shop**
screen reached from the Dino Diner and other shops. The Diner navigation
callback requests that screen, whose original setup loads `winshop.act` and
`winshop.pic` and installs the feeding handlers. The ordinary food-menu Diner
screen has the separate fly interaction described below.

Wait for a dinosaur to emerge at one of five locations. When its feeding
control is active, click to feed it. The code gives it an eight-callback
waiting window, then retracts it if nothing happens. These are callback
updates, not a measured wall-clock interval. [E17]

| Rule | Verified behavior |
|---|---|
| Allowance on entering | Up to three, limited by the remaining shared allowance |
| Initial shared allowance | Six; reentry does not reset it |
| Reward | One dollar added to both committed and working cash when eating completes |
| When the peanut is spent | On the accepted click, before the dollar is awarded |
| When the reward arrives | Eating reaches frame 10, six callback updates after the normal ready frame 4 |
| Herd/food benefit | No food-stock or park-herd replenishment in these handlers |

Eight persistent sequences used the original control-enable requests, fed
three times, reentered, fed three more times, and then found no remaining
allowance. Each earned six dollars. This is a small novelty, not a demonstrated
unlimited-income system. [E17]

**Finish the eating animation before leaving.** The tested exit/reentry
callbacks can discard an unfinished feeding after its allowance was spent.
The original new-park reset also leaves the remaining allowance unchanged.
The inherited ordinary save map does not serialize it; that last finding is
a static map check, not a newly executed complete load. Restart/load farming
has not been demonstrated. [E17]

**Long-wait quirk:** the initial delay is `rand()%50`, but the update decrements
before testing for zero. An initial zero wraps to 65,535 and takes 65,536
updates to begin the first appearance. Later idle delays are 25-74 updates
and do not have this zero-initialization problem. No seconds or pause behavior
are inferred from that count. [E17]

### Swatting the Diner fly

On the food-menu screen, turning among the three menu-category pages invokes
the fly-hit routine. If the fly is active and over the eligible page interior,
the action records a splat. The routine checks the fly's position, not the
mouse's distance from it: page turning is the code-backed action. Hits near
the outside are rejected according to the sprite's dimensions. [E17]

The game retains up to **nine** splat records, associated with the page they
landed on. Adding a tenth shifts out the oldest. The tested fly/page handlers
do not award money, alter debt or spend peanuts. [E17]

This cosmetic interaction still matters to reproducibility: flight decisions
and sound-pitch jitter consume the shared simulation RNG. The local fly
updater respects the Animation option, previously mislabeled a slow-update
gate. The peanut callback itself lacks that local check. The new common-loop
fixtures show the real Diner animation callback can run and consume RNG while
the simulation calendar is held, but rendered timing and every real pause/menu
route remain open. [RNGS], [OPEN], E17 and E18.

## AUCT: Auctions, stock and bids

Auctions have their own stock-generation path. E15/E21/E24 establish bounded
original-code mechanisms. E43-E45 subsequently follow actual input and rendering
through information excursions, purchase and rearrangement, watched seller
settlement, early-exit payment and street return. These qualify the stated
routes, not every timing variant or an optimal auction policy. [E43] [E44] [E45]

### An animal unavailable in DinoMart can appear at auction

The original candidate generator checks usable pen space, whether the species
is already offered, and whether it is marked as one of your sales. It does
not use DinoMart's availability flags. Changing all shop stock flags from
unavailable to available left auction output and RNG state identical in
977 distinct paired fixtures. [E15]

For an ordinary species, the eligibility helper accepts a usable empty pen,
or a pen of that same species containing fewer than two animals. This is the
lot-eligibility check, not a statement that every later purchase condition has
been covered. An auction can therefore be a second source of ordinary animals;
it does not guarantee the species you want will be offered.

### Vegasaurus is excluded from generated auction stock

The candidate scan considers the first nineteen catalogue entries and stops
before Vegasaurus, the twentieth. Its placement-eligibility helper separately
rejects that final entry. Every ordinary species succeeded in a matching-pen
positive control; Vegasaurus failed the corresponding generated-stock test.
The earlier refunded DinoMart gag is therefore not an auction unlock. [E15]

There is a deliberate qualification: the auction also appends animals marked
for sale from your own park. A manually injected Vegasaurus sale flag can
enter that list, because the seller loop covers all twenty records. That
assumes an already-owned or edited animal; it supplies no normal acquisition
route. The original quarter caller derives those flags from sale-marked pens.

### Opening bids and increases

The opening bid is half the catalogue price, rounded down. Thus Coelophysis
opens at 625 and Tyrannosaurus at 4,875. Competition can raise the final price;
these are not guaranteed purchase bargains. [E15]

For normal values before integer overflow, an accepted bid changes the next
asking bid as follows:

```text
next = 50 * floor(floor(accepted * 105 / 100) / 50)
if next == accepted: next += 50
```

| Accepted bid | Next asking bid |
|---:|---:|
| 625 | 650 |
| 650 | 700 |
| 1,250 | 1,300 |
| 2,500 | 2,600 |
| 7,500 | 7,850 |

The literal calculation uses 32-bit multiplication. Its overflow boundary has
arithmetic tests, but no maximum-price exploit is established. The original
also computes an internal threshold at 75 to 124 percent of catalogue price.
The connected updater uses that threshold when deciding further competition.
Exact display timing and all multi-lot cases remain unqualified. [E15, E21]

### Buying costs the accepted bid; selling loses ten percent

At settlement, a winning player pays the accepted bid. For one of your sale
lots, the original credits ninety percent of that bid, rounded down. A 2,500
purchase costs 2,500; a 2,500 sale returns 2,250. The seller flag is cleared
and the proceeds enter the current month's income record. [E15]

### Clicking Bid is not yet winning or paying

Bid starts the player's raising-hand state. The updater later accepts that
bid; the click itself neither changes the high bidder nor charges cash.
Animation off can show a fixed frame while this state machine continues.
At the third auctioneer call, a winning player pays and the **current shopping-
visit expenditure** increases. Placement follows after another phase/wait.
**Correction:** E21 called that field animal expense. E44 identifies DS:585A
and checks that all fifteen financial-history arrays remain unchanged through
its purchase's final street-entry boundary. The tested payment is real but is
not posted to the checked monthly expense histories. [E44]

The chosen pen is initially changed in the pending table. Confirmation commits
that table to the live park and advances the lot. Do not model payment and
placement as one instantaneous operation: the original has a paid-but-not-yet-
placed state. E44's live route also requires the bidder actor to be idle:
an enabled BID control alone does not guarantee callback acceptance. The actual
Confirm control stays disabled while an animal remains on the cursor. [E44]

A matching-species pen can stack the animal; clicking again picks one up without
refunding the auction payment. A different-species pen containing one animal
can swap that occupant onto the cursor. A three-click route rearranged the
existing Tyrannosaurus and stacked two Pentaceratops, then committed the pending
pens. Fences and electricity stayed with their slots. This qualifies those
single-occupant swaps and stacking to two, not every herd/eligibility case. [E44]

### Leaving settles remaining sale lots differently

An ordinary auction exit closes its availability and settles outstanding
seller flags. For each remaining species, in catalogue order, the original
uses 50 to 99 percent of its catalogue price, rounded down. It sums those
amounts, then deducts floor(total/10). This aggregate commission is not the
same rounding order as the displayed auction's accepted-bid settlement. [E21]

```text
amount_i = floor(price_i * (50 + rand()%50) / 100)
gross = sum(amount_i)
net = gross - floor(gross/10)
```

Both cash accounts and the current month's animal-sales record receive the
net amount. Clearing the seller flags prevents payment twice. Window-shop
and information-return exits take preservation paths instead of this ordinary
settlement. E24 now follows the actual information scene and reconstruction
with scripted loop delivery; see the reentry checks below. [E21, E24]

### Selling removes the offered animal before payment

At the tested nonannual quarter boundary, the original scans committed pen-sale
marks, registers the species as an auction sale, removes one animal from that
pen and clears its mark. One animal leaves a two-animal pen; a one-animal pen
becomes empty. Cash does not change at this preparation stage. The hammer pays
later, and does not remove another animal. Five original quarter fixtures cover
one, three and five distinct marked species. [E24]

Two connected three-lot seller sequences now run from that quarter preparation
through original bidding updates, payment and exit. With seed 1, Animation and
Sound FX off, a constructed park starting with 100,000 receives net amounts
5,760, 2,610 and 2,610, finishing with 110,980. Both cash accounts and monthly
income receive the credits; each seller flag clears. Repeated settlement after
normal exit pays nothing again. [E24]

A second seed/preference fixture finishes with 112,420. Both seed and Animation
differ, so these amounts do not isolate an Animation effect. These are original
routines in persistent test memory, with supplied input/rendering services and
sprite dimensions, not earned winning playthroughs or measured real-time rates.

### Information preserves the tested bid, but reentry advances the RNG

The actual information scene and its Next/Previous/Leave callbacks now execute
through scripted loop delivery. In 32 sequences, the information trip preserves
the selected lot, accepted/next bid, ceiling, high bidder, countdown, sale flags,
herd, money, catalogue prices and running RNG. Four further sequences first
accept a real player bid through the original updater, then retain that winner
and bid across information and return. [E24]

Reconstruction of the existing auction consumes four original RNG draws in the
tested states, without immediately changing those prices. The older rumor of
an automatic price increase on opening information was not reproduced here;
this does not rule out later changed competition or untested interactive timing.
Equal prices immediately after reentry do not guarantee equal future outcomes.
The separate Help callback has eight no-money/no-RNG-change checks with its
modal service supplied, not a full original help/input-loop recording. [E24]

### Live information visits preserve the bid, not the future RNG stream

E43's real-input ordinary-lot visits preserve price, next ask, high bidder and
countdown at the exact reconstruction boundary, including an accepted player
bid. Idle time inside settled information consumes no measured auction RNG;
normal waiting in the auction allows bidding to continue. These were not
matched-duration strategy trials. [E43]

Observed transitions were one entering information, one for each tested page
rebuild, one on returning before initializer entry, and four inside the auction
initializer. The earlier four-draw result described only the initializer with
its common loop supplied. Later active updates can add more; five is not a
universal count for the whole excursion. Immediate price inflation was not
reproduced on these ordinary lots. Seller-lot and other-version timing claims
remain separate. [E43]

### Actual seller payment and the notice boundary

Marking a pen in the ledger is pending until office exit. At quarter processing,
one offered animal is removed per valid mark and its seller flag registered,
without payment. The watched live route sold Pentaceratops for 1,600 and
Tyrannosaurus for 8,050, crediting 1,440 and 7,245 respectively. Cash and sale-
income history both increased; the removed animals were not removed twice. [E45]

A separate early-exit route estimated gross amounts 1,645 and 5,362. Their
7,007 total lost floor(7007/10)=700, paying **6,307**, not floor(90%*7007)=6,306.
The original notice announced that result **before** cash/history posting;
acknowledging it allowed the credit instructions to run. The animals were not
returned, and ordinary exit did not pay again. These separate RNG starts do not
rank watched versus early-exit strategies. [E45]

### A zero-cash exit has a divide-by-zero defect

Before the hold release or remaining-lot payout, the original exit computes
an expense ratio using 1 as divisor for positive cash, but cash itself when
cash is zero or negative. Exactly zero therefore produces a zero divisor.
A persistent seeded sequence won a Hadrosaurus for 3,450, placed it and
confirmed it. With starting cash 3,450, exit raised SIGFPE in the native
bridge. Starting with 3,451 completed the same purchase and exited with 1.
No mid-sequence command set the cash to zero. [E21]

The original DOS error-handler behavior has not been recorded. Avoid an
exact-cash auction purchase as a precaution, and do not assume remaining
sale proceeds can rescue this exit: their payout occurs after the division.
These are connected original-routine tests, not a recorded whole DOS game.

## SALE: Selling the park and reaching the leaderboard

### Sale is allowed with debt

The original office sale callback accepts an outstanding loan. After the
confirmation is accepted, it values the park and deducts the debt. The
executed handler does not require positive cash or a minimum park age.
Valuation happens after confirmation; this path does not offer a prior
price preview. E13's original-handler tests have later live corroboration:
E34 reached sale and a qualifying result from an existing first-year park with
debt; E35/E36 completed real keyboard name entry and score writing. These are
existing-save routes, not an earned opening strategy. [E34] [E36]

### What the buyer pays for

Let `y` be the zero-based year: displayed Year 1 means `y=0`. For normal
non-overflowing arithmetic:

```text
final cash = committed cash
           + owned-land contributions
           + dinosaur contributions
           - outstanding loan
           + facility contributions
```

Working cash is then set to the result. Separate fence/electricity resale,
employee value and food/plant/seed stock value do not appear in this
calculation. Changing those unused inventory fields did not alter the tested
valuation. [E13]

**Land:** each owned plot contributes `base*(y+10)/10`, with truncation.
Desert base is 500, Plains 1,000 and Marsh 750. Owned but unfenced land counts;
unowned land does not. There is a narrow-integer complication below.

**Animals:** each species-present pen receives one draw:

```text
floor(catalogue_price * animal_count * (50 + rand()%50) / 100)
```

The return ranges from 50% through 99%, never 100% in this term. Every
animal in the same pen shares that pen's percentage. Two Hypsilophodon,
priced at 1,500 each, return 1,500 at draw zero or 2,970 at draw 49. Pens
consume draws in internal order. [E13]

**Facilities:** each category contributes
`truncate(count*purchase_price*(y+5)/10)`. Prices are those in [SHOP]. The
formula uses **park age, not the facility's purchase date**:

| Displayed park year | Facility contribution versus base price |
|---|---:|
| 1 | 50% |
| 6 | 100% |
| 11 | 150% |

These executed formulas explain the valuation. They do not by themselves
establish a profitable buy-and-sell route through all original UI and timing
conditions. [E13]

### A long-term land valuation bug

The land intermediate is signed 16-bit: the exact expression is
`truncate_toward_zero(signed16(base*(y+10))/10)`. As park age rises, it can
turn negative. The first negative contribution occurs in displayed Year 24
for Plains, Year 35 for Marsh and Year 57 for Desert. These are tested
synthetic late-year inputs, not parks played for those decades. The facility
formula uses different arithmetic; do not apply the land overflow to it.
[E13]

### Ranking uses the resulting cash

The ten-entry table compares final cash directly. There is no additional
visitor, calendar or prestige score in the executed ranking routine. A new
score is inserted ahead of the first **strictly lower** existing score;
equal scores already present stay ahead. [E13]

The missing-file initializer has now executed and written ten MECC entries
from 100,000 down to 10,000, then reopened them through the original reader. Against that default-shaped table, 100,001 is first,
100,000 is second, 90,000 is third and 10,000 fails to enter. The supplied
research TOPTEN file contains nondefault scores and is not a pristine default.
The current table therefore determines the real threshold; there is no
universal fixed winning amount. [E13, E22]

The highest-entry path selects state 16, a lower top-ten insertion state 14,
and a nonqualifying result state 17. The corresponding scene bodies bind the
record-score, top-ten and try-again assets. Seven new original-instruction
sequences connect confirmed sale, ranking, real host-file persistence and the
ending callbacks through a supplied scene dispatcher. The result deactivates
the park and retains two pause holds in these fixtures. This is not a rendered
DOS ending in that older corpus. Later existing-save DOS sale, name-entry and
score-writing routes are recorded separately in E34-E36; an earned NEW GAME
campaign is not inherited from those results. [E13, E22] [E34] [E36]

### The score file survives a process restart

`TOPTEN.DAT` contains ten 25-byte records: a 21-byte name field and a signed
32-bit score. The loader and writer process 250 bytes. The name-entry limit is
20 characters plus a terminator. A missing file is created with the defaults;
normal loading does not erase an existing valid scoreboard. [E22]

The new test runs the original file wrappers rather than replacing the whole
loader/writer. A restricted host-file adapter supplies the lower filesystem
services. Seven successive synthetic submissions were each followed by a
fresh-process original-loader read; all 250 bytes matched. Another fourteen
constructed sales include land, dinosaurs, facilities, debt and original RNG
before recording the result. Those fixtures establish the pipeline, not a
strategy for earning their starting wealth. Actual DOS file services and
power-loss durability were outside those older fixtures. E36 later used real
DOS keyboard input and file services: uninterrupted, same-process restore and
fresh-process restore trials produced byte-identical 250-byte scoreboards within
each matched group. Mounted host files were explicitly reset between trials;
emulator state does not roll them back. This is not power-loss durability or
proof of a freshly earned winning park. [E36]

### Short writes and short reads can pass unnoticed

The writer opens `TOPTEN.DAT` with `wb+`, truncating the old file, then requests
250 bytes. It does not reject a short write if close reports success. A
fault-injected 25-byte write still selected the record-score ending, leaving
only one record on disk; a zero-byte write left an empty file. Failed open or
close instead reaches the original fatal-error service. Real buffering may
report a disk failure at close, so not every real error is silently accepted.
[E22]

An existing empty file is not the same as a missing file. It passes the
existence check, is not rebuilt, and leaves the unread destination bytes as
they were. The reader then uses that buffer. Short reads preserve the unread
tail, without a tested minimum-length or checksum rejection. Extra trailing
bytes are ignored when reading and removed by a subsequent full rewrite.
These are controlled filesystem-boundary tests, not a recorded DOS disk fault.

### Clicking an ending advances its state

A record-score ending click sets a one-update countdown and advances its
state; the following update requests top ten. The top-ten click likewise
prepares a state change, and its next update requests context 18. The
try-again ending differs: its falling object must reach its stopping position
before the one-update countdown is consumed. [E22]

With an explicitly supplied 32-pixel sprite height, clicking immediately took
15 try-again updates to reach top ten, versus one record-score update. These
are callback counts for fixture geometry, not measured seconds or rendered
frame counts. The later media pass must preserve this event/state ordering.
No remaining ending renderer or physical driver is implemented here.

## OPTS: Music, Sound FX and Animation

### Media handoff: decoded bytes and runtime behavior are separate

E47 decodes all **44 supplied ABT sound files**, with **636,978 output sample
bytes** matching the original decompressor, plus 200 constructed valid cases.
Its native execution uses a disclosed writable-segment alias for the decoder's
CS scratch table. This verifies sample bytes, not a physical sound device,
waveform timing or the original mixer. [E47]

DinoMart's initializer adjusts `CRACKLE.ABT`: its header rate is 22,000, but the
live registered playback-rate word is **30,000** after the original +8,000 step.
The other four tested DinoMart samples retain their header rates. Leaving the
shop replaces its five registered samples with the street's two. A file-only
extractor must not silently stand in for those scene-specific settings. [E47]

The inventory also checks 25 PIC containers / 166 images, 55 UNC2 actor
directories / 1,258 records, two still-unhandled UNCS actor files and seven XMI
containers. An actor record is not automatically an animation sequence. XMI
container validation is not MIDI-event decoding or musical synthesis. [E47]

The options menu has **three distinct toggles**, not one combined sound switch:

| Control | What the tested original logic does |
|---|---|
| Music | Controls sequence stop/pause and scene-music start/resume requests. |
| Sound FX | Gates sampled-effect submission and game-visible busy/wait queries. |
| Animation | Controls selected visual state paths, including alternate RNG and fast-forward behavior. |
| Music Vol. | Separate level from 0 through 11; zero does not turn the Music preference off. |

The original menu labels, command bindings and toggle instructions identify
these controls. Unavailable audio capabilities prevent the corresponding
click handler from changing the preference. Audio toggles do not directly
change Animation, the simulation pause counter, money or RNG in the tested
handler calls. Later callback behavior can still differ. [E20]

### Sound FX off changes completion behavior

With Sound FX off, the tested sample-busy wrapper returns "not playing" without
polling the device, and its wait helper returns immediately. The original
sample cleanup used by bank and office exits calls that wait helper. A later
port should preserve these completion contracts, not just lower host volume.
The new tests record device requests and supply busy replies; they do not
emulate a sound card or measure real audio duration. [E20]

The original FX toggle also clears the repeating-sample marker. Turning it
back on does not automatically restart the old repeating sample. Merely
writing the flag is not equivalent to using the handler. The off handler sets
the preference before calling its stop wrapper, so the wrapper's low-level
stop branch is skipped in the tested trace. Whether an already submitted
sample remains audible on real hardware is not established. [E20]

### Music off is not Music volume zero

Music on can resume an already selected paused sequence or take a new-start
path. That new-start path also invokes the sample-stop service, so separate
preferences do not imply completely independent playback lifecycles. Volume
zero leaves Music enabled; the original volume service receives nine times
the displayed level. No audible-fidelity claim follows from these requests.
[E20]

The old Vegasaurus "sound-off" shortcut belongs to **Animation off**, as
corrected in [DNOS]. The Animation option's other skip/substitution paths are
mapped in [RNGS]. Neither option is a substitute for the simulation pause.

## RNGS: Randomness, saving and reloading

### Current save codec and explicit continuation boundary

E36-E38 provide a lossless 75-record / 4,153-byte codec and a converter into the
unchanged JavaScript Lab 0.8. All eight supplied saves round-trip byte-for-byte.
Unknown bytes and inactive storage are preserved; one 48-byte record at file
582 / DS:C00B remains wholly opaque. The last 100 bytes are consumed by the
reader without becoming modeled game state. [E36] [E37]

Loading retains incoming live-pen geometry, restores saved pending geometry,
resets the maintenance-week counter, reconstructs progression without the daily
high-cash multiplier, and resets the selected auction species. Some pending
staff/stock/facility/ad-order buffers remain from the incoming session until a
later scene synchronization. Stored bytes, immediate-load state and resumed
scene state are therefore separate representations. [E37]

The importer requires explicit incoming session values and seller flags; it
does not invent the absent RNG or pending state. Its 144 loaded-save continuation
sequences cover 31 logical days and 4,536 day/quarter checkpoints, matching the
compared economics and RNG. Presentation remains adapted, and undefined-local
concession history cells are explicitly excluded. This is not full scene replay
or a reverse Lab-to-DOS exporter. [E38]

A native emulator checkpoint is a different artifact. E45 found an auction-exit
stall after fresh-process restore with both tested native backends under the
same Python controller, while uninterrupted routes exited normally. Its cause
remains unresolved; do not encode that debugger discrepancy as a game rule. [E45]

### The original generator

```text
state  = (state * 0x015A4E35 + 1) modulo 2^32
output = (state >> 16) & 0x7FFF
```

The seed setter takes sixteen bits and clears the upper half of the state.
The earlier E1 investigation executed all **65,536** seed values, each followed by eight
original random calls: **524,288 transitions**, with no differences from the
stated arithmetic. [E1]

This verifies the primitive, not every random consumer. A different generator,
such as the replica's SplitMix64, does not become equivalent by using the
same printed seed number. Modulo-based draws must retain their original
ordering and discrete behavior if exact replay is the objective.

### Ordinary park saves are not emulator snapshots

The ordinary save reader/writer has 71 matching constant-address payload
chunks totaling 4,011 bytes. None includes the running PRNG state. The
normal load wrapper, reset and full state reader have also now executed
with eight supplied saves, nine incoming random states and five session
seeds: **360 valid and 360 invalid-header cases**. [E1, E9]

Every valid load consumed 4,153 bytes in 75 reads, including header and
other data outside the 71 payload chunks. Both the running random state
and session seed remained unchanged. Invalid headers failed without
restoring them. Therefore **an ordinary load does not itself rewind or
advance the running RNG**. [E9]

The intro/demo caller passes `intro.dmo` to a different seed-bearing path.
Its bounded post-read reseed slice replaced the RNG with the session seed
in 1,280 cases. That path must not be used to describe ordinary park loads.
File access and display/directory operations were supplied; no interactive
OLD GAME screen or complete startup/menu sequence was executed. [E9]

**Practical conclusion:** an ordinary park save is not an emulator snapshot.
Loading does not restore the earlier random sequence, but it also does not
guarantee a reroll: if nothing else has advanced the RNG, the loader leaves
the same state intact. The bounded startup/demo and preference results below extend this evidence;
complete startup and random-consuming menu activity still require continuous
original-session verification.

### Which state a park load restores, and which state it retains

E23 now executes the original writer and reader in 27 same-process round trips,
plus the eight supplied saves under eight live session profiles. It also follows
OLD GAME through the original picker OK/Cancel callbacks, while replacing the
picker's construction, display and physical input. [E23]

| State | Ordinary park-load behavior |
|---|---|
| Committed and working cash, calendar, weekly counter | Restored separately from the save |
| Current scene, pause flag and counted holds | Restored; the saved scene becomes the requested scene |
| Pending-quarter flag | Restored |
| Running RNG and session seed | Live values retained |
| Music, Sound FX, Animation, volume and availability | Live values retained |
| Frame/day accumulator and day threshold | Live values retained |
| Shared peanut allowance | Live value retained |
| Selected auction lot | Read, then reset to the no-selection value |

This is a mixture of saved park state and continuing session state. A constructed
round trip saved an accumulator of 0, then loaded while the live value was 19;
it remained 19. The loaded scene may subsequently change pause holds, so this
is not an exact claim about seconds until the next day. Do not reset every timer
or preserve every live field indiscriminately in a reconstruction. [E23]

### Reconstructing the saved scene is a separate operation

Thirty-two E25 round trips now run the original writer and loader followed by
the original router and bank/office loops. Saved scene, money and holds are
restored, then scene entry adds its own hold. The office synchronizes working
cash, and the enabled main-street prefix releases outstanding holds. The live
day-counter phase retained by loading stays unchanged through those paused
routes. Scene setup and bank visitors advance the continuing RNG. [E25]

These are valid constructed bank/office saves with memory-backed file services,
not all save contexts, a live OLD GAME picker sequence, or actual DOS file I/O.
The first resumed main-street/day iteration is not executed in this pass.

### Animation off is not a universal randomness freeze

With seed 1, starting cash 1,000, no debt and a 5,000 bank loan, leaving the bank
at logical input iterations 5, 20 and 200 produced respectively 27, 28 and 58
RNG draws through the subsequent office and street-release prefix. Cash ended
at 6,000, debt at 5,000, and calendar/day phase stayed unchanged. Matched
Animation-on/off runs agreed. These are fixture-specific logical iterations,
not video frames, seconds or a verified event-manipulation strategy. [E25]

The original common setup contributes another draw at scene entry. Earlier
receipts that supplied the common loop, including E24's four scoped auction
reconstruction draws, must not be read as complete live-session draw totals.
E25 does not establish a replacement total for the untested full auction loop.

### NEW GAME is not the same operation as restarting the executable

The original NEW GAME callback resets the park, establishes a pause hold and
requests the new-park scene, but does not reseed the RNG, restore the peanut
allowance or reset the tested preferences and frame/day phase. The title-entry
hold slice also does not reseed. These tests begin after the title's intro
movement; complete title/demo/input timing remains open. [E17, E23]

The inspected startup has two clock-derived seed boundaries. Each passes only
the low sixteen bits of the clock-service result to the seed setter. The later
one also writes the separate session-seed word. The clock's return value was
supplied in these tests: no real-time seed period or DOS clock resolution is
established. [E23]

DINO.CFG's two inspected lines select audio drivers, not a saved park's checkbox
settings. The config stage initializes Music and Sound FX preferences from
whether the corresponding driver name equals NONE, case-insensitively. It leaves
Animation and volume alone in the tested slice. Actual driver loading and
hardware compatibility remain outside this check. [E23]

### The full demo initial-state loader explicitly reseeds

E9 tested a post-read reseed slice. E23 runs the original complete demo initial
loader: the supplied INTRO.DMO provides a two-byte seed of 31939 before the
park-state payload. Loading sets the running RNG and session seed to that value
and keeps the file open for later recorded-input playback. Stopping the demo
closes it and requests the title, but does not restore the previous RNG. [E23]

Persistent tests execute one explicit original RNG draw after that initial
load, then demo stop, the title hold block and NEW GAME. That advanced state
survives. This is not a replay of the remaining demo stream or a recipe for
forcing particular park events. [E23]

### A recognized header is not a complete save-file check

An ordinary load with only the six-byte DINOSG magic and no payload still
returns success. The original reset has already changed the park: in the tested
fixture, committed/working cash changed from 123456/234567 to 5000/5000. Eighteen
truncation boundaries were accepted. Partial payloads can produce different
mixed states; do not assume every damaged save becomes the same blank park.
The header-only result also occurred through the original picker OK callback.
**Keep an untouched backup and do not test damaged saves over your only working
session.** These are supplied memory-file tests, not observed DOS disk faults.
[E23]

The five-byte version field is compared, but the comparison result does not
reject restoration. A genuinely different save version is not therefore known
to be compatible. A wrong magic header takes a different branch: it rejects
before resetting the park, but skips closing the opened file. Repeated tests
confirm the missing close requests, not a measured DOS handle-exhaustion limit.
[E23]

### Save safety: corruption is established, code execution is not

A shared save is input to a parser, not automatically harmless data. The tested
partial-load path can replace the current park with incomplete/reset state; the
rejected-header path omits closure. Prior scoreboard fault injection can leave
a truncated persistent file. Preserve backups and do not import unknown or
damaged files into your only working session. [E21, E22, E23]

These findings have integrity and potential availability implications. They do
not demonstrate arbitrary code execution, privilege escalation or host escape.
The file loader makes fixed-size requests; an ignored read result is not itself
proof of a buffer overflow. Restored indices and other downstream consumers
would need a separate memory-safety assessment. [E24]

For a modern recreation, validate into temporary state before committing it,
check all IO, and close files on every path. Document the original's unsafe
behavior without requiring the shipping importer to reproduce it. This is a
proposed safety boundary, not a change made to production Swift. The detailed
assessment and external weakness references are in the E24 security notes.

### The bank has a nonfinancial random consumer

The bank visitor-initialization loop uses the same original RNG as the
simulation. Each of its ten visitors consumes either two or four draws, so
that isolated loop advances the generator by 20 through 40 draws. Actual
fixtures covered 20 through 38; the upper theoretical bound was not observed
in this sample. With incoming RNG state 1993, the loop consumed 30 draws. [E16]

This was original-code execution with supplied actor buffers and synthetic
image heights, not a rendered bank visit. Cash and debt stayed unchanged.
Full entry/exit, later animation frames and real elapsed-time effects still
need a continuous session. The result establishes one menu-side consumer,
not a recipe for forcing a favorable event or a fixed whole-visit draw count.

### Animation preferences can change later randomness

The option labeled Animation toggles a field different from the simulation's
pause flag. In a controlled moving-fly fixture, the original Diner callback
consumed four shared-RNG draws during an iteration with the calendar paused.
Turning Animation off through its original handler suppressed those fly draws
on the following iteration. Four is this fixture's count, not every fly frame.
[E18]

### What Animation off actually skips or substitutes

The flag also provides a useful index into presentation behavior. Sixteen
original direct-access instructions were identified: three in the options
handler and thirteen in park, employee, Diner, DinoMart and auction routines.
Indirect/cached settings and unguarded callbacks still require tracing, so
this is not a complete list of animations. [E19]

| Controlled path | On versus off | Evidence boundary |
|---|---|---|
| Park actor/pen helpers | Selected updates and helper calls are skipped when off | Static gates; not the entire park callback |
| Employee appearance | Categories 0-4 initialize appearance and choose state 3 when on; choose state 2 directly when off. Category 5 takes state 2 either way. | Original selection slice; appearance initializer recorded |
| Diner fly | The updater is suppressed when off | Prior E17/E18 execution |
| DinoMart transition | Off directly positions the actor near its target and reaches sound-stop; on takes the sample-start path | Original branch and positioning helper; output services recorded; not a completed purchase |
| Auction actor | Off selects base sprite + 4 instead of base sprite + current phase | Original selector; later phase updates statically outside the branch |
| Auction sprite sequence | On selects 18 + sequence-table value; off selects 18 + rand()%2 | Original selector and RNG executed; no rendered auction |

For seed 1 and sequence position 0, both auction alternatives select sprite
18, but off advances the RNG to 22,695,478 while on leaves it at 1. Equal
selected images do not establish equal game state. This particular off path
consumes a draw; the total draw count for a whole auction is not established.
The 746 new cases are bounded selectors/transitions, not complete scenes. [E19]

For reproduction, matching a saved park and elapsed days is insufficient:
callback activity, relevant preferences and RNG state also matter. This does
not prove a reliable timing trick for choosing a later event. Physical timer
cadence, complete startup and real input/load sequences remain open. [E9, E18]

## FAQS: Myths and practical questions

### Does Ctrl+1 supply 999 food?

Do not rely on it in this pinned DOS build. E40 tested thirteen Ctrl+1 attempts
across eight street/Diner contexts without the alleged stock change. Two traces
show the original handler actually receiving Control+1 and taking its unrecognized-
key return. That is stronger than a drained adapter queue, but it does not settle
another executable revision, platform or untested handler. [E40]

**Does the manager do anything?** Yes: a specific quarterly employee-
resignation check uses visitor volume and manager coverage. It does not
operate the park for you. [E3]

**Do I need more than four employees before anyone gets sick?** No such
headcount gate appears in the verified illness branch. Progression and random
draws are the conditions. [E3]

**Is the first guard useless?** No. It helps the attendance threshold. It
cannot stop the inspected theft branch because modulo one always permits it.
[E2, E5]

**Do vets only fix overeating?** No. They divide plague losses and block the
separate no-vet death branch. They do not block the hunger/predation routine.
[E3, E5, E12]

**Does a more expensive dinosaur necessarily attract more visitors?** That
does not follow from purchase price. The inspected capacity calculation uses
species representation, animal counts and a pen-slot lookup. Price directly
matters to the rustlers' target selection. [E5, E6]

**Can I get escaped animals back?** The recovered escape path removes them
and clears the pen. A paid recovery mechanic was a replica invention, not an
established original feature. [E4]

**Are three seeds an infinite-food exploit?** Their monthly 25% decay rounds
down to zero, and matching-terrain growth uses the pre-decay count. The weekly food routine does not eat seeds, and
their named products and terrains are now mapped. A complete indefinite
survival strategy still needs the rest of the park's costs and hazards to
be satisfied. [E1, E10, E12]

**Why didn't the annual parking bill appear?** The fee path needs both its
wealth/month conditions and a weekly/month-rollover coincidence. A matching
calendar label alone does not force the branch. [E1, E5]

**Is the game unwinnable?** No such conclusion follows. Existing-save original-
DOS routes reach qualifying sale, name entry and score writing. The other agent's
reported profitable NEW GAME route remains attributed pending receipt integration;
a profitable month is not an independently checked first-year survival policy.
Do not judge the original from a failed prototype park. [E34] [E36]

**Can two animals become three?** Yes. The annual birth routine can add one
animal to a pair, and larger herds can breed at declining thresholds. There
is no two-animal cap in that routine. [E11]

**Does enough maintenance prevent every escape?** No. It prevents the
separate neglect outcome when the active count covers occupied pens, but
random fence failure has its own test. [E11]

**Must I repay the loan before selling?** No. The original sale callback
allows debt and the valuation deducts the outstanding amount. [E13]

**Does Vegasaurus prove there was a Vegas terrain?** No. An animal record and
an alleged unused terrain are separate findings. The normal shop now has an executed special
Vegasaurus purchase/refund path. That does not make it an ownable animal or
establish another selectable terrain. [E14]

## OPEN: What this baseline does not claim

**The mechanics-recovery branch closes at this bounded baseline.** It is not a
claim that every executable byte, input race or renderer has been explained.
New contradictions can reopen a specific finding; more scene aliases alone do
not make established formulas unknown again.

| Remaining item | Precise boundary |
|---|---|
| Presentation reconstruction | Decode/render the remaining actor formats and animation sequences; reproduce palette, layering, text and input geometry. Preserve state/control transitions, not just pictures. |
| Audio execution | ABT sample bytes are recovered. XMI event interpretation, driver/mixer behavior, completion timing and scene-specific submission remain separate. |
| Event/interface coupling | Honor clocks, shared RNG, modal acknowledgements, asynchronous completion, pending versus committed state and redraw/control readiness. |
| Save/session semantics | Preserve the 48 opaque bytes and partially understood fields. Ordinary saves require explicit unsaved state for reproducible continuation; reverse Lab-to-DOS export is not supplied. |
| Native restoration | Carry E45's localized restore-associated stall to the tool owner. Uninterrupted original execution remains available. |
| Strategy claims | The proposed opening, exact MECC-attributed recipe, complete first-year survival and optimal pricing/investment require their own objectives and evidence. Other-agent reports remain attributed until their receipts are accepted. |

Not prerequisites for the media phase: testing every quantity of every species,
all historical cheat rumors, all malformed saves, every runtime API, or inventing
a percentage of understood code. The peanut/fly diversions remain documented
but excluded from Swift reproduction by user direction.

The companion [media event map](../docs/MEDIA-EVENTS.md) separates inherited
behavioral obligations, fresh E47 observations and genuinely open media work.
It is a project evidence handoff, not a UIL grammar or implementation.

## ENGN: Evidence, build identity and methods

### Exact build

```text
DINOPARK.EXE SHA-256
2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c

VARS.DAT SHA-256
5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153
```

Address labels use the investigation's Ghidra convention, not live DOS segment
values:

```text
file = 0x4800 + 16*(labelled_segment - 0x1000) + offset
DGROUP file base = 0x34A00
38FF code file base = 0x2D7F0
```

### Claim-to-evidence index

| Code | Scope and anchors | Evidence boundary |
|---|---|---|
| E1 | 24 Oct continuation: daily `38FF:4CA3-53EE`, inventory `31CE-3344`, seed `1000:1B3C`, save payload writer/reader, species table | 27,216 parent-schedule cases with declared stubs; 5,184 full inventory cases; all 16-bit seeds plus 524,288 original transitions. Save and demo distinction is static analysis. |
| E2 | Staffing `38FF:25B3-266E` with original arithmetic helpers | Earlier 40,128 original-instruction comparisons; not newly repeated for this guide. |
| E3 | Illness `4CCC-4E11`, overeating `527B-5396`, food `3345`, manager `4827` | Prior bounded executions and manager dataflow; no complete original playthrough or Apple UI claim. |
| E4 | Common quarter tail `4B2F-4B40`, escape gate `4494-44A1`, fence arithmetic `44E2-453F`, removal `42B0` | Prior quarter/gate/rate executions; historical partial scope, superseded for the full processor by E11. |
| E5 | Sync `2D0A:0000`, store `334B:0655`, event deck `38FF:3D55-4278` | Earlier 486 sync calls, 540 transaction sequences, 25,839 event cases; UI/rendering supplied by declared stubs. |
| E6 | Attendance `38FF:211F`; ticket controls `302C:28EF-2976`; advertising/season readers | Binary-derived rules, bounded input verification and historical recorded attendance observations. Not every combination independently played. |
| E7 | Prior bank/cap/weekly-payroll recovery and current research receipts | Historical observation/static evidence; bank arithmetic is superseded by E16. Full interactive bank-state equivalence remains open. |
| E8 | Concessions `38FF:2B66` and monthly accounts | Prior reported 5,760 isolated comparisons, plus a saved fixture reproduced through the Swift CLI. Not rerun as a full DOS session here. |
| E9 | Ordinary load `38FF:2048-211E`, reset `00CC-0471`, reader `17AF-2047` | Earlier 0.1a continuation: 720 valid/invalid loads, 1,280 demo slices, separately recorded seed and daily corroboration. Integrated here, not rerun. |
| E10 | Dino Diner `2D0A:26D3`, store `334B:0655`, gifts `0B52-0B7A` | 1,512 inventory sequences/7,560 snapshots; 168 gift sequences/336 snapshots. Original art/control/table mapping; declared UI stubs and ad/fence fixtures. |
| E11 | Payroll `38FF:2874-2A59`, births `3631-376D`, escapes `4390-476F` | 2,474 payroll; 11,975 controlled + 460 original-RNG birth cases; 2,008 controlled + 648 original-RNG escapes. Independent 13-case audit; annual caller statically inspected. |
| E12 | Feeding `3345`, predation `4B56-4CA2`, parent gate `5226-5240`, status `3A86-3D13` | 44,382 formal comparisons across feeding, all species/pen pairs, ordered predation and no-vet mortality. Controlled fixtures and declared external stubs. |
| E13 | Office `302C:27AD`, valuation `38FF:547F`, ending dispatcher `55A8`, ranking `27E5:04FF-0675` | 807 controlled + 40 original-RNG valuations; 144 office callbacks; 95 ranking cases. UI input and file I/O supplied; no completed original victory. |
| E14 | Original DinoMart initialization, selection, special animation/refund and UI hit-testing | 254 earlier formal cases, including 72 completed Vegasaurus cycles; graphics/audio supplied. Correction E20: the old input named sound actually varies Animation. Historical files remain unchanged. |
| E15 | Auction `37B0:0C3B-0E97`, eligibility `334B:1B69`, bids `03DB-0470`, settlement `09FB-0ACC` | 240 eligibility; 1,960 pool and 1,960 priced-lot cases with original PRNG; 10,013 bid and 704 settlement cases. 23 independent focused reruns. Fresh states, declared exits/UI stubs; no completed auction. |
| E16 | Bank quote `334B:23A2`, callback `2961`, payment `38FF:53FD`, loan block `4EEB-51CD`, visitor initialization `334B:2B89-2BF7` | 25 Oct: 76,002 checked output rows across 15 suites, including 3,096 original-RNG visitor fixtures. Original arithmetic; declared UI/end-game stubs; synthetic parameter controls separately labeled. Not a continuous game or independent review. |
| E17 | Window shop `302C:02F0`, `04CE`, `0557`; Diner `2D0A:26D3`, `2D88-3147`; reset `38FF:00CC-0471` | 25 Oct: 4,753 checked checkpoints across 14 suites. Original RNG, enabled-control feeding sequences, page-change callbacks and resets; explicit UI/audio/graphics adapters. Ordinary save coverage is a static inherited-map check. No live DOS or Swift implementation. |
| E18 | Common loop `1B29:05C7-06BC`, holds `1306/131C/1340`, context `38FF:3A28`, daily `4CA3`, quarter `4827`, main-street slice `2B5D:041B-043F`, options `1C6A:092C`, Diner callback `2D0A:2605` | 25 Oct: 1,864 checkpoints across 12 suites. Original scheduling, pause, option, callback and RNG instructions; economic calls recorded, display/input/timer services supplied. No full DOS session, new Swift work or independent review. |
| E19 | Animation flag `DS:3DFE`; employee `2D0A:1E06-1E65`; auction selectors `37B0:0711-072C` and `086B-0894`; DinoMart `334B:20C7` / `1D1E` | 25 Oct: 16 distinct direct-access instructions mapped; 746 original selector/transition cases across four suites. Original RNG and positioning execute; appearance/output services recorded. No full scene, graphics implementation or independent review. |
| E20 | Options `1C6A:092C`, audio wrappers `1862:01D5/03D8/0498/0544/05F7/0955/0A15/0A34`, bank `334B:2B32/26C9/2961`, office `302C:30B3/2728/27AD`, sync `2D0A:0000`, street release slice; crossed Vegasaurus preferences | 25 Oct: 1,558 checkpoints in 15 suites. Original instructions, native RNG and copy helpers; scripted scene-loop, resource, modal and device adapters. Corrects Vegasaurus Animation attribution. No live DOS, complete playback, independent review or Swift change. |
| E21 | Office `302C:076A/07C5/27AD`, auction `37B0:03CA/0563/0C3B/0F6E/1100/1459`, placement `334B:1A1F`, unsold settlement `37B0:006F` | 25 Oct: 2,467 checkpoints in 14 suites, including one expected native SIGFPE. Office desk registrations/reports, staged species-exclusive sale marks, six persistent buyer runs, sound-status boundary and exit proceeds. Original instructions with explicit presentation/input/device adapters; no DOS GUI or winning route. |
| E22 | Original `27E5:035B/03D8/04FF` score IO/ranking, `295E` file wrappers, office sale and ending callbacks | 25 Oct: 1,074 checkpoints in 14 suites, zero mismatches, including six expected fatal-service requests. Temporary host-file writes/fresh-process reads, asset/debt/RNG sales, short-IO behavior and connected ending callbacks. Explicit filesystem, scene-dispatch and presentation adapters; no earned winning route or DOS filesystem acceptance. |
| E23 | Startup/config seed slices, NEW/OLD GAME callbacks, original save writer/loader, demo initial loader/stop and title holds | 25 Oct: 324 checkpoints in 14 suites, zero mismatches. Saved versus live session-state boundaries, 27 writer/reader round trips, 64 actual-save profiles and truncated/header/version cases. Clock, memory-file, picker construction and presentation adapters; no continuous DOS startup or original demo playback. |
| E24 | Original information controls, auction reconstruction, nonannual quarter seller scan and multi-lot settlements | 25 Oct: 3,205 checkpoints in seven suites, zero mismatches. Two persistent three-lot sales plus preserved-bid reentry; scripted common-loop delivery and presentation/resource adapters. Security framing interprets earlier E21-E23 findings, not a newly demonstrated exploit. |
| E25 | Original scene router, full common-loop control flow, bank updater/commands, office/year-end updates, valid writer/load reconstruction and main-street release prefix | 25 Oct: 110 connected scenarios and 1,518 checked snapshots across five suites, zero mismatches; 55 matched Animation pairs. Physical control/timer/resource/presentation services adapted. No live DOS, earned win, fDisBull acceptance or independent review. |

### Later evidence and current limits

| Code | Scope | Claim ceiling |
|---|---|---|
| E26-E33 | Revenue, staffing/quarter timing, annual tax, histories, live tickets/placement, foreclosure | Original scopes retained in accompanying historical reports; no full rerun for E47. |
| E34-E36 | Existing-save park sale, real name entry, score persistence, matched restores, initial save codec | Not an earned NEW GAME policy or every restore path. |
| E37-E38 | Remaining save meanings, immediate-load projection and explicit save-to-Lab continuation | Unknown bytes and session requirements retained; presentation adapters remain. |
| E39-E42 | Portable scenes, Diner hotkeys, employment drafts/cancellation and capture phases | Tested UI routes, not a universal object detector or implemented UIL. |
| E43 | Live auction information, page/reentry timing and RNG | Ordinary tested lots; no immediate repricing, not a universal exploit disproof. |
| E44 | Paid auction placement, occupied-pen swaps and expense-history correction | Two tested placement branches; no universal herd-size or tax claim. |
| E45 | Watched and early-exit seller payments, notice/credit order, restore discrepancy | Separate starts are not a policy comparison; failed restores stay failed. |
| E46 | Twenty catalogue selections, cancel/buy/restock/buy lifecycle | One supplied-park route, two actual purchases, not twenty. |
| E47 | This consolidation, ABT decoder comparison, media inventory, live rate/registry observations | 44 original files plus 200 valid synthetic decoder cases; explicit segment alias; no full audio/rendering equivalence. |

The [evidence index](../docs/EVIDENCE-INDEX.md) identifies the supplied source
reports and their retained limitations. This compact edition includes those
reports, not every historical raw grid or probe. Complete earlier corpora remain
in their original checkpoint packages. Earlier counts are not newly performed
checks and must not be aggregated into a number of complete games.

Original-instruction probes use declared service or segment adapters. Live-DOS
routes use the actual guest input and scene code. Keep these methods distinct.
E47's audio comparison changes fifteen guarded CS segment overrides to a writable
GS alias of the same scratch-table buffer; arithmetic and control flow remain
original. It qualifies decoded bytes, not driver timing. [E47]

No original executable, save, sample audio, extracted artwork, font, private
checkpoint or byte-retaining database is included. Selected original-DOS evidence
screenshots are retained with provenance. No production Swift, Lab 0.8, E38
importer or remote repository was changed by E47.

## CRED: Credits, licence and revision history

### Revision 0.3, 27 October 2026

Consolidated the inherited 0.2s mechanics with E34-E46 addenda. Corrected the
auction shopping-accumulator/monthly-expense conflation and stale live-route
unknowns. Integrated staffing, stock, seller notices, save/import and hotkey
qualifications. Closed the mechanics baseline without claiming a complete game.
E47 adds sample decoding, a source-bound media inventory, a live playback-rate
observation and a structured event/interface handoff. Historical revisions below
retain their original chronology and evidence ceilings.

Research direction and authorship: **TiGa / TiGa-RCE**. Investigation and draft
preparation used AI assistance. Evidence, source inspection and actual outputs
are the standard for claims, not the model's confidence.

The original game is credited to **Manley & Associates** and **MECC**. This is
an independent guide, not their official documentation. Game titles and the
original executable, art, music and other assets are not relicensed here.

**Old-guide lead:** DaKay's DinoPark Tycoon Guide (2014, revised 2019) supplied
useful player questions about staffing, theft, food and planting. Its proposed
explanations are not treated as executable specifications. This document does
not reproduce its walkthrough prose.

https://dakaywritescrap.blogspot.com/2014/06/dakays-dinopark-tycoon-guide.html

Original explanatory text in this guide follows the repository's **CC BY 4.0**
licence. Retain attribution and identify modifications. That licence does not
apply to the original game or confer permission to redistribute it.

https://creativecommons.org/licenses/by/4.0/

**Revision 0.2s, 26 October 2026:** Added actual foreclosure/negative-debt bank
display and losing route, confirmed the early daily return before month/week/
quarter work, and corrected Lab0.8 terminal state/import/resume behavior. Added
E33 with original-instruction and real-DOS scopes kept separate. No earned win,
production Swift or remote change.

**Revision 0.2r, 26 October 2026:** Added live land selection/undo/commit/Cancel,
new Wood and full-price Chain Link upgrades, ordinary Coelophysis placement,
pickup/commit/cancel, and next-month refund-history placement. Added E32 and a
bounded-wait tool-friction note. Seven routes pass from recreated checkpoints;
failed synchronization calibrations are retained. Algorithm Lab0.7 unchanged.

**Revision 0.2q, 26 October 2026:** Used the operational pinned fDisBull candidate
for actual ticket-page controls and gift-stand confirm/cancel/reentry. Documented
the internal-day-zero price lock, staged expense boundary and stale cancelled
pending fields. Added E31 and Lab0.7 optional quarterly schedules, checked against
three two-year original instruction runs. Original/Swift/remotes unchanged;
no earned winning route or complete media parity claimed.

**Revision 0.2p, 25 October 2026:** Traced expense/history writers, corrected
C03B/C12B meanings and identified active-operator count CA8B. Verified month-end
payroll shifts, including the December two-years-back January placement, and
compared daily/quarter histories through four six-year constructed scenarios.
Lab0.6 records live history and qualifies missing/undefined values. No original
artwork, hardware behavior, earned strategy or production Swift change.

**Revision 0.2o, 25 October 2026:** Traced the ticket-pricing graph to visitor
history, distinguished concession net and cash-change reports, verified daily
versus monthly admission rounding and five-year shifts, and located the annual
tax in the shifted previous-year January fee slot. Added Lab0.5 reporting
kernels without changing daily economics or inventing missing history.

**Revision 0.2n, 25 October 2026:** Added E28 connected daily/weekly/quarter
economics and original RNG comparisons. Recovered annual37% cash-growth tax and
conditional midmonth financing advice, corrected Lab0.3 omissions, and retained
annual/monthly cash baselines.705 scenarios/2874 snapshots, not a full DOS game.
Original inputs, production Swift, remotes and debugger acceptance unchanged.

**Revision 0.2m, 25 October 2026:** Added E27 staffing/status comparisons and
original scheduler/day/quarter boundary tests. Corrected Lab 0.2's late
progression recomputation, which caused early or missed resignations. Lab 0.3
now preserves the daily cache across deferred quarters/snapshots. Broader
illness/revenue sequences retain original RNG; complete economics still open.
No original, production Swift, remote changes or new debugger acceptance.

**Revision 0.2l, 25 October 2026:** Added E26 original attendance, concession,
monthly inventory, event and connected countdown/revenue tests. Corrected two
JavaScript Lab defects without rebalancing: inspection is not park closure,
and its concession effect expires with the timer even if the flag survives.
Original instruction evidence remains bounded; full gameplay is unqualified.
Checked the published fDisBull 0.14 release separately; offline kit not retrieved
or accepted here. Original inputs, Swift and remote repositories unchanged.

**Revision 0.2k, 25 October 2026:** Connected the original scene router and
full common-loop control flow to bank/office transactions, year-end notice,
valid save/load reconstruction and the main-street release prefix. Identified
common-setup RNG and paused bank draws unaffected by Animation in 55 matched
pairs. E25 checks 110 connected scenarios / 1,518 snapshots in five suites.
Physical input and specified services remain adapted. No live DOS, fDisBull
acceptance, earned victory, production Swift or remote changes.

**Revision 0.2j, 25 October 2026:** Executed the actual dinosaur-information
scene and callbacks, preserved accepted bids across reconstruction, and measured
four reentry RNG draws in the tested states. Connected original quarter seller
preparation to two three-lot settlements and no-double-payment controls. Added
E24 with 3,205 checkpoints in seven suites. Added bounded security interpretation
of inherited malformed-save/score/fault findings, not a code-execution claim.
Offline kit not tested; no original, production Swift or remote changes.

**Revision 0.2i, 25 October 2026:** Executed startup/config seed boundaries,
new-park/title/old-game controls, original writer/reader round trips and the
complete demo initial loader/stop. Distinguished restored pause/calendar state
from continuing RNG/preferences/day phase. Added accepted-truncation, unused
version-check and rejected-header close warnings. Added E23 with 324 scoped
checkpoints. Existing instruction bridge used; offline kit not yet verified.
No original inputs, production Swift or remote repositories changed.

**Revision 0.2h, 25 October 2026:** Restored original score loader/writer and
file wrappers, tested real temporary-file persistence and fresh-process
reloads, connected sale/ending callbacks, and documented unchecked short IO
and the missing-versus-empty-file distinction. Added E22. fDisBull 0.14 was
partially installed in an isolated sandbox but remains blocked by missing
dependencies; the preserved instruction bridge produced the new evidence.
No original inputs, Swift or remote repositories changed. No earned win or
rendered DOS ending is claimed.

**Revision 0.2g, 25 October 2026:** Mapped and executed the eleven office desk
registrations and command handlers, staffing-advice priority and ledger sale
markers. Connected auction bidding, delayed acceptance, hammer payment,
pending placement, confirmation, temporary/ordinary exits and aggregate
unsold-lot payout. Found an exact-cash exit divide fault through a persistent
purchase sequence, with a one-dollar positive control. Added E21 and OFFC.
No original inputs, production Swift or remote repositories changed.

**Revision 0.2f, 25 October 2026:** Identified separate Music, Sound FX and
Animation controls, tested sound completion and volume contracts, and corrected
the old Vegasaurus sound/Animation mislabel with crossed preferences. Executed
bank controls and immediate finance inside original scene bodies, connected
office cash synchronization, and followed year-end hold release through main
street. Added E20; hardware/graphics remain deferred. No production or remote
changes, live DOS session or complete winning route.

**Revision 0.2e, 25 October 2026:** Used the Animation option as a behavioral
index rather than a reason to omit presentation logic. Mapped direct readers
and tested auction selectors, employee appearance states and DinoMart direct
positioning. Added E19 and the off-only auction RNG draw. Rendering/audio
implementation remain deferred; no original inputs, Swift or remote changes.

**Revision 0.2d, 25 October 2026:** Executed the common loop with original
calendar/quarter bodies and declared economic adapters, nested pause holds,
context-dependent quarter deferral, the main-street release/sync slice and
Animation-option/Diner-RNG interactions. Corrected the old slow-gate label.
Added E18. Algorithm-first scope; graphics/sound implementation remains deferred.
No production Swift or remote changes, full playthrough or ending acceptance.

**Revision 0.2c, 25 October 2026:** Added a dedicated quirks index and brief
original peanut/fly analysis. Executed feeding/reentry limits, paired one-dollar
rewards, zero-delay wraparound, the retained new-park quota, Diner page changes,
fly-mark FIFO and shared RNG behavior. Added E17. These diversions are excluded
from Swift implementation by project scope. No production or remote changes.

**Revision 0.2b, 25 October 2026:** Executed bank credit/manual repayment,
automatic payment/foreclosure boundaries and persistent payoff sequences.
Established the supplied 5,000 credit ceiling, final-installment overcharge
and a shared-RNG bank visitor-initialization consumer. Added E16 and the
restartable bank evidence packet. No production Swift or remote changes.

**Revision 0.2a, 24 October 2026:** Added original auction eligibility, stock,
Vegasaurus exclusion, opening price, bid increments and buyer/seller settlement.
Added [AUCT] and reproducible probes; full auction timing and exploits remain open.

**Revision 0.2, 24 October 2026:** Mapped inventory and store labels; verified
feeding substitution, hunger/predation, separate no-vet death, full payroll,
annual birth rules, complete escape/maintenance, bonus gifts, the refunded
Vegasaurus gag and sale/ranking.
Integrated normal-load addendum 0.1a. Added matching Markdown, 79-column text
and offline HTML editions. The opening remains proposed survival advice.

**Revision 0.1a, 24 October 2026:** Separate reader and original normal-load
execution addendum; ordinary loading preserves the running RNG.

**Revision 0.1, 24 October 2026:** First mechanics/survival draft. Added verified
daily ordering, conditional fee reachability, monthly stock arithmetic and
the seed-versus-save/demo distinction. Integrated earlier corrected findings.
No successful full-game completion claim.

[PREF]: #pref-about-this-guide

[FAST]: #fast-a-cautious-opening-checklist

[TIME]: #time-days-weeks-months-and-quarters

[CASH]: #cash-money-orders-and-the-bank

[VISI]: #visi-attendance-parking-and-ticket-prices

[STAF]: #staf-what-your-employees-actually-do

[FOOD]: #food-feeding-spoilage-and-planting

[SHOP]: #shop-food-stands-gifts-and-restrooms

[FENC]: #fenc-fences-and-escapes

[EVNT]: #evnt-events-rustlers-and-plague

[BRED]: #bred-breeding-and-herd-size

[DNOS]: #dnos-dinosaur-reference-table

[AUCT]: #auct-auctions-stock-and-bids

[SALE]: #sale-selling-the-park-and-reaching-the-leaderboard

[RNGS]: #rngs-randomness-saving-and-reloading

[FAQS]: #faqs-myths-and-practical-questions

[OPEN]: #open-what-this-baseline-does-not-claim

[ENGN]: #engn-evidence-build-identity-and-methods

[CRED]: #cred-credits-licence-and-revision-history

[QUIR]: #quir-quirks-traps-and-misleading-numbers

[SIDE]: #side-peanuts-window-shop-and-the-diner-fly

[OFFC]: #offc-office-desk-reports-and-sale-markers

[OPTS]: #opts-music-sound-fx-and-animation

[E30]: ../docs/dinopark-tycoon/ledger-posting/REPORT.md

[E31]: ../docs/dinopark-tycoon/live-tickets/REPORT.md

[E32]: ../docs/dinopark-tycoon/live-placement/REPORT.md

[E33]: ../docs/dinopark-tycoon/foreclosure/REPORT.md

[E34]: ../docs/E34-REPORT.md

[E35]: ../docs/E35-REPORT.md

[E36]: ../docs/E36-REPORT.md

[E37]: ../docs/E37-REPORT.md

[E38]: ../docs/E38-REPORT.md

[E39]: ../docs/E39-REPORT.md

[E40]: ../docs/E40-REPORT.md

[E41]: ../docs/E41-REPORT.md

[E42]: ../docs/E42-REPORT.md

[E43]: ../docs/E43-REPORT.md

[E44]: ../docs/E44-REPORT.md

[E45]: ../docs/E45-REPORT.md

[E46]: ../docs/E46-REPORT.md

[E47]: ../docs/REPORT.md
