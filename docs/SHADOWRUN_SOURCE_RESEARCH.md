# Shadow Run Genesis opening area: source research

## Scope

This note identifies a candidate opening area and its source-resource path for the private USA Genesis target. It separates local ROM structure checks from claims made by a third-party reconstruction project. This pass did not run the original game; original-runtime probes and visual comparisons remain separate qualification steps.

## Target identity and structure

The selected private file is 2 MiB and has SHA-256 `92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e`, SHA-1 `A06A281D39E845BFF446A541B2FF48E1D93143C2`, and CRC-32 `FBB92909`. The Genesis header declares `SHADOWRUN`, product `GM MK-1352 -00`, region `U`. Its stored checksum `0x6BAF` matches the checksum computed over `0x200..0x1FFFFF`.

The SHA-1 and CRC-32 match the USA identity listed in the README of [shadowrun-defragged](https://github.com/benfoxworthy/shadowrun-defragged/blob/main/README.md). This confirms a byte-identity match with that project's declaration, not publisher authenticity, ownership, or reuse rights.

Local read-only inspection resolved scene-table entry 2 at `0x323A` to profile `0x172C80`. That profile's collision and event pointers at `0x172CA6` and `0x172CCE` resolve to `0x172DAA` and `0x172CDC`. The local record reads agree with the pinned reconstruction's field-map tables: scene-2 records 89/90 use collision value `0x00C0`; record 91 at `0x173138` has bounds x `0x03C0..0x03DF`, y `0x0280..0x029F`, and value `0x00C2`; record 92 at `0x173142` uses `0x00CB`. Scene-2 event row 0 is `0x14`.

These are numeric structure facts. They do not by themselves identify the scene's story location or prove how the original runtime renders or processes it.

## Candidate opening path from the reconstruction source

The source project describes the flow as title/start options, character archetype choice, a timed opening sequence, then field scene ID 2. It identifies the three protagonist archetypes as Samurai, Decker, and Gator Shaman, and describes copying a selected `0x100`-byte template into the live record at `0xFF0100`. Its opening-sequence notes identify routines around `0x59C5E`, `0x59D7C`, `0x5AA96`, `0x5AD1A` and tables `0x5ADD0`/`0x5ADF0`.

The source project calls scene 2 the Redmond Barrens startup map by cross-referencing trigger coordinates against a separate public map. “Redmond Barrens” is therefore a source-project map crosswalk, not a label recovered from the ROM scene table. The project also reports a Stoker arrival dialogue override at record 91 during post-opening warmup, and an Ares service override at record 92. These sequence and interaction claims come from that project's source/conversion notes; this pass did not independently observe them on the original cartridge.

The project describes scene 2 as a set of separately decoded terrain layers, stream/descriptor data, collision rectangles, event rows, and actors—not a single full-screen bitmap. Its asset inventory names these extracted paths:

- `decompilation/assets/records/field/scenes/scene-02/terrain-layer-a.bin`
- `decompilation/assets/records/field/scenes/scene-02/terrain-layer-b.bin`
- `decompilation/assets/records/field/scenes/scene-02/terrain-stream.bin`
- `decompilation/assets/records/field/scenes/scene-02/descriptor.bin`
- `decompilation/assets/records/field/scenes/scene-02/terrain-collision-rectangles.bin`
- `decompilation/assets/records/field/scenes/scene-02/event-table.bin`

Relevant source notes identify profile-selection data near `0x3232`, field profile/resource paths around `0x03074`, `0x03084`, and `0x0313A`, terrain stream decoding around `0x01610`, and collision iteration around `0x0EE10`. These addresses and resource paths are research leads, not a complete decoder qualification.

## Typed movement source and reuse boundary

The same pinned repository contains typed C++ conversion code for movement. Its header `decompilation/ghidra_conversion/include/shadowrun_ghidra/field/field_movement_input_conversion.hpp` documents ROM routines `0x0BABC` and `0x195C/0x19D2`; implementation is in `decompilation/ghidra_conversion/src/field/field_movement_input_conversion.cpp`. The documented conversion rotates a heading to an eight-way movement ordinal and decodes a normalized D-pad nibble, including invalid/opposing combinations.

The reconstruction's status table cross-references `0xB530` to `gameplay/scripts/actor_ai.lua`'s `approach_heading`; the Lua step advances a 16-bit heading by `0x0800` and snaps when within one step. Its typed C++ reference implementation is `decompilation/ghidra_conversion/src/entities/entity_coordinate_conversion.cpp` (`approach_entity_fixed_point_target`). The project marks related movement conversion as partial and leaves NPC collision-route behavior open. Typed portable code is useful source assistance, but its presence does not establish full original-flow coverage or equivalence.

Pinned source links:

- [Field movement input header](https://github.com/adamaxis/srx/blob/bfa3908a26952cf0fbdb682dab1ee1ec5ba19e3b/decompilation/ghidra_conversion/include/shadowrun_ghidra/field/field_movement_input_conversion.hpp)
- [Field movement input implementation](https://github.com/adamaxis/srx/blob/bfa3908a26952cf0fbdb682dab1ee1ec5ba19e3b/decompilation/ghidra_conversion/src/field/field_movement_input_conversion.cpp)
- [Typed entity-coordinate helper](https://github.com/adamaxis/srx/blob/bfa3908a26952cf0fbdb682dab1ee1ec5ba19e3b/decompilation/ghidra_conversion/src/entities/entity_coordinate_conversion.cpp)
- [Actor heading script](https://github.com/adamaxis/srx/blob/bfa3908a26952cf0fbdb682dab1ee1ec5ba19e3b/gameplay/scripts/actor_ai.lua)
- [Native audit and completeness limits](https://github.com/adamaxis/srx/blob/bfa3908a26952cf0fbdb682dab1ee1ec5ba19e3b/decompilation/docs/rom-native-audit.md)

The inspected pinned repository has no root `LICENSE` file and its GitHub license endpoint returned 404. Do not assume its code or extracted/derived game assets are licensed for reuse. Only text documentation was retrieved into private research storage for this investigation. No ROM, asset, patch, or external code was added to this repository.

## Qualification boundary

The independent local checks here establish the selected file's identity/header/checksum and the listed numeric pointers/records. They do not establish publisher authenticity or rights. The third-party project is a partial conversion/reconstruction; its own audit reports unresolved/partial routines. The Redmond Barrens label and opening sequence are source-reported, with the map label specifically based on an external coordinate crosswalk.

Scene 2 is a reasonable first target for a playable-area reconstruction because the source identifies it as the first field scene and the local ROM confirms its profile and event/collision structures. Before claiming fidelity, compare the original runtime's scene entry, movement, collision, actors, and first interactions against a source-bound reconstruction. No such original-runtime or visual parity result is claimed by this note.

Machine-readable identity and evidence details: [`source-research.json`](evidence/shadowrun-uil-2026-11-01/source-research.json).
