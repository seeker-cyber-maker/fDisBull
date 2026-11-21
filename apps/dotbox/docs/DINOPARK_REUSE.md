# Reuse the recovered DinoPark model and harness

Decision: 18 November 2026. DinoPark Tycoon is an existing source of recovered
game knowledge and original-game controls. Consult that work before designing
new native state bindings, transaction handling or menu adapters. Dune remains
the next selected non-AGI target; DinoPark supplies a known reference for the
shared machinery, without requiring another complete playthrough first.

Status: research and source reuse guidance. This change does not port the
DinoPark provider, import the private research packet, implement WorldStore or
qualify new gameplay. The reviewed material includes the saved E55 research
reports and the later fDisBull 0.34.1 source. These are separate evidence lines.

## What has already been recovered

| Material inspected | Reusable contents | Scope to preserve |
| --- | --- | --- |
| E55 behavioral report and game-story map, 28 October 2026 | 22 mechanics cards linked to 14 earlier sources; simulation, transactions, clocks, persistence, interface and presentation contracts | A consolidated semantic handoff; its evidence families have different coverage. The map adds no new original executions. |
| E55 research packet described by those reports | Six JSON files for game/actor rules, source locations, evidence and export integrity; 122 ACT rules across nine selected programs | Research input for the existing Universal Interaction Language owner, not canonical UIL or a whole-game evaluator. The packet itself was not executed in this pass. |
| `src/fdisbull/dinopark_scenes.py` in the pinned release source | Native cash/debt, calendar, food/staff and ten pen records; menu recognition; bounded original-input handlers; save-field bindings | Exact executable/resource and scene profiles; several handlers deliberately require a specific opening state. |
| `src/fdisbull/dinopark_z.py` and purchase/land/fence helpers | Named actions, retained attempts, cumulative phase budgets, explicit continuations and read-only reconciliation | Original game code owns effects. Supported verbs alone do not establish that an action is enabled in the current state. |
| Later native handoffs retained in the release source | Confirmed purchases, operating-park observations, source-bound saves, navigation recovery and remaining investigation questions | Historical results belong to their recorded source/backend/session. They are not new DotBox acceptance runs. |

