# Persistent snippets and selectable UDL block layers

A logical operation can retain one typed contract while selecting a different
implementation. The project records the source captures, authored relationships,
contracts, implementations and selections as immutable, content-addressed
documents. Selection pins IDs; it does not resolve a name to whichever backing
happens to be available later.

This is a bounded prototype extending the
[cross-edition relationship proposal](uil-rfcs/0003-cross-edition-snippet-links.md).
It leaves `fdisbull-il-1` unchanged. The original byte-preserving
[DOS UDC](UDC_DOS.md), the new module UIL evaluator, isolated native block
execution, selected COM splicing and generated PE64 shells have separate
admission rules. None recovers a whole game automatically.
The [layer pilot record](UDL_LAYER_PILOT.md) records concrete experiments and
their evidence boundaries.

## Records, identities and source bytes

| Record | Format | Identity and purpose |
| --- | --- | --- |
| Snippet | `fdisbull-snippet-1` | Exact source-file and mapped-version hashes, architecture/image view, decode context, ordered spans, span hashes and authored boundaries |
| Relation | `fdisbull-snippet-link-1` | One or more source/target snippet IDs, relation kind, admitted domain, evidence, assurance, adapters and unknowns |
| Contract | `fdisbull-block-contract-1` | Typed logical ports and a fixed UIL behavior, bounded policy or admitted service |
| Layer | `fdisbull-udl-layer-1` | Exact contract ID, implementation descriptor, boundary adapter and optional source snippet ID |
| Selection | `fdisbull-udl-selection-1` | Logical binding names mapped to exact layer IDs, optionally retaining a program and target |

IDs have prefixes such as `snippet:`, `contract:`, `layer:` and `selection:`,
followed by a SHA-256 digest of the canonical document. Author and provenance
participate in that document. Created timestamps are local record metadata.
No generated host path participates in a portable endpoint identity.

Changing a definition produces another ID. Earlier records remain available;
creating a child byte version does not rebase a selection onto the new bytes.
An address alone is never the identity. In particular, NE segment indices are
[logical identities](NE_LOADING.md), not live Windows selectors or DOS paragraph
bases.

The source capture API accepts ordered spans in two explicit spaces:

```python
snippet = project.capture_snippet(
    "authored boundary",
    [{"address": "ne:4:0x54b5", "size": 124}],
    version=1,
    boundary="caller-supplied half-open extent; not a complete-function proof",
    evidence={"method": "manual source inspection"},
)

file_part = project.capture_snippet(
    "retained file bytes",
    [{"file": "source", "offset": 0, "size": 32}],
    version=1,
)
```

Replace the illustrative address and extent with facts from the owned input.
`{address,size}` captures the selected immutable mapped byte version.
`{file:"source",offset,size}` captures the original source retained in version 1;
an attached file name instead selects that version's immutable attached file.
File spans do not invent a memory address. A mapped span with an exact file
backing retains both its mapped-byte hash and original-file byte hash. These
may differ after a patch or loader transformation. Split spans at file-mapping
and allocation boundaries; allocation-only bytes have no original-file backing.

```python
metadata = project.snippet_info(snippet["id"], full=True)
explicit_bytes = project.snippet_info(snippet["id"], include_bytes=True)
span = explicit_bytes["document"]["spans"][0]
code = bytes.fromhex(span["bytes_hex"])
# source_bytes_hex is present only for an exact original-file backing.
```

Normal info/list replies are compact. `full=True` returns the document without
native payloads; `include_bytes=True` explicitly adds payloads and implies full
output. Captures validate retained source, version and payload digests. Reopen
and project copying preserve their identities without reopening an input path.
Malformed documents, invalid references, changed source bytes and inconsistent
payloads refuse. Operations use savepoints so a failed registration does not
leave partial records inside an existing caller transaction.

Limits are 4 MiB per canonical document, 256 ordered spans and 16 MiB captured
span bytes per snippet. Original and attached files retain their existing
64 MiB source limits. Lists are paginated. Byte-retaining databases, full
payload exports and compiler capsules belong outside Git.

## Cross-project links retain claims and unknowns

Use a full metadata receipt to carry an endpoint to another project:

```python
portable = left.snippet_info(left_snippet_id, full=True)
relation = right.link_snippets(
    sources=[portable], targets=[right_snippet_id],
    kind="candidate-correspondence",
    domain={"projection": "declared result ports", "input_width": 16},
    evidence={"method": "static interpretation", "notes": ["inspect helpers"]},
    assurance="candidate",
    unknowns=["caller-visible flags", "resource initialization"],
)
```

