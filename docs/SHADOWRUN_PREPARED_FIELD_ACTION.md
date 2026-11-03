# Shadowrun prepared field action

`shadowrun_field_combat.lift_field_combat(rom)` binds the reviewed ROM and
source ranges to the authored `shadowrun_field_action.c`. It supplies a
bounded **assisted, prepared-state** combat composition; it is not a recovered
ordinary-player encounter, complete projectile simulation, or whole-game
combat. GameIL callers set `shadowrun_field_*` state and invoke
`shadowrun_field_captured_fire` or the lower-level `shadowrun_field_fire`.

The captured-player procedure requires `shadowrun_field_captured_profile=1` as
an assertion by the caller, not as a discovery mechanism. Only assert it for
the qualified source profile: actor index `+$3E=0`, flags `+$10=$0F`, equipped
slot `+$56=0`, item `+$57=2`, source `+$4C=10`, `+$9C=10`, `+$4D=2`,
`+$78=3`, `+$7B=2`, `+$7C=4`, `+$81=4`, `+$82=0`, `+$90=$0004`, `+$9A=0`,
`+$B4=0`, and `+$DF=0`; inventory bytes `+$66..+$6D` are
`02 2C 0E 10 00 00 00 00` and phases `+$6E..+$75` are
`00 00 06 06 00 00 00 00`. For that profile the original `$55640` computes
six exploding six-sided trials at difficulty four and writes the success count
at `+$9F`. The model consumes loaded ammunition and computes this source roll,
then evaluates a **caller-supplied projectile position** against one prepared
actor. It does not derive the projectile path or target position.

The caller supplies target coordinates, `+$10`, `+$B0`, `+$9E`, primary HP,
`+$78`, `+$7B`, `+$7C`, posture and RNG state. The admitted target is the first
and only eligible candidate, uses the non-party `+$3E >= 3` branch, no armor,
cyberware, dynamic effects, defense inventory or special global override. HP
11..127 is accepted for any admitted target type; HP 1..10 is accepted for
type `+$9B=$13` with bounded death timer and counter inputs. The source’s
bit-7 `+$9A` one-point override and the type-$13 zero-health timer, saturated
count and three party-counter effects are modeled; later removal and animation
remain outside this boundary.
The target `+$77` defense bonus is an explicit input. The source and target
attribute and coordinate bounds are enforced by the procedure. A rejected domain sets `shadowrun_field_supported=0`. The caller
must establish the unrepresented source and target conditions before asserting
this profile; no inference from a visible sprite establishes them.

`shadowrun_field_outcome` is 0 for no ammo, 1 for failed slot allocation,
2 for no eligible collision, 3 for collision with no HP reduction, and 4 for
HP reduction. The motion composition additionally uses 5 for active flight
and 6 for a terrain stop. A projectile with zero source successes takes the
original contact branch without a damage roll or additional RNG draws. Slot values are source slot IDs 9..14. The first and second slot
outputs describe selection, not persistent actor records. In particular, with
only one free slot the source has already consumed ammunition, initialized the
first actor and rolled before its second allocation fails. The composition
records the ammo, first slot and random state but does not reproduce that actor,
the combat-state globals, graphics/HUD calls or other allocation side effects.

The lower-level `shadowrun_field_fire` accepts party actor indices 0..2 or index
3, weapon 1 or 2, a selected slot 0..7, active source flags, ammo, six occupied
slot bits, the prepared collision state, and a **caller-supplied** `+$9F`
source-effect byte. Its party ammunition mutation is bounded to `$38AC` and
`$36FC` before HUD presentation. Item 1 and 2 have original threshold 4 and 6
respectively in the downstream `$55948` target trial. Neither procedure
recovers ordinary input dispatch, projectile motion, later effects after target
health reaches zero, enemy AI, scene progression, or persistent actor lifecycle.

