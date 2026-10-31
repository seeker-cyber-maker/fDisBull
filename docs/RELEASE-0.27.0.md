# 0.27.0 cloud release candidate

This is an isolated integration candidate, not a published release. The pinned
cut and source PR checks are recorded in [the manifest](CLOUD-0.27.0-MANIFEST.json).
Publication requires ordinary and required-native Linux CI on the final source
SHA, followed by a separate release decision. No installation or environment
snapshot is promoted by this candidate.

## Changes

- Schema9 projects retain target bytes in a separate private object store.
  Exact source identity and base/candidate-specific approval govern divergent
  source layers. Inspection is not approval and never executes a candidate.
- Completed Z checkpoint saves can be reconciled without saving again.
  Oversized replies can be retrieved without replaying actions. Named DinoPark
  menu/quit actions distinguish prompts, leaving the park and actual DOS exit.
- Portable structural type catalogs preserve provenance. Bounded Win16 NE
  analysis exposes logical locations and fixups; it does not execute Win16 code.
- Both skills preserve their separate investigation and guide-writing roles.
  Investigation guidance qualifies prior source reconstructions and recovers
  missing tools. Permanent media adapters reuse GOG/AGI support and extract MZ
  envelopes and opaque tails. They do not decompress Civilization overlays.
- Civilization research leads and the reviewed research collection preserve
  historical evidence and its limits. Sanitized research databases are not
  runnable or reopening-equivalent original projects.

## Compatibility and recovery

New projects use schema9 external objects. Legacy embedded projects remain
readable; `migrate-external` explicitly creates a new derivative and preserves
the original. Keep the private object store with the derivative: missing or
corrupt objects prevent byte-dependent compilation and execution. Metadata that
does not depend on missing bytes remains readable where supported. Storage
separation is not a sanitizer: `publication_ready` remains false.

The combined integration checks cover main's native UDC source and capsule
tables, including SQLite/WAL references, fresh-process overlap materialization,
missing/corrupt objects, legacy migration, immutable identities and original
versus approved-child behavior. Original-layout compilation remains unavailable
for a child version; it must not silently substitute the original source.
Migration reconstructs COM loader options without module mode and recognizes NE.
NE source layers currently share one retained loader declaration set. Changes to
NE fixups, imports, exports, segment mappings or other retained NE metadata are
therefore refused even with exact byte approval; use `new-source-analysis` for
an independently loaded project. Code-only children with identical declarations
remain supported. Approval must never bind child evidence to stale fixup targets.

## Qualification boundary

The cloud host supplies the matching layers DOSBox backend and Python runtime.
Local combined tests do not qualify unavailable Wine/QEMU/IDA backends or the
stable DOSBox profile; the required-native CI matrix supplies those release gates.
The platform's `/tmp` Git marker can reject a historical test's hard-coded
private output directory. Such a failure must remain visible and must not be
worked around by weakening privacy guards.

The authored unpadded 14-byte COM acceptance requires five complete instruction
records, AX=12 after the store, native DS:0120 word=12, breakpoint removal and
same-guest DOS exit code 0 before debugger cleanup. A separate command reopens
the saved records without reanalysis. Private FDBs, object stores, raw replies,
states and original game inputs are excluded from release artifacts.

The broader experimental UDC/source-catalog stack is deferred. This candidate
does not promise whole-game recovery, generalized decompression or new compiler
targets beyond the pinned main and admitted changes.