The relation is an `authored-declaration`. A caller can record an equivalence
claim and its evidence, but storing that claim does not establish a proof.
No transitivity or automatic confidence promotion follows from connectivity.
Imported metadata is an `external-endpoint-declaration`; it is not silently
reported as locally source-verified. Raw external payloads are unavailable
unless the caller explicitly supplies a complete byte-bearing receipt.

For DOS/Windows counterparts, keep separate captures and adapters. A matching
record stride, function label or result on a few inputs does not transfer a
near/far pointer convention, selector state, caller ABI or all surrounding
effects. The [Colonization food study](COLONIZATION_FOOD_EQUIVALENCIES.md)
illustrates why the operation's domain can be narrower than its containing
function. Licensed source bytes and private executable databases remain private.

## Contracts and executable backings

Use the validated execution APIs in `fdisbull.udc_layers`:

```python
from fdisbull.udc_layers import (
    register_contract, register_layer, select_layers, run_selection,
)
```

`Project.store_contract`, `store_udl_layer` and `store_udl_selection` provide
structural persistence. `register_contract` and `register_layer` also validate
the supported behavioral/backend profile. Info methods are `contract_info`,
`udl_layer_info` and `udl_selection_info`; their `full=True` documents retain
the exact references. Registrations return `{id,sha256,document}`.

An exact arithmetic contract can use the existing shared IL:

```python
add_program = {
    "format": "fdisbull-il-1", "role": "uil",
    "variables": {
        "$left": {"type": "u16", "initial": 0},
        "$right": {"type": "u16", "initial": 0},
        "$carry": {"type": "u8", "initial": 0},
        "$sum": {"type": "u16", "initial": 0},
    },
    "resources": {},
    "body": [
        {"id": "copy", "op": "set", "var": "$sum", "value": {"var": "$left"}},
        {"id": "sum", "op": "add", "var": "$sum", "value": {"var": "$right"}},
    ],
}
contract = register_contract(project, {
    "format": "fdisbull-block-contract-1", "name": "word.add",
    "inputs": {"left": "u16", "right": "u16", "carry": "u8"},
    "outputs": {"sum": "u16"},
    "domain": {"carry": {"min": 0, "max": 1}},
    "behavior": {"kind": "uil", "program": add_program},
})
```

The sum wraps modulo 65536. Carry is an explicit input whose value does not
affect this contract's sum. Flags are not declared outputs; this example makes
no flag-equivalence claim.

For an authored fixture containing `01 d8 f8 11 d8`, imported as raw x86-16 at
base `0x1000`, retain two different native backings:

```python
add_source = project.capture_snippet("ADD AX,BX", [{"address": 0x1000, "size": 2}])
adc_source = project.capture_snippet("CLC; ADC AX,BX", [{"address": 0x1002, "size": 3}])
adapter = {
    "inputs": {"left": {"register": "ax"}, "right": {"register": "bx"}},
    "flag_inputs": {"carry": 0},
    "outputs": {"sum": {"register": "ax"}},
}
layers = []
for name, captured in (("add", add_source), ("clear-carry-adc", adc_source)):
    layers.append(register_layer(project, {
        "format": "fdisbull-udl-layer-1", "name": name,
        "contract": contract["id"], "snippet": captured["id"],
        "implementation": {"backend": "x86-16"}, "adapter": adapter,
        "assurance": "candidate", "evidence": "authored instruction fixture",
    }))
selection = select_layers(project, "carry-neutral", {"math": layers[1]["id"]})
result = run_selection(project, selection["id"], "math",
                       {"left": 65535, "right": 2, "carry": 1})
assert result["outputs"] == {"sum": 1}
```

Execution requires the optional `udc` CPU-provider dependency. Registration and
source inspection are static. The source bytes above are authored examples,
not game bytes. Plain `ADC AX,BX` with incoming carry 1 would return 2 for that
case and violate the sum contract. `CLC` discharges that incoming-carry
dependency; it does not establish equivalence of all caller-visible flags.

The x86-16 provider runs actual selected instructions in an isolated CPU. Its
adapter declares input/output registers or memory, segment-region bindings,
scratch, initializers and preserved registers. Source-matched segment-word
replacements are limited to the supported MOV-immediate profile and are retained
separately from original bytes. Undeclared memory use, unsupported transfers,
wrong exits or exhausted budgets refuse. This is not a DOS or Win16 process,
and an NE logical segment index does not become its live selector.

