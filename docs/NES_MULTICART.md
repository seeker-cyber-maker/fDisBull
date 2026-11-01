# NES multicart analysis and bounded packer

An NES multicart typically uses a mapper to choose which parts of a larger
program and graphics memory appear in the CPU and PPU address spaces. A menu
can select a bank and transfer control to a game's reset vector. The menu's
bank switch must run from RAM or from code visible in both banks, because
changing a program bank also changes the instructions at the current PC.

The examined “1200-in-1” image has an iNES mapper-227 header, 512 KiB of PRG
ROM and no CHR ROM (the core supplies CHR RAM). The pinned FCEUmm core's
[mapper-227 implementation](https://github.com/libretro/libretro-fceumm/blob/master/src/boards/addrlatch.c)
uses CPU write addresses to select PRG arrangements and mirroring. Two bounded
menu interactions launched distinguishable Bomber Man and Ice Climber title
screens; a passive write observer recorded different selection addresses and a
baseline run matched the observed run's final emulator state, screen, and RAM.
Three SELECT presses exposed four menu pages numbered 1–80. The labels include
numbered sets such as GAMBO 1/2/3 and RAGWEED 2/3; the labels alone do not
establish identical code or behavior. This is not evidence of 1,200 unique
games, and duplicate/variant counts are unknown. The 32 physical 16 KiB PRG chunks have different hashes; a chunk is
not necessarily a game. The Mario/Duck Hunt comparator instead declares mapper
66, with 64 KiB PRG and 16 KiB CHR ROM. The [FCEUmm mapper-66 implementation](https://github.com/libretro/libretro-fceumm/blob/master/src/boards/datalatch.c)
models a different banking scheme.

`fdisbull.nes_multicart` is a **post-compilation packaging prototype** with a
separate, explicitly narrower mapper-225 design. It does not lift game rules,
convert mapper 227 or 66, or establish compatibility with the original samples.
The [FCEUmm mapper-225 implementation](https://github.com/libretro/libretro-fceumm/blob/master/src/boards/225.c)
shows address-selected PRG and CHR banks and reset behavior used by the
prototype. The output contains a simple A/B selection menu, waits for those
buttons to be released, switches both banks from a RAM trampoline, and jumps
through the selected game's reset vector. FCEUmm's reset returned to the menu
in the bounded test; reset behavior on physical hardware remains unverified.

The `build_multicart(inputs, *, output, authored_compatible=True)` API accepts
exactly two explicitly attested authored iNES mapper-0 images with 32 KiB PRG,
8 KiB CHR ROM, matching horizontal or vertical mirroring, and no trainer,
battery, four-screen layout, or other header extension. The caller must also
attest that the games neither write to `$8000-$FFFF` nor require cartridge
RAM: mapper 225 handles those addresses differently from NROM, and that behavior
cannot be determined from an iNES header. Inputs are checked unchanged; output
is a new private `program.nes` and hash-bound `manifest.json` outside Git.
`multicart_profiles()` describes the supported profile, and
`inspect_multicart_path(path)` reports bounded header facts without identifying
or counting games.

The pinned FCEUmm qualification selected each of two synthetic cartridges,
observed 44 NMI callbacks from each, and reset from the first to the menu and
then selected the second. A separate pair of UIL-generated NROM cartridges
matched their standalone runs for 100 game ticks each, comparing controller
input and two game-state values under a bounded input sequence. The menu pixels
matched before and after reset in that core. The evidence is in
[verification.json](evidence/nes-multicart-2026-10-31/verification.json).
Real cartridge hardware, additional games and mappers, complete game behavior,
CHR-RAM games, and broad portability are not qualified by these tests.
