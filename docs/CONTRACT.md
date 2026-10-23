# fDisBull 0.3 acceptance contract

Provide a local, agent-first disassembly database: parse recoverable executable information; retain byte versions; recursively discover code/data under explicit rules and budgets; allow shared address annotations/representations; render stored findings without a GUI. Imported files are never executed.

Classic DOS MZ is now a first-class input. Validate fixed fields, page/header/relocation bounds and supported memory limits. Load at an explicit segment (default `0x1000`), apply fixups, retain source bytes, and zero-fill only paragraph padding/minimum allocation. Exclude header/overlay bytes from loaded code. Do not fabricate PSP memory, DOS allocator/runtime state or A20 wrapping.

Decode MZ with actual CS:IP semantics. Near branches preserve CS and wrap the offset; far branches carry their own selector. Separate CS-specific interpretations at the same physical address. Unknown register/segment/index states must not produce invented flat references. Make calling-convention, interrupt and deferred-seed assumptions inspectable.

Run entry recursion first. Admit relocation-backed far-call patterns, observed-data-segment callback pointers and paired literal far-pointer initialization as later **candidates**, preserving provenance. Never classify every relocation or whole candidate segment as code. `segments` reports inferred roles/bounds; `code-regions` reports only contiguous decoded facts per CS.

Persist and deduplicate code/data work. A budget stop remains explicitly incomplete; resumption may reach `stable` only when implemented queues drain. Stability does not prove all original instructions, functions, indirect targets or dynamic overlays have been recovered.

Names/comments/representations belong to versioned physical addresses and resolve in every referring query/export. A representation change retracts derived facts and triggers bounded reanalysis. Patching creates a child while retaining parent bytes/metadata/annotations. Reverse all MZ fixups in reverse order for retained file-backed child bytes; keep allocation-only edits memory-only. Inherited interpretations require semantic review.

Retain prior flat ELF/PE/Mach-O/raw behavior and offline CHimpREC-derived recovery. Static imports and captured-IAT reconstruction remain separate. Recovery retains aliases/unknowns and does not attach to Windows or rebuild a runnable executable.

Verify synthetic relocation/segmentation/state/alias/version cases, malformed inputs, schema 1/2 migration, existing format regressions and public protocol/render behavior. Exercise the actual original DinoPark EXE through import, bounded recursive resumption, segment/code-run inventories and known `38ff:*` routines; report measured evidence separately from assumptions.

Do not claim full game execution, every-instruction coverage, runtime overlay recovery, complete CFG/function boundaries, decompilation, unrestricted data flow, runtime SMC capture or macOS runtime verification. No new simulator or guest-code execution belongs to this milestone.
