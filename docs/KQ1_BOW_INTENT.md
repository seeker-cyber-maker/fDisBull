# KQ1: one executable audience interaction

The qualified KQ1 DOS AGI 2.917 resource set now has an executable, bounded
initial-audience bow interaction. Its UIL selects named outcomes and game
effects; a separate UDL definition connects those effects to the original
LOGIC53 operations. The complete scene census remains unchanged low-level IR.
The [verification record](VERIFICATION-KQ1-BOW-2026-10-30.md) distinguishes
source comparisons from fresh original-game observations.

The interaction covers command admission or refusal, the first respect reward,
the bow's completion event, its response and explicit acknowledgement. The
original parser, global/room dispatcher, animation scheduler, renderer and
modal clock remain host dependencies. This is a complete interaction within
that declared boundary, not a complete AGI player.

## Recover effects before simplifying their implementation

The executable definition contains ordered conditions, semantic state fields,
geometry, narrative resources and domain steps. It contains no LOGIC addresses,
variable numbers, flag numbers or instruction stream. The evaluator executes
these rules directly, without consulting the retained source control flow.

| Primitive | Recovered effect | UDL source correspondence |
| --- | --- | --- |
| `court.begin_bow` | Mark this visit's bow, suspend player motion, begin the gesture and request completion notification | Admission guard and LOGIC53 payload `[0x24b, 0x26f)` |
| `court.award_first_respect` | Add three points once, preserving byte score arithmetic | Reward latch and `[0x26f, 0x27b)` |
| `court.finish_bow` | Complete the gesture, restore the current actor baseline and player motion | Completion guard and `[0x42e, 0x44f)` |
| `narration.modal` | Present a selected response and suspend this dispatch until acknowledgement | Five bound local message resources and their print sites |
| `input.claim` | Consume a successfully recognized bow command, including a refusal | Ordered, stateful `said` alternatives |

`input.claim` is a supporting parser contract. Refreshing the source's position
flag is explicitly retained as residual IR. Neither becomes a newly invented
game action. Exact animation requests, scratch writes, message numbers and
source witnesses live in UDL and its adapter.

Geometry and byte arithmetic remain visible because they affect the outcome.
Moving these details into a mapping does not justify discarding their effects.
The original source currently remains the evidence for this profile; another
edition must be qualified separately.

## The interaction contract

The caller enters the selected LOGIC53 payload segment `[0x1b8, 0x460)` after
room initialization and the retained scheduler prefix. Room 53 must be active,
the ending prefix idle, and neither ending flag active. The carried magic
treasure count must differ from three. Output must use ordinary blocking print.
The caller must already have passed any earlier global death/return handlers.
These conditions are recorded in UDL and checked where represented in the
supplied state.

The command identities are `bow` and `bow_to_king`. Recognition requires ready,
unconsumed parser input. Each recognized outcome consumes that input, including
invisibility, position and repeat refusals. Other ready commands remain IR.

The rules retain the source's ordered tests and inclusive actor-baseline zones:

| Zone | x range | y range | Use |
| --- | --- | --- | --- |
| Addressing the king | 18–86 | 80–113 | Select nearby command handling |
| Improper position | 18–67 | 80–107 | Refuse a nearby bow from this position |
| Distance reference | 60–86 | 85–113 | Preserve the separate far-response condition |

Within the addressing zone, invisibility is checked first, then improper
position, then admission, then repeat/busy response. The far branch retains
its separate geometry and countdown conditions. A new admitted bow marks
`bowed_this_visit`, shifts the actor baseline seven pixels left, stops motion,
starts the bow animation and clears any stale completion event. If
`respect_awarded` is false, it sets that latch and awards **three** points.
The score addition wraps as an unsigned byte.

The reward happens at admission; the success response happens after animation
completion. On that event, `court.finish_bow` clears the completion and
stationary-animation flags, adds seven to the actor's **current** x coordinate,
restores normal motion, and then presents the response. It does not restore a cached
entry coordinate. Acknowledgement resumes the suspended segment.

