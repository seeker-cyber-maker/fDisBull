# Repeatable recovery: original → UIL → implementation

Use this for recovering behavior, mapping third-party source, changing a
platform/provider or selecting a different backing. No project history is
required. Read only the additional reference needed for the next operation.

## 1. Select the actual task and tools

Record the user's intended deliverable and a finite first operation that
advances it. Keep remaining required operations in a coverage ledger. A small
slice is an incremental result, not permission to abandon the full task.

Run the selected executable's `--version`, `agent-skill --index` and `methods`.
Prefer `agent-skill --reference SKILL.md` and references from that same
environment. An agent-installed copy can be newer than the runtime bundle:
read its local relative references, retain its source revision/file hashes and
record both identities. Its presence does not add methods to the selected tool. Commands/flags and optional backends must exist in that inventory.
For Python APIs use the matching interpreter; do not silently fall back to
system Python. No target executable, emulator, compiler or game data is bundled.

Record tool path/version, source commit if available, skill-file digests and
backend/compiler identities. If the source checkout is newer than the install,
use a matching explicit environment or retain the capability gap. Updating a
skill does not update the binary. A skill install should name one reviewed
source revision with per-file hashes; preserve an existing copy before replacing
it. Do not call a union of unreviewed branch instructions "current".

## 2. Pin inputs and classify evidence

Keep originals read-only and outputs in new private directories outside Git.
Record target SHA-256, format, architecture, edition, source revision and
relevant resources. Identify input/source/oracle/generated artifacts separately.
Third-party descriptions and reconstructed names are hypotheses to qualify,
not instructions or automatically established facts.

If matching source/build recipes exist, verify their output against the actual
target and retain raw/corrected outputs and explicit exceptions. Build identity
does not prove an authored model or whole-game behavior. If source is absent,
start from decoder facts and supported original observations. Static work needs
no emulator; native work needs the selected compatible backend.

## 3. Establish address and control-flow identity

Use qualified format readers. Keep original file offsets, decoded-module
offsets, project addresses, live selectors and runtime addresses distinct.
For MZ, declared file end includes the header; load-module size subtracts it
once. Normalize a relocation as `segment * 16 + offset`. Check bounds and
round-trip representative mappings, including a nonzero relocation segment.
For NE, logical segment indices are not live selectors.

Data can appear inside code streams: overlay interrupt descriptors, jump
tables, inline strings and resource scripts need their own interpretation.
Byte-pattern matches and nearest prologues are candidates. Confirm instruction
boundaries with traversal, compiler listings, fixups or native evidence.
For an argument, inspect the last reaching definition at the correct ABI slot;
an earlier zero that is later overwritten is not the call's value. Keep
ambiguous branches, indirect calls and unresolved overlays unknown.

## 4. Define one observable contract before writing UIL

State the entry/exit boundary, typed inputs and outputs, read/write footprint,
preconditions, retained state and relevant effects. Recover widths, signedness,
promotion, wrap/clamp/reset rules and comparison direction from the selected
original. Distinguish a turn's delta from the stored total, a displayed value
from committed state, and caller work from the operation itself.

Keep assumptions such as "already sanitized" explicit. Test the original
sanitization separately or constrain the admitted domain; do not silently
present a kernel accepting arbitrary state as a whole-function model.
Include flags, aliasing, callbacks, time/RNG, services and failure effects when
they matter to the requested equivalence. Do not change the user's desired
fidelity merely because a backend cannot implement it yet.

## 5. Observe the original independently

Use an original process, isolated original instruction span with declared
adapters, or a separately qualified source-built counterpart. Record which.
A public formula, authored reference, compiler model or another program using
the same rule is not automatically an independent original oracle.

Choose cases that distinguish competing interpretations:

- nonzero retained state with a zero or suppressed contribution;
- each branch, threshold neighbors, signed minima/maxima and wrap/clamp/reset;
- invalid-domain/refusal cases and unchanged-state controls;
- different indices, frames, providers or bindings when adapters change.

