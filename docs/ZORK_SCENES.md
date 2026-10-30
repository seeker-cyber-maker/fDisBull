# Zork scenes: explicit progression rules and resolved handler links

The scene export separates Zork's compiled representation from its progression
rules. It recovers **110 named scenes and all 352 encoded directional exits**,
including live conditions, door checks, refusal resources and resolved callback
identities. The scene evaluator chooses named destinations and effects directly.
It does not unpack a property record, compute a packed code address or use the
Z-machine operand stack to decide which scene a rule means.

This is a further semantic layer over the preserved playable conversion. It
does not claim that every room callback, puzzle, parser rule or background
event has been understood. Unrecovered behavior remains explicitly identified
as low-level IR. Resolving a routine's identity and recovering its body are
separate results.

## Export and run

Use the owned, qualified story and the existing intent package. Write generated
game resources outside the checkout:

```sh
fdisbull zork-scenes /private/ZORK1.DAT \
  --intents /private/zork1.intents.json.gz \
  --output /private/zork1.scenes.json.gz \
  --uil /private/zork1.scenes-uil.json \
  --udl /private/zork1.scenes-udl.json \
  --dispatch /private/zork1.dispatch-uil.json

fdisbull-player --scenes /private/zork1.scenes.json.gz --seed 12 \
  --checkpoint /private/zork1.scene-progress.json
```

The optional inspection files are the exact documents embedded in the runnable
package. Supplying `--intents` retains that entire package unchanged, including its
original IR and earlier mailbox/turn intent definitions. Omitting it builds the
existing intent conversion before adding the scene layer.

Resume with:

```sh
fdisbull-player --scenes /private/zork1.scenes.json.gz --seed 12 \
  --resume /private/zork1.scene-progress.json \
  --checkpoint /private/zork1.scene-progress.json
```

The player also accepts `--commands /private/commands.json` for a JSON array of
command strings, and `--transcript /private/results.json` for output and recovery
receipts. Its standalone module entry point is:

```sh
python -m fdisbull_player.scene_runtime /private/zork1.scenes.json.gz --seed 12
```

Generated files contain game-derived prose, source witnesses and retained
executable data. The generic distributions contain the producer and consumer
code, authored tests and sanitized naming metadata. They do not contain the
owned story or a generated game package.

## Documents and responsibilities

| Document | Format | Responsibility |
|---|---|---|
| Preserved base package | `fdisbull-zork-intent-package-1` | Retain the original executable IR and previously recovered mailbox and counter behavior. |
| Scene UIL | `fdisbull-scene-intent-uil-1` | Describe named scenes, directional rules, live predicates, ordered refusal effects and explicit residual requests. |
| Dispatch UIL | `fdisbull-game-dispatch-uil-1` | Name actions, rule precedence and selectable residual handlers independently of packed addresses. |
| Scene UDL | `fdisbull-zork-scene-udl-1` | Connect semantic fields and effects to original objects, properties, source operations, routine entries and live guards. Its `dispatch` member carries the dispatch source definitions. |
| Runnable scene package | `fdisbull-zork-scene-package-1` | Bind the preserved package, both UIL documents and UDL together. |

The package has five top-level fields: `format`, `base_intents`, `uil`,
`dispatch_uil` and `udl`. Canonical digests bind the preserved package and
both semantic documents. The full package identity also binds its UDL.

`src/fdisbull/zork_scenes.py` produces the scene model and source
correspondence. `src/fdisbull/zork_scene_dispatch.py` resolves finite rule
tables and callback references. `player/fdisbull_player/scene_intents.py` is
the independent, address-free scene evaluator. The player-side
`scene_bindings.py` validates source correspondence without importing the
producer or the Z-machine decoder. `scene_runtime.py` realizes admitted
semantic effects and resumes the declared residual behavior.

The older `zork-uil` command and `fdisbull-uil-word16-1` format remain
compatible names for the low-level executable representation. They do not
imply that all operations in that representation are game-intent UIL. See
[ZORK_UIL.md](ZORK_UIL.md) and [ZORK_INTENTS.md](ZORK_INTENTS.md).

## Source qualification and recovered scene identity

The producer qualifies only Zork I release 88, serial `840726`, with full
story SHA-256:

```text
0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd
```

It rejects a different edition. The whole-file identity includes padding;
source witnesses and executable memory use the declared story extent.