Run `scripts/check_shadowrun_field_action.py` with the private exact ROM, core,
and fresh private output directory for controlled helper comparisons. Run
`scripts/check_shadowrun_captured_combat.py` additionally with the hash-bound
private scene-005999 RAM capture for the captured-source composition. Its 40
cases compare source shot success and RNG, then use those results to seed a
separate controlled `$14E6E` target-hit continuation, and compare HP/final RNG
with GameIL. This is not one uninterrupted native shot. Native target
compilation, NES execution, input-to-projectile reachability, dynamic collision
and timing remain separate checks. Raw capture and original-core traces stay
outside Git.

## Captured-heading flight

`lift_field_motion(rom)` composes those action procedures with the existing
source-bound terrain collision and a separate motion procedure. With
`shadowrun_field_path_profile=1`, the caller asserts the same captured player
profile plus position `$3CE0,$2BCA`, heading `$8000`, zero linked target, and a
compatible current scene map, bounds and rectangle table. The initialized
projectile starts at fixed-point `$3CE00000,$2C7A0000` with source velocity
`$0000,$5FFF`. `shadowrun_field_captured_launch` runs its first four motion
substeps; subsequent calls to `shadowrun_field_captured_tick` run up to four
more. Each proposal calls the shared collision procedure using the mutable
`shadowrun_terrain_map` and actual supplied bounds. No wall step is hardcoded.
A terrain stop sets `shadowrun_field_motion_state=3`; state 1 means active
flight and state 2 means a prepared actor candidate was hit. The existing
candidate gate and effect routine handle that assisted actor branch. The
composition does not create persistent projectile records, render the actor,
model combat-global writes or dispatch the original controller input.

`scripts/check_shadowrun_field_motion.py` checks this path against the private
instrumented A-controller capture: original frames 6037–6044 match projectile
fixed-point position, with sampled ammunition, shot roll, RNG, lifetime and
terrain stop. The original input schedule has no memory patches, but capture
alone does not establish observer neutrality. This comparison contains no
original actor hit. It does not qualify arbitrary starting positions, headings,
changing scene assumptions, actors omitted by the single-candidate adapter,
timing on the NES, or player control outside the declared profile.


## Assisted captured actor

`scripts/check_shadowrun_field_actor.py` copies the original `$FF0400` actor
record from the captured run and diagnostically moves it into the existing
projectile's next movement window. Its original fields include `+$0E=11`,
`+$3E=3`, `+$10=$25`, HP 10, `+$77=2`, attributes 1/2/2, posture 2,
and `+$9B=$13`. Thirty-six controlled cases cover zero-success contact and vary HP, the one-point override,
and bounded death timer/counters. Original core execution continuously enters
the projectile update and runs terrain, actor collision, effect and HP handling;
GameIL matches position, lifetime, HP, RNG and these counter effects. One case
with unchanged captured combat fields produces HP 10→6. Target relocation is
assisted and does not establish that this actor was naturally in firing range.

## Linked target heading and flight

`shadowrun_linked_heading.lift_linked_heading` recovers `$15D3C` heading and
distance for supplied player and target coordinates whose signed deltas fit in
the admitted word range. It reads the original angle tables through the
hash-bound external ROM region. `lift_linked_spawn` independently computes the
source spawn and secondary coordinates and signed velocity words for a supplied
heading; the target ROM must remain private. Their checks compare 50 heading
cases and 259 spawn-vector cases with controlled original-core entry.

`lift_linked_motion` composes these operations with the captured player shot,
shared terrain, and single-candidate actor checks. The caller supplies the
player position, selected actor state, current terrain and an explicit
`shadowrun_linked_profile=1` assertion that the captured player combat profile
and linked-target preconditions hold. AI movement, presentation and allocation
lifecycle are not simulated. Out-of-domain signed deltas or unknown hit cases
are refused.

The linked-flight checker uses the assisted original B+A run after the recorded
position/camera intervention. A dense capture supplies target coordinates from
frame 6088, before the frame-6089 shot; the write observer records the source
heading write before the target coordinate update in that frame. These inputs
produce the observed `$3B00` heading. Source and GameIL projectile positions
match for frames 6089–6091, including terrain termination. Observer neutrality
is not established. This does not demonstrate that the target was hit: original
captured HP remains 10. An independently placed captured-actor hit is documented
above; those are distinct evidence surfaces.

