# Shadowrun inventory and field-action leaves

These source-bound GameIL functions are small recovered operations for the
reviewed Genesis cartridge, not a complete inventory or combat system. The
Python entry points `lift_inventory(rom)` and `lift_combat(rom)` require the
exact reviewed 2 MiB ROM and bind the explicitly listed source ranges and
C authoring source. Neither includes game bytes. Callers must supply the
original context and persist the resulting fields themselves.

The inventory selector follows the source's 2-column, 4-row slot lookup at
`$12148..$12166`. Its public adapter refuses row or column outside that grid.
The armor leaf at `$1219C..$121C0` toggles the runner's armor byte and selected
slot phase. It assumes the original dispatcher has already chosen that branch;
it does not establish item legality, update other slots, or implement the
menu. Against the pinned Genesis core, controlled entry matched eight grid
positions and 768 isolated armor cases. See
[inventory evidence](evidence/shadowrun-full-2026-11-01/inventory.json).

The combat module exposes the same arithmetic leaf at command-screen source
locations `$12D46` and `$12DD2` and field-action location `$55C80`. It takes a
skill byte and a caller-provided nonnegative baseline and computes the source
statistic. It does not provide the earlier helper results or the subsequent
action effects. Its posture leaf models only legal 0..4 values and steps -1,
0, +1 from `$11AE4..$11B0E` and refuses other inputs. Rendering and follow-up
recalculation are separate. Controlled original-core entry matched 1,536
cases for each command stat leaf and all 15 legal posture changes; see
[stat and posture evidence](evidence/shadowrun-full-2026-11-01/combat.json).

A second bounded field-action leaf at `$559CE..$559F4` adjusts an existing
value with two supplied bytes and can take the original early return. Its
public interface restricts the two byte inputs to 0..127 and the initial
value to 1..10; out-of-domain values are refused. The high-level meanings of
these inputs and their connection to damage remain unproven. A fresh controlled
original-core test covered 1,536 field-stat cases and 1,152 effect-gate cases;
see [field-action evidence](evidence/shadowrun-full-2026-11-01/field-combat.json).
Controlled entry is not a natural gameplay route or an NES integration test.

The field hit-point leaf at `$55A62..$55A9E` applies a previously computed
positive damage value to one of two actor bytes, with the source's bit-7
one-point override, selector reset and zero clamp. It stops before the
zero-health continuation; its caller must establish the actor branch and
supply the incoming damage. Controlled original-core entry matched 1,536 cases
across both health bytes, representative damage amounts, the flag and every
initial byte value 0..127. See [hit-point evidence](evidence/shadowrun-full-2026-11-01/hp.json).

These leaves do not implement targeting, firing, hit detection, damage
calculation, zero-health consequences, ammunition, enemy AI, full inventory
actions, or save/load. They do not establish
whole-game recovery or parity. Private ROMs and native trace payloads remain
outside the repository.
