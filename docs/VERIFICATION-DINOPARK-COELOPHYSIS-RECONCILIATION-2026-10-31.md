# Coelophysis purchase deadlines and read-only commit reconciliation

This continues the [DinoMart entry study](VERIFICATION-DINOPARK-DINOMART-RECONCILIATION-2026-10-31.md)
from source commit `076f8ab4ef85dd36faff0b66d7c13fb97e47cdc5` on the 0.26.1
research branch. It changes the original-backed Z purchase adapter, not the
original game. Raw game files, native states and trace databases remain private.

## Retained failure and implemented change

The earlier order selected species 4 at $1,250 and reached an arrival frame.
Committed cash was still $4,500, while working cash was reserved at $3,250.
That did not certify a dinosaur purchase. The request exceeded the player's
60-second transport deadline; its process was subsequently absent and no final
cleanup receipt was retained. That historical attempt remains unknown and was
not replayed or reconnected.

The old handler unconditionally requested 5,000, 6,000, 6,000, 8,000, 2,000 and
10,000 guest milliseconds: **37 seconds of fixed guest waits**, before any
extra catalogue preparation or observation overhead. The retained sampled ticks
show 5,008, 6,007 and 6,007 milliseconds between preparation, selection, price
and arrival frames. These establish the executed intervals; they do not isolate
the observer's causal share of the wall-clock timeout.

Z now selects an authored bounded purchase helper. It sends the same five
original inputs, in the same order: select dinosaur, select price, order,
place in the first pen and confirm placement. Each press is delivered once and
its original ticket is retained. After consuming its press/release interval,
the helper checks the actual phase pixels, balances and released mouse state.
It advances in at most 500 ms guest slices only while the next phase is absent.
It never repeats a press to obtain a cleaner observation.

One **40-second application deadline** covers the Z request from its initial
observation through preparation, native phases, oracle readback and final
witness. It is propagated to the real debugger underneath the input wrapper.
Native RPCs have a five-second cap; a fresh request is not sent unless that
allowance remains. The helper requests at most 15 seconds for an individual
execution interval. The private passive observer composes owned breakpoint
stops under its separately recorded 120-second allowance; it does not establish
that per-interval request limit under instrumentation. The shared 40-second
deadline on the real native RPC session remains active across that composition
and is the bounded-return condition exercised by the original-game trials.
A guest-phase budget bounds an unchanged display.
Nested helpers adopt the earlier enclosing request deadline. A typed admission
failure distinguishes a definitely undispatched RPC from an uncertain transport
failure: only the former restores the prior phase and input receipt. A missing
reply after dispatch still blocks continuation of that attempted input.
An exhausted application wait raises to the existing paused-provider recovery
path before the outer 60-second process deadline. A bounded cleanup window lets
the original run pause and restore timing; a three-second status scope checks
recovery eligibility after releasing the action budget. This is not a hard
deadline for arbitrary host filesystem operations or a guarantee that
an unresponsive transport or arbitrary instrumentation can always be retained.
The standalone legacy scene runner retains its earlier synchronous behavior;
the original-backed Z provider enables the bounded helper explicitly.

The first original-game trial of this bound stopped safely at the delivered
order, with its provider still paused and responsive. The request took 35.07
seconds before RPC admission stopped; 113 retained run segments accounted for
32.81 host seconds and 19.82 guest seconds, including catalogue preparation.
Delivery had not yet reached the placement view. Faster polling alone therefore
does not make every instrumented purchase fit one request.

A held order now exposes **`continue dinosaur order`** as its only ordinary
action. Each fresh request is bounded, starts from the retained phase and
waits for that phase before issuing a later input. It never resends an accepted
selection, price, order, placement or confirmation. Phase guest allowances are
cumulative across requests, and repeated failures retain the original buy's
session, order and recovery ID. Unsupported or stale contexts remain blocked.
Local actions share the live scene dispatch function rather than a second
whitelist that can silently omit a new action.

The final-deadline trial exposed another false rejection at the price phase.
After one original selection and one price press, all 25 retained selected
frames failed the fixed 48-anchor predicate at 36/48. Every fixed BUY anchor
matched; the card's anchors matched completely under a small horizontal
translation. The continuation consumed its remaining cumulative allowance and
stopped without sending BUY. Its original recovery ID and live guest were
retained. That particular order remains uncompleted; it was not patched live,
replayed, or restored to pretend it succeeded.

