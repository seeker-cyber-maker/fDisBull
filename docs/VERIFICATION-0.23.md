# 0.23 source verification

This record accompanies source finalization at `0.23.0`. It records local
acceptance before the exact-commit Linux CI gate. Live run status is available
from [Actions](https://github.com/seeker-cyber-maker/fDisBull/actions).
The source, fixed fixtures, bounded native receipts, tag and publication remain
distinct evidence surfaces.

## Native results

The exact compiler, lift and verifier hashes are recorded in the sanitized
receipts under [UDC evidence](evidence/udc-2026-10-29/). The tested backend is
the existing genuine macOS ARM64 DOSBox-X agent executable; original/emitted
inputs ran in fresh separate sessions. Game files and all raw outputs remain
outside Git. Source and emitted input inventories were checked for mutation.

- [Authored COM](evidence/udc-2026-10-29/synthetic.json): actual LLVM assembly,
  keypress, block entry/exit stops, AX 10 to 209, stored u16=209 and completion
  text. Original, ASM-derived UIL and C-derived UIL selected the same original
  native backing. Bounded traces and screenshot re-export after database reopen
  passed. The wrong UIL increment produced a Z3 counterexample and no output.
  Each file also passed five assisted CPU probes at input AX values 0, 1,
  65336, 65337 and 65535, including both sides of the wrap boundary. AX, stored
  memory and UIL agree in all 15 probes. Paused register/instruction-pointer
  edits distinguish these probes from the three ordinary keypress runs.
- [Zork](evidence/udc-2026-10-29/zork.json): compiler-emitted original COM and
  explicit story/setup resources; selected mailbox state and normalized first
  and repeated responses matched the fresh original run. Both bounded traces
  and stored screenshot re-exports passed. No story/parser reconstruction is
  inferred from this result.
- [DinoPark](evidence/udc-2026-10-29/dino.json): 183 non-save inputs reconstructed
  byte-for-byte; fresh NEW GAME office/bank/return routes matched on the
  observed selector and 48 sampled points at each comparison frame. Both
  traces and stored screenshot re-exports passed. This is not a whole-frame,
  financial transaction or full-campaign equivalence claim.

DinoPark and Zork use `original_bytes_only`, with **zero semantic blocks**.
The authored game has one qualified register block. Preserved native bytes,
modeled block equivalence and observed original-game behavior are separate
assurance levels.

## Proof and source-reader limits

Z3 5.3.2 checks explicitly modeled u16 register outputs at block exit. Flags,
memory, control flow, ABI, timing and intermediate state are excluded. Capstone
checks accepted instruction facts; its correctness is not proved by the solver.
The C view shares the ASM decoder and uses a bounded unsigned statement reader,
not a complete C/C++ decompiler or independent recovered source. Unknown,
unavailable, excessive or incorrect models never become successful compilation.

## Local checks

The final integrated focused run passed 73 tests with `--require-native`, including
actual synthetic DOS execution. It covers compiler/CLI, source readers,
native verifier, existing IL/recovery/language entry points, PR17 fixtures,
distribution rules, scene/skill discovery and source-reader modeling budgets.
Nine additional offline-kit tests passed after the packaging changes. These
runs used the genuine installed Python 3.13.17 environment with final source;
native acceptance used the tested macOS DOSBox-X backend. The three game
receipts were freshly repeated at final version 0.23.0.

The earlier development full Mac source run reported 1,459 passed, 106 skipped, two failed
and 23 setup errors. The two failures and 23 errors are Linux ELF fixtures
using the Apple host GCC/assembler. The full local suite is **not green**.
No missing dependency was replaced or faked to change that result.

The Linux native workflow includes the new suites for both backend variants
and installs LLVM for the authored assembly test. Ordinary/package and the
complete native workflow must both pass for the exact main commit before the
release tag is created. This pre-CI source record does not assert that result.

Source archive checks verify the exact PR17 fixture allowlist and sanitized
UDC receipts. The replay examples are checkout-only. Compiler outputs use new
private directories outside Git; native states and project databases are not
release payloads.
