# Independent review of the physical LE scope

Reviewed 2026-10-30: `independent/scope_le.py` and `independent/le-physical-scope.json`. No fDisBull module or earlier independent parser was imported or executed. Review used the current script, its JSON ledger and separate direct reads of selected original-file fields/ranges with standard-library `struct`.

## Verdict

No material interval or arithmetic error was found for this selected executable. The 19 disjoint physical ranges cover exactly 518,713 bytes. The nonzero page numbers form the permutation 1 through 105. This establishes the ledger's byte accounting, not the semantic meaning of every byte or native runtime behavior.

## Required qualifications

1. **Overlapping declared aggregates are real and must remain declarations.** Direct header reads reproduce loader `[10620, 88690)` (78,070 bytes) and fixup `[11145, 88690)` (77,545 bytes). Their difference is the 525-byte prefix containing object records, page map, resident name and empty entry table. The JSON correctly avoids adding these as disjoint ownership. The examined Open Watcom writer computes loader size before emitting fixups; therefore do not describe the target's inclusive loader declaration as behavior proven by that producer. Its historical producer/version rationale is unresolved. This is not evidence that the target is unloadable.

2. **The 20 bytes are present in the physical accounting.** `[0x2968, 0x297C)` is all zero and lies inside the 196-byte header leaf. For the observed OS/2-style DOS LE profile, reserving their meaning is appropriate. No VxD extension interpretation was established.

3. **The 524-byte slack is beyond the exact declared object size, not proved absent from native allocation.** `[0x559F4, 0x55C00)` is all zero. Object 1 declares 261,620 virtual bytes but owns 64 physical 4,096-byte pages. Clipping file-backed object content at the declared virtual size gives the recorded difference exactly. The original loader might allocate or copy a rounded final page; this analysis does not determine its accessibility, protection or deletion safety. Use "outside the exact object extent" instead of an unconditional "never loaded" claim.

4. **The 398-byte zero gap is structurally unassigned.** `[0x15A72, 0x15C00)` is all zero and exactly reaches the next 512-byte boundary. That supports a sector-alignment interpretation but does not prove the producing linker's intent, that the format requires this exact gap, or that removing it without updating downstream offsets is safe. The current `unassigned_zero_gap` classification is appropriately conservative.

5. **The debug wording should reflect the resolved erratum.** The JSON limit currently refers to "debug offset dialect differences." IBM Revision 11 explicitly corrects the earlier documentation: debug offsets are file-relative. The target has zero debug offset/length and does not exercise debug parsing. Prefer "Inactive optional tables are not exercised; earlier debug-offset documentation was corrected by IBM" to implying two established valid dialects.

6. **The parser is a selected-profile investigator.** It intentionally rejects optional sections, page aliases, nonenumerated pages, nonempty entry tables and most fixup forms. Several descriptive strings and the 398-byte-limit sentence are target-specific. The successful result should not be promoted to general LE conformance, exhaustive instruction recovery or a generic malicious-input parser audit. Its virtual-byte totals describe the LE objects, not a complete DOS-process memory map.

Source qualification is in `LE_Format_References.md` beside this review. The original binary was not changed and no native guest was run.