Two separate facts must survive the simplification. `bowed_this_visit` is reset
by original room-entry behavior; `respect_awarded` persists. A later visit can
therefore permit another bow without another reward. Source comparisons cover
these states; this change does not claim a fresh native leave/re-enter trace.
The king's quest dialogue requires a separate talk command and remains IR.

## Progression and time

Command handling precedes completion handling. If a repeat command and a bow
completion arrive together, the refusal modal pauses first. Its acknowledgement
can then expose the completion response, requiring a second acknowledgement.
Starting a bow resets its completion flag. The strict adapter declines a
supplied completion flag without a qualified outstanding bow; it does not infer
the origin of that callback.

Pending animation and pending output are separate states. Commands arriving
during the animation use its shifted, current position: for example, a bow
starting at `(68, 90)` shifts to `(61, 90)`, where another command can receive
the improper-position response. Removing that shift without preserving its
conditional effects would change progression.

The adapter preserves the original completion request order: set loop 1 before
restoring view 0. The fresh original run restores the left-facing normal pose.
The renderer's treatment of that request sequence is a host obligation; the
UIL consumer does not replace it with a generic loop-clamping rule.

An acknowledgement token binds the package and suspended interaction state.
Only engine-clock variables 11–14 may change during an ordinary modal wait;
their current values survive acknowledgement. Changes to score, position,
scratch state, parser state or other protected fields invalidate the token.
Timed or nonblocking output is outside this profile. No fixed number of AGI
cycles or milliseconds is invented for the gesture, and AGI cycles are not
Zork turns.

## Export and evaluate privately

Run these projectless commands against your own exact qualified resources:

```sh
fdisbull kq1-bow-intents /private/kq1 \
  --output /private/kq1-bow.package.json.gz \
  --uil /private/kq1-bow.uil.json --udl /private/kq1-bow.udl.json.gz

fdisbull kq1-bow-evaluate /private/kq1-bow.package.json.gz \
  --state-file /private/before-bow.json
```

The state carrier contains exactly 256 byte `variables`, 256 Boolean `flags`,
`ego` with byte `x`/`y`, parsed `words`, and Boolean `player_control`. An optional
`host` object is preserved. This is a declared source boundary, not an automatic
native-memory decoder. Unknown native fields must be qualified or reported;
do not populate them with invented observations.

The returned `state` is a carrier, while `effects` are ordered original engine
requests and writes. `semantic_effects` and `executed_intents` show what the
higher-level evaluator actually executed. A `slice_complete` result means the
selected dispatch segment completed; an animation can still be outstanding.
`awaiting_ack` returns a continuation. Save its carrier separately and pass
an event document containing `{"kind": "ack", "continuation": <returned token>}`:

```sh
fdisbull kq1-bow-evaluate /private/kq1-bow.package.json.gz \
  --state-file /private/modal-state.json --event-file /private/ack.json
```

The command does not send requests to a native guest, render frames, fabricate
an animation completion or acknowledge output automatically. The host supplies
the next qualified event. `unrecovered` returns unchanged state and no effects;
the caller retains responsibility for executing the original source path.

For Python integration, `recover_bow()` produces a package, `CourtRuntime`
validates it once for repeated `step()` calls, and `evaluate_event()` executes
the pure UIL definition against semantic state. The last interface can carry
unknown facts as `None`; an unknown required fact yields `unrecovered`.

## Exact binding and retained work

Package validation checks the pinned resource manifest and LOGIC53 digest,
re-decodes the source, verifies 18 instruction-aligned witnesses, rebuilds all
field/resource/geometry/primitive mappings, and checks the complete retained
census. Altering a mapping and recomputing a package digest cannot authorize a
different interpretation. The separate raw slice reference executes source
bytes and does not import the intent producer, evaluator or adapter.

Private exports include original messages, source witnesses and all 90 LOGICs
as retained census IR. The exporter refuses repository destinations and
existing files. Packages and raw reference observations are not distribution
assets; only selected aggregate verification metadata is committed.

Returning all three magic treasures, talk/dialogue, ending behavior, unrelated
commands and the rest of the game remain low-level IR. The census still accepts
zero interactions; this separate profile accepts one bounded interaction.
The working Zork conversion, its independent player and its tests are preserved.
