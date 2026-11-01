# Shadowrun Pac-Man-like actor stage

This source-bound experiment adds moving actors and an armed actor's combat
loop to a prepared Shadowrun NES scene. “Pac-Man-like” names the intermediate
analysis stage: restoring positions, movement, placed facts and mechanical
responses before recovering general item, dialogue and character interactions.
It does not identify a Pac-Man game or imply that all Shadowrun behavior is
recovered. Z is a separate text projection over the same qualified model.

The preserved static-NPC `shadowrun-play-build` profile remains available.
The new `shadowrun-ai-build` produces a private MMC3 cartridge from procedural
UIL/GameIL. It requires the exact reviewed 2-MiB Genesis ROM, opening manifest,
receipt-bound scene-2 frame-5999 capture and prepared cc65 toolchain. It does not
accept another edition or automatically lift arbitrary Genesis games.

## Prepared profiles and controls

The `assisted-arena` profile constructs the armed kind-8/item-10 actor from the
original scene-54 profile using the original constructor, then places it in the
captured scene-2 terrain. The original frame-5999 player has HP 10 and the pistol
and armor tested previously. The constructed actor has HP 10, ammo 48 and source
armor 3; this is a strong opponent for the starting pistol.

| Preset | Initial difference | Source witness |
| --- | --- | --- |
| `stationary` | Constructor action timer 0 | Source actor fires immediately; burst, two player hits, recovery and return fire are compared |
| `moving` | Explicitly assisted initial action timer 2 | Original actor chooses a path, moves while the player retreats, then fires and damages the player |

Both are assisted test scenarios. The original console ROM is unchanged.
Five initial work-RAM patch regions establish the source actor and
combat/target/alert/RNG context; the moving preset changes its action timer
within that actor record. Full-core tests then run the original engine with
sound enabled and ordinary controller input. The scene-54 encounter has not
been reached through ordinary game progression. This is not a recovered
scene loader or a complete hostile-population model.

D-pad requests movement; B selects the admitted target; A/held A requests
pistol fire. START opens the captured inventory while ready; D-pad selects and
A toggles the captured pistol or armor, with B/START to close. Inventory pauses
the arena as a target adaptation. SELECT debug placement is not admitted in
this profile. Unsupported input/state/terrain/concurrency branches produce an
explicit refusal rather than advancing a fabricated actor state. The receipts
identify the actual tested input routes; they do not establish free movement
or every combination of simultaneous actions.

Player HP and the hostile's current HP are displayed separately. Damage changes
the player's attack difficulty: primary HP 5..7 adds 1, HP 1..4 adds 2, and the
alternate health channel has the same thresholds. The captured alternate
channel remains 10 in this profile. Hit reaction uses original animation-counter
and admission rules; it is not an authored fixed delay. At the verified HP 0
boundary the model commits depletion and stops. NES START restarts the prepared
scenario through the target reset path; this is not original save/revival or
recovered death-scene behavior.

The symbolic terrain and actor markers are target-authored. Original sprites,
scene artwork and sound are not reproduced. Other source actors in the
captured scene remain historical facts with unknown current state when the
selected profile does not simulate them. They are not asserted absent.

## Repeatable entry points

Run the host's storage admission check before each bulk operation and select a
fresh private output directory outside Git. Keep original ROMs, source-derived
tables, captures, generated cartridges and raw traces out of tool packages.

```sh
fdisbull shadowrun-ai-profiles
fdisbull shadowrun-ai-build "$OPENING_MANIFEST" \
  --rom "$ROM" --capture "$CAPTURE" --cc65-root "$CC65_ROOT" \
  --profile assisted-arena --preset moving --output "$PRIVATE_BUILD"
fdisbull shadowrun-city-export "$ROM" \
  --snapshot "$CAPTURE/native/scene-005999" \
  --profile assisted-arena --preset moving --output "$PRIVATE_CITY"
fdisbull shadowrun-z "$ROM" \
  --snapshot "$CAPTURE/native/scene-005999" \
  --profile assisted-arena --preset moving --policy physical
```

The Z command serves the standard line-oriented observe/act protocol.
`shadowrun_assisted_arena.assisted_arena_from_capture(..., moving=True)` seeds
an independent GameMachine. Model execution uses its own current state,
source-bound tables and inputs; future original capture coordinates are never
replayed as actor behavior. NES and Z are separate instances, not synchronized
live sessions. JSON/text/interactive HTML city exports are private investigator
snapshots, not a second executable world.

## Accuracy boundaries and findings

Three checks remain distinct: original code versus recovered components,
original frame captures versus their composition, and compiled NES versus the
shared model at completed logical updates. Exact source/core/input/capture
hashes bind each receipt. Controlled CPU entries prove their supplied context;
they do not establish natural reachability or a complete game loop.

