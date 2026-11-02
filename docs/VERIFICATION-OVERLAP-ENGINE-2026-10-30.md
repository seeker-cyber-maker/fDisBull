# Entry-qualified overlap engine verification

Unreleased engine work based on main
`f783f2aa43bae779392fd3f6558c980c5e4884b5`. The requirements were read from
PR #45 at `bdde81db693a0e6165ddbaf5e678a2f5d073ed19`. No original Syndicate,
DinoPark or other game execution was used for this qualification. The inputs
are authored instruction fixtures. Historical original-program findings in
the companion LE report remain separate, attributed evidence.

## Implemented boundary

- Explicit code/code definitions can overlap; definitions involving data still
  conflict. Versioned patches and prior instruction interpretations remain.
- `code-backings` captures complete local instruction bytes, source/version
  and backing revisions, immediate/encoding roles, stored incoming evidence,
  explicit continuation ports and physical-union versus local-byte counts.
  Independent materialization needs no sibling byte storage.
- `code-layout` emits a single-context x86 16/32-bit raw layout with remapped
  supported direct near branches, explicit neutral jump glue, entry-reference
  values and source-to-output occurrence/fixup records.
- Source validation rejects stale patch versions and relabeled partial graphs
  by checking the selected project facts. Input mutation no longer changes an
  already emitted layout's provenance. Public digests are not authentication.

The result remains `structural_only`; native backings remain residuals rather
than newly invented UIL operations. Source instructions' feature requirements
remain, and the emitted near conditional forms require a 386 or newer CPU.
The existing original-byte DOS compiler and restricted register-only lift keep
their separate contracts. See [the engine contract](CODE_BACKINGS.md).

## Fresh checks

The developer environment used genuine dependencies in a private virtual
environment: Python 3.13.17 on macOS ARM64, iced-x86 1.21.0, Capstone 5.0.9,
LIEF 1.0.0 and Z3 5.3.2. The shared installed environment was not changed.

| Check | Fresh result | Scope |
| --- | --- | --- |
| Five new overlap test files | **45 passed, zero skipped** in the full run | Real project capture, API/CLI, layout, source identity, proof model and native execution. |
| Focused engine and adjacent analysis/UDL/UDC selection | **103 passed, one skipped** | The skip explicitly required an unavailable external original DinoPark fixture. Counts overlap the full run. |
| Native authored overlap tests | **3 passed, zero skipped** | Original and rebuilt COM inputs on the real DOSBox backend. |
| Bounded Z3 tests | **4 passed** | Symbolic source/rebuilt comparison in the authored ISA model, plus a naive-concatenation counterexample in each mode. |
| Full source suite on this Mac | **2,162 passed, two failed, 23 errors, 21 skipped** | Not a green full-suite result; see the baseline comparison below. |

These rows describe the initial overlap cut. The later native UDL-to-UDC
integration and its final frozen-source regression are recorded below.

The native backend SHA-256 was
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
Across original and rebuilt fixtures, the checks exercised AL values
00/55/AA/FF and both DF directions. TEST preserved the destination and memory
on the primary A path, with CF/OF clear and the expected SF/ZF/PF. STOSB
performed the expected byte store and index update while preserving flags.
Undefined AF after TEST was deliberately not asserted.

The address-size-override fixture compared ordinary STOSB against `67 STOSB`.
An additional boundary probe confirmed DI wrapping FFFF to 0000 while EDI
advanced to 10000. Boundary memory readback was outside that probe's supported
mapped-image check and is not claimed; in-image memory effects were checked.
The negative `A8 AA AA C3` case actually produced the extra AL store and index
change absent from entry A of the proper overlap.

The Z3 model includes symbolic AL, DF, 32-bit EDI with 16-bit low-word
wrapping, a byte-array memory and the defined CF/OF/SF/ZF/PF observations.
Under successful-access, fixed-address/segment and no-code-alias assumptions,
the solver found no difference at the declared RET boundary for the admitted
entries. It found a counterexample for naive concatenation. This does not
prove decoder fidelity, exceptions, timing, source-game intent or a general
compiler. Native observations and model checks remain separate evidence.

## Full-suite host limitation, verified against baseline

