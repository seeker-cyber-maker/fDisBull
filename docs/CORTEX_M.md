# Cortex-M static analysis milestone

This work adds explicit little-endian Cortex-M/Thumb static input with the
Armv7-M exception-vector layout used by the 121GW to fDisBull.
The native decoder supplies instruction facts; fDisBull owns traversal, stored
references, candidate functions and immutable byte versions.

## Acceptance contract

- Import a caller-selected flat flash image with an explicit base and vector
  count. Preserve raw vector words and their Thumb tags, validate the initial
  stack pointer and reset target, and seed reset before deferred interrupt
  entries. Never guess a device or flash base from the host architecture.
- Decode mixed 16/32-bit Thumb instructions, literal references and direct
  successors. Conditional execution, unknown register branches and exception
  returns must not acquire invented exact targets.
- Keep the vector table and evidenced literal pools as data. Preserve the
  source bytes, authored annotations and parent analysis when creating patches.
- Test budget stops, fresh-process restart, patch isolation and actual stored
  PNG/CFG exports against synthetic edge cases and the privately retained
  official 121GW 2.05 image.

The real image, byte-retaining databases and raw firmware disassembly remain
private. Commit only authored tests, verifier code and sanitized result receipts.
No firmware execution, hardware flashing or measurement equivalence is part of
this static milestone. SRAM, EEPROM and peripheral state remain unavailable
unless supplied as evidence; this does not create a board emulator.

## Import and query

```sh
fdisbull import /private/EEVBlog2_05.bin /private/121gw.fdb \
  --profile cortex-m --base 0x08006000 --vector-count 73
fdisbull info /private/121gw.fdb
fdisbull analyze /private/121gw.fdb --max-instructions 2000
fdisbull analysis-status /private/121gw.fdb
fdisbull disasm /private/121gw.fdb --address 0x08029174 --lines 8
fdisbull render /private/121gw.fdb /private/reset.png --address 0x08029174 --lines 8
fdisbull render-cfg /private/121gw.fdb 0x08029174 /private/reset.svg
```

The base and count are caller declarations, not automatically detected device
properties. `--arch thumb --base ADDRESS --entry ADDRESS` separately loads a
raw code slice without a vector table. Canonical code addresses are even; raw
vector values keep bit 0 and their original source words. The profile validates
SP against the generic SRAM range and validates reset inside supplied flash
after the declared table. It does not infer a device's exact RAM size. Missing,
reserved, untagged and out-of-image interrupt vectors remain explicit records.

Selecting `--profile cortex-m` declares the Armv7-M vector layout. Stored
metadata names that layout explicitly; no device/core detection is implied.
Armv8-M Security tables, including SecureFault at vector slot 7, are outside
this profile. Raw `--arch thumb` remains available for a caller-selected code
slice without imposing a vector-table interpretation.

Only supplied vector and flash bytes are mapped. The vector range is read-only
data; the remaining flash range is eligible for recursive code discovery.
Referenced PC-relative literal spans are held as data during native discovery.
This includes dual-word LDRD and single/double-register VLDR transfers. ADR.W
aliases retain exact address references without treating the addressed bytes
as a loaded literal.
Explicit `represent ... code` can retain an overlapping code interpretation.
If already stored code overlaps a newly discovered literal, both interpretations
remain with an issue. No unknown register-derived memory read is replaced by
zero or by a guessed peripheral value.

Lexical IT coverage is persisted per byte version. A conditional control
instruction retains its possible fallthrough even when another entry reached
it before its IT instruction. Display operands and CFG retain the predicate
qualification; raw operands remain unchanged. The runtime condition is unknown.
Register-indirect transfers, jump tables and exception-return destinations
remain unresolved. `BX LR` / `POP {...,PC}` are return-shaped observations, not
a recovered live stack or exception context. The decoder is M-class Capstone;
there is no chip-specific opcode-availability whitelist.

`auto-analyze`, derived Thumb semantics/ABI recovery and function-pattern scans
are explicitly unavailable in this milestone. Use native `analyze` and inspect
issues. A native fixed point only means these discovery rules have no queued
work; it does not mean complete firmware recovery.

## Verification

The authored regression cases are in `tests/test_cortex_m.py`. The standalone
verifier runs every command in a fresh process and requires a new private output
directory outside the repository:

```sh
python scripts/verify_cortex_m.py /private/EEVBlog2_05.bin \
  --base 0x08006000 --vector-count 73 --output /private/new-qualification
```

It preserves the input, moves only its own copy, reopens stored instructions and
annotations, writes real PNG/SVG/CFG files, tests a NOP child and a distinct
reset-vector child, and verifies the untouched parent. Vector metadata and
function seeds are rebuilt from each child's bytes; an invalid reset-vector
patch cannot silently reuse the parent's entry.

Earlier prerelease projects retain their historical discovery evidence on
reopen. Use a fresh import to qualify changed native discovery rules;
`refresh-facts` updates stored access facts without rerunning traversal.

The 121GW count is 73 through `COMP_ACQ_IRQHandler` in ST's
[STM32L152xD startup definition](https://github.com/STMicroelectronics/cmsis-device-l1/blob/master/Source/Templates/gcc/startup_stm32l152xd.s).
The template's later reserved padding/BootRAM word is not an implemented
interrupt entry. Instruction/vector rules follow ST
[PM0056](https://www.st.com/resource/en/programming_manual/cd00228163.pdf).
These references specify the target conventions; the original application
flash base remains a declared mapping for this qualification.

## Progress and scope

- Started on main `f94a5cd`, in an isolated worktree. The original local dirty
  checkout and its firmware evidence are preserved.
- Added the explicit profile, Thumb decoder, native memory/reference facts,
  literal/IT evidence, version-bound vector reseeding and private verifier.
- The pinned macOS environment uses Python 3.13.14 and Capstone 5.0.9.
- Real 121GW qualification and final test results are recorded in the sanitized
  evidence receipt and PR. No device execution or measurement claim is made.
