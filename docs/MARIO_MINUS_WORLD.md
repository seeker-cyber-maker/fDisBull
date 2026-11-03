# Investigating the minus-world warp

The familiar “World -1” screen can be explained by an ordinary unsigned table
lookup in Super Mario Bros. The issue investigated here is specific to the
supplied Super Mario Bros. + Duck Hunt mapper-66 cartridge (SHA-256
`23ec3f6bb68f8774070ce936869e7f62ac3490449f58e62d6ed33a0fb385d456`).
The runtime and mapped code windows were checked against that exact image;
the source identity is not a claim about publisher authenticity.

The player can reach warp pipes before the usual warp-zone setup is complete.
The pipe routine masks the warp-control byte, uses the result and Mario's
horizontal position to select a table entry, subtracts one, and stores the
result as the internal world number. In the observed left-pipe path, the
game-generated stale control value `1` selects entry 4, containing
`$24` (36). The native code subtracts one and stores `$23` (35). The display
adds one back, using `$24` as a graphics tile; that tile is blank, making the
number look like “-1” rather than displaying a negative integer.

The actual pinned FCEUmm run captured this sequence in the mapped program:

| Native PC | Observation |
|---|---|
| `$DF22` | Read `$24` at `$87F6`, table index 4. |
| `$DF26` | Store `$23` to world index `$075F`. |
| `$DF29` | Read `$33` at `$9CD7`, past the eight intended world offsets. |
| `$DF2C` | Read `$01` at `$9CEF` as the resulting area pointer. |
| `$DF2F` | Store `$01` to `$0750`. |

With the same player placement and ordinary pipe input, the comparison run
left the game's own control value `4` in place. It selected table entry 0,
stored world index `3` and area `$22`, corresponding to the intended world-4
route. In the stale-control run the observed display showed `WORLD -1`, then
an underwater scene. Hooked and unhooked paired runs matched their final
serialized state, RAM, display, and RAM trace hashes.

**Scope of the reproduction:** one continuous run starts from boot with an
assisted world-1-2 page-9 checkpoint and a later large-Mario seed. Thereafter,
controller input alone causes the original game to set warp control from `0`
to `1` at PC `$B7B2` (frame 1048), takes Mario through the upper wall into the
warp room, and enters the left pipe. The game stores world `$23` and area `$01`
at frame 1421; the `WORLD -1` screen appears at frame 1500 and the underwater
scene by frame 1900. No player position, warp-control, world or area-pointer
patch occurs in this connected path. A matching unhooked run confirms the
observer did not change its final state, RAM, display, or RAM trace.

A separate pipe-level experiment positions Mario at the left pipe and seeds
control `1`; the comparison leaves the naturally initialized control `4`.
Both directly exercise the original pipe routine, but their positions and the
experimental control value are assisted. These experiments isolate the table
selection from the earlier wall movement.

A further diagnostic starts from the connected minus-world route, then uses an
additional page-11 checkpoint and position seed to reach the underwater exit
pipe. The original game enters the pipe and reinitializes world `$23`, area
number `0`, and area pointer `$01`; it returns to page 0 of the same underwater
area. That is one observed assisted return, not a proof of infinite repetition
or an unassisted swim through the entire level. Screenshots, inputs, and
captured game bytes remain private.

The independently published [annotated disassembly](https://6502disassembly.com/nes-smb/SuperMarioBros.html)
provides the corresponding labeled routine and table. Its address-level
explanation was checked against short hash-bound code windows and the actual
CPU read/write events for this combined cartridge; it should not be treated as
a proof for arbitrary ROM revisions. The compact numerical observations and
limits are recorded in [verification.json](evidence/mario-minus-world-2026-11-01/verification.json).
