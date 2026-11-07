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
- The native fallback admits one fully decoded register MOV/INC/ADD/ADC in the
  stated mode. Explicit flag outputs are the default; INC preserves carry and
  ADC always consumes it. MOV preserves all declared flags. Other aliases,
  memory, traps, OS services
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

## Native modules and nested component choices

`uil-compile` also accepts `macos-arm64`, `linux-x64` and `windows-x64` targets.
Use `uil-link` first to inspect the deterministic native lock. Source-only
emission can be followed by `uil-build` in a prepared environment, or `uil-seal`
for externally compiled files. These gates do not execute the resulting image.
Compiler temporaries must stay in the generated directory's owned `tmp` folder.

The native lock binds target, ABI, ownership, numeric profile, effects and exact
intrinsic versions/types. Known built-in C and native-assembly arithmetic
providers are selected by deterministic rules. Unknown, missing, ambiguous,
conflicting, stale or cyclic requirements refuse; a module demanding
`sound.play@2` cannot fall back to the planned version-1 service.

Per-function and per-selected-implementation requirements can specify
`"arithmetic":"portable-c"` or `"native-asm"`. A `components` map overrides
individual `add/sub/mul/and/or/xor` children. For example,
`{"components":{"add":"portable-c","mul":"native-asm"}}` retains the parent
meaning and UIL while changing its native children. Actual operation counters
and import markers qualify which children ran; a label alone is insufficient.
Other operations currently use the fixed C core.

`uil-components` accepts module/provider documents and describes a bounded
cascading choice graph. Generic declarations grant no code authority; native
emission independently admits the built-in providers. An authored
show-image→decode/blit→atomic graph demonstrates the structure, not a working
image codec. Keep decoder/device behavior unknown until separately qualified.

Scalar value numbering removes temporary physical copies from straight-line
lowering, retaining immutable source values, every logical charge and all final
slots/flags. A later source-slot overwrite cannot change an earlier copy.
Unadmitted control/array shapes keep ordinary lowering. Source children and
copy mappings remain available, and no UIL document is rewritten.

Native probes currently admit numeric/bool/resource slots and fixed arrays;
text-typed slots refuse. Effects remain bounded pending plans. Their call ledger
observes exact implementation identity/status/arity rather than full import
argument snapshots; full entry state and outputs are retained. Qualify original
instructions, full models, native execution and physical windows/devices as
distinct edges. The source guide `docs/COMMON_UIL_NATIVE.md` records the APIs,
owned ABI, runtime protocol, component contracts and evidence boundaries.

## Native desktop shells

`uil-desktop` adds a native AppKit, X11 or Win64 window over a fixed u32 arena.
Supply program, presentation, catalog, orchestration, desktop plan and initial
arena as separate documents, followed by a new private output path. Source-only
emission uses `--source-only`; `uil-desktop-build` compiles retained sources and
`uil-desktop-seal` admits already compiled artifacts. All three commands work
without an analysis project. A build or seal does not execute the application.

The host plan declares indexed function bindings, input patches, output/commit
footprints, guards, palette/frame geometry, physical-keycode mapping and clock.
Choices select sealed arithmetic/component realizations of the same UIL;
intentional algorithm changes need their own declared semantic variant.
Keep one synchronous owner and a captured selection for each transaction;
refusal preserves committed state and drawing reads an owned snapshot.

Separate typed-core, stored-frame, native-window/presentation, programmatic
callback and original-code comparisons. Constructed events do not establish
physical keyboard/mouse consumption. The source-checkout guide
`docs/COMMON_UIL_DESKTOP.md` specifies the API and current qualification status.
