# SNES Shadowrun: morgue targeting, pickup and scripted response

This 2026-11-03 extension continues the [title-to-morgue study](SHADOWRUN_SNES_OPENING.md).
It follows ordinary original-controller routes through targeting, a context action
menu, Slap Patch and Scalpel pickups and a Wooden Door action that wakes a Mortician-associated
task and produces two text windows. The native `opening` profile uses the same
prepared title seed and derives later scene, script and item state from ROM.
The original Morticians do not offer a direct Talk menu in the tested state;
selecting an in-range Mortician and pressing B remains a no-op. The door response
is scripted dialogue, separate from the game's keyword-conversation system.

## Build and controls

```text
fdisbull shadowrun-snes-build --profile opening \
  --rom /private/source.sfc --ram /private/ram-000839.bin \
  --save-ram /private/save_ram.bin --output /private/new-interaction-study
```

ROM/title/save identities are unchanged from the preceding study. The factory
seeds once after original video frame 839, before START. The output contains
private game-derived seed data and must remain outside Git and tool packages.
Boot-to-title is not recovered.

Return selects NEW GAME. Arrows move, B enters cursor mode, arrows move the
cursor, and B on a source-valid target opens its available actions. Up/Down
select an action; B confirms and Tab supplies source SELECT cancellation.
Space pauses, R resets and Esc closes. Original source guards determine which
objects can be selected, whether an action is available, and whether it is in
reach. Unsupported paths stop transactionally.

The display is an adapted isometric actor view using the recovered camera and
source cursor coordinates. It shows decoded target/action names, source text
and the observed picked-up item count/owner. Original artwork, OAM/tile rendering,
NMI display timing and APU playback are excluded. The general keyword-conversation
interface, combat, other rooms and unrestricted exploration are unqualified.

## Source producer chain

| Edge | Recovered effect and boundary |
| --- | --- |
| `$BC37`, `$BE3D`, `$BC8E` | Cursor initialization/acceleration, bounds, reverse actor-order hit tests, retained target offsets and name-window ownership |
| `$DF35` | Player facing follows the cursor using source arithmetic and direction setter |
| `$BF0B` | Target task/redirect resolution, action-wait mask, reach test and event dispatch |
| `$996E`, `$A632` | Ordered action labels/hotkeys, selection, repeat, confirmation/cancellation and final input poll; suspended scene pass |
| `$FE33`, `$FAA7`, `$FA76`, `$FA08` | Encoded text pointers, source font advances including controller icons, logical row/cursor layout and direct-window release |
| `$81:8C2E`, `$81:8A91` | Live camera velocity/clamps and position; tile-stream side effects explicitly excluded |
| `$81:8686–86E4` | Other dynamic-owner overlap height for player queries; own record skipped; source blocked-X response and flag preserved |
| Item task/native helpers | Live player/X query, unsigned bytecode comparison, item count and owner writes, real child wait/sound and actor teardown |
| Door/NPC script linkage | Wooden Door action sets a shared entity flag; Mortician-associated task reacts, clears the flag and calls the existing text/window pipeline |

A target label does not establish an available interaction. The actual task wait
mask determines the action list. The original selected Mortician actor `$46`
while in range but offered no action on that route. Opening the Wooden Door
instead sets entity `$07EE`'s flag bit 2 and wakes actor `$44`'s task `$12`.
That task issues text calls with IDs `$39` and `$3A`. The source task association
identifies the producer; this study does not assign the visual speaker of each
box solely from that association.

The Slap Patch route selects actor `$38`. Its source task increments byte
`$2EA2` from 0 to 1 and writes owner/reference `$08B2` into `$2EA3–$2EA4`.
The first writer is `$80:9D87`, the second `$80:CBD2`. The actor remains briefly
while child script `$004B` waits and issues a semantic audio request, then the
parent tears it down. Removing the sprite immediately at selection would omit
that source ordering. The source count helper uses byte arithmetic and a maximum
of six; only the observed pickup/count transition is original-run qualified here.

The Scalpel follows a different operation: `$80:9CF8` writes the party entity
`$08B2` to owner word `$2E80` in record `$2E7D`, without incrementing its other
state bytes. It runs the same timed child before actor `$3E` disappears. The
placed Slap Patch actor record also differs from its inventory-type record;
the native last-pickup display follows the actual item writer rather than
assuming the selected actor record is the inventory record.

## Input and observation clocks

The existing main-loop checkpoint is before `$80:962E`. A context menu can suspend
one such pass across many video frames: the pickup menu occupies serial 1896,
and the later door menu occupies serial 2233. Each selector input poll, its final
post-confirm/cancel poll and the post-dispatch poll are separate observations.
NPCs, physics, camera and window timers do not advance once per modal input.
The native entry resumes the suspended scheduler once after dispatch completes.

The polling routine consumes an already published controller word. NMI can
change that word while the intervening sound or display routine runs, so the
final poll cannot reuse the earlier held value by assumption. Main/player held
values can legitimately differ when recorded intervening modal polls explain
the change. The checker validates that ordered chain and compares previous/edge
latches; it does not inject observed future game state.

The observer is pinned official SNES9x commit
`fae2fea08f74180759ef540ee94259213f503480`, with exact ROM identity, ordinary
controller inputs and no memory patches. The modal observer core is SHA-256
`34f40027761df3cdbcfa9efad1ad68540cc069105757168e8b81f19864d0b022`.
Each qualified route has a separate checkpoint-only observer comparison and an
unmodified-core selected/final comparison. These remain observations from one
emulator family; the unmodified core exposes no instruction checkpoints.

