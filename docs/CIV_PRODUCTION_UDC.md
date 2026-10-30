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

- `CIV.H` lines 38-39 declare `shield_box` as a signed DOS `int`, represented
  as signed 16-bit storage in this slice;
- lines 227-229 reset `shield_box` to zero when it is negative or greater than
  999 before production is added;
- line 639 adds the signed turn balance to the reset storage value;
- lines 642-645 compare unit cost times `cost_scale`, subtract the required
  shields, and enter the unit-completion path;
- line 714 clears the human unit-completion path;
- lines 728-752 perform improvement completion and shield subtraction;
- line 768 clears the human improvement-completion path.

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

| Port | Type | Admitted values | Meaning |
| --- | --- | --- | --- |
| `shield_box` | `i16` | `-32768..32767` | Signed stored shields before this turn; values outside `0..999` reset to zero |
| `shields` | `i16` | `-32768..32767` | Signed turn balance added after the reset |
| `needed` | `i16` | `0..32767` | Required shields after the caller's cost scaling |
| `clear` | `u8` | `0` or `1` | `1` for the human completion path, otherwise `0` |
| `new_box` | `i16` | signed 16-bit | Stored shields after completion handling |
| `complete` | `u8` | `0` or `1` | Whether the scaled requirement was met |

The source-shaped reference UIL and implementation UIL both compute:

1. normalize `shield_box` to zero when it is negative or greater than `999`;
2. add signed `shields` using signed 16-bit storage semantics;
3. compare the resulting signed box with non-negative `needed`;
4. leave the signed accumulated box when incomplete;
5. on completion, clear it for `clear=1` or retain the signed excess for
   `clear=0`.

The previous unsigned `u16`/sign-bit-only model was removed. It admitted an
incorrect arithmetic envelope and omitted the source reset. The current
program has IL `require` guards for the `needed` and `clear` limits, while the
module API validates every input against the same `_input_limits()` receipt. The
generic native-shell contract-domain field remains empty because that fDisBull
profile cannot yet carry a separate domain object; this module does not treat
that omission as an admission of arbitrary inputs.

The example registers both layers:

- `uil`: the shared `fdisbull-il-1` evaluator, used for model replay;
- `c-uil`: the generated-C implementation used for the native shell.

The implementation is in `examples/udc/civ_production.py`.

## Independent comparison and release gate

The contract's reference program and selected implementation are structurally
different UIL documents. Z3 qualifies their typed behavior. Separately,
`compare_oracle()` evaluates 896 deterministic signed/extreme/wrap vectors
against a direct Python oracle that uses the civd reset, signed comparison, and
signed 16-bit storage rules without reusing the UIL bit-test implementation.

`qualification()` reports both results. `build_native()` refuses native
emission unless shared-UIL qualification and the independent oracle both report
success. This keeps the slice out of release while either the limits,
comparison, or oracle disagrees.

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

- compares the implementation UIL with the independent civd oracle over signed
  boundary, reset, negative-balance, overflow, and deterministic vectors;
- verifies IL admission guards refuse negative `needed` and non-binary `clear`;
- persists and replays the `uil` layer through a fDisBull project;
- compiles the generated C with clang, decodes signed output words, and
  compares every output to both the UIL evaluator and the oracle;
- requires distinct source-reference and implementation UIL hashes;
- qualifies the implementation with the installed Z3-backed contract checker
  and the explicit release gate;
- emits a Linux x86-64 ELF selected shell only after that gate, then verifies
  its ELF header and selection capsule.

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
