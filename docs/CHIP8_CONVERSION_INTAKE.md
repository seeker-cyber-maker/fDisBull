# CHIP-8 conversion intake: pinned G0 identity

This is a bounded implementation of the **G0 source-identity** slice of the
[CHIP-8 G0–G8 plan](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md).
It creates an ordinary persistent fDisBull project only after checking one
caller-supplied ROM against one caller-pinned Git-corpus manifest. It does not
resolve a reusable ISA/environment package closure, lift semantics to UIL,
produce a conversion, execute a guest, or establish G1–G8 acceptance.

After G0 intake, the separate [G1 package resolver](CHIP8_PACKAGE_CLOSURE.md)
can bind exact declared ISA/environment dependencies without changing this
source-identity receipt or running the target.

The accepted profile is explicitly `chip8-classic-pilot-default-v1`: raw
CHIP-8, 16-bit instruction words in big-endian order, 4 KiB memory, and ROM and
entry at `0x200`. The selected ROM must be 2–3,584 bytes; an odd-length data
tail is allowed. The selected manifest entry must declare `platform: chip8`.
The declaration does not independently prove dialect compatibility. SCHIP
and XO entries do not fall back to this profile, and dialect is not inferred
from a filename or byte pattern.

## Prepare the inputs

Supply an existing ROM file and a regular, nonsymlink UTF-8 JSON manifest in
the format of
[`examples/chip8_pilot/corpus/manifest.json`](../examples/chip8_pilot/corpus/manifest.json).
The caller supplies the exact lowercase SHA-256 of the manifest's **raw file
bytes** and the explicit member key. The manifest is limited to 1 MiB, rejects
duplicate JSON keys and nonfinite numbers, and has a bounded program list.
Unknown root or program fields are refused. The repository declaration must be
an HTTPS URL without user information, query or fragment; the source commit
and metadata blob must be full 40-digit lowercase Git hashes. The member key
is explicit and unique. No ZIP is opened or extracted, no network access is
performed, and no file is selected by matching its filename.

The importer checks the selected entry's size, SHA-256 and Git blob SHA-1
against the single immutable ROM snapshot returned by the loader. Those checks
and the manifest pin are completed **before** project or target-object writes.
The Git-corpus edition identity recorded by the manifest is the repository,
commit and `roms/<member>.ch8` path. An optional human edition label is retained
as attributed text, or `null` when absent. The repository, author and license
are manifest-attributed claims: matching a caller-pinned manifest does not
independently authenticate its publisher, repository contents or rights.

## Python, CLI and JSON

Choose private paths and a private target-object store. For example, with the
manifest SHA-256 obtained and checked independently by the caller:

```python
from fdisbull.chip8_intake import create_intake

with create_intake(
    '/private/analysis.fdb', '/private/member.ch8',
    manifest_path='/private/manifest.json',
    manifest_sha256=manifest_sha256,
    member='member_key',
) as project:
    receipt = project.chip8_intake_info(
        expected_manifest_sha256=manifest_sha256)
```

The equivalent CLI emits the usual JSON protocol envelope, with the receipt
under `result` when `ok` is true:

```sh
fdisbull chip8-intake /private/member.ch8 /private/analysis.fdb \
  --manifest-path /private/manifest.json \
  --manifest-sha256 "$MANIFEST_SHA256" --member member_key
fdisbull chip8-intake-info /private/analysis.fdb \
  --expected-manifest-sha256 "$MANIFEST_SHA256" \
  --expected-intake-sha256 "$INTAKE_SHA256"
```

`--profile chip8-classic-pilot-default-v1` is optional because it is the only
admitted profile. The first command creates a new project; it does not replace
an existing project. `chip8-intake-info` may also take `--version`; the original
version is required. The corresponding JSON methods are:

```json
{"method":"chip8-intake","params":{"project":"/private/analysis.fdb","path":"/private/member.ch8","manifest_path":"/private/manifest.json","manifest_sha256":"<64 lowercase hex characters>","member":"member_key"}}
{"method":"chip8-intake-info","params":{"project":"/private/analysis.fdb","expected_manifest_sha256":"<64 lowercase hex characters>","expected_intake_sha256":"<64 lowercase hex characters>"}}
```

The information method is read-only and can run after closing and reopening the
project. Its expected pins are optional; provide them when a previously
accepted identity must be checked against an outside record. It refuses a
caller-owned transaction, a patched or divergent version, unavailable or
corrupt source objects, mismatched manifest/receipt pins, or inconsistent
profile and mapped bytes. It does not bind a different source to the project.

## Receipt and storage boundary

The compact receipt has format `fdisbull-chip8-conversion-intake-1`, gate `G0`,
and status `exact-identity-verified`. It reports:

- `manifest_sha256` and `intake_sha256`;
- `source`: ROM SHA-256, byte size, Git blob SHA-1, member key and member path;
- `provenance`: attributed repository, commit, metadata blob, license, title,
  author, platform and optional edition label;
- `profile`: the explicit architecture, layout, entry, memory size and byte
  order; and
- `project`: project ID, original version and **mapped** SHA-256, plus `claims`
  that delimit the evidence.

The ROM SHA-256 identifies the supplied file bytes. The mapped SHA-256 is the
project's separate region/layout digest; the two hashes have different inputs
and must not be treated as interchangeable. The canonical `intake_sha256`
binds the manifest pin, source/member, attributed provenance, profile and
claim fields. It excludes the project ID, project path, source filename and
time, so importing the same pinned member through another path yields the same
intake digest while each project retains its own binding. No raw ROM bytes or
local paths are included in the receipt.

The original source is retained in the **required private content-addressed
object store** for later verification. This is a real private source copy;
there is no additional working ROM copy created by this intake. The project
also retains the bounded manifest text and its pin so the information method
can revalidate the selection. Protect and preserve the project and its external
object store together. An exact byte/hash match is not proof of publisher
identity, licensing, execution behavior or semantic correctness.