## Qualification

All four final interaction routes pass their recorded original comparisons.
The same hash-validated native program is used for every route.

| Route | Original checkpoints | Selected source values | Modal input polls | Complete native/UIL elements |
| --- | ---: | ---: | ---: | ---: |
| Slap Patch pickup | 1,973 | 4,499,113 | 64 | 3,081,036 |
| Scalpel pickup | 1,928 | 4,396,423 | 64 | 2,934,320 |
| Repeat attempt at removed item | 2,128 | 4,839,666 | 64 | 3,374,468 |
| Pickup, door action and scripted response | 2,363 | 5,353,426 | 119 | 4,401,480 |

The routes share the opening prefix; these counts are not unique coverage
added together. Native/UIL checks cover the continuous title/first-two-pass
prefix and declared one-step samples, including distinct modal poll sites and
navigation/confirmation edges. The complete native replay is compared against
each original checkpoint; complete UIL interpretation of every pass is not
claimed.

Cancellation has a separate complete input replay with **82 sparse original
checkpoints** and selected/final observer-neutrality gates. SELECT follows
phases 1→2→3→0, releases the window, and commits no action or item change.
The source observer has a matching checkpoint-only comparison and seven
unmodified-core RAM/image comparisons. This sparse result is not described
as a continuous comparison at every original pass.

The prior 1,615-checkpoint opening route and 60-pass scripted profile also pass
fresh regressions. Repeated unsupported input after accepted routes and a
repeated refusal of the unimplemented out-of-range-warning branch preserve
1,173,728 exposed native state elements across eight readbacks. This is atomicity
evidence, not source-equivalence for the warning.

The public native app matches the independently checked program/seed/C/header/
core and accepts 2,482 updates on the door route, 2,037 on Slap Patch and 1,992
on Scalpel, with the original final player positions. Menu, pickup, and scripted
text views render offscreen. Live keyboard operation remains unqualified.

The broad macOS suite reports **4,020 passed, 142 skipped, 3 failed and 23 setup
errors**; the same 26 non-green cases/types match the preceding baseline and
source stayed unchanged during the run. A subsequent host CLI help clarification
(`--inputs` expects a JSON file path) passed all 68 host tests and help readback.
The checker also gained explicit compiler samples at the newly recovered
collision/query/NPC transitions; its four focused tests and all four source
routes were rerun after that verification-only change. The source ZIP/sdist
selectors and archive guards were also synchronized so the sanitized receipts
are bundled with their linked methodology; all 976 distribution tests pass.
Exact-commit package/install results are retained in the local review.

Sanitized receipts are in
[`docs/evidence/shadowrun-snes-interactions-2026-11-03/`](evidence/shadowrun-snes-interactions-2026-11-03/).
 `scripts/check_shadowrun_snes_interactions.py`
compares the title-seeded native execution against original main-loop checkpoints,
with declared native/UIL prefix and sampled one-step checks. Modal phase checks
include distinct poll sites and navigation/confirmation edges. Additional source
readsets include camera, cursor/target fields, actor entity records, item count
and owner alongside the prior actor/task/window/text/sprite/collision checks.

The named pickup requirement explicitly checks original before/after count and
owner plus actor presence/removal, as well as model/source equality. A separate
ordinary repeat attempt returns the cursor to the former item hit position:
the removed actor cannot be selected, no Pickup menu appears for it, and the
count/owner remain unchanged. Cancellation and unavailable NPC actions are
separate negative cases, not invented successful conversations.

Whole-WRAM equality is not claimed. Cursor display latch `$0204` and tile-stream
scratch `$0CE8–$0CF3` are unknown presentation state, with dependent script reads
refused. The source initialized camera velocities explicitly; they were not
filled from a later observation. Other-actor collision is supported only under
the source-qualified player-query branch. The separately recovered prospective
action query tests the dynamic grid before the door closes. The original
out-of-range warning has been observed, but its complete window/input continuation
is unimplemented and refuses transactionally. Unobserved continuations still refuse.

A separate source-derived conversation-record helper can select entries, insert
keywords and expose text/child-script references. Its synthetic tests do not
qualify a live `$92EF` keyword conversation, and that helper is not substituted
for the observed door-triggered script response.

## Friction and next decisions

The investigation skill records the practical decisions from this run: select
an available action rather than inferring it from an NPC name; distinguish item
count/ownership writes from delayed actor deletion; observe modal input clocks;
follow live camera and collision dependencies; distinguish text IDs, encoded
pointers and CPU addresses; and preserve controller-icon widths. It also records
that a source task's identity does not identify every box's visual speaker.

The next room uses a different source constructor path that preserves world state
and reconstructs carried party members. Reusing the new-game constructor there
would reset unrelated state. Room transitions and a real keyword-conversation
route need their own producer/consumer recovery and qualification. They remain
outside this first-morgue interaction result.
The subsequent [room and keyword study](SHADOWRUN_SNES_TRANSITIONS.md) records
the recovered loaders and conversation components, together with the remaining
hardware-RNG boundary. Its results are separate from this preserved milestone.

Original ROMs, RAM, saves, states, screenshots, decoded text, generated apps and
byte-containing UIL seeds remain private. Only authored code, hashes, counts and
sanitized methodology belong in Git/tool packages. Hosted CI, merge, release and
system installation are separate gates.
