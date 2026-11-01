# Shadowrun prompt and field profile readers

These bounded readers use the privately supplied, byte-identified US Genesis
cartridge. They retain numeric references rather than exporting text, graphics,
or other original assets. The hash is an identity check, not an authenticity or
rights claim.

`fdisbull.shadowrun_dialogue.read_prompt(rom, address)` parses the prompt record
consumed by the original 68000 routine at `0x1F3C4`: a title pointer, a first
option pointer, optional second and third option pointers, and one 32-bit target
per present option. A negative first option is a terminal page. `select_prompt`
returns `wait`, `terminal`, `command`, or `record`; command values are opaque
and their effects are not implemented. It uses the original A, B, C priority and
refuses negative targets. It does not decode text, draw the panel, model timing,
run command handlers, or connect a dialogue to the NES target.

`lift_dialogue(rom)` provides a source-bound typed GameIL version of the
selection step. The caller supplies the parsed option count and targets; the
model returns an opaque command or next-record reference. Unsupported negative
targets are refused rather than dispatched.

For the source-bound Stoker arrival and manager records, controlled entry on the
Genesis Plus GX original 68000 core at `0x1F522` matched GameIL for all
eight combinations of the three buttons per record, 16 cases total. The
private receipt and contract preserve this evidence. This check does not prove
ordinary reachability, third-option handling, timing, text display, or command
side effects. Existing ordinary-input evidence for the opening remains described
in [the interaction note](SHADOWRUN_INTERACTION.md).

`fdisbull.shadowrun_world.read_scene(rom, scene_id)` verifies the source hash
and reads the 56-entry table at `0x3232`, the 0x60-byte scene profile copied by
`0x3084`, terrain pointers consumed by `0x313A`, collision rectangles and an
optional event table. The record preserves raw words, including unusual bounds,
without assigning destinations or game meaning. Source readback found 56 scene
references, 54 distinct profile addresses, 5,163 collision rows and 10 present
event tables. Scene 2's record 91 and event row 0 agree with the independently
documented values in [source research](SHADOWRUN_SOURCE_RESEARCH.md). These
are static source facts, not proof that every scene can be entered, rendered or
played; event table entries may be bypassed by other dispatcher branches.

The check can be reproduced with `scripts/check_shadowrun_dialogue_world.py`
using `--rom`, `--core`, and a new private `--output` directory.

The typed dialogue model also includes the source payment leaf at `0x21458`:
it subtracts the byte charge from the 32-bit wallet, selects a failure response
and preserves both fields when the result's sign bit is set; otherwise it stores
the result, changes the charge byte to `0xFF` and selects the success response.
Six controlled original-core cases matched GameIL, including exact funds and an
insufficient balance. This leaf does not establish how a charge is chosen or
whether a player reached the command.

Controlled original-core checks also exercised all eight button combinations
with a synthetic three-choice RAM record and checked three negative/nonnegative
terminal-pointer cases. These are assisted boundary checks, not ordinary play.

`decode_stream` implements the byte decompressor at `0x1610` with explicit
output bounds and invalid-reference refusal. `decode_scene_stream` selects a
flagged source candidate from the profile's `+0x18` field. The original loader
copies that field into its cursor and the conditional path at `0x29FC` calls
the decompressor; intervening runtime mutation is not ruled out. A controlled
original-core entry matched all 13,568 output bytes of scene 0's candidate
stream, in addition to a synthetic literal/run/overlap case. A second controlled original-core entry matched all 20,288 decoded bytes
of scene 2, with 112,567 instructions executed. The probe permits at most
32 KiB of watched RAM, with a 4 KiB per-watch limit and finite instruction
and cycle budgets. Neither result demonstrates scene rendering or
complete world recovery. Keep returned bytes private.

`scripts/check_shadowrun_dialogue_extra.py` reproduces the assisted three-choice,
terminal, payment and decompression checks with the same private arguments.

The typed dispatcher supports three identified command leaves. Command `0x06`
uses the payment leaf; `0x30` sets bit 1 of the source long flag at `FFFC30`;
`0x31` sets bit 0 of the source byte flag at `FFFC27`. Each returns its source
next-record reference. Four controlled initial values per flag matched the
original processor, including already-set bits. Other command numbers are
explicitly unsupported; no general conversation coverage is claimed.

The fresh [qualification receipt](evidence/shadowrun-full-2026-11-01/dialogue-world-qualification.json)
binds the model, authoring source, GameIL engine, comparison script, probe,
ROM and core identities, along with the per-boundary contract and trace hashes.