The 25 full-suite problem nodes belong to four unchanged Linux ELF fixture
modules. `/usr/bin/gcc` selected Apple clang on this host. One test therefore
received Mach-O where it expected ELF; the remaining compiler/linker fixture
commands required Linux ELF options or link behavior.

The same four modules were rerun against the unchanged installed 0.26.1
package, with source-path injection disabled. Before that rerun, installed
`project.py`, `analysis.py`, `cli.py`, `inspection.py`, `decoder.py`,
`loader.py` and `elf_metadata.py` were byte-compared against the baseline Git
blobs, as were the four test files. Baseline results were **20 passed, two
failed, 23 errors**. All **25 of 25** failed/error node identities and outcomes
matched the candidate run; there were no changed outcomes in those modules.

The 21 full-run skips cover explicit unavailable original-game, Linux/display,
QEMU/PE runtime, IDA, source-checkout or filesystem prerequisites. They were not
reclassified as successful checks. Raw JUnit, commands, exit records, identity
checks and the node comparison remain in the private engine-work receipts.

The five new test files were added to both required-native DOS selections in
`native-debugger.yml`; ordinary CI already discovers them. This local record
does not claim a Linux CI result. Packing, publication and system activation
are separate work owned by Dot/cloud agents.

## Direct UDL-to-UDC and logical block integration

The follow-up engine path separates logical splitting, exact pass-through and
explicit raw relayout. `code-blocks` derives entry-qualified multi-instruction
groups while declaring the source layout unchanged and the groups unplaced.
`udc-native-capture` persists their source backings and ports without UIL.
Default `udc-native-compile` returns the full retained original file, with
`original_file_offsets_preserved: true`; physical overlap is not expanded.
Explicit relayout instead returns new placement/fixup mappings, stable group
IDs and `structural_only` qualification. No arbitrary replacement is claimed.

The final runtime/test/workflow cut has manifest digest
`d8417538fd60062a7839f3584cdedb8de47149fd8b41aede1d61cbf2186b80dc`.
Its 16 recorded files matched their frozen hashes after the full regression.

- All **71 tests across the eight new engine test files passed**, including
  grouping, the native UDC bridge, API/CLI, the existing overlap cases and the
  bounded proof model. **14** of those cases cover native UDC definitions.
- The three real DOSBox overlap tests exercised the persisted definition after
  reopening the project, checked exact whole-COM pass-through, then executed
  source and explicitly relaid-out paths. The matrix retained all **68 authored
  native runs**, the AL/DF combinations, address-size boundary checks and the
  naive-concatenation negative control. No UIL was supplied.
- An authored MZ fixture proved that the loader changes a relocation word from
  0x1234 to 0x2234 in mapped memory. Exact pass-through still returned the whole
  original header, relocation record, unrelocated 0x1234 word and shared AA byte
  at original file offset 67. This is container byte-identity evidence, not a
  native MZ behavior claim.
- A re-sealed partial-graph metadata regression cannot promote completeness.
  Info/exact output freshly validate the graph; failed validation reports
  `graph_complete: null` and `graph_validation: unverified` while allowing
  independently verified exact source bytes. Relayout refuses that graph.
- The final full Mac run collected **2,234 tests**: **2,188 passed, two failed,
  23 errors, 21 skipped**, exit 1. All **25** problem node IDs and outcomes
  exactly matched both the previous full run and the unchanged installed
  baseline described above. No additional failure/error node appeared.

The three additional test files were included in both required-native DOS
selections. No Linux CI, package, release or installation result is claimed by
this local engine record. The broader pass-through, block-boundary and testing
contract is documented in [NATIVE_UDL_UDC.md](NATIVE_UDL_UDC.md).

## Remaining PR #45 requirements

The bounded cases establish complete backings and the qualified authored
TEST/STOSB composition. General executable/container generation, call and far
transfer adapters, arbitrary table discovery, computed entries, code-as-data
compatibility, self-modifying aliases, exceptional paths and game-level UIL
recovery remain outside this implementation. They are preserved as explicit
requirements in [the broader overlap contract](UDL_OVERLAP_RECONSTRUCTION.md).

No game files, emulator states, byte-retaining project databases or raw private
deliveries are part of this change. Runtime inputs and generated projects were
kept in private temporary workspaces outside the checkout.