The selected-price predicate now treats the two layout groups separately:
all **13 BUY anchors remain fixed**, and all **35 card anchors** must match
together at one offset within -24 through +24 pixels. Multiple matching offsets
are retained as alternatives; none is used as a click target. The next BUY
coordinate stays fixed. The original species-4 and $1,250 fields still have to
match before that input. The imported predicates and their thresholds are
unchanged, and this projection applies only to the selected-price phase.
Independent retained-frame review accepted the selected reference and all 25
affected frames, and rejected two pre-price and three Vegasaurus frames.
Separate regressions reject a wrong native species or price, altered fixed
anchors, card anchors without a common offset, out-of-range motion, rejected
views and pending pointer release. An exhausted cumulative wait is never
renewed to accommodate a new observation.

A later first-selection trial exposed the same layout issue in the distinct
`coel_picked` profile, before any price or order input. The request returned in
35.037 seconds; one continuation used the remaining cumulative allowance in
6.450 seconds. Its selection was delivered once and balances stayed unchanged.
This profile has **38 moving card anchors and 10 fixed BUY-control anchors**,
not the selected-price profile's 35/13 split. Its correction uses a separate,
narrower **-8 through +8 pixel** range around the existing price-click point.
The price coordinate and the original species/price guard after that click
are unchanged. No unqualified assumption about the species field before the
price click is introduced. Of 25 retained first-selection frames, 24 match
every anchor under the bounded translation and the transitional frame still
fails. The held older provider was not patched or replayed.

Independent review found that a real selected-price reference also satisfied
the translated picked signature. The fixed control colors overlap between
these views and do not prove an enabled or disabled state. First-selection
qualification now explicitly excludes every view accepted by the selected
matcher. A regression constructs the overlapping signatures and requires that
ambiguity to be rejected; an authored selected-frame negative alone had missed
the real overlap. The post-price native species/quote check remains separate.

## Native commit versus presentation

One original trial delivered all five inputs exactly once, reached the final
view and read cash/loan/working cash as $3,250/$5,000/$3,250, but the new
certificate incorrectly required native pen record 1. The authored boundary
fake had repeated that assumption. A retained original oracle, independently
decoded by both parent and Luna, shows record **10**, species 4, count 1 at
purchase completion and five following command observations. Both the commit
and retained-order predicates now require that observed record; a separate
regression rejects record 1. The first-plot user description is not a native
array index. No interpretation of the record's geometry prefix is needed for
this correction.

The affected live provider retains its older checker and remains uncertified;
its current pen/month/expense values were not exported by that installed
diagnostic surface. Read-only reconciliation correctly returned incomplete
with zero execution, input mutation or restore and unchanged diagnostics.
The corrected checker records its observed after-state on a future broad
commit mismatch so that this evidence is not discarded. It does not certify
the earlier held attempt retroactively.

The adapter captures a baseline before original input. A commit certificate
requires all of the following original observations:

- The qualified species/price are 4 and $1,250, and the final confirmation has
  an accepted, queued original input ticket.
- Cash changes from $4,500 to $3,250; loan stays $5,000; working cash is $3,250.
- The previously empty herd contains exactly one species-4 dinosaur in native
  pen record 10, the record used by this qualified first-plot interaction.
- The same original month has a $1,250 purchase-expense increase; the other
  monthly purchase-expense records are unchanged.

Working-cash reservation, a sprite, a successful resource read or a queued BUY
alone is insufficient. The helper records qualified native commitment before
the first post-commit frame capture or catalogue requalification, so a later
host observation failure cannot erase the
known purchase. Original game code still owns all money, herd and expense writes.

For a held `buy coelophysis`, `reconcile` binds the same session/run, original
canonical action, source revision, order identity and retained input. It reads
the original native state, after-purchase pixels and mouse release state, then
rebuilds host scene metadata and returns a fresh witness. Screenshot hooks are
explicitly disabled, including in the existing DinoMart navigation qualifier.
It sends no input,
runs no guest code and restores no checkpoint. `input.mouse.state` is a read;
it must not be counted as an input mutation merely because of its method name.

A reservation-only, wrong-species, unproved-expense, unqualified-view or
pending-release state stays held. The original diagnostic remains unchanged.
After a continuation completes, the original hold remains until **`reconcile`**
qualifies the original buy; a processing acknowledgement cannot mint that
certificate. A missing processing marker, commit phase or proof produces no
successful acknowledgement. Existing player and Batch reconciliation consume
the same original-action certificate. Automatically driving these continuations
from a Batch plan is separate work; this does not claim native Batch end-to-end
acceptance. Live
checkpoint metadata also retains the order record.

## Original-game qualification of the corrected adapter

