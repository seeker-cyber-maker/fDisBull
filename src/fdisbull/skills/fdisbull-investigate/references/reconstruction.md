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

For concrete memory-shell backends, read the
[desktop and Win16 realization contracts](udl-uil-udc.md#win16-segmented-memory-shell).
The Win16 route preserves the full logical u32 arena through paged storage;
compiler success does not qualify segmented file transfer, GDI or input.
Its source-checkout guide is `docs/UDC_MEMORY_WIN16.md`. Keep the selected
runtime's method inventory authoritative when a skill is newer than the install.

### Progressive console support

Use this procedure for cartridge compatibility, a hardware execution provider,
or console UDC development. Keep the user's complete outcome in the coverage
ledger; a small increment advances it without replacing it. Implement only the
hardware dependencies needed by the declared boundary. A bounded code generator
does not require an independently authored emulator for every device or opcode.

Borrow the progressive replacement method from
[EmuDevz at commit 95ee5a5](https://github.com/afska/emudevz/tree/95ee5a5b0d00ddca3ec288d069409d90e5ec721f):
hold most components fixed, replace one component, run focused checks, inspect
the first divergence, then expand the supported profile. Its
[component builder](https://github.com/afska/emudevz/blob/95ee5a5b0d00ddca3ec288d069409d90e5ec721f/src/EmulatorBuilder.js)
and staged tests provide a methodological reference, not a normative hardware
specification. This procedure summarizes that method without copying lesson
dialogue. Qualify educational approximations independently before using them
as target-console facts.

1. **Select the boundary and profile.** Distinguish a machine provider that
   executes original cartridge code, a recovered UIL game model, and a UDC that
   realizes UIL through selected code and adapters. Record the target format,
   CPU/region, mapper or board variant, memory/resource layout, controllers and
   observation clock relevant to the task. Keep native emission, host-native
   execution and post-compilation multicart packaging separate. A matching
   extension, header, title screen or mapper number does not establish their
   other contracts.
2. **Qualify intake and the reference.** Pin source bytes, model, parser,
   runtime/core and configuration. Validate complete magic, version, declared
   lengths, offsets and bounds before execution; test truncated and unsupported
   cases. Preserve unknown fields and trailing data. Admit only understood
   mappings, or explicitly refuse unsupported execution while continuing useful
   inspection. For NES, do not silently reduce NES 2.0 mapper/submapper or region
   fields to legacy defaults, confuse battery-backed memory with all RAM, or
   assume trainer contents and CHR-RAM size. Reproduce a bounded baseline on an
   independently qualified implementation; an educational parser's acceptance
   is not its own compatibility oracle. A wrapper around the same implementation
   is not an independent oracle.
3. **Replace one explicit seam.** Choose the next missing capability on the
   requested path: loader/map, CPU or lowering operation, controller service,
   PPU/APU effect, scheduler, or mapper transition. Record actual provider
   identities for candidate, reference and placeholder components after
   construction, including automatic substitutions and fallbacks. Requested
   provider settings alone are insufficient. A passing hybrid run qualifies its
   tested composition; borrowed machinery remains a declared dependency. Hold
   other components fixed where possible and retain their existing evidence.
4. **Predict and compare deterministically.** Before running, define expected
   state and ordered effects, an unchanged-state case, a deliberately incorrect
   candidate or adapter, and a bounded stop condition. Require the wrong control
   to fail the intended claim. Derive expected input
   from the independent stimulus schedule and qualified controller mapping,
   never from candidate RAM. Specify whether that schedule uses CPU cycles,
   scanlines, frames or completed application ticks, and define startup and
   sampling alignment explicitly; do not shift inputs until outputs match.
   Run the narrow witness and affected regression set. Compare lengths, event
   counts and completion boundaries before values: equal shared audio prefixes
   do not establish equal streams. State the video representation, audio rate,
   channel/mix boundary and justified numerical comparison policy. Preserve the
   first divergent observation and context instead of repairing expectations.
5. **Compose devices and state.** At the needed fidelity, test ordering between
   CPU work, register effects, rendering, audio and input. Distinguish asserting
   an interrupt, CPU recognition/service and device acknowledgement; include DMA
   and bus interference when required. Equal final pixels or scalar values can
   conceal different state or effects. For checkpoint claims, include owned
   registers, buffers, mapper latches, interrupt/DMA state, clock phase, input
   cursor and pending effects; branch, restore and compare continuation. A
   serialized save object alone proves neither completeness nor durable replay.
6. **Promote only the observed capability.** Report not-run, unsupported,
   partial, finite-match or mismatch as scoped evidence descriptions, not new
   tool status fields. A budget stop before the comparison boundary leaves
   coverage partial; an observed unequal required value or effect is a
   mismatch. A known violation of a required completion deadline is itself a
   mismatch. A finite equal prefix cannot justify a completed-run claim.
   Before blaming execution for a missing event, check the observation predicate
   against actual instruction boundaries; an exclusive range-end label need not
   execute.
   Record candidate/oracle identities, actual providers, inputs, aligned
   interval, cases and fields compared, skipped gates, negative-control result,
   remaining fidelity debts and next discriminator in companion evidence.
   Promote lesson-equivalent, target-console-verified and application-verified
   claims separately. A new mapper, peripheral, region or timing requirement
   opens another gate; do not generalize from one cartridge.

For UDC output, preserve UIL semantics while selecting explicit storage, code
placement, ABI, startup/vector, resource and hardware-effect adapters. An
emulator may supply the independent execution oracle or a declared backing;
its implementation is not automatically a UIL translator. Execute the emitted
artifact and perform both edges and composition from this recipe. For a package,
qualify each admitted program and launch/bank/reset/state-isolation behavior;
header similarity cannot establish cartridge-write or RAM assumptions. Consult
the installed console profile section in `udl-uil-udc.md` rather
than treating this curriculum as new support. Keep source ROMs, assets and states
outside publications under the existing target policy; retain authored code,
attributed links and sanitized evidence separately.

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
