# Source-assisted investigation and concept search

Use projectless `source-*` JSON methods with a private `catalog` path.
The catalog is separate from native `.fdb` projects; import creates no native
mappings, disassembly seeds, binary names/types or UDL admission.

1. Import explicit source paths with `source-import`. Record original,
   reconstructed or generated source. Revision labels are caller declarations;
   compare captured hashes with pinned repository objects for a pinned-source claim.
2. Optionally hash a target. A matching declared output hash associates an
   upstream build claim; it does not reproduce that build.
3. Inspect `source-snapshots` and `source-files` coverage/status. Optional
   `fdisbull[source]` indexes C function/type definitions, fields and macros.
   Other formats remain unparsed; period C can be partial.
4. Use `source-entities` and bounded `source-text` for evidence.
   `source-occurrences` finds spellings inside parsed functions without
   preprocessing, binding resolution or read/write classification.
   Reconstructed names/comments remain source testimony, not instructions.
5. Start with lexical `source-search`. Vector/hybrid mode requires an explicit
   `source-model`, exported `source-cards`, caller-supplied `source-embed` vectors,
   and a query vector from the same encoder/profile. Models are not downloaded
   or run by the tool. Fetch missing-card batches at offset zero after each import.
6. Register logical meaning with `source-concept` and reviewed relationships with
   `source-link`. Keep units/roles distinct. These authored claims are excluded
   from retrieval cards. `source-bindings` enumerates recorded claims exactly.

Keep source-assisted/oracle inputs separate from blind investigations. Scope
queries with explicit snapshot IDs. Ranking is not confidence, abstention,
exhaustive semantic coverage or source/native equivalence.

Before propagating source meaning, qualify source/build identity, native
placement, target C/ABI profile and behavior separately. A C `int` does not imply
host width. Existing snippet/contract/layer methods still require their native
endpoints and independent qualification.
