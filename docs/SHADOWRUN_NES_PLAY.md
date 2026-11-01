# Shadowrun scene-2 NES play experiment

This source-bound, prepared-state NES experiment starts from the separately
receipt-verified scene-2 capture at Genesis frame 5999. It is a partial
experiment, not complete Shadowrun gameplay or a claim of native Genesis or
NES pixel parity. Original ROMs, screenshots, RAM snapshots, cartridge builds,
and raw execution runs remain private outside the repository.

B selects a captured NPC and A fires the captured player's equipped item `02`
toward it. The original target-direction and spawn tables, source-order terrain
and captured-actor collision, damage arithmetic and cooldown are composed in
the shared model. Holding A repeats when the cooldown and the target's
one-active-projectile policy allow it. The selected NPC's current HP appears
in hexadecimal at the upper right. A no-target shot is supported only from the
reviewed initial position and heading. The target holds the prepared action
timer until the first A, and its single-active-projectile lifecycle is an
explicit target adaptation; the original allocates multiple actor slots. NPCs
remain frozen at captured positions and do not fire or run AI. Gameplay after
other actor, inventory or scene changes is not generalized from this slice.

The normal D-pad uses the existing source-bound player movement, terrain,
rectangle, slope and camera procedures. Its new presentation is a target-only
64 by 44 grid: one tile represents a 32 by 32 source-pixel terrain cell. Tile
categories distinguish the raw values 0, 127, 1..126 and 128..255, plus cells
outside the captured bounds. Those categories do not determine walkability,
visibility, scenery, or an original image. Collision and event refusals come
from the model, not the symbolic view. Scene changes, dynamic entity simulation, audio,
interaction dispatch beyond this scope, and animation are not implemented.
The earlier captured-atlas and finite right-walk animation profiles are separate
and remain available.

START opens a target-authored inventory browser. The captured eight raw item
IDs are shown in hexadecimal; D-pad selects a slot, A applies a supported
operation, and B or START closes the browser. Item `02` in captured slot 0
can be equipped or unequipped within the verified state domain, including the
source's loaded-round/percentage conversion. Item `2C` uses the source armor
branch. Other item actions refuse; a red X briefly marks a refusal. These UI controls
are a target adaptation. The original comparison uses two confirmations per
item action, while this target uses one. Inventory is not saved. On the tested
NES core, returning to the symbolic field paused updates for 21 physical frames
while its overwritten nametable was restored.

B refreshes source-derived screen admission and cycles eligible captured NPC
records. NPC positions are frozen from the initial capture; colored markers
are target-authored symbols and do not show original sprites. Target selection
has no verified line-of-sight or range semantics. A red X marks an unsuccessful target selection or
an unsupported action. This is a partial targeting adapter, not an active enemy
simulation. On a hit the shared captured-actor HP
changes; unsupported equipment, actor types and state paths refuse.

SELECT enters an explicitly assisted debug placement mode. D-pad moves a red
cursor one terrain cell, A requests placement, and B or SELECT cancels. The
same GameIL operation used by the spatial adapter checks the source terrain and
rectangle/slope model, bounds and camera conditions, then applies a target-only
camera recenter. It refuses unresolved collisions and out-of-domain state;
dynamic actor collision, original reachability, and cross-scene travel remain
unknown. This action is not ordinary physical movement.

The API `shadowrun_nes_play.build_play` takes an existing opening manifest,
ROM path, reviewed capture directory, cc65 root and a new private output
location. It verifies the exact ROM and captured frame identities and lifts
`shadowrun_play.lift_play` before compilation. The private output contains
source-derived state and must never be added to Git or a tool package.
`shadowrun_play.machine_from_capture` seeds the same GameIL composition for
spatial investigation. Neither a successful build nor a symbolic grid proves
runtime behavior.

Controlled original-core comparisons separately cover the item-44 dispatch
and the captured item-2 equipment/ammunition domain. The scripts
`scripts/check_shadowrun_play_armor.py` and
`scripts/check_shadowrun_play_weapon.py` reproduce those comparisons with
private inputs; they stop before the original UI routines. Ordinary menu
reachability and generalized equipment are not established by those controlled
entry tests. A separate unpatched original-controller route confirms the captured
weapon and armor unequip and re-equip effects, using two confirmations where the
target uses one. The linked encounter remains bounded to captured actor profiles
and source leaves; ordinary progression and dynamic enemy behavior are not established.

The finite no-target shot comparison at `scripts/check_shadowrun_play_shot.py`
checks source timer/latch samples, ammunition, RNG and eight projectile states
through terrain contact against actual FCEUmm output. Six held-A shots are
checked by `scripts/check_shadowrun_play_repeat.py`. Linked combat is checked
against the shared GameIL by `scripts/check_shadowrun_play_combat.py`; separate
prepared original-core probes qualify the source leaves and ordered collision.
A separate ordinary-controller LEFT, UP, B, A route reaches the first captured
NPC in both the original and target: selected identity, player position, ammo
and HP match at four sampled boundaries through two hits. The original NPC
moves and the target NPC remains frozen; the target also completes a third hit.
An uninstrumented original control matched all RAM bytes at 16 sampled frames.
These observations do not establish NPC AI, timing, or whole-game combat parity.