- The three initially captured walkers move in the original, but a one-shot
  then idle test showed no retaliation or player HP change at its sampled
  states. This did not justify inventing hostile behavior. It redirected
  investigation toward original actor definitions and the armed profile.
- The stationary from-launch witness patches no player, projectile, terrain,
  camera or audio state. Source HP 10→5 at frame 6000, recovery at 6012, another
  HP 5→3 hit at 6030 and recovery at 6042 are independently compared. Holding A
  from 6013 lets the source player fire on 6043 while an enemy projectile remains
  active; the player allocates source slots FF0C/FF0D instead of occupied FF0B.
- Original item 10 fire uses a burst: its early lifetime 127 checkpoint is
  overwritten to 32 later in the same source path. Sprite passes gate two more
  redirected fragments, and exhaustion deactivates the projectile. Source
  actor passes and sprite passes must not be conflated. An HP-changing hit can
  redirect the original actor-loop pointer and cause another actor pass within
  the same frame; the extra pass does not imply an extra sprite pass.
- A prior post-impact-injected test produced a moving-shooter self-contact.
  The stronger from-launch test retained the attack pose and instead hit the
  player. Both remain valid for their stated preparations; neither substitutes
  for the other. Self-contact and armor absorption can consume RNG even when
  HP does not change.
- The moving source witness uses neutral input at 6000, then LEFT 6001..6040.
  Player and armed-actor motion occur in the original, followed by the enemy
  shot and HP 10→5 at 6021. Combat-mode movement selects a different source speed
  table from calm walking; reusing the old calm speed was detected and fixed.
- Captured-player defense/HP math matches 1,200 controlled original cases over
  five weapons, four armor values, three HP values, five incoming effects and
  four RNG seeds. The wound attack modifier matches 100 original cases. These
  are arithmetic/consumer boundaries; their counts are not full encounters.

Compiled target comparisons use input consumed at completed logical updates.
Bank switching and expensive 6502 arithmetic change physical-frame cadence;
identical physical-frame button schedules can therefore reach different logical
release edges. Equal completed logical workloads and actual input history are
reported separately from wall/physical timing. No 60-fps, hardware or whole-game
parity follows from a passing bounded comparison.

The first NROM dynamic build exceeded 32 KiB. The new target uses MMC3 procedure
banks and a separate source-table data window. A binary span reader and direct
word fetch preserve byte/fault/bank-selection behavior while avoiding repeated
linear scans. The equal-budget intermediate run dropped from 694 to 420 elapsed
physical frames for 112 logical updates, but the program also changed between
those runs: this does not isolate the reader's contribution. The final moving
build completed 124 updates over 641 elapsed physical frames; the stationary
build completed 243 over 862. These are multiple physical frames per logical
update, so the prototype does not run at 60 gameplay updates per second. Final
native hashes, timing, tested boundaries and failures are recorded below.

Unsupported firing, targeting and projectile continuations propagate a hard
boundary. Z discards the candidate update. NES retains the last completed
publication and epoch, shows refusal immediately and stops invoking the
controller; its interrupted internal state is unqualified. The moving test's
125th attempt and the held-fire test's 166th attempt are not counted as completed
updates. Actual source-guard regressions cover an unequipped pistol, empty ammo
and an unsupported target selector, alongside ordinary successful firing.

## Analysis approach and evidence

The bundled investigation skill now has a selectively retrievable
[analysis approach plan](../src/fdisbull/skills/fdisbull-investigate/references/analysis-approach.md).
It starts with the requested outcome, maps dependencies, ranks the next few
questions by decision value, evidence, risk and cost, selects a discriminator,
and gives branch/stop criteria. Worked examples explain why an unarmed actor,
a stale capture, or a passing intermediate helper may be the wrong next
analysis target. A small complete behavior path takes priority over collecting
more unrelated leaf tests.

Sanitized results are in
[source.json](evidence/shadowrun-ai-2026-11-01/source.json),
[nes.json](evidence/shadowrun-ai-2026-11-01/nes.json),
[z.json](evidence/shadowrun-ai-2026-11-01/z.json),
[skill.json](evidence/shadowrun-ai-2026-11-01/skill.json),
[suite.json](evidence/shadowrun-ai-2026-11-01/suite.json) and
[verification.json](evidence/shadowrun-ai-2026-11-01/verification.json).
Component-only route and projection leaves are labeled separately from the
wired controller. The source-native checkers under `scripts/check_shadowrun_*`
consume private inputs and write private receipts. Tool packages contain
source, authored tests and sanitized hashes/semantic results only.
