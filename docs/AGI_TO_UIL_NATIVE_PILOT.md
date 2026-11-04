# AGI to UIL to native: PQ1 pilot

Status: **experimental draft**, 2026-11-04. This work is stacked on the experimental ScummVM AGI backend. It is not a release claim and does not publish original game files, messages, saves, screenshots, resource bytes or generated private projections.

## Goal and two deliberately separate lanes

The requested end state is a real target executable produced from recovered AGI behavior, not merely another launcher for the original DOS interpreter.

1. **AGI-only ScummVM Linux scaffold.** Build ScummVM v2.8.1 at the exact source identity already pinned by the fDisBull AGI backend, with every engine except AGI disabled. This gives a small native behavioral oracle and playable replacement interpreter. It still executes AGI bytecode at runtime, so it is **not** AGI-to-UIL compilation.
2. **AGI -> UDL/UIL -> UDC/native.** Parse original AGI resources, lift bytecode and conditions into explicit behavior contracts, replace engine services with typed UIL/provider boundaries, then lower the admitted graph to a native target. This is the compiler path that can eventually remove the AGI interpreter.

Do not collapse these lanes into one claim. The ScummVM lane can be useful and complete while the native compiler remains partial.

## Private-source PQ1 census

The held-out source was the owner-supplied Police Quest I EGA AGI release using the 2.917 interpreter profile. The target remained outside Git. fDisBull 0.31.1 parsed every present logic resource and resource layout without a layout error.

| Measure | Result |
| --- | ---: |
| Present/decoded LOGIC resources | 118 / 118 |
| Encoded instructions | 26,105 |
| Encoded conditions | 10,446 |
| Action/control instances already in the current strict direct-lowering vocabulary | 20,649 (79.10%) |
| Condition instances already in the strict scalar condition vocabulary | 6,296 (60.27%) |
| Whole logics currently liftable with no opaque operation under compact control/effect mode | 3 (72, 105, 108) |

The condition gap is dominated by parser and world predicates rather than unknown byte layout: `said(...)` accounts for 3,147 instances, followed by `posn` (617), inventory `has` (202), `obj.in.room` (69), string comparison (63) and controller/input predicates (40). Those are strong candidates for typed UIL intent, spatial, inventory, string and input contracts instead of recreating Sierra parser internals in every target.

The largest unimplemented action families are similarly recognizable services: `move.obj` (655), `display` (472), `add.to.pic` (413), loop/cel selection (407/315), update scheduling (228/168), priority (224), RNG (194), strings (166), sound (139), room transitions (82) and input gating. Only 18 `call.v` sites occur across nine logics; direct `call` already appears 227 times and has an explicit captured-callee model.

These counts are static encoded-instance counts, not reachability or whole-game parity claims.

## First native specimen

PQ1 logic 72 was selected because the current strict lifter admits its complete graph with no opaque operation. Its lifted graph contains nine source instructions and six `ui.print` effect sites. No original message text is required by the native PoC.

The private experiment performed:

```text
PQ1 AGI LOGIC 72
    -> fDisBull AGI 2.917 decoder/layout
    -> compact UDL (fdisbull-il-2)
    -> UIL role projection
    -> headless ui.print provider
    -> generated C
    -> gcc x86-64 Linux
    -> static ELF
```

The static ELF was 758,560 bytes with SHA-256 `cbf1719b999ff1ea14d4739abc5d289d9ec9cd993f81f07ac86233ca877bf996`. One initial-flag branch emitted five bound `ui.print` message IDs and the alternate branch emitted one, then both returned. The same two paths were replayed through fDisBull's nominal AGI effect model; effect sites and final modeled scalar state matched. The executable carries message IDs and source identity, not proprietary text or resources.

This qualifies the **control graph plus the declared headless print provider**, not visual rendering, timing, parser behavior, native AGI scheduling or whole-game equivalence.

`examples/agi/compile_compact_linux.py` preserves that deliberately small boundary. It refuses effect types it cannot realize instead of silently treating them as no-ops.

## Proposed compiler pipeline

### P00: source identity and resource intake

Keep LOGDIR/VOL, WORDS, OBJECT, VIEW/PIC/SOUND identities and exact provenance. Original bytes remain private.

### P01: complete AGI byte-layout IR

