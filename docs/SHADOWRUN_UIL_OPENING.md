# Shadowrun Genesis opening to NES replay

This profile exports and rebuilds one bounded, assisted opening slice for the
exact reviewed Shadowrun Genesis cartridge. It combines authored GameIL for
opening movement and the guarded Stoker request/UI projection with one
provenance-bound Genesis RAM/VDP snapshot and one bounded observed atlas. It is
not whole-game recovery, original NES pixel parity, or automatic support for
other ROMs.

Keep the original ROM, capture directories, atlas assets, exported bundle and
generated NES output in private directories outside Git. Export does not run a
compiler. The capture must be a `native/scene-NNNNNN` directory whose parent
capture receipt binds that frame, ROM, core and exact RAM/VDP array hashes. The
atlas index must bind the same source identities and the selected snapshot.
The exported bundle contains no ROM; it contains the authored GameIL, captured
RAM/VDP arrays, and separate VDP-reconstructed and screenshot-validated atlas
layers.

```sh
fdisbull shadowrun-opening-profiles

fdisbull shadowrun-opening-export /private/Shadowrun-Genesis.bin \
  --snapshot /private/capture/native/scene-005999 \
  --atlas /private/opening-world-assets-07/index.json \
  --output /private/new-shadowrun-opening-bundle

fdisbull shadowrun-opening-inspect \
  /private/new-shadowrun-opening-bundle/manifest.json

fdisbull shadowrun-opening-build \
  /private/new-shadowrun-opening-bundle/manifest.json \
  --rom /private/Shadowrun-Genesis.bin \
  --cc65-root /private/cc65 \
  --output /private/new-shadowrun-opening-nes
```

The standard `console-udc` entry point accepts the same bundle manifest:

```sh
fdisbull console-udc \
  /private/new-shadowrun-opening-bundle/manifest.json \
  --target nes --region /private/Shadowrun-Genesis.bin \
  --cc65-root /private/cc65 \
  --output /private/new-shadowrun-opening-nes
```

Build verifies every fixed bundle payload, checks the supplied ROM identity,
re-lifts the current source and requires canonical GameIL equality before it
invokes the registered NES opening-atlas backend. Bundle paths do not select
tools or source files. `inspect` validates payload hashes and the GameIL
structure without running a compiler or treating the bundle's claims as native
execution evidence. A target build is still an assisted projection with a
captured scene and camera; it does not reproduce the original Genesis dialogue
engine or establish general gameplay parity. See `docs/SHADOWRUN_INTERACTION.md`
for the bounded Stoker interaction contract and the Shadowrun evidence folder
for source-bound capture and asset qualification records.

The tested NES milestone supports D-pad movement, turning and the recovered
wall-slide/stop paths within the captured courtyard. Approaching the Stoker
door with UP triggers the guarded request; there is no invented generic
interaction button. A continues the sign, B leaves the manager conversation,
and A closes the farewell. Release the button to return to the field. The
screen stays black during a bounded reentry while the camera reaches an
observed view; input is suppressed during that transition. Other conversation
choices display a refusal. Field actions such as firing, inventory, audio and
travel to other areas are outside this profile.

## Recovered logic and target adaptations

This experiment manually transcribes reviewed original-code slices into typed
procedural C and lowers them to GameIL. It does not run an automatic whole-ROM
decompiler. Input sampling, source direction selection, heading changes, player
vector selection, terrain/rectangle/slope collision, wall fallback and normal
camera follow are qualified at their own original-68000 boundaries. The final
NES backend emits C from the composed GameIL and compiles it to actual 6502
instructions with the separately prepared cc65 toolchain.

The Stoker request additionally needs the observed context, phase, collision
corners, actor/latch conditions and an explicitly supplied carry-set result
from an opaque original activity dispatcher. The authored NES sign, manager,
farewell and exit/reentry are target projections of an observed path. They do
not recover the general original dialogue or scene-reload interpreter.

