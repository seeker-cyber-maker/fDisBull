# Shadowrun SNES: bounded native movement transfer

This experiment transfers the **investigation process** from the Genesis work
to the separate SNES game. It recovers a bounded player-movement and collision
slice from the original SNES ROM, represents it as procedural UIL, and compiles
it to a real ARM64 library and a private Mac app. It does not translate the
Genesis game's rules into the SNES game or establish a complete SNES port.

The prepared scene is the opening morgue. The native app displays an authored
world-coordinate grid and player marker. Original camera transforms, artwork,
NPC behavior, dialogue, combat, animation, audio, menus and scene transitions
remain unqualified. The original runs use ordinary input without RAM patches;
the model starts from an explicitly captured state and static collision data.

## Identity and source edges

The supplied `Shadowrun.zip` has SHA-256
`2163a4ec63483b060094914df6c5570fe7e8eca5b96537ce937a4c4b88118a13`.
Its sole 1,048,576-byte member has SHA-256
`e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4`.
The calculated full-ROM checksum is `F834`, matching the stored checksum; its
complement is valid. These establish byte/header identity, not authenticity or
rights. The existing intake retained an archive rather than a raw `.sfc` at the
anticipated location; the exact member was reused privately.

The original execution backend is official
[libretro SNES9x at `fae2fea08f74180759ef540ee94259213f503480`](https://github.com/libretro/snes9x/tree/fae2fea08f74180759ef540ee94259213f503480),
built privately with the existing compiler. The baseline and a bounded observer
matched complete WRAM at six checkpoints and final RAM, save state and image
hashes on the selected route. The observer records instruction-entry context
and successful direct-mapped byte/word stores. DMA, MMIO and other shortcut
writes are excluded; this is bounded observer neutrality and coverage.

Recovered source dependencies include:

| Meaning | Source evidence |
| --- | --- |
| Player actor slot | Captured selector is byte index `0042` into word arrays |
| X/Y integration | Observed writers `80:AAD3` and `80:AB2A`, from routines beginning `80:AAC5` and `80:AB1C` |
| Direction and velocity | `80:DE91–DEB9`, source direction table `80:DF15`, velocity tables `80:DEF1/DF03`, rotation at `70:1FFD` |
| Collision | Axis-bound construction and `81:86E5` traversal of captured cell lists, linked nodes and six-field rectangles |
| Position representation | Source values are divided by four before collision-bound comparisons; original display scale is unqualified |

CPU writes use bank-`80` low-address WRAM mirrors, while captured WRAM is a
linear little-endian 128 KiB buffer. The source adapter explicitly composes
little-endian words. It does not reuse the Genesis core's byte-pair swapping.
The conservative reusable LoROM mapper accepts qualified low-bank upper-half
windows; high-bank mirror normalization in this recovery is a distinct,
source-observed mapping fact.

The frame-2999 WRAM hash is
`0032d4c7e01fce638a8ef653be6ab94871d7aa51ce48bb65d5d7b1444f791211`.
The save-RAM input hash is
`5eef00d9bf324987decb0aae450a28a73b8ceb2a61cdf5360440f41eddc97130`.
Save RAM was exported at the end of the source run; the rotation value used by
the model was separately observed in the frame-3000 CPU trace. It is not a
claim that the complete save-RAM image was captured at frame 2999.

## Replay and native output

`shadowrun_snes_field.machine_from_capture(rom, wram, save_ram)` validates those
identities and returns the source-specific GameMachine. Its
`shadowrun_snes_frame` entry consumes logical Up/Down/Left/Right bits `1/2/4/8`.
Cardinals, neutral, turns and release are qualified on the recorded routes;
chords and other buttons refuse. The source direction tables, captured
rotation and linked collision rectangles determine motion. Future original
coordinates are comparison evidence, never model inputs.

The model restricts coordinates to X `1356–1581` and Y `1795–2023`. Later
source LEFT/DOWN samples acquire actor-flag changes that have not been
recovered. Keeping the earlier domain avoids manufacturing those transitions;
the domain and static-geometry assumption do not establish every possible
trajectory inside that rectangle.

The shared Mac compiler now accepts an explicit source entry and verified
additional immutable regions. Region 0 remains the caller's hash-checked ROM;
region 1 is the captured collision data, embedded only in private output.
The eight-bit logical-input C ABI and default Genesis entry remain available.
Status 2 refuses a step and restores the complete native state. Typed UIL
arithmetic, loop/operation limits and transactional faults are retained.

```text
fdisbull shadowrun-snes-build \
  --rom /private/source.sfc \
  --ram /private/ram-002999.bin \
  --save-ram /private/save_ram.bin \
  --output /private/new-snes-study
```

The app starts paused. Space starts/pauses, arrows move, R resets, and Esc
closes. Unsupported inputs or states stop. `--snapshot` and comma-separated
`--pads` on the app executable render stored native state without operating a
GUI. Output includes the UIL document, seed, native source/header/library and
identity receipts. Builds contain private captured game data; none belong in
Git, releases or public packages. A requested 60 Hz host timer is not measured
display or whole-game timing parity.

## Comparisons and limits

| Check | Observed result |
| --- | --- |
| Short original routes | Neutral and four cardinals, 12 checkpoints each, six selected actor fields |
| Turn/release original route | 22 consecutive source frames matched |
| Longer holds | RIGHT and UP through 200 logical updates at sparse original checkpoints; earlier bounded LEFT/DOWN checkpoints retained |
| Withheld route | 61 native/UIL updates; six actor fields at 52 original checkpoints; no observed divergence |
| Complete native/UIL state | 896 element comparisons including seed and refusal controls |
| Unsupported chord | Two attempts each preserved the entire native state |
| Genesis compatibility | 52 prepared original frames, 190,320 native/UIL element comparisons, six original actor/HP fields per frame |
| Integrated focused suite | 131 passed before final broad verification |
| Full macOS suite | 3,894 passed, 142 skipped, 3 failed, 23 errors; the 26 non-green identities and types exactly match the recorded baseline |

One UIL actor update corresponds to one original `retro_run` frame in these
fixtures. Source snapshots are sampled after the zero-based frame. Neither
host wall-clock timing nor matching other actors follows from this comparison.
The selected six actor fields are position XYZ, velocity XY and actor flags;
full native/UIL state agreement is a different, stronger compiler-edge check.

Reproduce with `scripts/check_shadowrun_snes_field.py`,
`scripts/check_shadowrun_snes.py`, and `scripts/check_genesis_native_compat.py`.
The trace adapter refuses a different SNES9x revision or source anchor hash.
Clean tool packages carry the authored adapters. Sanitized comparison receipts
are retained in the repository review evidence; the ROM, private snapshots,
native app and embedded collision data stay in the private workspace.

The broad suite completed on CODEX after the initial 1.3 GB CACHE admission
failed and the user approved up to an additional 1.5 GB of bounded tests and
packages above the 20 GB minimum. Its 933-file production/test/script/config
inventory was unchanged during execution; documentation was excluded while
being authored. There were no unexpected or missing baseline failures. Final
package and exact-commit publication receipts are recorded in the local review.
No hosted CI, merge, release or global installation is claimed.

The final dependency was the official PyPI `capstone==5.0.9` wheel, verified
against PyPI's digest. Its distribution metadata is `5.0.9`, its upstream
Python `__version__` string is `5.0.7`, and its native API version is
`(5, 0, 1280)`. Record all three identities and the native-library hash rather
than inferring the installed distribution from one embedded version string.

## Observed friction and changes to the skill

1. **Intake location was mistaken for missing input.** The raw member was not
   where a filesystem search expected it. The existing archive identity was
   sufficient to recover the exact source privately. The guide now directs
   agents to the manifest and archive members before requesting the input again.
2. **An installed emulator did not provide the required observer.** OpenEmu's
   ARM64 SNES9x plugin had frame/state APIs but no public PC/write callback;
   the installed BSNES plugin was x86-only. A pinned private source build
   supplied the smallest useful observer, followed by baseline comparison.
3. **Advertised decoder modes were not usable modes.** Capstone exposes plain
   65816 mode but the tested native libraries reject its construction; setting
   it afterward also failed. The one-instruction adapter selects a working
   opposite width when M and X are both short, and verifies the instruction's
   actual immediate length. Synthetic tests cover all four combinations and
   the 12 width-dependent immediate opcodes. This qualifies the workaround,
   not a complete decompiler or general static processor-state analysis.
   The width requirements follow the
   [WDC processor specification](https://www.westerndesigncenter.com/wdc/documentation/w65c816s.pdf).
4. **Genesis assumptions leaked into a new edition.** Bank addresses, byte
   order and even the draft label “courtyard” were inappropriate. Stored SNES
   imagery establishes a morgue. Instruction-start PC, mode and memory mapping
   are now explicit investigation prerequisites; no related 6502 language is
   substituted for 65816.
5. **The operation's read set was larger than movement coordinates.** Rotation
   comes from save RAM and collision geometry from captured WRAM. The native
   backend's previous fixed entry and single-region requirement prevented a
   faithful representation. Explicit entries and identity-bound private regions
   remove that integration gap while preserving unsupported dynamics.
6. **Held input concealed release and later state transitions.** Press/release,
   turns and an independently withheld route exposed those questions cheaply.
   Later unknown flag changes remain a boundary rather than fabricated rules.
7. **Skill forward-testing caught a process/behavior mix-up.** A fresh Luna
   reader proposed comparing the two games' movement directly. The revised
   guide states that each model is judged against its own source edition;
   transferring a method does not require shared lineage or equal controls.

These decision rules live in the bundled
[`analysis-approach` reference](../src/fdisbull/skills/fdisbull-investigate/references/analysis-approach.md#transfer-an-investigation-to-another-target).
They say what observation to choose next and when to stop, while target facts
remain here. Skill retrieval and the skill-creator validator passed. The next
causal question is the writer of the additional actor-flag transitions and the
mutable collision/actor updates, before widening normal exploration.
