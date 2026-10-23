# fDisBull engineering contract

Build a usable local agent-first disassembler. Native decoders provide instruction facts; our analyzer owns traversal and the persistent database. Screenshots must come from stored state without operating a GUI.

- Start with recursive entry-point traversal, then investigate referenced memory and later symbol/export seeds. Deduplicate work and facts; a budget stop must never be called stable.
- Resolve entry names and representations from shared address identity in every query/export. Keep raw operands and evidence intact.
- Preserve original bytes and every earlier code version. Do not key an instruction by address alone.
- Label inferred functions as candidates; preserve xref evidence and annotation authorship. Keep unknown indirect/segmented behavior unknown.
- Do not substitute a mock disassembly, web landing page, decompiler framework, or runtime harness for the working tool.
- Keep `README.md` limitations and verification aligned with the final packaged source. macOS is unverified until actually run there.
- Use `python -m pytest -q` from this directory. Demonstrate restart, patch isolation, and real image exports for changes to those seams.
