# Temporal runtime code interpretations

Version 0.16.0 adds an explicit bridge from a runtime byte observation to the
persistent analyzer. Capturing code remains an observation; it does not change
existing disassembly or prove that the CPU executed the captured bytes.

```python
# Within an original-version DOS or custom PE64 debugger session:
capture = debug.capture_code("334b:0c9e", cs=0x334b, length=8, view="execute")
# Close the emulator, or reopen the project later:
child = project.debug_promote_code(capture["artifact"], max_instructions=64)
version = child["version"]
view = project.disassembly("334b:0c9e", cs=0x334b, version=version)
project.runtime_version_info(version)
```

PE64 uses flat project addresses and omits `cs`. Promotion supports real-mode
MZ and x86-64 PE, requires an executable mapped span, and verifies the capture's
source/version, run, mapping, CPU mode, byte hash and immutable active-layer
identities. Earlier captures without the qualified identity must be recaptured.

The child is a mapped-byte interpretation, not a reconstructed executable.
It retains the original container in its parent and has no replacement disk
image. Only the captured span is observed; all other mapped bytes are inherited
and explicitly unobserved. Unchanged known loader fixups are normalized into
project space. Partial, overlapping, modified or unsupported fixups are refused
rather than guessed. The raw runtime artifact is preserved unchanged.

The analyzer decodes fresh facts and traverses targets from the captured start
with its actual project CS context. Captured general registers are provenance,
not assumptions about other entries. A bounded analysis can leave pending work;
its budget stop is never called stable. A second promotion of the same capture
reuses the child and can continue analysis. A RAM capture and execution-view
capture produce separate siblings, even when their bytes happen to agree.

Ordinary `project.patch(..., version=version)` creates a further authored child.
It does not replace the capture or its parent. Annotations and authorship are
inherited; derived instruction/xref/CFG facts are rebuilt. Disassembly, xrefs,
CFG and stored-state PNG/SVG exports expose temporal provenance. Query the
original explicitly with `version=1` and launch the debugger from that original
version; a temporal interpretation is not a launchable patched EXE.

A stored trace can be compared offline with the interpretation:

```python
comparison = project.debug_trace_view(trace_artifact, version=version)
```

This compares each available instruction's actual byte stream and CS/address
context. It retains the native observation/completion stage, reports unmatched
or unsupported observations explicitly, and never assigns an entire trace to a
version based on address alone. Bytes matching an inherited region are still
unobserved in the code capture. A matching instruction is not evidence that the
whole temporal version executed.

The foreground JSON methods are `debug-promote-code`, `runtime-version-info`
and `debug-trace-view`; all three also work offline through one-shot CLI
commands, for example:

```bash
fdisbull debug-promote-code private.fdb CAPTURE_ID --max-instructions 64
fdisbull runtime-version-info private.fdb --version 2
fdisbull debug-trace-view private.fdb TRACE_ID --version 2
```

Runtime artifacts can contain program bytes. Keep private databases/states out
of Git. The authored branch test proves changed CFG edges, restart and patch
isolation; the DinoPark lookup test proves a changed operand and observed price,
not a completed purchase or reconstructed game binary.

## Feeding observed code versions into patch analysis

For x86-64 Wine/QEMU, `debug_compare_runtime_code` connects two explicitly
promoted captures to the existing regional analyzer. Supply a completed trace
for each interpretation and an explicit live-state contract:

```python
report = project.debug_compare_runtime_code(
    original_child["version"], modified_child["version"],
    original_trace["artifact"], modified_trace["artifact"], contract={})
```

An empty contract keeps all modeled GPRs and FLAGS live. Each trace must contain
at least the modeled instruction and a following pre-instruction state. Capture
the exit instruction too: both the region and its exit boundary must be fully
observed, match the temporal byte interpretation, and have analyzed instruction
facts. A one-event trace cannot supply its missing terminal register state.

The bridge checks the stored artifact hashes, owning source/run, loaded-address
mapping and observed byte view. It retains the native trace's original source
version and records the temporal version separately. Matching an address alone
does not assign execution to a whole code version. It performs no promotion or
artifact mutation implicitly, and authored edits are not treated as observed
captures. An explicit `correspondence` list uses the **original trace identities**
when entries or exits move between encodings. The existing private-RAM evidence
and timeout options are also accepted.

The result's `regional` field contains the bounded difference witness or
equivalence-under-contract report. Equivalent regions retain an expandable
contraction; use `expand_pe_contraction` with the exact original traces. Whole
function/module equivalence, external effects and timing remain outside this
claim. The PE64 model includes register/immediate dword MOV zero-extension into
the full GPR; byte/word aliases and dword memory loads/arithmetic remain unknown.

The same operation is available offline through JSON and the CLI:

```bash
fdisbull debug-compare-runtime-code private.fdb 2 3 TRACE_A TRACE_B --contract '{}'
```

`tests/test_smc_patch_analysis_wine.py` is the native known-source acceptance:
original `MOV EAX,1`, guest-modified `MOV EAX,2`, and an explicitly layered
`MOV RAX,2` encoding control. Its region ends at the native RET pre-state, so
the proof does not interpret RET or infer caller/ABI effects. The guest's
ordinary first/second calls are checked separately. Register seeds and
debugger-directed probes are recorded; exact difference-witness replay on
Unicorn stays distinct from Wine execution. Original captures and static version
1 remain preserved.
