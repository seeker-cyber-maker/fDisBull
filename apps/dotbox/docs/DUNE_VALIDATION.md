# Dune: next non-AGI transfer test

Decision: 18 November 2026. Use the original Cryo Dune adventure/strategy game
as the next non-AGI target. The user's menu-driven description and the existing
project evidence identify this game, rather than Dune II. Confirm the exact
platform, language, release and resource hashes before executing a new trial.

Status: validation plan plus a completed, isolated
[RIP-edition probe/rewind batch](DUNE_BATCH_PROBE.md) and a
[continued-play/workload experiment](DUNE_PROGRESS.md). The continuation reached
a Fremen sietch, recruited a troop and obtained its report of spice mining.
It adds bounded UI readers and continuation mechanics; complete strategic-loop
and original-Dot acceptance remain open. The initial documentation
pass consulted the manual and existing public trial; the later 18 November batch
actually executed the newly supplied DOS edition. Its menu/navigation dispatch
and memory-repeatability findings do not complete strategic-play acceptance or
original-Dot integration.

Use [DinoPark's recovered mechanics and existing provider](DINOPARK_REUSE.md)
as a reference for the shared state, menu and delayed-action machinery. Retain
the already established distinctions between committed state, pending orders,
interface selection and presentation readiness. Develop those general
contracts before freezing the next Dune baseline, and record their origin.
This does not require another DinoPark campaign or transfer its addresses,
economic rules or timing assumptions into Dune.

## Preserve the earlier result and record exposure

The [15 November Dune CD receipt](evidence/dune-local-terra-2026-11-15.json)
records an assisted local trial using user-supplied CD media in a dependent
prototype. It reached four opening views and retained procedural controls.
Dialogue highlighting/animation was observed, but spoken meaning and story
effects remained unknown. Later desert and strategy play was not investigated.
That result is useful history, not standalone-package or original-Dot takeover
qualification, and must not be relabeled as a new baseline.

Dune is therefore not an untouched or blind holdout. The prior holdout rule
means: freeze the generic mechanisms before target-specific adaptation, record
earlier exposure, and distinguish baseline results from adapted results. The
user's next-target direction is not blocked by that rule. This documentation
pass adds exposure to the original manual's interface descriptions; it does
not claim independent discovery of those concepts.

Record the exact generic package/source revision, native build, controls,
available analyses and prior knowledge for the next bounded baseline. Then
record which failures need a Dune-specific binding and which expose a reusable
gap. After adaptation, compare against the frozen baseline instead of silently
changing the baseline's tools or retesting it as if unassisted.

## A scene can be a menu or strategic context

The original manual describes a point-and-click command panel, conversation,
a world map and orders to troops, including activities with delayed effects
[1]. Treat those descriptions as expectations for validation, not observed
behavior of the currently selected edition.

The model should support distinct physical location, interface mode and selected
subject. Opening a troop panel need not move the player. Returning to the same
map view need not restore the same selection, available commands or state.

The proposed representation should be able to describe:

| Context | Candidate model contents | What must be checked live |
| --- | --- | --- |
| Conversation | Participants, offered choices and potential story dependencies | Current speaker, current options, accepted choice and observed result |
| Local navigation or travel | Places, destinations and transition conditions | Selected destination, departure, pending travel and arrival |
| Map/strategic panel | Stable entity identities, selected subject and available operations | Which entity is selected and which data belongs to it |
| Order | Acting entity, operation, parameters, prerequisites and expected effect | Admission, acceptance, ongoing job and later outcome |
| Time-dependent state | Clock observations and candidate update rules | Which actions or interface states advance game time |

Model an order as an operation on an entity with parameters, not as the third
button in a panel. Menu labels, positions and ordinals can change with subject
and mode. A qualified input route binds the current context and checks it before
execution. Retain learned menu mechanics while refreshing the selected entity
and applicable choices.

This is also the useful transfer seam for a later Civilization adapter: cities,
units and their decisions can use entity/action/menu contracts. Shared menu
mechanics do not establish shared rules or timing. Keep immediate, queued,
continuously updated and turn-gated effects explicit until the target behavior
is established.

## First acceptance slices

These are proposed tests, not assertions that the corresponding controls or
state readers are already available:

1. **Menu identity and one action.** Recognize one current interface context
   and selected subject; perform one selected choice and verify the resulting
   context without relying solely on a click receipt.
2. **Conversation semantics.** Enter and exit a conversation and establish the
   meaning of one offered/selected response from permitted evidence. Record
   unavailable speech/subtitle evidence as a gap; animation alone is not a
   confirmed story effect.
3. **Travel.** Select one destination, observe departure and arrival, and refresh
   the scene after the transition. Do not count destination selection as arrival.
4. **Strategic entity identity.** Inspect one entity, change selection and prove
   which displayed or observed fields belong to each entity. Investigate whether
   an ambiguous value is global, pointer-selected or temporary storage.
5. **One delayed order.** Issue one currently supported strategic order under
   the selected goal, then distinguish acceptance, pending work and its observed
   effect. Check a related view for a confirmed consequence without repeating
   the order merely because the display has not updated.
6. **Clock semantics.** Compare game-clock/state observations across ordinary
   waiting, menus, conversation, travel and the selected order. Measure the
   applicable cases; neither host elapsed time nor an RTS/turn-based label
   establishes when this edition advances its simulation.
7. **Warm reuse.** Resume with the retained harness/model, rebind to the actual
   current state, and demonstrate reuse without repeated discovery.

Start with the opening interaction and one strategic order reached through
ordinary play or an explicitly selected compatible starting save. Record the
starting state and assistance. A full campaign, combat solver or complete Dune
decompilation is not a prerequisite for that slice.

## Reverse engineering at the actual ambiguity

Use the [ongoing investigation workflow](REVERSE_ENGINEERING.md) when menu
observation leaves a meaningful question unanswered. For example, compare the
same action on two selected entities, trace the record selector, or follow a
candidate field's writers and consumers. Preserve storage lifetime and code
context instead of assuming one address always has one semantic meaning.

Measure cold preparation, intent-to-first-input, effect confirmation, foreground
blocked time, worker duration and warm reuse separately. Natural travel or an
already pending order can provide useful preparation time, but do not extend
it to conceal unfinished research. Qualified captures must resume owned pauses
before analysis. Memory rewind remains a separate live qualification and
preserves current disk files.

## Reference

1. [Original Dune instructions, archived PDF](https://dosdays.co.uk/media/games/dune/Dune_Manual_DOS_EN.pdf),
   especially the control-panel, map and troop-order sections. The archive is
   hosting the original manual; it is not current runtime evidence or proof
   that every control applies unchanged to the earlier CD edition.