`run_layer` and `run_selection` compare the observed outputs with the contract
for that invocation. A mismatch raises `LayerQualificationError` with a receipt.
Matching calls are finite evidence; a registration's assurance is still an
authored declaration.

## Exact behavior and intentionally variable policy

`behavior.kind="uil"` fixes the shared program's declared outputs and ordered
event plans. Changing an observed sequence requires another contract or an
explicitly broader policy.

`behavior.kind="bounded"` admits implementation variation deliberately:

```python
rng = register_contract(project, {
    "format": "fdisbull-block-contract-1", "name": "rng.seed.step",
    "inputs": {"seed": "u16"}, "outputs": {"seed": "u16"},
    "behavior": {
        "kind": "bounded", "bounds": {"seed": {"min": 0, "max": 65535}},
        "policy": "seed-step algorithm and sequence are implementation-defined",
    },
})
```

Two seed algorithms can satisfy this policy while producing different future
rolls. The range check does not prove period, distribution, fairness, security
or equivalence to an original RNG. A seeded reference algorithm that must retain
its exact sequence belongs in an exact behavior contract instead.
If the algorithm is outside the supported shared-IL operations, retain that
unsupported original dependency and its qualification boundary rather than
inventing a translation.

## Module UIL composes logical operations

`fdisbull-module-uil-1` adds explicit module invocation and unsigned remainder
to a separate profile. Its `role` can be `udl` or `uil`; changing the role does
not translate a program. Existing `fdisbull-il-1` validation and execution stay
unchanged.

```python
from fdisbull.udc_blueprint import execute_module_uil

program = {
    "format": "fdisbull-module-uil-1", "role": "uil",
    "variables": {"$seed": {"type": "u16", "initial": 9},
                  "$face": {"type": "u16", "initial": 0}},
    "resources": {},
    "body": [
        {"id": "advance", "op": "invoke", "binding": "rng", "contract": rng["id"],
         "inputs": {"seed": {"var": "$seed"}}, "outputs": {"seed": "$seed"}},
        {"id": "copy", "op": "set", "var": "$face", "value": {"var": "$seed"}},
        {"id": "reduce", "op": "remainder", "var": "$face", "value": 6},
        {"id": "one-based", "op": "add", "var": "$face", "value": 1},
    ],
}
# rng_layer_id must reference a registered layer of this exact rng contract.
chosen = select_layers(project, "rng-choice", {"rng": rng_layer_id}, program=program)
observed = execute_module_uil(project, program, chosen["id"])
```

Every invocation carries an exact contract ID and typed ports. The evaluator
checks selected bindings in untaken branches too. Unsigned remainder rejects a
zero divisor. The profile bounds nodes/depth and execution steps; failure
returns the original modeled state, no committed event plans, and retained
call receipts. It does not roll back effects in an external process.
For reproducible replay, retrieve the retained program from the selection and
pass that document explicitly. The module evaluator records the actual supplied
program's `uil_sha256`; a selection ID alone is not evidence that an arbitrary
later program argument has the same meaning.

## Model proofs and native output are separate gates

`qualify_uil(contract, implementation, timeout_ms=2000)` in
`fdisbull.udc_qualify` admits a different shared-IL implementation before PE
lowering. Exact structure can establish a shared definition, ignoring only
role/block-ID/evidence metadata while preserving resource data and event order.
Different programs use a bounded scalar Z3 profile: typed set/add/subtract,
if/eq/not/and/bit-test and require, including signed wrapping, assignment-range
refusal and atomic failure. Completion must agree, and declared outputs must
agree when complete, over the admitted typed input domain.

Counterexamples include interpreter replay. Unknown/unavailable solvers,
timeouts, unsupported event comparisons and extra unmodeled effect claims do
not qualify a different program. When the scalar solver establishes that both
programs always refuse, it labels the result `refusal-only`; a shared-definition
result leaves successful execution unqualified. Neither establishes a working
computation by declaration alone. These are model proofs, not proof
that recovered source bytes or generated native code implement the model.

There are two native output routes:

