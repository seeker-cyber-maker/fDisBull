# DotBox development handoff

Updated 19 November 2026. This is a development continuation, not a release or
proof of live desktop input through the ownership fence.

## Latest continuation: composable RTS actions and dynamic entities

19 November 2026. The user's RTS correction is implemented as separate action
primitives, with no fixed select–Move–target continuation. See
[RTS_PRIMITIVES.md](RTS_PRIMITIVES.md), the `rts` guide and `dotbox rts` CLI.
The bounded world contract includes visible NPCs/allies/hazards, independent
faction/control/commandability, observation-scoped or incarnation-scoped
identity, logical groups and mission events. Its projection feeds the existing
scene schema/store. The controller binds one single-use intent to the complete
observation and provider admission, with sticky uncertainty after ambiguous
delivery and no automatic event dismissal or per-member command fallback.

The original Dune II study remains private evidence. Its captured worlds are
reprocessed through the new public schema without promoting unknown control,
entity lifetimes or current readiness. Source-level OpenDUNE findings inform
the interface, but right-click semantics, original NPC behavior and story-event
bindings require their own original-game qualification. No new native game is
launched by this source slice. The service's ordinary desktop input boundary is
unchanged; an actual live provider must enforce its current ownership/context
fence inside every operation, including all held-gesture phases.

The agent-board task and checkpoint writes were both rejected with
`PILOT_CAPACITY`; the service reported that nothing was committed. The prior
resolved RTS study and checkpoint remain authoritative board history. This
source handoff records the continuation without deleting that history or
changing board storage policy.

Fresh [verification](evidence/rts-primitives-2026-11-19.json): 101 public RTS
cases and an independent 113-case run passed. The full repository suite passed
1,169 tests; 15 native fixtures were skipped because no native inputs were
configured for this offline run. All 21 original captures were reprocessed
against the final world module into four stores; 80 stale/cross-branch writes
and three cross-restore diffs were refused. This does not add live gameplay
qualification.

Next: integrate the qualified original v1.0 reader and per-action input bindings
through the new provider protocol, then exercise the independent primitives in
a fresh owned original-game session. Native multi-selection remains unavailable
unless a real supported route is demonstrated; logical groups already work
without claiming native selection.

## Previous continuation: execute the deterministic Dune batch

18 November 2026. The user supplied the original English DOS RIP edition and
requested actual deterministic setup/input/probe/rewind trials, including a
no-hit timeout. [DUNE_BATCH_PROBE.md](DUNE_BATCH_PROBE.md) records the local
experiment and links its sanitized receipt and reusable experimental runner.
The initial nine-trial full-observation batch took 18.080 seconds, covering six
visible controls, an empty row, idle and a repeated map choice. All ten memory
restores matched CPU registers and 640 KiB RAM; the map repeat matched dispatch,
final RAM, registers and screenshot. A changed authored mounted-file canary
kept its newer contents. Actual game files were unchanged during the measured
trials/restores. `DUNE21S0.SAV` had already changed during pre-checkpoint startup;
that difference from the unchanged supplied archive is retained in the receipt.
The reviewed reusable runner then completed the same nine-row dispatch profile
in 3.233 seconds, plus 0.418 seconds for checkpoint preparation. It used DotBox's
own Python transport with the retained native executable. All destination/fallback
entries were reached after one guest millisecond; idle exhausted 30 frames/428
guest milliseconds. Stops occur before instruction execution, so the first full
pass remains the evidence for visible effects. The second batch also passed
all ten restore checks and retired pending clicks through restore.

The map and conversation rows expose different resolved handlers. Arrow controls
reach original navigation callbacks; the down arrow is intercepted by Leto's
dialogue in the tested starting state. The center control opens the floorplan.
This is a retained dispatch map and observed opening outcomes, not full game
semantics, a callable deep-entry contract or strategic-loop qualification.

The run used the existing fDisBull offline 0.34.1 native executable, not the
newer DotBox-owned native binary. Its original protocol and the later
generation-fenced ownership protocol remain distinct. Preparation time is
reported separately from the warm batch. Original-Dot ownership/capture,
repeatable Police Quest controls and missed-briefing rewind remain open.

## Previous continuation: record transient dispatch across controls