The final pinned source completed an original-game order in a single retained
guest. The first buy returned its controlled application hold in about
**35.1 seconds**; one advertised continuation completed the remaining phases
in **12.4 seconds**. A literal `reconcile` then certified the original buy in
**0.09 seconds**. The 60-second transport and 40-second application limits
were unchanged. This verifies bounded multi-request progress, not a one-call
purchase guarantee.

The parent independently checked the retained proof and every phase ticket:
selection, price, order, placement and confirmation were each accepted exactly
once under one order ID. Cash and working cash changed from $4,500 to $3,250;
loan stayed $5,000. The empty herd became exactly one species-4 dinosaur in
native record 10. Month remained zero, its purchase-expense entry changed from
zero to $1,250, and the other eleven expense entries stayed zero.

The read-only certificate identified the original canonical buy and original
recovery ID, with a fresh DinoMart witness. Counters recorded **zero execution,
input mutation or restore calls**, one mouse-state read, the same PID/session/
run and an unchanged diagnostic hash. The continuation acknowledgement alone
had retained the hold; only this certificate cleared it. The source matched
all nine frozen runtime files and source commit `72e82e1e`.

Bootstrap and land were explicitly unobserved by the passive 97/13 capture.
After land's canonical success, all 221 original-byte guards passed and the
observers were installed once on the native owner, with zero execution/input/
restore calls at installation. The original 192-file folder remained unchanged.
Earlier held attempts keep their own source pins and unknown outcomes; this
fresh qualification does not retroactively certify them.

## Source checks

The focused regression first failed on the old handler's 37,000 fixed guest
milliseconds. Its authored native-boundary fake now completes already-ready
phases without paying those sleeps. Separate checks exercise delayed arrival
without another order press, application-budget exhaustion with a retained
ticket, confirmed commitment followed by failed scene requalification,
read-only recovery, stale attempt rejection, wrong species/expense, and a
pending mouse release. These are source tests, not original-game evidence.

The imported scene-class identity and sampled profile hashes remain separate
from the updated adapter class and new purchase-helper source hashes. No
original media or executable bytes are added to source or package data.

The final source check ran **215 passed / 19 skipped** across the affected
purchase, recovery, Z, Batch and debugger files. Five separately selected real
native fixture checks passed, covering the shared deadline, paused-provider
readback with a stored image, speed restoration, input evidence after restart,
and source/patch isolation. Those authored fixtures are separate from the
original DinoPark trials below. Independent Luna source review found no further
material defect in the final deadline/admission change.

The complete suite finished **2,127 passed / 132 skipped / 12 failed /
23 errors**. The 35 failure/error test IDs exactly match the retained baseline:
Linux ELF/linker fixtures are unsuitable for the current macOS toolchain, and
managed-format fixtures report missing parser dependencies. No new failure ID
appeared; the complete suite is still not green. A mistyped native-check
selection initially collected no tests; the corrected five-test selection is
the evidence quoted above.

The research source remains on its 0.26.1 branch. The old backend release path
was absent, so native checks use the existing 0.27.0 installation's backend
after verifying its full binary digest equals the earlier retained backend.
This qualifies that backend with the pinned research source, not the 0.27.0
Python core or a release build. Sound uses the dummy audio driver, disabled
mixer and disabled MIDI. No package, native build, installation or release is
made by this change.

## Continued caller and filename investigation

An independently byte-checked slice covers 323 original instruction rows with
zero mismatches against the relocated MZ image. It connects the active dinosaur
record, its first-word species index plus 180, the four-byte offset table in
`STRINGS.DAT`, and the filename returned to the ACT loader. In the selected
180–199 table span there are 19 dinosaur ACT filenames and one message. The
constructor's initial count is 20; the legal live record domain remains a
runtime question. Neither those filenames nor the message names `BUS.ACT`,
`OFFICE.ACT` or `PEOPLE.ACT`. This narrows this producer only; other paths and
abnormal records remain open.

One unresolved entry previously described as a recursive forwarder is a
separate function after a far return. Its body forwards unchanged arguments
to the ACT loader, but its own incoming caller remains unqualified. Narrowing
its role does not remove it from the 97 outstanding caller/producer cases.
The other ten asset candidates retain their earlier scoped evidence. No asset
is certified globally unused from a missing literal or a bounded no-hit run.

A separate immutable-database screen examined **8,503 stored non-call rows
with targets**; none targets the remaining 97 entries. Ninety-three entries
have an immediately adjacent decoded predecessor, and every one terminates
unconditionally: 84 far returns, seven near returns and two jumps. All 93
predecessor byte sequences matched the original relocated image. Four entries
have no decoded adjacent predecessor. This narrows modeled direct/fallthrough
routes independently of the earlier call scan. Unmodeled indirect, constructed
return, segmented and undecoded paths remain open; the count of unresolved
entries stays 97.

