# Genesis to NES research handoff

Status: preserved research branch, **possible for qualified bounded slices but
not recommended as the primary Genesis reconstruction target**. The user chose
native macOS ARM64 as the next output on 2026-11-01. Keep the Genesis input,
recovered procedural UIL, source comparisons and reusable analysis modules.

## Frozen result

The qualified implementation is commit
`46e331aa794bbecc9981fb652362cc59466a4594`. Its assisted Shadowrun moving preset
matches 101 consecutive original frames plus two checkpoints. The MMC3 output
matches 124 completed model updates before an unpublished unsupported attempt.
The stationary output matches 243 updates to source-confirmed HP0; held fire
matches 165 completed updates and terminal START reset was tested separately.
This is source-constructed scene 2, not a naturally reached encounter or a
whole-game conversion. Other actors retain unknown current state when unmodeled.

See [the experiment](SHADOWRUN_AI_EXPERIMENT.md) and
[hash-bound evidence](evidence/shadowrun-ai-2026-11-01/nes.json). The earlier
Miniplanets work and console/compiler modules remain available in this history.
Original inputs, generated cartridges, states, assets and raw traces are private.
Tool packages contain source and sanitized evidence only.

## Why park this output

Genesis-class game logic, graphics and audio require substantial adaptation to
the NES. The measured moving run spans physical frames 85–726 for 124 completed
updates; the stationary run spans 91–953 for 243. These are multiple display
frames per gameplay update, with symbolic graphics and explicit audio limits.
Procedure banking, a separate data bank and a faster table reader helped make
the experiment executable; they do not establish general real-time conversion.
An intermediate timing improvement used different program versions, so it is
not an isolated measurement of the reader optimization.

The NES output is native 6502 compilation of recovered UIL, not a Genesis CPU
emulator running inside an NES. There is no need to discard the source recovery
or UIL to choose a more capable output. A native ARM64 target removes NES bank,
memory and upload constraints; its speed and semantic correctness still require
measurement. It does not recover missing game behavior automatically.

## Resume contract

1. Start from the frozen commit and retained original/core/capture identities.
   Review the source, model, native and Z receipts separately. Do not convert
   passing sampled projections into whole-game or hardware parity.
2. Reproduce the private presets with `shadowrun-ai-build`, including the exact
   cartridge hashes and consumed logical input. Preserve failures and original
   frozen artifacts rather than replacing them.
3. Preserve hard boundaries: Z discards an unsupported candidate; NES retains
   its last completed publication and epoch, marks refusal and stops. Native
   interrupted internal state is unqualified. The moving source frontier is
   frame 6124; original death/story/scene continuations remain unknown.
4. Before pursuing faster NES output, select a concrete workload, unchanged
   semantics, useful frame budget and equal completed input workload. Include
   mapper/interrupt, display upload, arithmetic, audio and memory costs.
5. Keep research feasibility distinct from a recommendation. Reopen this lane
   when a better-matched input or a new measured lowering justifies its cost.

## Deferred research candidates

- Atari input to an NES multicart container: first select the Atari platform
  and actual cartridge/mapper. Separate translating a game's behavior from
  packaging multiple programs and selecting their banks. No compatibility or
  conversion claim is made yet.
- Sega Master System input: a distinct architecture and graphics/audio path;
  reuse parsing, input contracts and semantic checks, then qualify the selected
  game's hardware-dependent behavior. Do not assume CPU similarity alone makes
  it an NES conversion.

The next active lane is Genesis-source recovery → procedural UIL → native macOS
ARM64, initially reusing the bounded Shadowrun model and the same original
captures. The NES lane remains available for later research.
