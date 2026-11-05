# First CHIP-8 Sandsifter-style pilot result

Run: 2026-11-02. Python 3.13.5; bounded authored VM. The complete detailed
machine-readable receipt is in `results/pilot.json`. This report is safe to
share without commercial game binaries; it does not certify original-runtime
behavior or legal provenance beyond the cited public archive's license claim.

## Enumeration and probing

- 65,536 16-bit words × 3 profiles = **196,608** comparisons.
- Table-driven vs independently branched classifier: **0** disagreements.
- Classic profile: **43,954** syntactically supported encodings, **4,094**
  opaque legacy `0NNN` encodings, **17,488** invalid encodings.
- One-step classic VM test: **43,938** executed, **16** waiting for a key,
  **0** unexpected traps on the deliberately controlled state.
- SCHIP profile: 69 extension encodings; XO profile: 577 XO extension encodings
  (including declared four-byte `F000`). No extension execution claim.
- Five quirk probes exhibit expected profile-dependent state outcomes.
- Synthetic decoder mutant: **256** `5XY1` false acceptances; minimized to one
  `5011` word. Not a real interpreter defect.
- **3,000** arbitrary legal-opcode short sequences + **3,000** straight-line
  sequences, each rerun with the same initial state and seed: zero repeatability
  disagreements. Control-flow and memory traps are logged, not hidden.

## Public corpus pilot

| Program | Declared profile | Runtime status | Distinct PC/word candidates |
| --- | --- | --- | ---: |
| Snek | chip8 | waiting for key after 977 steps | 18 |
| Ghost Escape | chip8 | 1600-step budget | 35 |
| 1D Cellular Automata | chip8 | 1600-step budget | 72 |
| Octojam 5 Title | chip8 | 1600-step budget | 55 |
| Br8kout | chip8 | 1600-step budget | 75 |
| Flight Runner | chip8 | 1600-step budget | 84 |
| Dodge | schip | static only | 0 |
| Mondri8 | schip | static only | 0 |
| Octo paint | xochip | static only | 0 |

**Totals:** 9 pinned/byte-verified CC0 programs, 6 classic headless observations,
339 distinct `(source, PC, opcode)` candidates, 367 observed PC→PC edges.
Natural classic family coverage: **26/34 (76.47%)**. Eight missing families
are in `gap_probe_results`, with all eight authored bounded probes passing.
These fixture checks are **not** natural corpus discoveries.

## Coverage curve

| Classic programs inspected | Families observed | New families | Pairs | Triplets |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 11 | 11 | 15 | 17 |
| 2 | 18 | 7 | 44 | 57 |
| 3 | 23 | 5 | 81 | 121 |
| 4 | 25 | 2 | 91 | 137 |
| 5 | 25 | 0 | 114 | 197 |
| 6 | 26 | 1 | 132 | 244 |

There is no statistical extrapolation yet: these nine programs were deliberately
selected for size and variety. Opcode syntax coverage is not behavioral or
whole-game coverage, and one execution policy cannot reach all program paths.

## Evidence ceiling

The decoder comparisons can detect inconsistent classifications between two
implementations that share a public specification. They cannot prove the
specification historically correct. Same-VM replay detects nondeterministic
implementation behavior, not semantic equivalence against Octo, a COSMAC VIP,
or Timendus. The proposed UDL→UIL records carry a qualified *source identity*
but only an unqualified semantic-intent label. The local SQLite registry and
its receipts must never be interpreted as permission to execute arbitrary
submitted code, or permission to publish private games.

## Next

Run the pinned Timendus GPLv3 interpreter checks and independent differential
emulator tests; then expand to the remaining 44 `chip8` titles while holding
whole titles/authors out for evaluation. Add separate SCHIP and XO semantics
rather than silently calling extension opcodes classic.