18 November 2026. The user treats the debugger as an active experimental
instrument: arm candidate exits/destinations together, trigger one control,
record transient hits, then restore a comparable memory baseline and compare
other controls. Added the protocol to [BEHAVIOR_AND_ENTRY_POINTS.md](BEHAVIOR_AND_ENTRY_POINTS.md#record-transient-paths-across-controls),
available in the existing `entrypoints` topic, and aligned bootstrap, reversing,
transition, model and agent-start guidance.

Retain the cheap dispatch map before explaining every handler or qualifying a
direct invocation. Record actual input delivery, ordered site/selector/target
evidence, the armed set, stopping condition and coverage. First-hit stops censor
later execution; missing or uninstrumented observations are not absent effects.
Shared exits and selectors retain many-to-many relationships. Repeat/idle/
contrast trials address concrete ambiguities rather than gating the first map.

Recordings live outside the guest checkpoint and survive rewind. Each restored
trial refreshes branch/mapping/input bindings and reconciles owned probes.
Memory rewind preserves current files; separately prepared helper fixtures or
explicitly recorded environment differences are needed when a trial writes disk.
Helpers remain isolated from player progression and ordinary visible gameplay.

Source reuse is concrete but composed survey execution remains unimplemented:
`z_capture_watch.py` supplies a 1-16-candidate flat32 E8 first-hit watch,
`execution_trace.py` supplies its bounded stopped-real-mode predicate workflow,
and `event_search.py` retrospectively narrows retained evidence. These three
files match audited source, the offline fDisBull 0.34.1 wheel/RECORD and pinned
Git source at `ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd`. They do not establish
an automatic six-button sweep or a shared restore/probe lifecycle.

Fresh verification: 23 kit tests passed. A rebuilt wheel installed into a fresh
target matched all 56 resources, 35 runtime modules and 26 guide functions;
six affected CLI guides matched source and the installed offline doctor passed
with native qualification false. Independent protocol and source-contract
reviews found no blockers. See [the verification receipt](
evidence/breakpoint-survey-guidance-2026-11-18.json). BBS task:
`e-86c5f116-b3da-49ec-a11e-c001c0ac2566` in project `dotbox`.

The next implementation is a bounded action/probe trial coordinator and retained
dispatch observations around qualified capture and memory restore. Preserve the
existing original-Dot ownership/capture and Police Quest route/rewind gates.
No new native build, game trial, survey runtime or release was performed here.

## Previous continuation: behavior hypotheses and alternative entry paths

18 November 2026. Added [BEHAVIOR_AND_ENTRY_POINTS.md](BEHAVIOR_AND_ENTRY_POINTS.md),
packaged as `dotbox guide --topic entrypoints`. Agents use plausible authored
implementations to predict distinguishing code, state and execution evidence.
Retain several routes to one operation with their arguments, skipped setup,
continuation and scoped equivalence. Observation hooks and callable entries
remain separate. Modal, tail-transfer and deferred behavior need their own
contracts; an unknown outcome can still support a qualified attempt.

[Navigation](NAVIGATION.md) now describes position discovery, ordinary-motion
verification, controlled same-room perturbation, coherent placement, normal
crossing observation, original room-entry reuse and constructed research states.
Use already qualified capabilities without replaying earlier learning stages.
Helpers can investigate beyond normal progression with explicit imposed-state
provenance. Visible play retains original movement/events, including supported
click delivery without unnecessary pointer travel. Direct original Save/Load
retains its game/file effects and remains separate from memory-only rewind.

Four fDisBull files were verified against audited source, offline 0.34.1 wheel
contents and RECORD hashes, and pinned Git source at
`ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd`: `z_native.py`, `z_call_contract.py`,
`assisted_travel.py` and `runtime-navigation.md`. Their limited call/return and
placement-plus-original-portal contracts are reusable work, not new DotBox
adapters. No runtime implementation or original-game execution was added here.

The earlier blanket missing-menu-archive claim is corrected. The exact
`fdisbull-menu-event-discovery-20261107.zip` was recovered again: 120,922 bytes,
SHA-256 `cff20df90a2ac3db1589dfc83ca0c663150f92d6b885fb1f42ecc5773e60e1d7`.
All 24 checksum entries and nine source-manifest outputs matched. Its private
game companion was not recovered; later MR !119 equivalence and release/DotBox
integration are not established. Historical evidence receipts remain unchanged.

Fresh verification: 23 kit tests passed; the rebuilt wheel installed into a
fresh target matched all 56 resources, 35 runtime modules and 26 topic functions.
Nine affected CLI guides matched source; the installed offline doctor passed
with native qualification false. Independent integrated-design/archive and
native-source-contract reviews found no blockers. See [the current receipt](
evidence/behavior-entry-guidance-2026-11-18.json). Current BBS work: project
dotbox, ticket e-e618b6d6-8b8f-4269-9e4a-4248e3663682.

The next runtime slice remains supported original-Dot ownership and bounded
capture, then one qualified alternative route with retained normal fallback.
An offline hypothesis/entry ledger can extend the proposed family/evidence
store independently. Preserve the one functional Police Quest shower run;
repeatable route/timing, live coordinates, assisted placement and missed-briefing
memory rewind still require their actual qualification.

## Previous continuation: generic transitions and analysis dependencies

18 November 2026. The user generalizes menus, screen changes and room entry as
event-conditioned state transitions. Added [EVENT_TRANSITIONS.md](EVENT_TRANSITIONS.md),
packaged as `dotbox guide --topic transitions`, and aligned the existing world,
process, reversing, incremental-play and agent entry guidance.

The design separates reusable families/rules, concrete bindings and observed
occurrences. A recovered dispatcher, structural pattern or data schema can
enumerate siblings and satisfy prerequisites for independent analysis. Transfer
established common facts without repeating an identical experiment for every
instance; keep interpretation, execution support and current applicability
separate. Invocation readiness does not require knowing the outcome in advance.
Track dependency invalidation, bounded expansion and the existing foreground
budget. The knowledge frontier is distinct from player reachability.

The recovered XCOM selector rule and inspected serializer candidate extractor
are concrete precedents. Their documented bounds remain: no automatic induction
from one click or all-button count. That pass did not reconcile the XCOM add-on
source archive; the latest continuation above corrects its recovery status.
This slice implements no family ledger, general structural scanner, scheduler
or live capture. The existing Police Quest controls/rewind acceptance is unchanged.

Fresh verification: 23 existing kit tests passed; a rebuilt wheel installed into
an isolated target matched 55 resources and 35 runtime modules. All 25 topic
functions and seven affected CLI guides matched source; the offline doctor
passed with native qualification false. Independent design and source-reuse
reviews passed. See [the verification receipt](
evidence/event-transition-guidance-2026-11-18.json). Current BBS work:
project dotbox, ticket e-a784add1-d1b9-4879-9dff-5819a247eba9.

An offline family/binding/evidence ledger fed by existing census outputs is a
bounded future slice. DotBox-owned live capture and further native scanning
remain separate integration work; original Cryo Dune remains the next transfer
target after the declared generic baseline.

## Previous continuation: bootstrap strategic interfaces and model event loops

The user added the original main-menu analysis workflow and the missing process
model: Options/control mappings, Load/serializer state, New Game/intro prompts,
isolated helper perturbations, phased/timed events and action-bound visual/native
evidence. Read [BOOTSTRAP_AND_EVENT_LOOPS.md](BOOTSTRAP_AND_EVENT_LOOPS.md) and
[XCOM_REUSE.md](XCOM_REUSE.md), packaged as `loops` and `xcom`.

Recovered fDisBull MR !82 reports separate named startup controls, serializer
transfer/adoption/continuation/display boundaries and later original-menu event
discovery. A later UFO cold-context run reached Geoscape at 171.355 seconds but
its full save/money goal remained incomplete after 91.060 minutes. Prepared
route timings and earlier assisted runs have different scopes. No universal
ten-minute minimum or complete XCOM loop qualification follows from them.
That XCOM-specific pass recovered the public note for the source-only 7 November
add-on without reconciling its archive. See the latest continuation above for
the corrected recovery status; selected-release integration remains separate.

The inspected DinoPark provider already has sparse pixel witnesses, targeted
two/four-boundary original transaction checks, retained attempts and guest-phase
budgets. Generic fDisBull event-search/trace and serializer modules are reuse
candidates. A broad automatic DinoPark breakpoint-discovery sweep was not located
in those provider modules. Their primitives do not qualify DotBox's pending
owned capture or arbitrary executable modes.

The 180-second policy is now explicitly the initial usable-control evaluation
profile. A complex cold-preparation job can declare a longer bound and milestones
while preserving the original timeline and missed deadlines. The 15-second/two-
probe foreground limit is unchanged. First visibility, useful control, relevant
operating loop and complete goal are distinct. Natural movement is useful time;
menu transitions may offer none, and no artificial delays should conceal work.

This continuation changes design and packaged guidance only. It adds no process
store, XCOM/DinoPark provider port, live event capture or game run. Fresh checks:
23 kit tests passed; a rebuilt wheel installed into an isolated target matched
54 resources and 35 runtime modules. All 24 guide topic functions and nine CLI
guides matched source. The offline doctor passed without native qualification;
117 relative links and the play skill frontmatter were checked. Independent
design, XCOM and DinoPark/provenance reviews passed, with scoped continuation
and source-locator corrections applied. See the [verification receipt](
evidence/bootstrap-event-loop-guidance-2026-11-18.json). The BBS work ticket is
`e-3f9890c0-4d46-4353-a7d2-380c0b0f1c7e` in project `fdb`, role `fdb-dotbox-dev`.

## Previous continuation: reuse DinoPark's recovered work

The user identified extensive prior DinoPark Tycoon research. The coordinator
read the saved E55 handoff, behavioral report, 22-card game-story map and
progress receipt, then inspected the existing fDisBull 0.34.1 provider and its
later 3 November handoff. Read [DINOPARK_REUSE.md](DINOPARK_REUSE.md), packaged
as `dotbox guide --topic dinopark`, before new menu/state discovery.

The research already distinguishes committed state, pending transactions,
continuing session values, interface selection and presentation. The later
provider adds bounded original-game controls, retained attempts, native effect
proofs and read-only reconciliation. Use these as inputs to the world model
and a small DotBox-owned adapter. Dune remains the next selected target; another
complete DinoPark playthrough is not required before proceeding.

The inspected source is manifest commit
`ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd`. Its six DinoPark Python modules and
nine data/provenance files match the wheel RECORD and pinned public source.
The older UDC definition reconstructs original bytes with zero semantic blocks;
it is separate from recovered rule knowledge. The later handoff still retains
97 caller/producer questions, 13 asset candidates and a confirmed purchase with
unqualified final presentation. Those are scoped investigation questions, not
a reason to repeat settled mechanics or delay useful integration.

This continuation adds a reuse guide and aligns the existing world-model,
investigation and Dune plans. It imports no private reports, game material or
fDisBull runtime code, executes no DinoPark session, and does not yet implement
the world store or provider port. Do not copy the old provider's disk-change
checkpoint restriction into DotBox's requested memory-only rewind.

Fresh verification: **23 existing kit tests passed**. A new ordinary wheel
installed into an isolated target matched all 52 packaged resources and 35
runtime modules, registered 22 topics and returned the five checked guide
texts exactly. The offline doctor passed while reporting native qualification
false. Source integrity checks matched all 15 DinoPark files to the wheel and
pinned public commit, plus the three bounded-helper provenance hashes.
Independent source/documentation review was completed; its deadline wording
and inventory-scope clarifications were applied. See the [verification receipt](
evidence/dinopark-reuse-guidance-2026-11-18.json). Historical DinoPark test counts
were not rerun or promoted to new gameplay qualification.

## Current architecture decision: Dot's internal game model

Follow-up on 18 November: reverse engineering is an ongoing requirement for
ambiguous meanings, dependency discovery and storage reuse, including non-AGI
games. Read [the investigation workflow](REVERSE_ENGINEERING.md) and
[Dune validation](DUNE_VALIDATION.md), also packaged as `reversing` and `dune`.
The current inspector has bounded identity/search/diff/linear disassembly;
native capture/watch/trace integration and automatic native xref/def-use analysis
remain missing. The next reusable live slice is a bounded owned evidence
capture operation feeding offline analysis and the world model.

The user proposed Dune as the next non-AGI direction, interpreted as the original
Cryo game from the description and existing project evidence. Preserve
the existing 15 November assisted Dune CD opening receipt: four views were
reached, but dialogue semantics, story effects and later strategy were not
qualified. Freeze a fresh generic baseline and record this prior/manual exposure
before target-specific adaptation. The new plan covers menu/subject identity,
conversation, travel, one delayed order, clock semantics and warm reuse. This
documentation pass consulted that receipt and the original manual; it did not
inspect Dune assets, execute the game or recover Dune internals.

Fresh verification of this follow-up: **59 existing kit/inspection tests passed**.
The rebuilt ordinary wheel was installed into a new directory; the `world`,
`reversing`, `dune`, `play` and `guides` topics matched their source text. All
51 packaged resources and 35 runtime modules matched; 21 topics were registered,
and the offline doctor passed without native qualification. The source links
and patch whitespace were checked. See the [verification receipt](
evidence/reverse-engineering-dune-guidance-2026-11-18.json). This is guidance
and packaging verification, not a live investigation or strategic-game test.

The user clarified that Dot should build her own convenient representation of
the game's entities, relationships, rules and possibilities, while z-scenes
describe the relevant present situation. Read [WORLD_MODEL.md](WORLD_MODEL.md)
or the packaged `dotbox guide --topic world` before extending scene storage.
Use a typed relational foundation, initially separate from the strict existing
SceneStore, with optional text/vector indexes over useful semantic material.
Dot can create abstractions and hypotheses; observations, predictions, model
revisions and live state revisions remain distinct. Rewind retains knowledge
while invalidating dynamic bindings to the abandoned branch.

This documentation continuation is based on PR #10's primary head
`adade95acad4ae5062de99f76805305e7a3a2203` and independent mirror head
`6dbef65fe923eb54a1a498d63d5c8259671578f1`, with the same input tree
`0e4e2a82826b274b1ef211f29a988c61d38e753a`. It preserves those histories and
adds packaged guidance; it does not implement WorldStore, embeddings, live
driving or another rewind operation. Complete cheap static extraction and
draft compilation are compatible with incremental live qualification.

The next useful implementation is a private versioned world store with stable
typed entities/relations, evidence and conditional rule references. Use the
recovered DinoPark state/transaction contracts as reference inputs alongside
AGI draft import and observation linking. Exact neighborhood/dependency queries
should feed the existing scene/action admission path. Semantic indexing can
follow a measured retrieval need. Do not insert new tables into SceneStore
without a migration, or relabel its last-fact cache as a complete event history.

Fresh verification for this guidance change: all 23 existing kit tests passed.
A newly built ordinary wheel was installed into a new directory, imported from
that directory rather than the checkout, and returned the exact source text for
`guide --topic world`. All 49 packaged resource bytes/hashes matched the source;
19 guide topics were registered and the offline doctor passed without claiming
native qualification. Relative document links and the patch whitespace check
passed. An independent read-only review found no actionable issues. The
[verification receipt](evidence/world-model-guidance-2026-11-18.json) records the
reused dependency environment and initial environment/checker corrections.
No native rebuild or gameplay test was part of this documentation change.

## Start here

- Primary repository: `seeker-cyber-maker/DotBox`.
- Independent mirror: `TiGa-RCE/DotBox`.
- Active upstream implementation: draft PR #2, branch
  `codex/standalone-engine-20261116`, inspected at
  `3e011712c628b86642003e780fbf482e5c913018`.
- Follow-up branch: `codex/async-turn-fence-20261117`, based on that exact commit.
- Learning-kit continuation: `codex/incremental-learning-kit-20261117`,
  based on primary async-turn-fence commit
  `999dc0ed788e6b20593166a4e9e40b2c2525004e` (draft PR #3). The independent
  mirror's matching parent is `69c5289786b2752bffd669bdf605745432a7929c`;
  those parents have identical trees but different account commit metadata.
- Conversational-scene continuation: `codex/conversational-scenes-20261117`,
  based on primary learning-kit commit `605f41240f271f2311a997495b3eb0292c574f35`
  (draft PR #4). Its independent mirror parent is
  `c131661fece58a3d096938df5632d2986cf0ed90`; their shared tree is
  `55265b1641e9d97a8f52e1e427fa2d3039c6ff0d`.
- Predictive-preparation continuation:
  `codex/predictive-scene-preparation-20261117`, based on primary conversation
  commit `676ed6fdc16cafccbd4d676a016a5d5d4deeb463` (draft PR #5).
  Its independent mirror parent is `e3e2548c5cefda60406ee4a8402edbbea1d9684a`;
  their shared tree is `e25e44aa791ecc4159985a9c093d56e9c7e8737b`.
- Stateful-scene continuation: `codex/state-aware-scenes-20261117`,
  based on primary predictive-preparation commit
  `2322cfbf16441343ea998d76479b7b4fbfd59340` (draft PR #6).
  Its independent mirror parent is `c88464e656912e41a74b986f416d0380e804623f`;
  their shared tree is `93e2baa150ea6e6234e23bad9ebb24c43217ac36`.
- The state continuation is now published as [draft PR #7](https://github.com/seeker-cyber-maker/DotBox/pull/7).
  Primary head is `cb72a966411a821cb860c56760675891fc0d0ea3`; independent mirror
  head is `a7c8556a992a2a64a4474104e44a36f1cf2d8c84`. Their verified shared tree is
  `4dc1a12a2e871b980db37ea78decf5d85768b4f1`. The user's explicit GitHub update
  instruction resolved the earlier automatic publication-review refusal.
- The AGI/navigation continuation is published as [draft PR #8](https://github.com/seeker-cyber-maker/DotBox/pull/8).
  Primary head is `f9572d84943c57dcdb83587f85966619ef392325`; independent mirror
  head is `b018024963dac96e75785b0fc084c63d697333a2`. Their verified shared tree is
  `707ab7a0a3ce0cb68087368389c48895ad6cd448`.
- The memory-recovery continuation is published as [draft PR #9](https://github.com/seeker-cyber-maker/DotBox/pull/9),
  branch `codex/memory-recovery-20261117`. Its initial fence snapshot has primary
  head `f364476892b309ff76fa024a739b36c2c0f6fc73`, mirror head
  `727babb122f2bc09bbfe311635e0c9b38e423c5c`, and shared tree
  `9d88e87fb4990f47a74da9f8f1c6c1609c8eb810`. The Police Quest acceptance
  specification continues on that draft branch, preserving both histories.
- Local-build continuation: `codex/local-macos-build-20261117`, based on primary
  memory-recovery head `2b61471a5159825e466ab8c201aa6e3c7cd306a2` and independent
  mirror head `d12764adc1feccfd1361af45a67c1f36ce651adf`. Their shared input tree
  is `f63ffc7cc7bddadf80db6c8355f238be146c1d90`. Use this implementation branch
  for the local build; do not assume the draft stack is merged into `main`.
- The local build's SDK fix is published in [draft PR #10](https://github.com/seeker-cyber-maker/DotBox/pull/10).
  Its publication snapshot is primary `18d374d395471ef0ef741187a955c8ad66773b70`,
  independent mirror `238b5a1bc3c9a35612bc93f7a0b9c6d74f000f23`, and shared tree
  `45d39466a994b488ed1faf767beff5f3abbcf587`. The measured Mac worktree identity
  is recorded separately below; it was not a rebuild of these later commits.
- At inspection, `main` was the design baseline at
  `10fa86d8a91bb75e0ccf3da346bc9f72eab91d03`; it did not contain the implementation.

Read `AGENTS.md`, `docs/PRODUCT.md`, `docs/CONVERSATIONAL_PLAY.md`,
`docs/GUIDE_RECONSTRUCTION.md`, `docs/INCREMENTAL_PLAY.md` and
`docs/LEARNING_KIT.md`, `docs/ENGINE_AWARE_PREPARATION.md`, `docs/NAVIGATION.md`
and `docs/RECOVERY_AND_SAVES.md` for the current work. Read `docs/OWNERSHIP_BRIDGE.md` and
`docs/OWNERSHIP_CONNECTOR.md` before changing the ownership boundary. Follow
`docs/REPOSITORIES.md` for publication. Earlier AGI/walking/HUD experiments stay
in the original developer's private checkout and snapshot. This continuation
inspected the installed fDisBull 0.34.1 package and selected pinned source; the
user's exact old x/y TAS script remains unidentified. The latest board-led
recovery did retrieve the AITD movement/menu source described in `AITD_REUSE.md`.

## What was already working

The standalone Python package owns its transport, input validation, screenshot
handling, SQLite store and persistent control definitions. It does not require
fDisBull. A prepared native DOSBox-X executable remains a separate dependency.
The normal desktop harness owns keyboard/mouse capture; direct native agent
input is disabled in that mode.

The latest upstream [live connector receipt](
evidence/ownership-connector-live-2026-11-16.json) records read-only original-Dot
observations for Dot control, human takeover and Dot return. Stopped sampling
returns unknown. Its historical 407 source and 180 installed-wheel checks were
run on the previous host and are not results from this continuation.

The connector is status-only: no turn claims/checks/releases, input, frames,
files or shell. A status response never grants input. The receipt reports that
the publisher was stopped and connection processes were left running; their
continued availability cannot be inferred from that historical receipt.

## Current continuation: cloud Linux native and functional game test

The coordinator compiled the pinned native source on its own Linux x86_64
computer and executed the full gate: **8 passed in 3.59 seconds**, four headless
and four visible, with no skips, failures or errors. The build input was local
commit `dee1213f1701917fd523911c3a477645c5bd2054`, shared tree
`1911d22aceeb546712e90f7bcc2894f4389c8315`. Missing official Debian development
packages were extracted into a private prefix; no elevated execution or Studio
connection was needed. See [the Linux test record](LOCAL_LINUX_TEST.md).

The same native executable completed one Police Quest EGA functional controls
run through ordinary desktop input: lobby, assigned locker, change to towel,
close locker, usable shower, successful activation and turn-off cleanup. All
27 recorded original and copied game input hashes were unchanged. The route
encountered latched movement, NPC dialogs and a shower collision barrier; the
game's response confirmed the final arrival. The
[controls receipt](evidence/police-quest-local-controls-2026-11-17.json) separates
this result from a reusable harness, cold preparation, latency measurement,
original-Dot ownership integration and memory rewind. Those remain open.

## Earlier local Mac native qualification

Version `0.1.0.dev7` adds `scripts/build_local_macos.py` for a fresh, private
Apple Silicon build with two compiler jobs, the pinned bundled SDL2, an ordinary
Python wheel/isolated installation and retained stage logs. Required system
dependencies remain an explicit Terminal setup step. The procedure is packaged
as `dotbox guide --topic macos`; the executable helper requires the full source
checkout, not only an exported operational kit.

`scripts/test_native.py` requires the explicit native executable and exact
JUnit identities/counts. All eight selected fixtures must execute without skips;
four headless or four visible tests can instead be selected and are reported as
that limited scope. The executable must have the same SHA-256 before and after
the run. A source receipt is metadata, not an independent binary attestation.
Installed-wheel doctor evidence remains separate from fixtures importing the
checkout's source. Runner unit tests use authored reports and do not run DOSBox-X.

The Browser plugin established command access to a logged-in Studio Terminal.
That existing connection was used for the local build. Direct SSH from the
cloud executor still fails before contacting Studio, and the platform forbids
the elevated execution path requested to diagnose that client. No Tailscale
configuration change was part of the native build.

The full `all` build succeeded on Darwin 27.2.0 arm64 with Python 3.12.16 in
**4 minutes 22 seconds**. The native gate executed exactly **eight fixtures:
four headless and four visible**, with pytest exit zero and no skipped, failed
or errored test. The executable SHA-256 stayed unchanged across the run. The
separate installed-wheel doctor reported the offline learning kit ready.

The first attempt failed at SDL2 configuration with `ld: library 'System' not
found`. The helper had resolved the SDK and direct Command Line Tools compiler
paths but had not passed the SDK root to its child processes. A minimal C probe
failed with the inherited environment and succeeded when only `SDKROOT` was set
to the selected SDK. The helper now includes `SDKROOT=sdk` in its existing
compiler-environment binding; the fresh retry passed the full build and gate.

The measured Mac checkout was primary
`6573cb5fb1c135629bac5d5ebcd1738fd91ab44c` plus that exact one-line SDK fix. Its
build-helper SHA-256 was
`bfb462f0f57e337df9e3e805185cf0b14f3232cc6cc4ef8ed1b19cc21d82a155`.
The fix was subsequently committed locally as `b25346a` and published in the
SDK-fix snapshot listed above. Do not attribute the measured binary to a later
documentation or publication commit. See the
[sanitized native-build receipt](evidence/local-macos-native-2026-11-17.json)
for the complete bounded evidence.

The focused helper suite was rerun after the fix: **39 passed**. It covers
unset and stale inherited SDK roots, propagation to a real child process and
preservation of the parent process environment. This is separate from the
eight real native fixtures. The output is a developer executable and isolated
Python environment, not a signed application or portable offline release.
The Mac result did not qualify original-Dot takeover/input integration or either
Police Quest trial. The later Linux controls pass is separate. A complete
player-facing memory-rewind API is still absent.

### Historical helper/source verification

Before the Mac run, source verification passed **802 tests**, with exactly
**eight native executable skips**. That complete source suite was not rerun for
the SDK fix. The supplied pinned base enabled the real overlay application and
repeat-application check. At that snapshot the build helper had 38 focused
checks and the strict runner had 28, including authored process cleanup and
read-only pip configuration probes. The ordinary wheel and clean offline
installation matched all 35 runtime modules, 48 resources and 18 topics;
the installed `macos` guide, export and doctor passed. Independent review found
no remaining blocker after the cancellation and pip-probe fixes. Preserve the
[earlier sanitized helper verification](evidence/local-macos-build-2026-11-17.json)
as historical evidence rather than treating its native skips as the new Mac result.

## Retained continuation: memory-only recovery and recovered AITD work

Version `0.1.0.dev6` corrects the recovery contract and adds a native source-level
restore admission fence. Revert restores memory and necessary machine/device
state; it must not replace files with older copies. A changed, closed autosave
does not itself block recovery. Immutable source/resources, mount configuration
and concrete saved-handle dependencies remain separate compatibility checks.

The native overlay advertises `input.restore_control=dotbox-restore-control-1`.
Raw `state.load` now requires `expected_generation`. The emulation-thread check
preserves owner and advances generation before cleanup/loading; stale generation
is rejected before effects. Old tagged input stays invalid after an admitted
failure. This is not a `memory_checkpoint` capability or a public Python recovery
API. The serializer and explicit `frame_keys` policy are unchanged. Native
load can rehydrate keyboard hardware state; neutral capture and verification
remain necessary. Newer mutable files must not be restored from history.

Two source audits found that DOS handle reconstruction can flush current pending
writes while reopening a file. That is persistence of current writes, not disk
rollback, and should not be confused with the historical backup/restore path
already disabled by `AGENT_StateFile`. Qualify the I/O boundary before exposing
interactive recovery. A small initial profile can exclude active writable
handles/pending writes/mutable disk images while allowing changed closed saves.
Do not omit DOS handle restoration or claim byte-preserving load without proof.

The original Charming board's stored fDisBull handoff led to the preserved
source/history archive. All 69 indexed artifacts matched size/hash. Eight
AITD continuation Python files and earlier menu/reference helpers were recovered.
Their ordinary walking controller uses current X/Z/heading, bends and bounded
stall/divergence checks; its object planner includes actor contact stances.
DotBox keeps its existing heading-aware planner and stronger footprint/safety
admission. Menus use sparse current-state and highlighted-selection guards,
with modal exclusion and separate selection/execution outcomes.

The old AITD continuation's `load()` explicitly replaces `SAVE0.ITD` from a
retained copy. Exclude that research policy from memory revert. The new installed
`aitd` topic documents the reusable parts, exact provenance and missing private
calibration. No AITD source/asset or new game-specific adapter is imported.
Historical AITD tests/replay timings were not rerun.

The existing service identity already includes native generation. An authenticated
socket regression verifies that a same-owner generation change invalidates the
old turn while an ordinary `state_revision` change does not. It does not repair
the ownership boundary automatically. A future complete recovery controller must
handle admitted failure, fresh branch/store and coherent post-restore observations;
offline SceneStores and worker candidates do not invalidate themselves.

Matching upstream source was available and both patch stages could be verified
at that memory-fence continuation, but it had not built a matching complete
native executable. The Mac native qualification above is a later result;
original-Dot live recovery remains unqualified. The historical fDisBull binary
was a different native revision and was not substituted for this overlay. The
recovered walking/menu work remains a controller reference. The user selected
the concrete Police Quest controls and rewind trials below. The later Linux
functional controls pass is recorded above; memory rewind remains open.

### Initial Police Quest specification and static investigation

The controls endpoint is changing in the locker room, closing the locker and
walking to the usable showers. Water activation is an optional separate action.
The recovery endpoint is missing the first briefing, restoring a predeadline
memory checkpoint while preserving newer disk files, and successfully attending.
Use the separate starting states and predicates in
[Police Quest acceptance](POLICE_QUEST_ACCEPTANCE.md), also installed as
`dotbox guide --topic policequest`.

Fresh read-only inspection of the supplied EGA 2.0G/AGI 2.917 files established
the two timer mechanisms: late arrival tests engine minutes on entry from the
lobby, while newspaper return accelerates a separate event countdown. Recent
key activity can affect the countdown without resetting the clock. The shower
approach stays in room 5; called LOGIC 39 is not a destination. These are static
findings and candidate observation predicates, not qualified live mappings.

The retained census matched nine resource files and all 118 LOGIC payloads.
The coordinator reran a private check of 34 operations and 16 conditions against
the current bytes; hashes and mtimes remained unchanged. That initial static
investigation launched no game or native session. The later Linux run adds one
functional route pass, while the original interpreter's clock/pause behavior
and memory restore remain unverified. The initial follow-up changed operational
resources and evidence only; runtime code and native patch were unchanged.
The existing source kit suite passed 23 checks. An ordinary wheel and clean
offline installation agree with the source on all 35 runtime modules and
47 operational resources, with 17 topics. The installed `policequest` command,
resource export and offline doctor passed; that documentation-only follow-up
did not perform native qualification.
See the [acceptance investigation receipt](evidence/police-quest-acceptance-2026-11-17.json).

### Initial memory-fence snapshot verification

| Check | Result |
| --- | --- |
| Full source suite with exact base native source supplied | 736 passed, 8 native-binary skips, 36.01 seconds |
| Independent focused native/service review | 21 passed, 4 native-binary skips; no blocking finding |
| Direct wheel and wheel rebuilt from sdist | Both built; all package bytes match |
| Source / both wheels / clean offline installation | 35 runtime modules and 46 resources match; 16 guide topics |
| Four copied focused suites outside the checkout | 44 passed, 4 native-binary skips, 3.12 seconds |
| Pinned native source and overlay | Upstream tree reconstructed; 37 base-result hashes and the 38-file final recipe verified; repeat application leaves bytes unchanged |
| Recovered AITD source archive | All 69 indexed artifact sizes and hashes matched |

The installed package used Python 3.12.14, Pillow 12.3.0, iced-x86 1.22.0 and
pytest 9.2.0, with no fDisBull or optional MCP available. The exact-base native
patch application test ran; the eight full-suite skips all require a matching
native executable. No emulator binary was built, native session launched, game
input delivered or end-to-end rewind qualified. See the
[sanitized memory-recovery receipt](evidence/memory-recovery-2026-11-17.json).

## Prior continuation: engine-aware preparation, routes and recovery

Version `0.1.0.dev5` owns the small AGI V2 logic/resource census and an offline
walking planner, with `agi`, `navigation` and `recovery` installed guide topics.
The AGI reader keeps the existing census contract, requires explicit profile
2.917, preserves per-resource failures and emits a private report plus a compact
summary. It supplies static conditions, state-write sites and resource/room
candidates; it does not read live flags, decode original-game saves or qualify
interactions. The high-bit IF displacement range remains opaque because the
consulted interpretations disagree; ordinary forward IF and signed GOTO remain
covered. The selected first-party source and license status are in `EXTRACTION.md`.

The walking planner reuses `fdisbull-spatial-map-1`, including collision footprint
and coordinate domains. Bounded heading-aware A* minimizes distance, then turns.
Unknown ground and unresolved hazards stay unavailable. All portal footprints
are blocked: plan an approach before a separately selected crossing. Collinear
steps become long legs. A proposal binds exact supplied map, scene, conditions
and state branch; `route check` reruns bounded deterministic planning and rejects
stale or edited content. Neither command establishes live freshness or moves
the actor. Existing x/y monitored controllers and frame/TAS key edges are useful
integration references, not a second input owner or a shipped live executor.

The prior recovery audit found full native checkpoint and frame-timeline machinery
already present in fDisBull and raw `state.save/load` in DotBox's native base.
Before dev6, raw load had no expected-control-generation admission/bump. The
service's run/session/generation/owner identity could consequently remain
unchanged through a world restore. That audit called for a restore fence,
input cleanup, new branch/context, immutable-dependency checks and fresh observations as
specified in `RECOVERY_AND_SAVES.md`; dev6 implements only the native control
fence portion. Ordinary `state_revision` is not a substitute
because ordinary input and saves advance it too. The user's subsequent correction
requires memory-only recovery: mounted host files retain their current versions,
and an unrelated changed autosave must not block restore. Do not implement a
matching filesystem snapshot or copy fDisBull's blanket mutable-file restriction.
Qualify native DOS handle/device behavior as well as the Python boundary.
Qualify one capture and restore
before promising a rolling rewind buffer. No live rewind was added here.

Saved-game differences are hypotheses for persistent state. Compare repeated
baseline saves, one meaningful action, static writers/consumers and observations
after the real loader reconstructs state. Keep commercial resources, saves and
raw reports private. The current static AGI reader is not a save-file decoder.

Independent review found and fixed two preparation-bound issues in the first
AGI extraction: layout was parsed before checking instruction/code limits, and
message aliases could multiply decoded text outside those limits. Code spans
and attempted instructions are now charged before more parsing. Shared text
budgets cover messages, initial object names and vocabulary; aliases reuse
unique work while emitted literal occurrences remain charged. Incremental JSON
hashing/encoding bounds the complete report before file creation. A failed
report cap produces no file. Coverage distinguishes logical alias entries from
actual attempted/admitted work. The new text allowance defaults to 256 KiB;
the report allowance defaults to 8 MiB with a 16 MiB hard ceiling.

Final verification on the calibrated build:

- **733 source tests passed, 7 native checks skipped**, in 34.72 seconds.
  The native checks require the actual source/executable acceptance inputs.
- **412 installed tests passed, 0 skipped**, in 16.60 seconds, from 13 suites
  copied outside the checkout and using authored fixtures exported from the
  installed wheel. The first invocation lacked those fixture files; that setup
  error was corrected without changing the runtime.
- **35 runtime modules, 45 resources and 15 guide topics** match source, direct
  wheel, sdist-rebuilt wheel and the clean offline installation. Neither fDisBull
  nor optional MCP is installed there. No source import is used.
- Independent AGI regression review passed all 56 focused tests and reproduced
  both original budget failures after correction. Independent navigation review
  passed 59 focused tests plus 632 separate route-oracle comparisons with no
  mismatch. The 160-by-168 authored grid used 486 expanded states for 326 steps,
  one turn and two legs under the normal 10,000-state allowance.
- Independent installed guidance/CLI review passed ten scenario checks across
  15 invocations, followed by four narrow final default/help/doctor checks.

Read-only runs against the existing private AGI resources decoded all 90
King's Quest I LOGICs and 118 Police Quest I EGA LOGICs with no layout, code,
instruction, text or value-analysis budget stop in resolve mode. The selected
profile was explicitly 2.917; prior edition identification was retained. Static
room candidates remain 81 and 42, respectively, with zero qualified executable
interactions. The first 4 MiB report default refused the roughly 4.6 MB Police
Quest census, so the final 8 MiB default was tested successfully on both games.
Final local command times, including process launch and report write, were
0.947/0.962 seconds for King's Quest outline/resolve and 1.883/1.961 seconds for
Police Quest. These exclude agent dispatch and live gameplay. Input hashes and
mtimes stayed unchanged. King's Quest still reports four sound-resource errors;
its resource-integrity flag stays false while its LOGIC coverage remains useful.
Original resources and full reports remain private. See
`docs/evidence/agi-navigation-kit-2026-11-17.json` for the sanitized receipt.

## Prior continuation: game state and useful choices

The user requires persistent game flags, offscreen consequences, independent
opening/lock state, useful option filtering and passive scene description.
Version `0.1.0.dev4` adds `scene_state.py` and extends the bounded scene packet.
The engine/provider remains authoritative; no second puzzle-rule interpreter
or expected-effect application was added.

`SceneStore` records the latest provider snapshot and last reported facts in a
private SQLite store bound to source, edition, optional selected resources,
provider, session and timeline. Increasing observation revisions prevent late
results from replacing newer state; an identical current repeat is idempotent.
Selection through the store checks its latest packet atomically, including
offscreen changes. The returned intent preserves the provider context token
and still requires a live admission/ownership check before any input.

An optional stable entity ID joins the same object or global flag across rooms.
Facts without it remain scene-local, preventing two doors with the same label
from replacing each other's memory. Sparse missing facts remain historical;
they are not reaffirmed or changed to false. Private provider outcome receipts
retain effect status and phase without creating flags. Current public facts,
provider enabled/readiness assertions and suggestion policy remain separate.
An incidental verb may be available on request without appearing in the default
menu; preference cannot override admission. Passive `look` returns the supplied
current scene description without input or a new choice prompt.

The new `state` guide and authored closed/open-window examples ship in the
ordinary package. `record`, `present --store`, `choose --store`, `look` and
internal `memory` are offline commands; no fDisBull installation is required.
Existing packets preserve their previous behavior when optional fields are
absent. Providers must supply current action gates; the supported Z verb list
alone is insufficient. Live flag extraction, observation delivery, provider
token rechecks and voice/input integration remain qualification work.

The source suite passed **616 tests with 7 native skips** in 34.98 seconds.
The focused scene/policy/state/CLI/package suite passed **131 tests** in 0.60
seconds. Independent review found a cross-scene identity collision in the first
store draft; the stable-entity/scene-local key fix and regression cases are
included. A fresh offline installation passed **295 tests, 0 skipped** across
11 suites copied outside the source tree, in 15.57 seconds. All **27 runtime
modules and 40 resources** match source, direct wheel, sdist-rebuilt wheel and
installation; the package has 12 guide topics. The installed authored window
sequence persisted the observed change, refused its old selection, preserved
explicit incidental input and returned passive descriptions. The environment
contains neither fDisBull nor optional MCP, and no source import was used.
An independent reader used only the installed guides/examples/APIs and passed
eight authored window, readiness, offscreen, delivery-order, door-identity and
restore/reopen scenarios. It found no blocking issue in the documented offline
contract. This was an executed offline scenario review, not native async timing
or live gameplay qualification.
The checks and their limits are recorded in
`docs/evidence/stateful-scenes-2026-11-17.json`.

## Prior continuation: predictive preparation during movement

The user clarified that Dot can spawn full cloud agents when usage permits.
Dot narrates, orchestrates retrieval and controls the live game while workers
prepare candidate scenes for selected or likely accessible upcoming locations.
Graphical movement is useful progress and a natural preparation window; instant
text choices may provide little such time. This continuation makes that method
explicit in the installed guides and removes the previous instruction against
creating a cloud environment merely to parallelize.

Keep one foreground blocker and a bounded predictive queue. Each worker has a
near-term consumer, frozen evidence/branch identity, useful-by point, hard work
bound and early partial output. Workers can edit and test their own candidates
in isolated environments, including separate mutable files. Dot retains the
single live owner, checks actual destination/state and adopts compatible
revisions between completed actions. A clone result is evidence for that clone,
not progression in the player's game.

Start appropriate known movement promptly. Do not slow walking, add detours or
pad narration to buy preparation time. On early arrival, use a working ordinary
route immediately; a late worker does not imply a stall. The lead's existing
15-second/two-probe journal is unchanged and is not a distributed worker queue
or a blanket background deadline. Arrival, new screenshots and late results
cannot reset an existing focus. Capture foreground blocked intervals separately
from traversal, user decisions, worker duration and adoption costs.

`dotbox guide --topic lookahead` aliases the packaged continuous-play reference.
This is a documentation/resource continuation of `0.1.0.dev3`, with 37 resources;
it changes no Python runtime module, learning-store API or ownership behavior.
It does not implement a cloud scheduler, predictive recognizer, movement monitor
or concurrent voice frontend. Qualification of the real flow remains pending.
Fresh verification: the existing package suite passed **21 source checks** and
**21 checks copied outside the checkout** against a fresh offline installation.
All **26 runtime modules and 37 resources** match source, wheel and installed
bytes; `lookahead` and `continuous` return identical guide content. An independent
reader of the installed guides found no blocking contradiction across six
movement, route-change, late-worker, usage-loss, takeover and instant-text cases.
That review is a policy walkthrough, not an executed concurrency test.
The installed-package and independent scenario evidence is recorded in
`docs/evidence/predictive-scene-preparation-2026-11-17.json`.

Use existing provider scene/workflow/Z contracts when integrating the result of
the separate fDisBull 0.34.1 study. The DotBox scene packet remains a bounded
presentation/evidence boundary; selected reusable modules must eventually ship
inside DotBox rather than require a separate end-user fDisBull installation.

## Prior continuation: conversational scenes

The user clarified that autonomous play is supported, while the primary
experience is Dot acting as the game's conversational interface. Z-scenes
provide grounded descriptions and choices; Dot phrases them according to the
player's preferences. An initial manual/guide pass supplies the broad goal and
expected objects/exits as a reconstruction checklist. The Magic Door was named
as an interaction reference, not an integration target.

Version `0.1.0.dev3` adds `scenes.py` and `dotbox scene` with four offline
operations: present, checklist, validate and choose. A closed, bounded authored
packet keeps current observation claims separate from guide expectations.
Brief/normal/detailed player views retain the same permitted facts and choices;
their deterministic narration and choice prompt provide a fallback for Dot's
own phrasing. The internal checklist preserves disagreements, unknown editions,
copied-source groups and unchecked conditions without voting claims into truth.

Choice selection is bound to the exact document digest and observation ID. It
returns an intent with no input execution, no ownership grant and no inferred
outcome. Choices reference existing immutable controls or ordinary supported
input routes; there is no second raw input language. All semantic observations,
audience classifications and route applicability remain caller assertions.

The guide/skill now distinguishes player-led choice from autonomous delegation.
"Act now" applies to an already selected intent or delegated goal. A bounded
guide pass fits the existing preparation timeline, and incomplete reconstruction
does not block a working route. Description length, decision maker and hint
preference are separate. Guide-informed narration does not imply blind play.

The wheel contains 37 operational resources, including two new topic guides
and authored mailbox/station/barrel examples. Doctor projects and selects the
mailbox fixture without executing an action. The examples contain no commercial
game data; their source identities and input-route references are illustrative.

Current source verification: **551 passed, 7 native skips** in 33.84 seconds.
The new scene suite has **45 passing cases** and the package suite **21**,
including exported-example CLI round trips. Independent review found no
confirmed blocking defect. A fresh-reader eight-scenario test exercised offline
projection/selection and produced the intended game-facing decisions; wording
about zero/ambiguous targets and using the full scene view was clarified.

Direct and sdist-rebuilt wheels have identical package bytes. All **26 runtime
modules and 37 operational resources** match source, both wheels and the fresh
installation. Installing from local dependency wheels with `--no-index` passed;
there is no source import, fDisBull or optional MCP in that environment. Eight
copied suites outside the source tree passed **230 tests, 0 skipped**, in
15.87 seconds. Installed mailbox/station/barrel projection and selection checks
also passed, including detail invariance, partial coverage, hidden-content
exclusion, stale-observation refusal and zero execution. Python/dependency
versions remain those recorded for the preceding learning-kit slice.

See [the scene receipt](evidence/conversational-scenes-2026-11-17.json) for the
completed installation results, exact artifacts and qualification boundaries.
No automatic guide extractor, condition evaluator, natural-language parser,
scene recognizer, goal planner, live input adapter or voice frontend is supplied
by this offline module.

## Prior continuation: incremental learning kit

The user redirected the available offline development time toward ordinary
players: DotBox should supply the reversing machinery, and Dot should learn
only what is needed next without making working play wait for harness authoring.

Version `0.1.0.dev2` adds three modules and five CLI entry points:

- `inspection.py` / `dotbox inspect`: explicit COM/MZ/resource identity, bounded
  strings, masked byte patterns, real 16/32-bit iced-x86 decoding and frozen-range
  diffs. Limits and exact selected-byte identities travel with each result.
- `learning.py` / `dotbox learn`: one private SQLite focus, a non-renewing default
  15-second/two-probe admission allowance, explicit retirement and immutable
  caller-reported evidence. Same-context updates do not reset time or counts.
- `kit.py` / `dotbox guide`, `doctor`, `kit-export`: installed progressive
  instructions, resource-integrity/decoder/clock checks and a private new-directory
  export of the native preparation resources. No command launches a native game.

The core dependency now includes `iced-x86==1.22.0`. Setuptools stages an explicit
32-file resource manifest into the wheel, generating a hash/size catalog. The
play skill and its references are included; no installed personal-skill plugin
was changed. Native patches and source notices are packaged, while a prepared
native executable, platform libraries and the final player installer remain
separate requirements.

The method now says: use an applicable known action immediately, observe its
effect, then save useful metadata without replay. No named scene, wrapper or
complete starting buffer gates an already usable control. A current missing
interaction gets one bounded question; a working fallback takes priority over
optional research. The 180-second initial preparation ceiling is not a minimum
wait or a per-room reset. One agent is sufficient; workers are optional.

Default desktop input and diagnostic native `act` are now distinguished in all
current play/control guides. The old dependent-prototype startup pointer was
replaced with the standalone route. Budget enforcement covers admissions only;
it cannot preempt reasoning/tools, recognize scenes or grant input ownership.

### Learning-kit verification

| Check | Result |
| --- | --- |
| Inspection, learning and resource/CLI cases | 36 + 27 + 17 = 80 passed |
| Full source suite | 502 passed, 7 native skips, 32.91 seconds |
| Direct wheel and wheel rebuilt from sdist | Both built; package bytes match |
| Source / both wheels / isolated installation | All 25 modules and 32 resources match |
| Fresh installation from local wheelhouse only | Passed with no index and no fDisBull or optional MCP |
| Seven copied suites outside source checkout | 181 passed, 0 skipped, 15.74 seconds |
| Installed authored workflow | Identity, admitted decode, candidate receipt, expiry/fallback and retirement passed |
| Fresh-reader instruction forward-test | All seven decision scenarios resolved; wording ambiguities corrected |
| Independent implementation review | Concrete findings fixed; no remaining material issue found |

The tested interpreter is Python 3.12.14 on Linux; Pillow is 12.3.0, iced-x86
1.22.0 and pytest 9.2.0. Source checks also had optional MCP 2.3.0. The Linux clock
identity was exercised; the macOS branch remains unexecuted. The runtime still
lacks the two native inputs listed in the earlier verification, hence the same
seven skips. The small authored CLI commands took about 0.06–0.14 seconds each
in one host run; this excludes model and dispatch time and is not player latency.

See [the learning-kit receipt](evidence/incremental-learning-kit-2026-11-17.json)
for artifact identities, scope, commands, reviews and qualification limits.

## Prior continuation: asynchronous turn fence

An additive `Client.run_turn_step_async(lease, action)` fences a fresh Python
coroutine on an executor that already has supported action and coordinator
access. It snapshots one receipt, checks it without blocking the event loop,
awaits the callback, then checks the unchanged receipt. It preserves completed
results on postcheck interruption and propagates cancellation with inspection
guidance. It rejects prestarted and nested deferred work. There is no retry,
renewal, permission change or change to the synchronous helper.

The new regression tests use a real authenticated loopback coordinator and
harmless data callbacks. They do not operate a desktop or launch a game.

## Prior turn-fence verification

Fresh baseline on Python 3.12.14: **400 passed, 7 skipped** in 28.80 seconds.
The skips require `DOTBOX_DOSBOX_EXECUTABLE` or `DOTBOX_DOSBOX_BASE_SOURCE`,
neither supplied to this task. The checked dependency set is Pillow 12.3.0,
pytest 9.2.0 and optional MCP 2.3.0.

Final verification:

| Check | Result |
| --- | --- |
| New asynchronous regressions | 22 passed |
| Combined client/ownership suite | 101 passed, 0 skipped |
| Full source suite | 422 passed, 7 native skips, 32.60 seconds |
| Ordinary isolated wheel build | Passed |
| Client/ownership suite from the installed wheel outside the source checkout | 101 passed, 0 skipped, 15.26 seconds |
| Source, wheel and installed runtime identities | All 22 modules match exactly |
| Installed base package without fDisBull or optional MCP | Verified |
| Independent code review and cancellation experiment | No blocking finding; experiment exit 0 |

The first regression failed on the missing async API before implementation.
The final checks confirm local Python cooperation only. See the
[sanitized verification receipt](evidence/async-turn-fence-2026-11-17.json) for
commands, package identities, setup corrections and qualification limits.

Reproduce source checks in a project virtual environment with:

```sh
python -m pip install '.[test,connector]'
python -m pytest -q -ra
```

## Next development and live gates

First connect one small real scene to the qualified observation/input path:
present useful choices, resolve an unambiguous player intent, perform a bounded
ordinary action and describe only its observed result. Establish the exact game
edition and a small cited goal/guide brief. Test the same scene under bounded
autonomous delegation. A complete world graph or scene checklist is not required.
Speech can consume the same view and intent contract after the text loop works;
actual voice availability and pacing remain integration measurements.

Then qualify one selected movement leg with a real cloud worker preparing the
destination: verify timely partial delivery, fresh arrival checks and adoption
between actions. Exercise a different exit, late result with a working fallback,
usage loss, takeover and an instantaneous text transition. Measure first-input
latency, confirmed effect, natural travel and actual foreground blocks on the
same lead timeline; do not infer latency improvements from this guide change.

When that route needs native evidence, expose a short owned capture transaction
that validates an entire bounded plan, captures only the required memory/register
packet and resumes before model reasoning. The pinned native backend requires a
stopped guest for those reads; raw RPC passthrough is not an acceptable shortcut.
Test consistency, aggregate limits, partial failure and takeover behavior before
any real-game use. Then add one edition-scoped engine reader or applicability
predicate only when it resolves a near-term play question. Existing descriptive
control metadata does not enforce resource identity or live scene recognition.

The live gates remain separate:

1. Establish a supported path on the original Dot executor that can check a
   turn receipt and complete its existing desktop action without switching
   environments. The Python helper alone does not provide that path, and the
   status-only MCP connector does not expose it.
2. Keep the three-second receiver freshness contract. Use the same unchanged
   receipt before and after a harmless authorized input and observation of
   its visible effect. Record takeover, return and interruption behavior.
3. Qualify the standalone native package on that actual Dot runtime, including
   frame/input operation, persisted controls and process cleanup.
4. Measure the new method on cold start, warm reuse and a real room/menu
   transition. Include agent reasoning and dispatch in interruption timings;
   keep animations and user decisions distinct. Full game recovery and audio
   remain later work. Keep private game files and raw runtime evidence outside Git.

These are sampled cooperation checks, not an atomic capture lock. A transition
entirely between samples can be missed; the outer harness still owns capture
and input already in flight. The local Mac build and authored native fixtures
recorded above do not qualify these original-Dot desktop gates or commercial-game
play. Full memory rewind and release publication remain separate work.