The current 2.917 layout parser already establishes instruction/condition boundaries for all PQ1 logics. Expand semantic opcode naming separately from byte-layout support so unknown behavior never forces guessed instruction lengths.

### P02: UDL semantic lift

Translate bytecode into source-bound behavioral blocks. Scalar operations remain direct. Engine operations become typed effect/predicate contracts. Preserve direct and indirect logic-call distinctions, scan starts, cycles and scheduler boundaries.

### P03: ScummVM oracle closure

Use the integrated ScummVM AGI bridge as a native oracle for opcodes and predicates whose result depends on engine state. Capture arguments, pre/post state, selected continuation and resource identity. Do not substitute ScummVM execution for proof of original DOS equivalence; keep original DOS checks as a second oracle where useful.

### P04: UIL abstraction

Prefer intent over interpreter mechanism. Examples:

- `said(...)` -> parsed player-intent / vocabulary predicate;
- `posn`, `obj.in.box`, room membership -> spatial predicates;
- `has`, `get`, `drop`, `put` -> inventory contracts;
- picture/view/cel operations -> presentation/object contracts;
- sound -> audio service;
- random -> explicit RNG service/state;
- save/restore -> persistence contract;
- `new.room` -> scene transition;
- update/motion/cycle operations -> scheduler/object-motion contracts.

This is where AGI-specific machinery should disappear when its mechanism is not part of observable behavior.

### P05: UDC providers

Provide target-specific realizations for Linux headless, SDL/native desktop, browser or other targets. A provider must return every output port it owns. Unsupported ports are a compile refusal, never an invented default.

### P06: native build

Lower closed UIL components to C/native code, then link provider implementations and resource loaders. First compile components, then scenes, then the scheduler/root graph. Keep original data external unless an explicitly private build chooses to bundle it.

### P07: differential qualification

For each admitted component, compare source-bound branch/effect/state traces against the ScummVM AGI oracle. For selected high-value paths, also compare against the original DOS interpreter. Scene and whole-game claims require progressively larger closure tests; a green component is not a green game.

## Why not simply copy the ScummVM AGI engine

The AGI module is not a single opcode loop. Its upstream module includes loaders, logic, cycle/scheduler, graphics, picture/view decoding, sprites, motion, text/menu/input, inventory, save/load and multiple sound implementations, plus ScummVM common/backend services. Copying those files into a new binary mostly creates another ScummVM fork and retains the interpreter we are trying to remove.

The AGI-only build is still valuable as an oracle and temporary replacement runtime. `experimental/scummvm/build-linux-agi-standalone.sh` provides a pinned Linux build recipe for that lane. Because ScummVM is GPL-3.0-or-later, any direct reuse of its implementation code also needs an explicit licensing decision; the compiler lane should keep provenance and implementation boundaries reviewable.

## Skill/benchmark connection

The improved investigation skill is in MR !82; MR !84 is the Castles II harness and cold-agent comparison protocol that references that candidate skill. This task is a useful example of the new `task-framing` rule: a replacement/new target executable is an explicit requested deliverable, so the investigation should not stop after finding a working harness over the original.

The run also exercised the new first-failed-boundary discipline. The first generated C attempt failed because repeated effect-local variables shared one `switch` scope. The failure was isolated to C emission, fixed by giving each continuation case its own scope, and the same semantic test was rerun. No AGI or UIL requirement was weakened to make the build pass.

For a future skill A/B, reuse !84's protocol: independent cold workers, identical target/tool access, time to first correct causal finding, time to first valid native component, and a held-out component/scene acceptance test. “Seconds to replay an already-authored harness” is not the compiler benchmark.

## Current next closure order

1. Add typed predicates for `said`, `posn`, inventory/room membership and controller input.
2. Add the high-frequency action providers: move, display, add-to-picture, loop/cel, update scheduling, priority, RNG, strings and sound.
3. Admit cycles and explicit scheduler ticks without flattening them into unbounded host execution.
4. Model the 18 `call.v` sites with runtime target constraints rather than guessing from one observed state.
5. Differentially close one complete room/scene, then several rooms, before attempting the root scheduler and whole game.

That ordering attacks the actual PQ1 frequency distribution rather than implementing the AGI manual alphabetically because humans apparently enjoy finishing features nobody uses.
