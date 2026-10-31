# Reuse type interpretations between projects

A structure learned in one program can be a useful starting point in another.
`export-types` and `import-types` exchange explicit structural definitions while
each project keeps its own addresses, bindings, bytes and evidence.

This is declaration transfer. An imported type remains an interpretation;
source hashes and authors identify the declared origin, not proof that the
layout or ABI is correct in the receiving program. Validate the target before
binding it. The [Colonization DOS/Win16 pilot](COLONIZATION_DOS_WIN16_PILOT.md)
shows both useful transfers and an incompatible pointer convention.

## CLI and Python

```sh
fdisbull export-types first.fdb --name Record --output private-types.json
fdisbull import-types second.fdb private-types.json --author receiving-analyst
fdisbull types second.fdb
```

`--output` writes a raw catalog to a **new** file, suitable for the import
command. It refuses an existing file, including a database or alias to one.
Without `--output`, the CLI uses its ordinary JSON response envelope. Catalog
definitions retain their original JSON values; enum members named `address`,
`target` or similar are not reformatted as native addresses. For a
large catalog, use file output or retrieve the retained output artifact rather
than treating an incomplete inline response as the catalog.

```python
from fdisbull.project import Project

with Project("first.fdb") as source:
    catalog = source.export_types(version=1, names=["Record"])
with Project("second.fdb") as target:
    receipt = target.import_types(catalog, version=1, author="receiving-analyst")
    assert receipt["bindings_imported"] == 0
```

The JSON methods are `export-types` with optional `version`, `names` and `output`, and
`import-types` with `catalog`, optional `version` and `author`. The latter also
accepts `catalog_file` through the CLI/JSON boundary. Explicit `apply-type` or
`apply-file-type` is a separate local action after validation.

## Envelope and validation

The `fdisbull-types-1` envelope contains exactly:

- `format`: the catalog version.
- `source`: source-file SHA-256, mapped-version SHA-256, local version number,
  architecture, bit width and byte order. A version number has meaning only
  within its source project.
- `types`: ordered user definitions with `name`, original `definition`, `author`
  and declared `origin`. Built-in scalar definitions are omitted.

Use repeated `--name` options (Python/JSON `names`) to export a selected
set and its transitive custom-type dependencies. An unrelated context-bound
pointer does not prevent exporting a portable structure. A fixed pointer inside
the selected dependency closure still refuses. Omit `names` to export all user
types; an empty list exports an empty catalog. Unknown, duplicate or built-in
requested names are errors.

No project pathname, source-file bytes, memory/file binding, attachment,
annotation, function identity, scene, native observation or effect contract is
included. Fixed pointer segments are refused: make a separate context-free
layout rather than carrying a DOS segment into another address model. An
unbound far-pointer layout or function ABI declaration still requires local
validation before use.

Import validates the entire incoming document and combined dependency graph
before insertion. Definitions may arrive out of dependency order. Recursive
pointers are allowed when the named target exists; recursion by value is
rejected. A missing target is not an implicit opaque declaration. Define an
explicit placeholder structure when that is the intended interpretation.

Different definitions with the same destination name fail without changes.
Identical definitions are skipped and retain destination authorship. Import
never replaces existing definitions or bindings. Empty catalogs round-trip as
no-ops. The receipt lists imported/skipped names, the receiving author, declared
source, `bindings_imported: 0` and no invalidated analysis jobs.

Budgets are 4 MiB of encoded UTF-8 JSON, 4,096 definitions, 64 KiB per
definition, and an aggregate expansion limit of 65,536 nodes/members and 4,096
union instances. Native and file layout constraints still apply when a type is
explicitly bound later. Structurally valid definitions can still be semantically
wrong for a program.

## Provenance, restart and versions

Original authorship and declared source origin survive import, restart and
re-export. The receiving operator is recorded separately. Imported rows are
marked `imported_interpretation`; local declarations are
`declared_interpretation`. These statuses do not authenticate a supplied claim.

An optional per-version origin table is created for existing schema-8 projects.
It contains no program bytes. Child byte versions inherit the current type
interpretations and origin records; subsequent changes remain local to that
child. No schema version or existing byte version is rewritten by an import.

Origins are tied to the canonical definition digest and author. A redefinition
through current APIs forgets incompatible imported origin. Export also checks
for edits made by older writers that do not maintain the new table; a mismatch
becomes `changed_local_interpretation` with the current local source instead of
silently reusing the older source attribution.

The catalog is a useful way to share a reviewed hypothesis. Native bindings,
readiness, runtime confidence and proof results stay with the project that
actually established them.