| Route | Admitted input and output | Qualification boundary |
| --- | --- | --- |
| `compile_splice_selection(project, selection, recipe, destination, output_name="PROGRAM.COM")` | A complete retained source-file snippet, exact selected x86-16 modules, and an explicit COM placement/data recipe | Hash-bound byte derivation and specified invocation checks; target callsite, relocation and continuation assertions remain explicit |
| `build_selection_shell(project, selection, plan, destination)` | A structured `fdisbull-native-shell-1` plan with supported selected UIL and notification providers; emits a new native PE32+ AMD64 program | Shared-IL admission, supported lowering and build hashes; Windows execution and visible provider effects need separate native evidence |

COM recipes use `fdisbull-udc-splice-selection-1`, `source_snippet`,
`placements`, `data_bindings` and optional `qualification_inputs`. A placement
declares its binding, original offset/size/hash, prologue, epilogue and
continuation. Supported data bindings derive ASCII text or a u8 constant from
specific UIL nodes. The fixed selected UIL must actually invoke the placed
contract. There is no automatic cave finder or general DOS linker. Source
files are unchanged; output is a new artifact with a new identity, a receipt
and a selection capsule. The first selected-splice profile is limited to a
65280-byte COM image and refuses implicit CPU-provider segment relocations.

Keep reusable module math free of target file offsets. The placement recipe,
seed load/store sequence, register preservation, pointer binding and return
continuation are separate source-specific adapters. A compatible adapter is
part of the experiment, not evidence that every surrounding game path is safe.

The first selected PE64 profile accepts canonical `$port` bindings and the
supported `u8`, `u16`, `i16` and `bool` native cells. Nonempty contract/layer
domains are refused until the bridge emits their native guards. Activation
copies declared inputs, initializes local variables per invocation and commits
declared outputs. Arbitrary port aliases, x86-16/NE backings, exception unwinding,
reentrancy and recursive function graphs are outside this profile. Loops and
resource/code slots are bounded. A matching model result does not relax those
native admission checks.

The shell input budget is 1 MiB for the plan and modules together, with at most
32 bindings, 128 native state cells, 16 functions and 32 text resources. The
module UIL profile permits at most 1024 blocks and depth 32, with an explicit
execution budget up to 100000 steps. Isolated x86-16 blocks also have an explicit
instruction budget and must fit their declared 16-bit origin/exit boundary.
These bounds describe the implemented profiles, not general compiler support.

The native notification profile is `ui.notify` (with admitted notify aliases),
with no outputs and at most one u16 input. Its current providers are
`MessageBoxA` and `OutputDebugStringA`; they are not interchangeable with an
arbitrary service merely because a label changes. Text event plans are queued
until pure qualification succeeds. A service failure after commit is explicit;
there is no transparent fallback that could duplicate an already emitted effect.
Graphics, audio, file/media services and general callbacks remain outside the
first PE profile.

## Logical services and state bridges

A future `read_file` operation should describe logical resource identity,
offset/length, returned bytes/status, ownership and partial-read/failure rules.
Source provenance can point to a DOS file service, a Windows library call or
an authored provider, while an adapter supplies the concrete handle, pointer,
buffer and error representation. The current notify backends explicitly do
not implement `read_file` or media services. This is not an automatic sweep or
replacement of BIOS calls.

Providers need not share one physical state arena when their adapters explicitly
bridge authority and values. The current PE shell uses its declared word-carrier
arena; the isolated CPU provider has its own regions. A general cross-provider
bridge must account for aliasing, ownership, callback lifetime, ordered effects
and failure after mutation. Do not infer those properties from matching scalar
ports or a persistent snippet link.

## Agent surface and verification

The JSON methods are discoverable through `fdisbull methods`. They include
`capture-snippet`, `snippet-info`, `snippets`, `link-snippets`,
`snippet-link-info`, `snippet-links`, `store-block-contract`,
`store-udl-layer`, `select-udl-layers`, `run-module-uil`, `run-udl-layer`,
`run-udl-selection`, `build-udc-shell` and `compile-udc-splice`. Read methods
retain compact defaults; request full documents and byte payloads explicitly.

Authored regressions are in `test_snippet_links.py`, `test_udc_qualify.py`,
`test_udc_layers.py`, `test_udc_blueprint.py`, `test_udc_native16.py`,
`test_udc_layer_api.py`, `test_udc_shell.py` and `test_udc_splice.py`.
They cover persistence, identity/tamper failures, typed policy and model
comparisons, native/provider boundaries and emitted artifacts. Runtime tests
can skip when their separately prepared dependency or native backend is
unavailable; a skipped test establishes no native result. Game inputs,
byte-retaining projects, compiler capsules and native traces remain outside Git.
