# CHIP-8 compatible package closure

This guide describes the bounded **G1 declared package-closure** step in the
[CHIP-8 G0–G8 plan](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md).
Begin with an original, verified [G0 intake](CHIP8_CONVERSION_INTAKE.md).
G1 binds that exact intake to separately versioned ISA and environment package
definitions. It checks declared compatibility; it does not prove that a ROM
conforms to a dialect, qualify instruction semantics against historical hardware,
or perform the remaining conversion work.

The admitted ISA is `isa:chip8-classic-qemu-v6:1`; the caller must explicitly
select `env:chip8-qemu-v6:1`. Their contracts describe the bounded
`chip8-classic-pilot-default-v1` profile and the corresponding v6 environment.
They are separate definitions: a compatible ISA name alone does not select an
environment or prove compatible device and quirk behavior. Inspect the catalog
for the exact version, SHA-256, contract fields and evidence labels used by this
copy of fDisBull.

## Discover and resolve

The package catalog is available without a project or guest:

```sh
fdisbull chip8-packages
```

The CLI emits the usual JSON envelope: a successful response has `ok: true`
and the catalog or receipt under `result`. In Python, use a verified original
G0 project and supply the environment explicitly:

```python
from fdisbull.chip8_packages import catalog
from fdisbull.project import Project

packages = catalog()["packages"]
by_id = {item["id"]: item for item in packages}
isa = "isa:chip8-classic-qemu-v6:1"
environment = "env:chip8-qemu-v6:1"
pins = {isa: by_id[isa]["sha256"], environment: by_id[environment]["sha256"]}

with Project("/private/analysis.fdb") as project:
    closure = project.chip8_closure_resolve(
        environment=environment,
        pins=pins,
        expected_intake_sha256=intake_sha256,
    )
    checked = project.chip8_closure_info(
        closure["closure"], expected_intake_sha256=intake_sha256)
```

Pins are optional, but if supplied they must name **both** built-in IDs with
their exact catalog hashes. Save independently accepted hashes when reproducible
selection matters; do not silently substitute the newest catalog values for a
previously accepted pin. An update to either definition changes its hash and
requires a new compatible selection. `expected_intake_sha256` is also optional;
provide a previously accepted value when the source binding must match an
outside record.

The equivalent CLI calls are:

```sh
fdisbull chip8-closure-resolve /private/analysis.fdb \
  --environment env:chip8-qemu-v6:1 \
  --expected-intake-sha256 "$INTAKE_SHA256"
fdisbull chip8-closure-info /private/analysis.fdb "$CLOSURE_ID" \
  --expected-intake-sha256 "$INTAKE_SHA256"
```

Resolve additionally accepts `--requirements`, `--pins` and `--runtime` as JSON
objects, `--include-analysis`, and `--version`. Info accepts `--version` and
`--expected-intake-sha256`. The corresponding JSON methods use the same names
and argument fields:

```json
{"method":"chip8-packages","params":{}}
{"method":"chip8-closure-resolve","params":{"project":"/private/analysis.fdb","environment":"env:chip8-qemu-v6:1","expected_intake_sha256":"<accepted G0 digest>"}}
{"method":"chip8-closure-info","params":{"project":"/private/analysis.fdb","closure":"<closure ID>","expected_intake_sha256":"<accepted G0 digest>"}}
```

## What the closure binds

The receipt format is `fdisbull-chip8-closure-1`. Its source binding includes
the G0 intake, original source and mapped-version identities; its package
references identify the selected architecture and environment definitions by
ID and digest. Package-definition hashes are source independent. The closure is
source bound: a second ROM can select the same compatible ISA and environment
definitions, but retains its own G0 identity and closure. Similar names or an
architecture label do not transfer target observations or semantic proof.

`requirements` is an optional nested exact-match subset of the catalog's
`architecture` and `environment` contracts. Unknown fields, mismatched values
or incompatible declarations refuse; they are not silently relaxed. Resolve
validates the source, requirements, package identities and optional declarations
before initializing or writing the project's immutable definition and closure
records. Repeated resolution and cold inspection revalidate the stored identities
and dependencies. Neither operation runs the guest, decodes instructions, or
repeats a behavioral proof.

Definition records follow the project's existing private object-store policy;
some metadata is externalized there as well as the original source objects.
Keep the FDB and its object store together. Missing or changed definition
objects refuse inspection. Catalog and closure replies contain identities and
declarations rather than raw ROM bytes.

An optional runtime is a **caller-declared, unverified** identity, subject to
strict admitted fields and profile compatibility. It is not a path to probe, a
launch request, or evidence that a binary exists or passed tests. If requested,
`include_analysis` records a bounded digest of the original version's
`instructions`, `functions`, `xrefs`, `work` and `analysis_state` tables. It does
not fingerprint every project fact, run analysis or qualify those records.
Changes outside those five tables, such as annotations, are outside that pin.
Inspection refuses a stale included-table binding instead of presenting changed
records as the original closure. Without
these options the runtime and analysis bindings are absent.

G1 itself does not perform source mapping or qualify G2–G8. The separate
[bounded original-source map and typed UDL candidate](CHIP8_SOURCE_MAP_UDL.md)
uses this closure to retain PCs, words, spans, control contexts and explicit
frontiers; its cold verification does not make the candidates executable common
UIL or independent semantic proof. G3–G8 source-to-UIL qualification, target
selection, executable comparison and delivery remain separate work. The
DOSBox-to-QEMU migration gate is independent of this
CHIP-8 declaration; DOSBox remains the default, with its separate outstanding
141 unqualified surfaces and seven campaigns in the current gate unchanged by a
G1 closure.