The inspected release is fDisBull **0.34.1**, manifest source commit
`ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd`, wheel SHA-256
`2cabcc5956e40a3c205d90025b226e6c271b0b1c149050e6b5571b8c420fd0f6`.
The six DinoPark Python files and nine data/provenance files match the wheel
RECORD and that commit's source blobs. The adapter and E55 reports identify
`DINOPARK.EXE` SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`;
the adapter also requires its pinned `VARS.DAT` and selected resource inventory.
An equal filename or game title does not establish compatibility. [S1–S4]

## Lessons the shared model must retain

**State has several owners and lifetimes.** Keep committed park state, a pending
transaction, continuing session state, interface/selection state, presentation
state and external artifacts distinct. The E55 account identifies working cash
separately from committed cash. A pending roster can survive leaving a menu;
bank changes can commit before a working copy is synchronized. Save coverage
is useful evidence about state, but ordinary game loading does not restore every
session field. A future model importer must preserve these distinctions. [S3]

**An order has observable intermediate states.** The recovered ordinary purchase
contract separates reservation and expense posting, arrival, placement and
commit/cancel. Cancellation can reverse an expense in the current month rather
than restoring an entire earlier state. Store the original attempt identity,
observed phase, relevant entity and remaining permitted actions. A delayed
screen update must not cause a second purchase. [S2, S3]

**Effect and readiness are independent.** Input acceptance, semantic effect,
control readiness, rendered observation and persistence each need their own
evidence. Their order is action-specific. The later retained Coelophysis case
has confirmed cash, pen and expense changes while its final content-sensitive
display witness remains unqualified. Keep the confirmed effect and investigate
that witness; do not replay the purchase or weaken the guard merely to finish
the workflow. [S2, S4]

**Read-only reconciliation and continuation are different operations.** A
reconciliation checks the existing attempt without input, guest advancement or
restore. An explicit guarded continuation may advance the guest or send only
later inputs for that same attempt. Retain cumulative guest allowances and the
incoming host deadline within a composed request. An explicit continuation has
its own bounded request deadline, while the attempt's guest phase allowances
remain cumulative. A new call does not renew those allowances or make an
unknown input safe to replay. [S2]

**Clock and numeric details belong to the rule.** The prior research distinguishes
calendar holds, actor updates and input/service phases; a held calendar does
not imply every subsystem stopped. Retain field width, signedness, ordered
rounding, cached values and shared random-stream order where established.
Transfer those representation capabilities to Dune, while measuring Dune's own
rules and timing. [S3]

## Pixel witnesses and action-event boundaries

The inspected provider's `pixel_predicate`/`matches` functions compose positive
samples, tolerance, minimum matches and explicit rejection predicates.
`observe_frame` can read pixels directly without retaining another screenshot;
`take_frame` retains a full frame for durable evidence. Static profiles exclude
known moving or changing regions. Screen recognition, selected species/price,
modal exclusion and input readiness remain separate predicates. [S1]

`TextScene.confirm_food_order` arms two byte-verified original execution
boundaries, sends one queued confirmation click, and checks native before/after
food, cash and expense fields. It distinguishes a completed bulk commit from
a partial write and from the later street request. `confirm_vegasaurus_order`
uses four known post-update boundaries and retains animation frames. These are
concrete targeted phase checks, not evidence that a generic automated shotgun
breakpoint discovery sweep was recovered from the DinoPark provider. [S1]

The package also contains generic `event_search.py`/`execution_trace.py` and an
execution-event-search reference: repeated action A, idle/contrast B, candidate
sites and site/register/value refinement. Preserve shared-dispatch arguments,
coverage bounds and the actual executable/backend support when adapting it.
The reference's initial live `debug-trace-until` owned, stopped real-mode path
does not qualify XCOM LE tracing or DotBox's normal live session API. [S5]

Saved-state bindings illustrate the loader distinction: the inspected native
format covers cash/loan, calendar/counters, food/staff, species and pen records,
while the loader rebuilds pen geometry prefixes. Serialized state is useful
structural evidence without being the whole live model. `advance_time` observes
bounded guest advancement and actual calendar/counters/notices; inherited wait
constants are not natural-play timing measurements. [S1]

See [bootstrap and event loops](BOOTSTRAP_AND_EVENT_LOOPS.md) for the generalized
capture, process and isolated-experiment contracts and [XCOM reuse](XCOM_REUSE.md)
for the related original-menu research. No new runtime test is reported here.

## Smallest useful DotBox integration

1. **Recover and bind existing evidence.** Index the relevant source, report,
   rule and receipt identities against the selected edition. Import a bounded
   set of established entities, fields and transaction relationships into the
   proposed private world store. Keep unresolved claims and evidence maturity;
   do not turn a report summary into a current observation.
2. **Separate semantic records from runtime bindings.** A park, pen, selected
   species or pending order is a model entity. An address, sampled pixel or
   save offset is an edition/context-bound observation recipe. Reuse recovered
   meanings and predicates while binding them to DotBox's actual session,
   mapping and observation revision.
3. **Port one existing route through the owned runtime boundary.** Start with
   a state read and one menu action, then the already studied first purchase.
   Use ordinary controls and a coherent owned capture. Keep exact opening-state
   restrictions until a broader state domain has its own evidence. Package the
   necessary dependencies in DotBox; no fDisBull install is required of players.
4. **Project current facts and applicable actions.** Combine model knowledge
   with fresh provider observations and admission. Do not map every verb from
   the old Z object list directly to an enabled choice. Keep presentation gaps,
   pending work and partial inventory explicit. The existing strict SceneStore
   remains an observation store, separate from the proposed world store.
5. **Exercise recovery of one attempt.** Cover pending work, a confirmed effect
   followed by failed display readback, read-only reconciliation, an explicit
   later-phase continuation and stale observations after human play or rewind.
   Verify that none of these paths repeats the original purchase.
6. **Freeze the reusable baseline for Dune.** Record which general contracts came
   from DinoPark and compare Dune-specific adaptation against that baseline.
   Further DinoPark campaign recovery is not a prerequisite. Measure cold
   preparation, first useful input, foreground blocked time and warm reuse;
   inherited wait constants are not DotBox latency targets.

This sequence informs the [world model](WORLD_MODEL.md), the
[investigation workflow](REVERSE_ENGINEERING.md) and the
[Dune transfer plan](DUNE_VALIDATION.md). Existing research should reduce new
analysis to an actual missing binding, discrepancy or unsupported state domain.

## Porting boundaries

The old scene module depends on fDisBull's broad `Project` API, and the Z launcher
uses its original-backed UDC pipeline. Copying the entire provider would import
that architecture. Extract only the needed observation, predicate, action and
continuation contracts behind DotBox-owned interfaces. The source's bounded
continuation and deadline helpers are useful candidates, subject to source and
attribution review. No external code or game-derived data is copied by this
documentation change.

The existing UDC definition has zero semantic blocks and reconstructs the
original executable bytes. It is useful packaging evidence, not proof that
the game's recovered rules already execute as an independent replacement. The
E55 report explicitly leaves page/service/rendering and other closure work;
the later 3 November handoff still lists 97 selected caller/producer questions
and 13 unresolved asset candidates. Preserve those recorded questions while
reusing the substantial recovered mechanics. No whole-game completion
percentage or complete DotBox harness is inferred. [S2–S4]

Do not copy the older checkpoint policy that invalidates an in-memory restore
whenever mounted files changed. DotBox's requested rewind restores machine
memory/state while keeping current disk files. Game-native saves, the player's
rewind and a failed transaction's read-only reconciliation are separate
operations. See [recovery and saves](RECOVERY_AND_SAVES.md).

## Sources and continuation locators

- **S1 — inspected release:** [fDisBull 0.34.1 portal notes](https://release.brewsterjennings.ca/releases/0.34.1/README.txt),
  its retained manifest/wheel, and [pinned source](https://github.com/seeker-cyber-maker/fDisBull/tree/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd).
  Relevant modules are `src/fdisbull/dinopark_{scenes,z,purchase,land,fence,terminal}.py`
  and `src/fdisbull/data/dinopark-e55-*`. The version identifies the inspected
  package, not a claim about the latest release.
- **S2 — provider contract:** [DinoPark Z at the inspected commit](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/docs/DINOPARK_Z.md).
- **S3 — saved private research:** `DinoPark-E55-Handoff.md`,
  `DinoPark-E55-Behavioral-Story-Report.md`, `DinoPark-E55-Game-Story-Map.md`
  and `DinoPark-E55-Progress.json`, dated 28 October 2026. Retrieve the original
  `DinoPark-E55-UIL-Research-Handoff.zip` and its delivery check when exact rule
  or receipt bytes are needed. Reports were read here; the archive was not
  executed or imported. The handoff points back to Mechanics 0.3 and E42–E54.
- **S4 — later state of work:** [3 November interruption handoff](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/docs/agent-handoffs/2026-11-03-dinopark-interruption.md).
  Its native sessions had exited. Use its source-bound evidence and remaining
  questions; historical handles are not live connections.

- **S5 — bounded event discovery:** [execution-event-search reference](https://github.com/seeker-cyber-maker/fDisBull/blob/ad1e9a3177cc8fda60b9c0c64e8a40f6fabb1edd/src/fdisbull/skills/fdisbull-investigate/references/execution-event-search.md)
  with `src/fdisbull/event_search.py`, `execution_trace.py`,
  `serializer_discovery.py` and `serializer_candidates.py` at the same commit.

Keep private reports, games, captures, saves and analysis databases outside Git.
This guide is a small authored reuse map and can ship without those artifacts.
