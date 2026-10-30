# Civilization city-production UDC

This slice turns one original DOS Civilization city rule into a shared UIL
program and a generated-C/native UDC module. It is intentionally smaller than
city management as a whole.

## Authority and boundary

The DOS semantic source is the `sjmelia/civd` 474.05 reconstruction. Its
`CIV.EXE` SHA-256 is
`22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a`, matching
the pinned DOS target and the executable identified in the Civ64 intake.
Relevant source is `src/CITYMGT.C`:

- line 639: add the turn's shields to `shield_box`;
- lines 642-645: compare unit cost times `cost_scale`, subtract the required
  shields, and enter the unit-completion path;
- line 714: the human unit path clears `shield_box`;
- lines 728-752: improvement completion and shield subtraction;
- line 768: the human improvement path clears `shield_box`.

The civd technical book gives the same rule in
`book/src/city/production.md`, under **Shields and completion**. The module's
`needed` input is the caller's already-computed `cost * cost_scale` value;
`CITYMGT.C` sets the human scale to 10. Multiplication and the unit/improvement
selection policy are outside this first contract.

The intake hashes the authority files as `CITYMGT.C` =
`78e435ff78709dde8bbab028a81c9899ea8f4602f591c974f4be06e1280457cc` and
`production.md` =
`8b4a72e31d99e092d330b6070a324f0d2d13e63d6394dfdc490806d0dd5dfbe3`.

## UIL contract

The logical contract is `civ.city.shield-completion`:

| Port | Type | Meaning |
| --- | --- | --- |
| `shield_box` | `u16` | Stored shields before this turn |
| `shields` | `u16` | This turn's shield yield |
| `needed` | `u16` | Required shields after the caller's cost scaling |
| `clear` | `u8` | `1` for the human completion path, otherwise `0` |
| `new_box` | `u16` | Stored shields after completion handling |
| `complete` | `u8` | `1` when the scaled requirement was met |

The UIL program computes:

1. `new_box = shield_box + shields` with `u16` wrap semantics;
2. `diff = new_box - needed` with `u16` wrap semantics;
3. the wrapped subtraction's bit 15 selects incomplete versus complete;
4. incomplete keeps the accumulated box; complete either clears it (`clear=1`)
   or retains the excess (`clear=0`).

The admitted arithmetic envelope is `0..32767` for each of
`shield_box`, `shields`, and `needed`, with `clear` equal to `0` or `1`.
Within that envelope, the sign-bit test is equivalent to the original
unsigned comparison. The current contract has no compiled admission guard;
callers must enforce the envelope. Values outside it are not claimed to match
civd.

The example registers both layers:

- `uil`: the shared `fdisbull-il-1` evaluator, used for model replay;
- `c-uil`: the generated-C implementation used by the native shell.

The implementation is in `examples/udc/civ_production.py`.

## Original-backed DOS baseline

The pinned packed DOS image was also captured through fDisBull's
original-backed DOS UDC. The temporary definition receipt had
`definition_sha256=223a5243e1ca3209e1a068b68d623933d7e916d01b8c0355b8453c168500574d`,
one `CIV.EXE` artifact, five retained original chunks, and
`semantic_block_count=0`. Compiling that definition produced an output whose
SHA-256 was
`22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a`, exactly
matching the input. This proves byte-preserving reconstruction only; it does
not provide a semantic UIL for the packed overlays. The `uil`/`c-uil` city
module above is the first semantic layer added beside that baseline.

## Executable proof

The generated C is compiled only from the typed UIL AST. The test
`tests/test_udc_civ_production.py`:

- compares the shared UIL evaluator with a direct civd arithmetic oracle over
  boundary and deterministic pseudo-random vectors;
- persists and replays the `uil` layer through a fDisBull project;
- compiles the generated C with clang, loads the resulting host shared library,
  and compares every output to both the UIL evaluator and the oracle;
- qualifies the implementation with the installed Z3-backed contract checker;
- emits a Linux x86-64 ELF selected shell and verifies its ELF header and
  selection capsule.

The macOS host replay is actual native execution of the generated C shared
library. The Linux shell is emitted as a cross-target artifact; the test does
not claim that a macOS host executed that Linux ELF. Its capsule explicitly
reports `native_execution: false` until a Linux runtime observation is bound.

## Deliberate non-claims

This is not yet a complete city-management reconstruction. It does not model
purchase prices, corruption, tax/luxury allocation, food growth, AI production
choice, unit creation, improvement side effects, or the original DOS process
state. The next arithmetic extension needed for the purchase-price formula is
bounded multiplication and division; adding it here would widen the first
executable slice without a corresponding contract.

Civ64 is used as a secondary reverse-engineering corpus, not as a substitute
for the civd DOS authority. Its public repository contains no reconstructed
source or pull requests; its DOS correspondence document records that the
Win16 port uses different compiler/runtime conventions and RNG behavior. A
function-level Civ64 PE64 correspondence remains a separate static-analysis
obligation and is not silently claimed by this module.
