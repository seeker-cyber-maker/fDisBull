# Cortex-M static analysis milestone

This work adds explicit little-endian Cortex-M/Thumb static input to fDisBull.
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

## Progress

- Started on main `f94a5cd`, in an isolated worktree. The original local dirty
  checkout and its firmware evidence are preserved.
- Confirmed that current main still accepts only x86 and ARM64 raw inputs.
- Implementation and fresh verification are in progress.
