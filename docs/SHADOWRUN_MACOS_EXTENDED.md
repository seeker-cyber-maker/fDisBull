# Shadowrun actor-stage extension on macOS ARM64

This work continues the [native ARM64 experiment](SHADOWRUN_MACOS_ARM64.md)
from qualified commit `acfb843fa972cd2f2bbca468ab832e4d270a0dfe`. That retained
moving build stops transactionally at source frame 6124. New behavior is
qualified against original Genesis execution, a procedural UIL interpreter and
compiled native contexts separately. The preserved NES research is not being
requalified by the native extension.

## Choose a simple source scenario

The priority is the Pac-Man-like actor stage: useful player movement and
collisions, current actor positions, source-backed scheduling and repeatable
mechanical interaction. Dialogue, quests, original artwork/audio and full-story
boot are separate recovery questions.

Two source preparations must stay distinct:

- The armed tests use the original five declared setup patches and an original
  constructed actor placed in scene 2. They are assisted. Player health, enemy
  timers and RNG must not be changed merely to prolong a test. A lethal result
  remains part of the evidence.
- The calm courtyard uses the original captured player and three civilians,
  without the armed-actor construction patches. It is a prepared native entry
  into a source-observed scene, not a native reproduction of the preceding
  whole game. Directional exploration and actor behavior are qualified before
  enabling inventory, firing or other interactions.

Original input routes are recorded in their capture receipts. Runtime motion
uses current state, ROM tables and supplied input; future captured positions
are comparison outputs, not playback commands.

## Extend the missing dependency

The first 6124 boundary is a repeated moving-origin negative attack pose
`8058`, followed by idle pose `18` and another source attack. Recovery follows
the original actor/service and sprite-clock operations, including their
separate counters. These are state-dependent continuations; source frame
numbers are evidence coordinates, not runtime cases.

Ordinary retreat and turn probes also exercise live-coordinate aiming,
projectile expiry, held-direction recovery and a wall stop. A route that dies
sooner is not presented as a survival improvement. The calm actor-service
route adds the waypoint/scheduler dependencies of actual civilians rather than
making an armed opponent harmless.

Unsupported continuations remain explicit boundaries. Native contexts roll
back the entire candidate state and the app stops; resetting or choosing a
prepared scenario does not establish an original save/load transition.

The longer routes exposed an earlier composition error: an expired player
action timer was reset during held movement. Original code at `AD4E–AD7E`
only takes that reset path when there is no directional heading. Correcting
this changed the later reachable states. The earlier candidate's claimed
moving terminal at 6267 is withdrawn; the corrected route refuses at 6257.
A separate regression now keeps the entire terminal model snapshot stable
when callers attempt another input after terminal status.

## Current qualified windows

| Route | Completed native/model updates | Original comparison and current boundary |
| --- | --- | --- |
| Unpatched courtyard | 451, source frames 6000–6450 | Player and three civilian positions/HP match 30 main-witness checkpoints; supplemental fixtures add overlapping comparisons. HP remains 10. |
| Armed LEFT then neutral | 257, through 6256 | Passes the former 6124 boundary; expired-timer idle recovery at 6257 still refuses. |
| Armed retreat and turn | 117, through model HP0 at 6116 | Original first samples HP0 at 6120; exact terminal-frame parity is not established. |
| Armed B then held fire | 41, through 6040 | B target selection at 6041 is outside the modeled target domain and refuses. |
| Armed LEFT then DOWN | 93, through 6092 | DOWN recovery is qualified; the next hostile decision at 6093 refuses. The original-only route survives to 6300 at HP3. |
| Stationary held fire | 80 | Separate retained original return-fire witness: 15 checkpoints, ammunition 12→11 and projectile slot/position checks. |

The native/UIL check compares all 3,407 courtyard state elements or 3,660 armed
state elements after each completed update. This is not a full-RAM comparison
with the original: source comparisons retain their specified fields and
checkpoint density. Failed or unqualified armed routes remain visible rather
than being combined with the calmer exploration result.

## Main menu and intro as source probes

The source menu has **New Game / Load Game**, then **Samurai / Decker / Gator
Shaman** for New Game. The recovered module uses the original input-edge word,
cursor wrap, preview and confirm rules. Start is ignored by the reviewed source
menu. The macOS frontend adapts keyboard delivery and uses authored text, not
the original menu graphics or sound.

Original archetype initialization and Load Game are distinct source boundaries.
The frontend identifies them and offers a separate, labeled prepared-scenario
entry. Selecting an archetype does not claim to initialize that character in
the existing captured arena.

In the source menu, use Up/Down and Z/X to confirm; Enter represents the source
Start button and does not confirm. After the initializer boundary, **P** enters
the separately prepared selected profile, paused. **Space** starts/pauses,
arrows move, and **R** resets. Armed profiles additionally admit their bounded
Z fire/equip, X target/back and Enter inventory paths. The calm profile marks
those interactions unavailable. Escape quits.

The opening field-arrival witness has no memory patches and no scheduled
controller input after frame 4765. At 5249–5251 the player moves automatically
through Y 10440, 10410, 10380 at X 15584. Position writers `BBEC`/`BBF0` and
callback `B574` connect this automatic walk to the ordinary movement machinery.
This is stronger than inferring a shared engine from similar-looking motion.

Fourteen earlier cinematic samples leave the sampled player record at
1920/1920 with callback `B45C`. Those samples and combat artwork establish
neither cinematic combat AI nor continuous inactivity of every actor. The
complete opening script is not yet reproduced by the arrival-writer witness.

## Repeatable native output

Build outside Git after storage admission, with an external per-command
temporary directory and the same reviewed manifest, ROM and capture:

```sh
fdisbull shadowrun-ai-build "$OPENING_MANIFEST" \
  --rom "$ROM" --capture "$CAPTURE" --target macos-arm64 \
  --profile assisted-arena --preset moving --output "$PRIVATE_ARMED"
fdisbull shadowrun-ai-build "$OPENING_MANIFEST" \
  --rom "$ROM" --capture "$CAPTURE" --profile captured-courtyard \
  --output "$PRIVATE_COURTYARD"
```

The captured-courtyard profile defaults to ARM64 and its courtyard preset;
armed defaults remain compatible with the prior API. The calm profile refuses
the NES target. The final build receipts identify the supported source windows
and input routes; the command alone does not establish unrestricted exploration.

## Verification method

First reproduce the retained 124-update baseline and its unchanged-state
refusal at 6124. Then compare every scalar and array element of each new native
context after each completed update with an independent GameMachine. Compare
source actor/player/health/RNG projections separately at receipt-bound original
checkpoints, with matching inputs and preparation. Preserve damage-terminal
boundaries separately from unmodeled source death-scene continuation.

Menu checks distinguish original 68000 execution, full-core controller actions,
standalone UIL and compiled native menu behavior. Stored-state rendering and
live keyboard observations have their own scopes. Measure native update and
drawing work with equal completed budgets, separately from setup, compilation
and onscreen scheduling. No future game or hardware guarantee follows.

Counts, hashes, outcomes and remaining boundaries are recorded in
[menu and intro evidence](evidence/shadowrun-extended-2026-11-01/menu-intro.json)
and the final extension verification receipts. Five equal offscreen drawing
budgets have a median of about 0.93 ms/draw; ten equal native update budgets
have a median repeat mean of about 1.55 µs/update on the tested M1 Max. These
measurements exclude onscreen scheduling and do not establish every frame's
deadline. Original ROMs, captures,
generated apps/libraries and images remain private; packages contain authored
source and sanitized evidence only.