The canonical file-backed load identity is measured over 250,048 bytes after
4,139 relocations at the declared load segment. It is separate from an older
database-region digest with a different or unexplained span. Byte identity and
this producer trace do not establish runtime use of a filename.

## Friction and follow-up boundaries

- The input wrapper did not itself establish a deadline on the native RPC
  session. The helper now unwraps that session and shares the enclosing request
  deadline. A cleanup reserve and a separately bounded status read preserve a
  reachable paused provider when application admission expires.
- A queued order can require more instrumented host time than one request
  allows. The explicit continuation retains phase and ticket identity across
  requests. Automatic Batch driving of this particular continuation still
  needs its own native qualification; a generic completion certificate alone
  does not prove that consumer path.
- A later final-source trial exceeded the transport deadline during the
  earlier land purchase, before any Coelophysis attempt. The process-backed
  consumer reported an unknown action outcome and killed its worker. This is
  separate from the bounded dinosaur handler and remains an uncovered setup
  recovery case. The supported consumer caps its timeout at 60 seconds;
  silently changing that contract would mask the test boundary. Heavy observer
  setup and land intervals must be scoped separately when qualifying the
  dinosaur change, with every omitted tracing interval recorded as unobserved.
- A second live action whitelist omitted the new continuation and could
  acknowledge a no-op. The scene runner and tests now use the shared local
  dispatcher, and acknowledgement requires a matching processed-order event,
  final phase and commit proof.
- A first post-commit screenshot failure could hide an already completed
  business effect. Native commitment is now retained before that screenshot;
  display qualification and original-action completion remain separate.
- The authored pen-1 fake agreed with an incorrect production assumption.
  Independent original-memory calibration was available and should have been
  checked before fixing that expectation in the certificate. The pen-10
  regression now derives its expectation from the retained original oracle.
  The installed mismatch diagnostic exposed cash and input receipts but not
  the other failed-proof fields. Future held-state inspection should return
  bounded native observations separately from whether the current qualifier
  accepts them; an unqualified outcome must remain unknown. This change
  retains the observed after-state in the private broad-guard diagnostic.
- Reconciliation screenshots must disable hooks. A frame capture that runs a
  hook is not read-only. The source checks include the real hook dispatcher.
- Keeping a provider alive preserves its guest and receipts, not a supported
  way to replace its loaded adapter. Testing a later recognition fix required
  a fresh pinned guest while the earlier unknown attempts stayed paused. A
  future reviewed-definition handoff would need explicit same-guest ownership,
  source revision and input-history checks; arbitrary hot reload is not a
  recovery mechanism supplied by this change.
- A known successful purchase was canonically rewound to the pre-purchase
  checkpoint, with `restored`, `replay_safe`, a same-session witness and equal
  native fields. The next new order then failed in preparation with "Scene
  parent must be the current revision": restored host scene IDs referred to
  an older revision while the persistent scene history retained its later
  head. No selection or purchase input had been sent. The planned host fault
  did not trigger, so that case is not native fault-recovery evidence. A
  restore should qualify the authored scene namespace as well as native state,
  while preserving all earlier revisions; it must not claim friction-free
  replay from native-field equality alone. The private controller's single-use
  restore gate also rejects held attempts. No second canonical restore was
  attempted through that gate, so public-provider eligibility was not tested.
- Filename producers require the record, index arithmetic, resource offset
  table and reader path to be linked. A future reusable producer report should
  expose those edges and the legal-domain assumptions; literal scans and a
  no-hit trace remain supporting evidence with explicit limits.
- A deferred-observer trial qualified land in 2.57 seconds and installed all
  221 guarded sites with zero execution/input/restore calls, but navigation
  then stopped at an observer-owned breakpoint after only two guest
  milliseconds. The private harness had attached its callback and trace
  attributes to `BankInputSession`; internal scene execution used the native
  session underneath it. The zero-mutation installation check did not test
  actual native callback delivery. This is a harness attribution failure,
  separate from a game navigation timeout. A useful tool API would install
  instrumentation through an explicit native owner, with a wrapper-aware
  qualification check, instead of relying on instance attribute assignment.

The earlier eight evidence packets were rechecked read-only: **16,133 members,
zero size or hash mismatches**. Current live contexts remain outside that
immutable historical claim. Recovery experiments retain their individual
source pins; a later fix is never attributed to an already running older
provider. GitHub is unavailable at the user's direction, so this follow-up is
delivered through the local hub and PR #41 registry rather than a GitHub write.
