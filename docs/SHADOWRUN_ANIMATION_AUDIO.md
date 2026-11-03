# Shadowrun animation and audio investigation

This is a bounded source investigation and prepared-state NES experiment for
the exact reviewed Genesis source identified in `SHADOWRUN_UIL_OPENING.md`.
It does not implement full-game animation or audio. Private captures, generated
patterns, chip traces and source ROM remain outside Git.

The actor phase-counter slice at 68000 addresses `0x5fee..0x600c` adds the
actor's 16-bit increment at `+0x18` to its phase at `+0x1a`; a signed comparison
against the threshold at `+0x1c` controls incrementing the index at `+0x1e`,
setting bit zero of `+0x11`, and subtracting the threshold. The positive-count
selector slice at `0x6060..0x606c` resets an index at or beyond the signed
count. The authored C lifts these two slices to GameIL, separately from the
selector, mode changes, graphics upload and rendering.

Controlled execution in the pinned Genesis Plus GX core matched the GameIL
counter for 96 cases and positive-count index wrap for 32 cases, with no
mismatches. These are controlled component inputs, not a proof of game
reachability. In the existing ordinary-controller right-walk capture, phase and
index matched 60 successive transitions using captured increments, thresholds
and a declared count of four. This comparison excludes the following button
release and does not establish how the source selects those inputs.

The original walk selector at `0xb6ba..0xb6e2` chooses the actor's heading, or
its transition heading when the applicable flag is set, and uses a rotated
heading to index the source table at `0xc062`. A separate controlled comparison
matched all 32 tested heading and flag combinations. The source frame table at
`0x62ac` maps actor kind three to table `0x6378`.
The observed right-walk actor selectors and frame indices correspond to seven
distinct decoded SAT poses; source-table selection precedes the corresponding
captured sprite by one video frame in the 61 transitions tested. The extraction
API requires receipt-bound contiguous snapshots and exact source/core identities;
unknown selector/index combinations fail closed. Projected NES colors and
patterns are private reduced-color assets. The observed mappings do not qualify
other actors, directions, modes or game areas.

The separate right-walk NES experiment compiles the source-bound phase counter
through GameIL to 6502 code and uses the source heading selector. Seven private
projected poses occupy switchable CNROM CHR banks. Source frame records supply
the sprite anchor offsets, using the previous completed player/camera state to
match the observed one-frame display delay. The target holds the prepared state
until RIGHT, refuses other inputs or unobserved selector states, and stops at
60 right-walk updates. This is an assisted prepared-state experiment, not the
full NES opening profile or whole-game recovery.

On the pinned FCEUmm core, the final private cartridge matched 60/60 original
completed updates for player position, heading, camera position, animation
phase, index, pose and complete projected actor OAM. Seven target screenshots
covered all seven CHR banks; all 2,737 sampled nontransparent actor pixels were
consistent with their target CHR/OAM and three-color palette. These are target
checks, not Genesis pixel or palette equivalence. UP and button release each
triggered the input refusal; a continuous right walk reached the 60-update
observation limit. The target took approximately two physical frames per
logical update, so this is not a realtime or physical-console claim.

`scripts/check_shadowrun_nes_animation.py` rechecks the three controlled
Genesis receipts, the hash-bound capture and target run receipts, 60 state/OAM
comparisons, refusal controls, and seven target screenshots. It writes its
result only to a new private path; use `--help` for required private inputs.

A fresh sound-chip observer captured 137 YM2612 writes and no Z80 writes to
the observed PSG address `0x7f11` during source frames 5990–6060 of the same
input schedule. Other PSG access paths were not observed. Its captured WAV and final
RGB frame matched the uninstrumented capture byte for byte. This is a bounded
observer-neutrality check for that run, not a recovered music driver or a NES
arrangement. Neither the original audio sequence format nor the complete audio
command and timing semantics are established. No sound is synthesized from an
invented generic melody, and the existing NES opening remains silent until a
source-qualified target audio path is implemented and tested.
