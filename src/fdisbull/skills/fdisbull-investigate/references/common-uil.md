# Indexed common UIL: compose, reconstruct and qualify

Use this guide for the additive `fdisbull-common-uil-1` profile. Discover the
installed `uil-*` methods first. Original-backed DOS, legacy scalar/memory,
AGI, Zork and console profiles retain their distinct formats and limits.

The source-side UDL descriptor supplies an admitted model and its source
identity. The catalog groups exact normalized models, preserving each distinct
implementation and source assurance. UIL composes typed indexed functions and
imports. Orchestration selects exact implementations and owns call shims.
Presentation binds constants, initial values and resources. Emitted code and
runtime qualification are separate results.

## Small complete construction

The following uses only authored data and the shipped Python APIs:

```python
from fdisbull.common_uil import digest
from fdisbull.uil_catalog import build_catalog
from fdisbull.uil_runtime import execute_program

catalog = build_catalog([
    {"language": "x86-16", "code": "40", "flags": "unobserved"},
    {"language": "c-u16", "source_text": "ax += 1;",
     "inputs": ["ax"], "outputs": ["ax"]},
    {"language": "python-u16", "source_text": "ax = (ax + 1) & 65535",
     "inputs": ["ax"], "outputs": ["ax"]},
])
assert len(catalog["groups"]) == 1 and not catalog["rejected"]
group = catalog["groups"][0]
program = {
    "format": "fdisbull-common-uil-1",
    "capabilities": ["core.scalar@1", "core.calls@1"],
    "imports": [{"semantic_id": group["semantic_id"],
                 "inputs": [{"type": "u16"}], "outputs": [{"type": "u16"}],
                 "effects": []}],
    "functions": [{"variables": [{"type": "u16"}], "constants": [],
                   "inputs": [0], "outputs": [0], "max_steps": 1024,
                   "body": [{"op": "invoke", "block": 0,
                             "inputs": [{"var": 0}], "outputs": [0]}]}],
    "entry": 0,
}
presentation = {
    "format": "fdisbull-uil-presentation-1", "program_sha256": digest(program),
    "functions": [{"constants": [], "initial": ["0"]}], "resources": [],
}
plan = {
    "format": "fdisbull-uil-orchestration-1", "program_sha256": digest(program),
    "bindings": [{"import": 0, "implementation": group["implementations"][0]["id"]}],
    "ownership": "copy-in-copy-out", "max_call_depth": 32,
}
result = execute_program(program, presentation, plan, catalog, inputs=[65535])
assert result["status"] == "complete" and result["outputs"] == [0]
```

Changing the selected increment backing preserves this program and result.
Selecting an add-two implementation under the increment ID refuses. Plain
unmasked Python increment is not wrapping-u16 semantics. An alternative RNG
likewise needs a declared behavior variant, not a false equivalence claim.

## Representation and execution rules

- Variables, constants, local functions and imports use zero-based indices.
  UIL slot declarations contain types, not source names, paths or values.
- Integer presentation values use canonical decimal strings. Live inputs are
  typed values. Width/sign, cast, wrapping, signed division, eager expression
  evaluation, bounds and budget refusal are explicit.
- Fixed arrays have typed elements and lengths. Each function owns a frame;
  shims copy arguments/results and preserve caller values outside result slots.
- Local call graphs are acyclic; imported implementations are closed. Unknown
  fields/capabilities, stale identities and unsupported source operations refuse.
- The native fallback admits one fully decoded register INC/ADD/ADC in the
  stated mode. Explicit flag outputs are the default; INC preserves carry and
  ADC always consumes it. Other registers/aliases, memory, traps, OS services
  and timing are not silently supplied.
- `uil-fold` retains a function's exact children plus before/after digests.
  `uil-expand` restores them exactly. A group label grants no execution or
  proof authority; catalog matching recomputes normalized content.
- Effects (`text.show`, `image.show`, `sound.play`, `music.start`, `music.stop`)
  are plans only. `pending_host` preserves committed state and returns a separate
  proposal. Nothing is displayed/played merely because a plan exists.
- Context tickets are consumed once. A stale epoch refuses without retry.
  This pure profile allocates no GPU work and grants no physical cancellation
  or host-state-locking guarantee.

## Output and persistent handoff

`compile_program(program, presentation, catalog, plan, new_private_directory,
target="python" or "javascript")` in `fdisbull.uil_codegen` emits real source
functions/control/shims. Output requires a new directory outside Git. The
standalone JSON-lines program imports no fDisBull and does not interpret an
embedded UIL AST. Its manifest binds all documents, generator and artifact
hashes, selected implementation provenance and bounded trace/event policy.
Run the emitted program and retain its output receipt; source emission is not
execution. Origin C/x86/Python is normalized through an admitted source model;
these outputs are not general foreign-runtime/polyglot hosting.

`Project.store_uil_package`, `uil_package_info(full=True)` and `uil_packages`
retain immutable source-version-bound packages. Updating requires the current
parent. Reopen/patch checks must preserve earlier IDs and source originals.
Metadata integrity does not prove source correspondence.

Before claiming conversion, compare source/original, common model, emitted
output and composed runtime independently under the same admitted inputs and
observation boundary. Retain counterexamples and refusals. Large trace values
may be hash summaries, so use the full owned outputs/state for value comparison.

Source-checkout `docs/COMMON_UIL_CONTRACT.md` specifies all fields and limits;
`docs/COMMON_UIL_CONFORMANCE.md` records food/Snake/synthetic evidence. Keep
private initial arenas, resources, generated programs and raw target projects
outside Git and tool packages unless separately authorized and reviewed.