A further controlled continuation, `scripts/check_shadowrun_linked_actor.py`,
starts from the captured linked projectile at frame 6090 and relocates the
captured `$FF0500` actor into its next substep. Original-core execution then
moves through terrain, collision and HP handling; GameIL matches both projectile
coordinates, lifetime, RNG and HP 10→6. The relocation is a second diagnostic
intervention. It does not turn the earlier original missed shot into a naturally
observed hit.

## Ordered captured-actor adapter

`shadowrun_linked_actors.lift_linked_actors` composes the linked path with
`shadowrun_actors_launch` and `shadowrun_actors_tick`. The NES composition can
reuse its existing `shadowrun_target_x/y`, `shadowrun_target_flags`,
`shadowrun_target_flags_b0`, `shadowrun_target_selected`, and
`shadowrun_play_actor_hp` arrays. Target slots 0–6 represent source slots
`$FF0400..$FF0A00`. The caller asserts `shadowrun_actors_profile=1` only while
slots 0–2 retain the captured type-$13 combat attributes described above, the
relevant hidden target flags remain within that profile, and no earlier party
actor is eligible for a hit. The adapter checks each projectile substep against
all eligible records in source order and updates the first qualified actor's
HP. It refuses when a potentially eligible in-window slot 3–6 is encountered,
or when other admitted domain conditions are not met. A refusal encountered
after earlier substeps preserves those prior effects; it is not a rollback or
authorization to replay the shot.

The ordered-actor checker compares eight controlled original-core projectile
continuations, including all three actor slots, precedence, ineligible/dead
skips, no hit and zero-success contact, after diagnostic relocation of captured
records. A separate assisted original B+A run checks the adapter's linked shot
against three projectile frames, with the three source actors held at their
captured pre-launch positions by the target adaptation. Original NPC movement
continues and the observed original shot misses. These checks do not establish
NPC AI, animation, arbitrary actor types, free-form whole-scene combat, or a
natural original hit.

## Projectile retirement boundary

`lift_projectile_lifecycle` exposes the source primary and secondary active-bit
retirement gates after the caller supplies the original animation word. The
primary gate models the captured repeat-count-zero branch; positive-repeat
rearming is refused. The secondary gate clears its active bit when its
animation word is negative. Forty controlled original-core cases match these
boundaries. The separate original no-target run observed the secondary actor's
active bit clear at frame 6041 and the main projectile's clear at frame 6051,
but the transition itself was outside that capture's PC filter. A bounded
`shadowrun_lifecycle_animate` models the original `$5FDC` accumulator and the
`$600E` type-1/index-0 descriptor (three frames, rate `$0800`, period `$1000`).
Twenty-four controlled original-core cases match these two sequential
boundaries. Six service invocations from the sampled post-impact state produce
the sampled negative animation word, then the primary gate clears the bit.
The cadence of those service invocations and complete presentation remain
separate checks; the interface does not impose a fixed delay.

## Original controller route

On the reviewed original, the standard opening schedule followed by LEFT at
frames 6000–6059, UP at 6080–6100, B at 6120–6121 and held A at 6140–6249
selected source actor `$FF0400`. The instrumented run recorded ammunition
12→11 at frame 6164 and 11→10 at 6216; it recorded that actor's HP 10→6 at
6172 and 6→5 at 6224. The actor moved under the original AI, unlike the frozen
actor adaptation. A second unpatched run of the same input schedule without the
write observer matched all 65,536 RAM bytes at 16 sampled frames, including
the selected target and the two later HP/ammunition observations. The exact
intervening write frames are from the instrumented trace. This is one
original-core route and sampled observer control, not hardware equivalence,
full-machine equivalence or proof that an NES adaptation reproduces NPC AI.
