# External targets and repository publication policy

**Priority: required before publishing research databases or target-derived archives.**
Do not upload original or modified game binaries, story images, game assets,
resource files, saves, emulator states, or archives/databases containing those
files to GitHub, release artifacts, tool packages or skills. A filename,
`.fdb` extension, hash, download availability or a claim of abandonment is not
permission to distribute the contents. Keep runtime inputs private outside Git.

Authored reports, semantic UIL and game representations are allowed under the
current project policy, pending a future sanitation pass. That allowance does
not include a representation that embeds a complete original file, memory image
or raw asset under another name. Inspect nested archives and JSON, including
`low_level_ir.memory.initial`, not just top-level filenames. A hash establishes
byte identity relative to a recorded import; it does **not** establish publisher
authenticity, ownership, license, safety or permission to publish.

## Schema 9 storage boundary

New projects use `external-objects-1`. SQLite stores references containing
exact length, SHA-256 and encoding; the payload stays in a private content
addressed store. This includes the original container, mapped regions, per
instruction hex, attached files, debugger artifacts and UDC block BLOBs.
The Project connection externalizes binary parameters before SQLite receives
them, so those payloads do not first enter a database page, journal or WAL.
Known nested raw caches and structured `*_hex`, `*_base64` and byte-valued
`*_bytes` fields (including breakpoint `runtime_bytes`) are stored externally as complete records,
preserving their original certificate/digest instead of deleting a field.
Debugger event evidence is always externalized as a complete record, including
unknown future payload fields, rather than relying only on recognized byte keys.

The default store is `$XDG_DATA_HOME/fdisbull/target-objects` (or
`~/.local/share/fdisbull/target-objects`). `FDISBULL_TARGET_STORE` selects another
private location. The store requires private permissions and no Git or symlink
ancestry. **Do not upload, package or place this store beside a public FDB.**
Object names are SHA-256 digests; each read checks length and digest before
returning data. A changed/corrupt object fails closed. No absolute source or
store path is recorded by the new identity contract.

`target_sources` records the source identity, format, architecture, loader
options, loader name/version, schema and source-layer approval provenance.
Mapped version hashes remain distinct from container hashes (relocations and
memory-only edits can make them differ). Existing authored patch APIs still
preserve parent versions, with payloads external in new projects.

```text
fdisbull source-info /private/analysis.fdb --version 1
fdisbull storage-info /private/analysis.fdb
fdisbull source-candidate /private/analysis.fdb /private/candidate.exe --version 1
fdisbull bind-source /private/analysis.fdb /private/original.exe --version 1
```

The equivalent JSON methods accept `project`, `path` and optional `version`.
The Python APIs are `source_info`, `source_candidate`, `bind_source` and
`new_source_analysis`. The last two operations perform static loading only;
they never execute a target.

## Exact sources, divergences and user choice

An exact source can refill missing container, mapping and instruction-cache objects only if both
the container identity and mapped-version digest match. Missing source/store
objects do not become zero bytes or an implicit new analysis. Stored
instructions, labels and research remain readable where their dependencies
are available; a missing instruction hex cache is returned as an empty string.
`byte_cache_available` marks missing hex caches explicitly; interrupt details
requiring absent bytes stay unknown. `source-info.verified` reports container
availability/identity. Byte-dependent
analysis, memory reads and artifact exports fail clearly when needed objects
are absent. Cached original objects are immutable evidence; replacing a file
with the same name does not replace that evidence.

A mismatch stays unattached. `source-candidate` returns an `approval` receipt
bound to the project ID, selected base version, base mapped digest, base
size/hash, candidate size/hash and loader options. Show these identities to the
user and obtain explicit approval for **this** candidate against **this** base.
Only then pass that exact object to `bind-source` as `approval` (CLI:
`--approval '<the exact JSON object>'`). Generating the receipt or echoing it
programmatically is not evidence of user consent. Generic booleans, different
base versions/projects, and different candidate hashes are refused. The file
is read again into an immutable snapshot at binding; a changed candidate
invalidates the approval. A granted receipt can authorize that same relation
again, but never a different relation.

Approved divergence creates a distinct child version with a fresh analysis
queue and permanent approval provenance. Its bytes also stay external. Base
identity and discoveries remain unchanged. Candidates must retain the selected
format, processor and entry; use a separate analysis for other layouts. Native
debugger launch still enforces its original/unpatched-version contracts;
approval of a static source layer does not qualify a new native launch path.

Without approval, keep the candidate unattached. Offer a separate analysis and
create it only when the caller explicitly chooses the destination:

```text
fdisbull new-source-analysis /private/analysis.fdb /private/modified.exe /private/new-analysis.fdb --version 1
```

Declining a layer does not execute the binary, start another analysis, alter the
base, or supply approval for a later candidate.

## Legacy projects and migration

`storage-info` opens SQLite read-only, reports legacy embedded storage and
known payload columns, and performs no migration. Opening a legacy project
still follows the older additive schema upgrades; it does **not** silently
externalize, delete or sanitize its bytes. Legacy projects remain private.

For an explicitly requested derivative:

```text
fdisbull migrate-external /private/legacy.fdb /private/new-derivative.fdb
```

The source is opened read-only in a consistent snapshot. Tables/rows stream
through the external encoder into a new destination; raw SQLite pages are not
copied, so old payloads do not survive in the derivative's free pages. Existing
destinations are refused. The original and its private bytes are preserved.
Known instruction caches, BLOBs and raw JSON records become references. Legacy
identities/provenance are retained if present. For older retained source bytes,
the derivative records their measured size/hash, reconstructed loader options
and an explicitly unknown original loader version; exact mapped-byte verification
is still required before binding. Projects without retained source bytes need
a fresh explicit import to obtain the source-binding workflow.
Historical proof/macro records retain their original import-hash binding plus
mapped-version hash; migration does not rewrite or invalidate their certificates.
`source-info` separately reports the measured per-version container identity.
New approved source layers bind new records to the new source identity. The store
is a separate dependency and must be retained privately for full restart.

## Limits and integration requirements

This draft implements the core FDB storage boundary, **not a universal
publication sanitizer**. `storage-info.publication_ready` is always false: its
payload-column inventory is evidence, not approval to upload. Free text,
annotations, extracted strings, arbitrary extension schemas or user-supplied
semantic arrays can still reproduce protected content. Review those separately.
Non-FDB exports (Zork executable IR, checkpoints, screenshots and raw response
archives) are unchanged and can retain original files/assets. Keep them private
unless separately reviewed and stripped. UIL/game semantics are permitted;
raw originals hidden inside them are not.

Public Project methods use the external connection; arbitrary SQL, direct
cursor mutations and SQLite tools are not supported write interfaces. Schema 9
stores descriptors in the historical payload columns. Older tools must reject
it rather than treat descriptor text as game bytes. Raw SQLite tools see
references; use the Project API to resolve payloads. JSON reference envelopes
preserve the `kind` and `source.kind` selectors used by existing SQLite indexes.
Keep new payload writes at this boundary; do not add a new hex cache, use SQL
literals to bypass it or put arbitrary byte lists under unrecognized JSON keys.

Active integration owners: #31 type transfer shares CLI/docs;
#32 Zork shares CLI/skill guidance and needs its own export sanitation;
#36 → #38 → #39 share project/CLI/UDC paths and must retain the external
connection when adding snippets/backings. #37 checkpoint reconciliation keeps
its separate provider contract. No branches in that stack are modified here.
Native execution of divergent source layers and arbitrary export sanitation
remain separate qualification work. No merge, release or installation change
is implied by this priority draft.