Native VDP plane maps and linked sprite patterns are decoded separately.
Same-frame original raster checks established the horizontal-scroll sign and
the render-camera phase. Views are registered in absolute world coordinates;
the physical VDP ring coordinates alias different world rows. That correction
removed 11,414 false conflicts. The final private atlas combines 180 visible
field captures into a 512×480 rectangle at world origin `(768,512)`, with
116,808 known pixels and no conflicts. The decoder matched all 10,481,664
eligible background pixels and 71,042 nontransparent actor pixels against the
original screenshots. These counts qualify Genesis asset decoding; the NES
uses a reduced palette, one frozen actor pose and a 256×224 viewport. It does
not reproduce the original pixels. Unknown coverage is refused rather than
turned into terrain.

## Original and NES comparison

The original uses the pinned Genesis Plus GX core and the exact 2 MiB source
cartridge. The target uses the pinned FCEUmm core. The NES starts from the
captured free-play state at original frame 5999; it does not reproduce the
opening menus or the entire original boot sequence. Runtime input is then
ordinary controller input, with no RAM patches or state restores in the
canonical target route.

| Check | Result | Timing boundary |
| --- | --- | --- |
| Right walk | 60/60 states, nine fields, zero differences | One matched update per physical frame. |
| Left walk | 60/60 states, nine fields, zero differences | One matched update per physical frame. |
| Approach to door | 38/38 states, nine fields, zero differences | Compare completed logical ticks; collision work misses physical deadlines. |
| Door request | Nine fields match the original event | NES event frame 556, eight physical frames later than the nominal frame 548. |
| Conversation and return | Sign → A → manager → B → farewell → A → field | Authored target UI and exit/reentry projection. |
| Extended native replay | 1,080 frames, no ROM or coverage faults | Field settles at observed camera `(848,624)`. |

The nine compared values are player X/Y, heading, sampled input, direction,
camera X/Y and plane-A scroll X/Y. The final seven pre-event UP updates take
two physical frames each; that slowdown remains visible in the evidence. No
universal 60 fps, realtime equivalence, vblank safety or physical-console
stability claim follows from these emulator runs.

The normal reentry lasts 14 completed ticks in this target. A separate
assisted negative control freezes the camera, reaches the 240-tick failure
bound and preserves the failure latch. Its RAM patch is kept separate from
the unpatched canonical route. A second run verifies that unsupported manager
choices display a refusal, and a control-injection run verifies that movement
input during black reentry does not change the published state.

The final private NES image is 40,976 bytes, SHA-256
`b51b7cc71b101db990deb1a2ac3ed9dc147fc2651a9a651a0dfd91047efed0da`.
Dedicated replay and standard `console-udc` builds produce those same bytes
from canonical GameIL
`1f52ee3427862239d8c9ddf4d658ee695222aee95300bfb290da5038daa90cf9`.
Source hashes and private receipt hashes are recorded in
[verification.json](evidence/shadowrun-uil-2026-11-01/verification.json);
[camera.json](evidence/shadowrun-uil-2026-11-01/camera.json),
[assets.json](evidence/shadowrun-uil-2026-11-01/assets.json) and
[interaction.json](evidence/shadowrun-uil-2026-11-01/interaction.json) preserve
the separate component contracts.

The reusable route checker now requires source/target receipts, cartridge and
core identity, trace hashes, source snapshot hashes, complete input schedules
and zero runtime patches. Odd publication sequences, duplicate frames and
missing completed ticks fail the check. This is finite experimental evidence
for the listed boundary, not a proof for all inputs or a whole-game semantic
equivalence result.

The final source suite completed with **3,064 passed, 142 skipped, 3 failed and
23 errors** on macOS. All 26 failure/error case names match the recorded
platform baseline, with no new names. This is not a green full-suite claim.
Distribution guards explicitly retain the authored modules, helpers, tests
and sanitized evidence while rejecting game binaries, states and databases.