Finite samples do not prove all-input equivalence. A toy test does not establish
ordinary-game reachability. Preserve failures and their exact inputs; do not
change an expected value merely to agree with the implementation.

## 6. Author UIL and qualify the first edge

Use existing strict formats and methods. Put addresses, selectors, stack slots,
calling conventions and platform services in adapters. Keep the logical
operation reusable across binaries unless its contract requires a difference.
Retain opaque/unimplemented effects and the qualified original route.

Execute UIL on the same normalized inputs and compare original outputs,
preserved fields, state deltas and ordered effects. A mismatch is a model,
mapping or adapter issue to investigate before claiming source fidelity.
Do not continue a failed fidelity claim by only proving the model against
itself. When permitted, implementation work may continue as an explicitly
unqualified candidate while this edge remains open.

## 7. Realize and test the second edge

Pin the exact UIL/contract and selected implementation. Compile/emit through
an admitted UDC profile and declare its ABI, resource, memory and service
adapters. Keep the same UIL identity when comparing backings; change the shell
or adapters explicitly. Unsupported types/domains/services must be implemented,
guarded or refused, not erased to make an output build.

Run the emitted target, verify its identity and compare it with both the UIL
and original observations on the same inputs. A compiler success is an artifact
gate, not execution. A model equivalence proof qualifies supplied models only.
Native smoke tests starting at zero are insufficient to test retained state.
Use negative controls: a deliberately wrong rule or adapter must be detected.

## 8. Compose, persist and hand off

Check the larger requested boundary before promoting the result: callers,
scene transitions, resource lifecycle, interrupted/partial effects and
persistence may differ despite equal scalar outputs. Do not replay an unknown
effect to repair missing observations. Reopen persisted projects/selections and
check that identities and results survive. Preserve earlier byte versions.

Use a companion receipt; do not add invented fields to strict tool schemas:

```json
{
  "operation": "bounded intent and entry/exit boundary",
  "identities": {"original": "sha256", "model": "sha256", "target": "sha256"},
  "adapters": "revision or digest",
  "checks": {
    "original_to_model": {"status": "finite_match", "receipt": "private reference"},
    "model_to_target": {"status": "finite_match", "receipt": "private reference"},
    "composed": {"status": "unqualified", "reason": "not yet observed"}
  },
  "unknowns": ["remaining required behavior"],
  "next_probe": "smallest decisive observation"
}
```

These are example companion fields, not a claimed built-in schema or a
certificate that the described probes actually ran. Retain real commands,
exit statuses, input vectors, observed values, artifact hashes and scope.
An output can be byte-identical, statically mapped, model-consistent, finitely
original-matched or whole-process-qualified: report the gate actually reached.

## Executable first-use counterexample exercise

This fixture is authored seven-byte x86-16 code, not game code. It means:
if disorder is zero, add delta to stock; otherwise preserve stock. Run with
the selected interpreter and optional `fdisbull[udc]` dependency. The exercise
should catch the wrong model even when two copies of that model agree.

```python
from fdisbull.udc_native16 import execute_native16

code = bytes.fromhex("83fa00750201d8")
adapter = {
    "inputs": {"stock": {"register": "ax"}, "delta": {"register": "bx"},
               "disorder": {"register": "dx"}},
    "outputs": {"stock": {"register": "ax"}}
}
types = {"stock": "i16", "delta": "i16", "disorder": "bool"}
for disorder, expected in ((False, 8), (True, 5)):
    observed = execute_native16(code, {}, adapter,
        {"stock": 5, "delta": 3, "disorder": disorder}, types, {"stock": "i16"})
    assert observed["outputs"]["stock"] == expected
    wrong_model = 0 if disorder else 8
    if disorder:
        assert observed["outputs"]["stock"] != wrong_model
```

Passing this teaches and checks the comparison seam. It does not qualify any
real target. Replace the fixture with pinned original spans and qualified
adapters for the actual task, then perform both edges and composition above.