The original object model contains 250 objects. The 110 room objects are
children of the room collection. Each has its own property list, and its
directional properties use five compact layouts. Actual V-WALK operations
establish how those layouts are interpreted; the producer does not infer
meaning solely from the appearance of a byte sequence.

A sanitized metadata profile supplies source-language room symbols and graph
relationships from
[historicalsource/zork1 at revision 97b7b3d](https://github.com/historicalsource/zork1/tree/97b7b3d68c075dd9af7da499c3e9690ada3471fd).
Every recovery re-associates the symbols through the actual binary graph:

1. Match exact sets of directions and exit kinds.
2. Constrain each possible association by its named destination relationships.
3. Enforce one-to-one scene identity.
4. Require every scene to have one remaining association.
5. Check the qualified edition's expected object identities independently.

The association algorithm does not use the metadata profile's numeric object
hints or title strings to choose candidates. This resolves even the rooms
whose displayed names are identical. Ambiguous or contradictory graphs are
refused.

The historical source corroborates names and conventions. It is not
transplanted as an equivalent executable. Its revision differs from R88 in
some spelling and code details. The exporter obtains actual narrative, values
and operation witnesses from the qualified binary. No online fetch is required
when a user runs the producer.

## Scene UIL

A scene document contains:

| Field | Meaning |
|---|---|
| `entry_scene` | The initial named scene. |
| `scenes` | Scene identities, displayed names, exits, description resources and explicit event handlers. |
| `resources` | Extracted narrative fragments, including separate newline resources. |
| `facts` | Named Boolean selectors with initial values; current truth is supplied by live state. |
| `doors` | Named door entities, their displayed names and initial open states. |
| `handlers` | Explicit residual room-event or exit handlers. |
| `missing_exit` | The residual behavior to request when a direction has no encoded exit. |

Directions are named `north`, `east`, `west`, `south`,
`northeast`, `northwest`, `southeast`, `southwest`,
`up`, `down`, `in`, `out` and `land`.

An abbreviated example illustrates the recovered structure. It is a fragment,
not a complete standalone document:

```json
{
  "entry_scene": "west_of_house",
  "scenes": {
    "west_of_house": {
      "exits": {
        "north": {
          "id": "west_of_house.exit.north",
          "kind": "direct",
          "destination": "north_of_house"
        },
        "southwest": {
          "id": "west_of_house.exit.southwest",
          "kind": "conditional",
          "destination": "stone_barrow",
          "fact": "won_flag"
        }
      }
    },
    "east_of_house": {
      "exits": {
        "west": {
          "id": "east_of_house.exit.west",
          "kind": "door",
          "destination": "kitchen",
          "door": "kitchen_window"
        }
      }
    }
  }
}
```

The evaluator reads a named scene and a named predicate. Object numbers,
property lengths, global-variable numbers, memory addresses, packed routine
values and stack operations belong to the UDL correspondence.

### All encoded exit forms

| UIL kind | Count | Decision and effects |
|---|---:|---|
| `direct` | 277 | Request travel to the named destination. |
| `blocked` | 37 | Emit the bound refusal resource and a newline. |
| `conditional` | 25 | Test the live named fact; request travel if true, otherwise emit a custom or default refusal. |
| `door` | 6 | Test the live door state; request travel if open, otherwise emit a custom or default closed-door refusal. |
| `routine` | 7 | Invoke an explicitly named residual exit handler whose identity and entry are already resolved. |

The default closed-door outcome has an additional effect: after prefix, door
name, suffix and newline, it remembers the mentioned door and current scene
for discourse resolution. A custom door refusal does not automatically acquire
that extra effect. This ordering comes from the original operations.

Missing directions remain residual. Their original behavior can involve
darkness, a random draw and death. An absent exit is not interchangeable with
a fixed refusal message.

The 12 named facts include `won_flag`, `troll_flag`, `rainbow_flag`,
`magic_flag`, `low_tide`, `lld_flag`, `empty_handed`,
`dome_flag`, `deflate`, `cyclops_flag`, `false_flag`
and `coffin_cure`. These identify live source-backed Boolean selectors.
Their complete setter behavior remains residual. A suggestive symbol name
does not authorize replacing a selector with a guessed score threshold,
inventory calculation or permanently false constant.

The three door entities are `kitchen_window`, `trap_door` and
`grate`. Their six exit references use current open state, including
changes made by commands earlier in the same session.

### Descriptions and event handlers

The producer extracts static long-description resources from 87 scenes and
resolves room-event callbacks for 40 scenes. Seventeen scenes have both.
A static resource is the original fallback when the room handler declines;
it is not permission to discard that handler.

Scene `initial_traits` records the initial land, natural-light and ruined
attributes. These are descriptive metadata. The evaluator does not substitute
them for live movement, light or hazard conditions.

Routine exit bodies and room-event bodies remain explicitly residual even
when their original source names are known. A named `forest_room` callback
is a resolved behavior identity, not a claim that forest events have been
converted into semantic primitives.

## Independent effect evaluation

The pure evaluator imports neither the producer nor the Word16 runtime.

```python
from fdisbull_player.scene_intents import initial_state, evaluate_exit

state = initial_state(scene_document)
plan = evaluate_exit(scene_document, state, "north")
```

The input state contains `current_scene`, `facts` and `doors`.
Missing facts and door states are unknown, represented by missing entries or
`None`; they are not false.

Exit evaluation returns `travel`, `refused`, `residual` or
`unknown`, an ordered effect plan, and an unchanged next state. Selecting
an exit requests travel; it does not itself move the actor. In particular,
unknown input produces no guessed destination and no narration or state effect.

`evaluate_relocation` supplies the separate `scene.move_actor` primitive.
It requires a known actor, known origin, consistent actor location and known
destination. Its ordered effects move the actor and then establish the current
scene. It does not infer arrival scoring, description policy or a turn count.

## Executing the higher-level representation

The compatibility consumer executes the semantic plan and connects it to
explicit residual phases:

| Phase | Implemented behavior |
|---|---|
| Input and parsing | Retained IR handles language recognition, scope, pronouns and action formation. |
| Rule selection | Resolved named links replace qualified source table/property loads and computed routine calls. |
| Directional decision | `scene.select_exit` executes the UIL's live condition and refusal rules. |
| Movement admission | Original GOTO behavior retains vehicle, destination and other pre-move checks. |
| On-foot relocation | At the qualified effect boundary, `scene.move_actor` replaces the actor insertion and current-scene assignment. |
| Arrival | Remaining light checks, hazards, callbacks, scoring and presentation execute as residual IR. |
| Turn completion | The preserved base package retains the previously recovered bounded action counter; other scheduler work remains residual. |

The movement effect span is deliberately narrow. Its UDL requires the
qualified six-local GOTO frame, no vehicle, the adventurer as actor, an actor
parent matching the current scene, and a known destination. The original
on-foot insertion and assignment are replaced; the prelude and continuation
remain explicit residual behavior. Being able to name a destination does not
establish that every condition for entering it has already succeeded.

### Resolved dispatch links

The dispatcher exporter recovers 146 action-table entries and the ordered
selection stages used by PERFORM:

1. Actor action.
2. Scene before-action handler.
3. Verb before-action handler.
4. Indirect-object action.
5. Direct object's container action.
6. Direct-object action.
7. Default verb action.

The source's conditions for reaching those stages remain in the original
control flow. At an admitted link, the runtime uses the named definition to
select the routine directly. It does not run the original sequence that
pushes a packed target and calls through the stack.

The dispatch document also names object callbacks and qualifies supported
source-defined callback substitutions. Such substitutions are not arbitrary
mutable-pointer guesses: the export retains their finite target definitions,
setter evidence and appropriate guards. Unsupported mutations fall back to
the original behavior.

Lexical aliases and grammar associations provide evidence for action naming.
They do not replace the original parser or claim that every syntax filter has
been recovered. Exported handler bodies remain marked as low-level IR. The
existing mailbox semantic replacement can still execute when a resolved OPEN
handler reaches its independently qualified mailbox binding.

Source arguments and original frames may still be needed to call an
unrecovered body. That transport is confined to the compatibility adapter.
The scene UIL and named handler definition do not acquire stack operands or
packed addresses merely because a residual routine still needs its original
calling convention.

Some residual room behavior can request nested input or save state before the
enclosing travel action returns. Its caller frame is therefore observable at
that boundary. UDL includes the original temporary-local correspondence and
the already resolved property-address, length, door and failure-resource
constants needed to reproduce that frame. The adapter materializes those
constants when joining the residual body; it does not rerun the property-size
switch or use the frame to decide the semantic destination. These compatibility
details disappear with their residual bodies. They are not requirements of UIL.

## UDL integrity, live guards and faults

The source definitions bind several distinct things:

- Initial source identity and the exact preserved base package.
- Semantic document digests.
- Object property-table layout and selected exit records.
- Packed text, abbreviation references and name dependencies.
- Source operations and their lowered IR counterparts.
- Routine headers, initial locals, return conventions and continuations.
- Mutable global facts, door attributes and object links.

Initial mutable values are evidence, not permanent runtime assumptions. The
runtime projects facts and door states from the current world. It checks
structural and narrative dependencies before replacing the corresponding
algorithm. A changed exit record, unsupported callback substitution, unknown
scene, unqualified frame or changed dependency produces an explicit fallback.

The player validator independently checks source correspondence. Recomputing
a document hash cannot make a contradictory destination, field mapping,
routine entry or omitted guard valid. Source witnesses establish integrity;
executed reference comparisons establish the separately declared behavioral
scope.

An effect plan is committed in order. A commit failure retains its partial
effects and fault evidence. It is not retried through the original algorithm,
which could duplicate already completed output or state changes. A faulted
runtime must be restored from a qualified checkpoint before execution resumes.
CLI fault handling retains the previous completed checkpoint.

Execution budgets count consumer dispatches. Replacing several source blocks
with one semantic operation changes that count. A smaller dispatch count does
not mean that the game consumed fewer turns.

## State and recovery receipts

```python
from fdisbull.zork_scenes import recover_scenes
from fdisbull_player.scene_runtime import SceneRuntime

package = recover_scenes(story_path, base_intents=preserved_package)
runtime = SceneRuntime(package, seed=12)

opening = runtime.run()
next_result = runtime.command("north")
live_facts = runtime.scene_state()
```

The optional constructor switches `enable_scenes=False` and
`enable_intents=False` support comparisons through the same package while
disabling the corresponding semantic replacement.

Results retain the existing `recovery` data and add `scene_recovery`.
The latter reports:

- Resolved dispatch sites and selected named handlers.
- Selected exit outcomes.
- Executed scene primitive counts.
- Invoked residual handlers.
- Fallback reasons.
- Replaced source-block counts where recorded.
- Ordered completion or fault segments.

These receipts distinguish actual semantic execution from source metadata.
A handler being listed in a document is not evidence that it ran. A residual
handler invocation is not counted as recovered game intent.

## Checkpoints and compatibility

Scene checkpoints bind the complete scene package, including the preserved
base package, both UIL documents and UDL. Editing a rule or correspondence
creates a different identity; an old checkpoint cannot silently resume under
it. Nested original-game save slots use the same bound package identity.

The old IR and mailbox-intent packages retain their own consumers and
checkpoint identities. Adding the scene layer does not rewrite them or claim
that their checkpoints are interchangeable with scene checkpoints.

The semantic evaluator and player use only packaged Python code. No original
Z-machine interpreter, native debugger or analysis database is required for
this consumer. The original reference executable remains a separate verifier,
not a runtime dependency of the generated package.

## Verification boundary and remaining work

Authored tests exercise the pure evaluator, each source exit convention, graph
association, resolved calls, source bindings and rejection paths. The
[executed verification report](VERIFICATION-ZORK-SCENES-2026-10-30.md) records
the actual-story comparisons, exact package/source identities, inputs and
observed boundaries.

The appropriate claims are distinct:

- **Scene inventory:** all 110 qualified room definitions are named.
- **Encoded exits:** all 352 source exit records have explicit definitions.
- **Reference resolution:** qualified table/property links have named targets
  or an explicit residual classification.
- **Effect recovery:** supported exit decisions/refusals and the bounded
  on-foot relocation execute as game-intent primitives.
- **Behavioral equivalence:** limited to the cases and state/effect boundaries
  recorded by executed checks.
- **Whole-game intent:** remains incomplete.

The next semantic work can replace a named residual handler with its actual
conditions and effects without reconstructing its packed-address mechanism.
For example, a room event, a routine-selected exit, or an arrival rule can be
recovered and tested against its declared source boundary. The retained
conversion remains available for every behavior not yet recovered.

