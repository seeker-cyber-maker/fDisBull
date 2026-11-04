# Experimental component package and link contract, version 1

This specification is implemented by this example. Identifiers below are not
registered core fDisBull language profiles. Unsupported required fields, types,
versions, members and providers cause an admission failure before execution.

## Outer package

ZIP with one `manifest.json` plus `blobs/<lowercase SHA-256>` members. All members
use ZIP STORE; timestamps are 1980-01-01 00:00:00, permissions regular 0644 and
names sorted. No duplicate names, path traversal, symlinks, directories,
encryption, undeclared members or external filesystem payload paths are allowed.
No ZIP member is extracted to disk or executed by the reader.

Manifest fields are exactly:

```json
{
  "format": "fdisbull-component-package-1",
  "component": {
    "id": "logical-component-id",
    "entry": "logical-entry-asset-id",
    "requires": {"logical-port": "contract-sha256"}
  },
  "assets": {
    "logical-asset-id": {
      "kind": "typed-payload-kind",
      "media_type": "text/plain;charset=utf-8",
      "sha256": "payload-sha256",
      "bytes": 123,
      "dependencies": [],
      "metadata": {}
    }
  },
  "metadata": {}
}
```

The abbreviated digests above are descriptive placeholders, not accepted values.
Actual hashes are exactly 64 lowercase hexadecimal characters. An asset ID is
not its storage path. Multiple logical identities can share one identical blob.
Dependencies must exist and form an acyclic graph. All payload sizes, hashes and
members are checked, not only those selected by the initial scene. Every asset
is immutable; live state and checkpoints are separate products.

Canonical JSON is UTF-8, sorted keys, compact separators, no NaN/Infinity and no
ASCII escaping. Duplicate JSON keys are refused during reading. Limits: fewer
than 20,000 assets, 20,000 archive members, 8 MiB manifest, 128 MiB per payload,
192 MiB aggregate declared assets/archive output, and at most 64 required pins.
Metadata is inert annotations. Unknown mandatory behavior must be represented
by a required versioned contract, not smuggled into ignored metadata.

## Pin contracts and linking

The pilot's `CONTRACTS` objects define two generic text interaction pins:
`command` returns one UTF-8 command line or EOF; `present` consumes a text turn
with narrative, a scalar status map and ordered event receipts. No source
instruction address, calling convention or register assignment is in either
contract. Concrete contract objects are canonicalized and hashed by the tool.

A shell descriptor contains exactly `id`, `target`, and `provides`, mapping its
provider-port names to exact contract hashes. A wire map must cover each required
component port exactly once and point to an existing provider with the same
contract identity. Name similarity is insufficient. These are statically selected
built-in implementations; no arbitrary plugin/module name is imported.

The link receipt contains:

```text
format = fdisbull-component-link-1
package_sha256
component
shell { id, target, provides }
wires { required-port: provider-port }
link_sha256
```

`link_sha256` hashes the canonical receipt without that field. Retargeting the
shell leaves the package identity unchanged but changes the link identity.

## Text and reference-die components

`text.*` payloads are UTF-8 with no recovery-time whitespace/control-code
normalization. `text.index` is a source-specific binding component with format
`fdisbull-text-bindings-1`, a `bindings` map and explicit `miss_policy`.

A binding key is `<source-byte-offset>:<exclusive-limit-or-*>`. Its entry contains
an `asset` logical ID and `reads`: sorted, non-overlapping `[offset, length]`
pairs covering every byte read during decoding, including abbreviation pointers
and their referred text. This source-coordinate map is deliberately not the
universal text asset or shell interface.

`die.program` has kind `reference-die` and explicit gzip-JSON encoding. Its inner
format is `fdisbull-word16-reference-die-1`, containing:

- `program`: the unchanged legacy word16 program except its memory field;
- `memory`: `asset` reference plus `writable_end`;
- `text_index`: the binding component ID;
- `program_sha256`: identity of the exact reconstructed legacy program.

The consumer reconstructs the legacy memory field from `state.initial`, checks
the exact program digest, then invokes the existing profile validator. The gzip
reader enforces its expanded-size limit. This is a declared storage realization,
not an undocumented extension to the word16 schema.

## Runtime and checkpoint boundaries

A successful cached text lookup requires matching dependency bytes in current
memory. A miss or changed dependency invokes the retained codec and increments
explicit counters; strict mode refuses the lookup. The same guarded mechanism
is available for an indirect reference only when its selected identity is in the
index. No inference from one route silently adds unobserved bindings.

Package checkpoints use `fdisbull-text-package-state-1`, exact package SHA-256
and the existing complete word16 snapshot. They may cross qualified shell
bindings, not asset-package revisions. Host output formats do not alter die
state, source bytes, dictionary semantics or random state.

## Trust and verification

Hashes establish integrity/identity, not source authenticity, rights or semantic
equivalence. A newly authored replacement asset is a new package, not an original
fidelity result. This reader does not load executable members. A cooked ZIP
application contains selected authored host code and should be treated as an
executable, not as an untrusted data-only container.

The required evidence edges remain distinct: original source to retained model,
model/normalized-assets to selected implementation, and composed application
behavior. This pilot freshly checks the latter two against the shipped model;
it does not rerun the independent original-interpreter edge.
