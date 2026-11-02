# Shadowrun full-game NES recovery: progress and open work

The full-game conversion is **incomplete**. This increment adds permanent,
source-bound UIL components for inventory, combat arithmetic, dialogue and
animation, a scene/resource reader and decompressor, a reusable native NES
component checker, and a separate animated walking experiment. It does not
turn the opening cartridge into a complete Shadowrun game. The earlier
[courtyard and Stoker profile](SHADOWRUN_UIL_OPENING.md) remains available.

All results use the reviewed USA Genesis cartridge with SHA-256
`92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e`.
Keep that cartridge, captured imagery/audio, states, exported bundles and all
generated NES cartridges private and outside Git.

## Reusable component route

`shadowrun-systems` reports the component catalog and whole-game exclusions.
`shadowrun-system-export` lifts one registered component into typed GameIL;
`shadowrun-system-inspect` checks a private export without compiling it.

```sh
fdisbull shadowrun-systems
fdisbull shadowrun-system-export /private/Shadowrun-Genesis.bin \
  --system inventory --output /private/new-inventory-uil
fdisbull shadowrun-system-inspect /private/new-inventory-uil/manifest.json
fdisbull shadowrun-system-build-check /private/new-inventory-uil/manifest.json \
  --rom /private/Shadowrun-Genesis.bin \
  --procedure shadowrun_inventory_armor_branch \
  --cases /private/inventory-cases.json --cc65-root /private/cc65 \
  --output /private/new-inventory-check
```

The case document contains `states` (a finite list of scalar state objects)
and `watch` (scalar output names). Each case resets the complete component to
its declared initial state. The registered zero-argument procedure then runs
in the UIL reference and in compiled 6502 code. This headless NES cartridge is
a conformance instrument; it has no game menu or playable combat.

`scripts/check_shadowrun_system_nes.py` requires the original ROM, case
document and explicit cc65 toolchain again. It recreates the source lift,
reference outputs and executable before accepting the existing check image.
Its FCEUmm run requires every ordered case, coherent publication epochs and a
final completion marker. Metadata changes, reordered/missing results and
incorrect outputs fail. This keeps original-code fidelity, UIL semantics and
native target execution as separate checks.

## Current evidence

| Area | New result | Remaining game behavior |
| --- | --- | --- |
| Inventory | Eight grid positions and 768 armor-toggle cases match controlled original CPU execution. | Menu, item legality, other slots, use/buy/sell/drop and persistence. |
| Combat | Stat leaves, posture, an intermediate action gate and health application match the original across 7,311 cases. Includes the one-point flag override, alternate health byte, selector reset and zero clamp. | Targeting, firing, hit detection, damage calculation, ammunition, enemy AI and zero-health consequences. |
| Dialogue | 41 controlled cases cover real prompt priority, synthetic three-choice and terminal boundaries, payment, and two flag commands. Other commands refuse. | Complete text/UI interpreter, all command effects, NPC logic and quest progression. |
| World/resources | Reads 56 scene references, 54 unique profiles, 5,163 scene-reference collision rows and ten event tables. Decoder matches complete scene-0 and scene-2 candidate streams: 13,568 and 20,288 bytes. | Ordinary loader linkage through intermediate state, world transitions, terrain streaming/rendering and all scenes. |
| Animation | Source counter 96 cases, wrap 32 and heading selector 32 match controlled original execution. Separate NES probe matches 60 original walk updates and projected actor OAM; seven target poses checked. | Other directions, release/idle, actions, actors, scenes and general animation dispatch. |
| Audio | Observed 137 YM2612 writes over a finite source interval; instrumented/uninstrumented audio and final frame agree. | Music driver, sequence format, sound effects, NES arrangement and runtime audio. NES remains silent. |

The inventory and combat total is 8,087 controlled original-CPU cases.
Controlled entry seeds RAM/registers to isolate a source routine; it does not
show natural gameplay reachability. Scene streams are also tested through
controlled decompressor entry. The native probe needed a 32 KiB total watch
budget and a 200,000-instruction per-case ceiling to observe scene 2; its
112,567 executed instructions exceeded the former 100,000 ceiling. All
budgets remain finite, with the existing combined batch ceiling retained.

Separately, 17 FCEUmm conformance runs compare **3,590** compiled component
cases with the UIL reference, with zero differences. Their cases and the
original controlled-entry cases have separate denominators. Passing these
tests does not establish a composed game loop or whole-game equivalence.

## Animated NES experiment

```sh
fdisbull shadowrun-opening-animation-build \
  /private/opening-bundle/manifest.json \
  --rom /private/Shadowrun-Genesis.bin \
  --capture /private/reviewed-right-walk-capture \
  --cc65-root /private/cc65 --output /private/new-animated-opening
```

The wrapper requires the reviewed opening bundle, exact source-associated
capture, canonical source lift and independently pinned atlas payloads. The
backend emits the source counter from GameIL, uses the recovered heading
selector and source descriptor anchors, and switches seven private projected
pose banks through CNROM. It executes ordinary RIGHT input rather than
replaying the captured input timeline. The prepared starting state and its
finite pose coverage remain explicit.

The first 60 completed updates match original player position, heading, camera,
animation phase/index, pose and projected actor OAM. Seven sampled screenshots
cover 2,737 nontransparent actor pixels with no target-palette inconsistencies.
This is a reduced-color NES projection, not Genesis pixel parity. The probe
takes about two physical frames per update. It refuses UP and release, and
stops after 60 right updates instead of extrapolating unobserved behavior.
It is separate from the more interactive, frozen-pose courtyard build.

## Methodology and next dependencies

Disassemble the exact original routine; declare integer widths, storage,
inputs, admitted branches and stopping PCs; independently transcribe that
bounded behavior into typed C; lower it to GameIL; compare against controlled
original CPU execution; then compile and compare native target outputs. Use
ordinary controller traces where claiming scene or animation behavior. Record
assisted setup, unsupported branches, timing losses and target adaptations
alongside each result. Original chip observations do not establish a recovered
sound driver, and table inventories do not establish playable locations.

Full-game acceptance still requires the missing dispatchers and complete
world/actor loop, playable inventory and combat, all dialogue effects and
missions, Matrix gameplay, animations, audio, saves and endings. Those must be
integrated into a banked target with an explicit NES memory and timing plan,
then compared against original progression and negative/failure paths. No
percentage-complete estimate follows from the current component counts.

Detailed boundaries: [combat/inventory](SHADOWRUN_COMBAT_INVENTORY.md),
[dialogue/world](SHADOWRUN_DIALOGUE_WORLD.md),
[animation/audio](SHADOWRUN_ANIMATION_AUDIO.md). Sanitized evidence lives under
`docs/evidence/shadowrun-full-2026-11-01/`; raw runs and media remain private.

The focused source regression passed 119 tests and distribution checks passed
341 tests. The broad macOS run finished with 3,180 passed, 142 skipped,
4 failed and 23 errors. Twenty-six failure/error names match the previous
platform baseline. The additional failure was an OS “no space left” error while
writing a test transcript; that case passed in isolation with external-volume
temporary storage. The broad run remains non-green; its counts are retained
rather than rewritten after the rerun. Source/test/helper bytes were unchanged
through that run. Package and hosted review qualification are recorded
separately in the local PR registry.
