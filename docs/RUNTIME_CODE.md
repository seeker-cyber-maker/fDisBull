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
COM/MZ and x86-64 PE, requires an executable mapped span, and verifies the capture's
source/version, run, mapping, CPU mode, byte hash and immutable active-layer
identities. Earlier captures without the qualified identity must be recaptured.

For a selected FreeDOS COM or MZ process on QEMU, use a project address and
`space="source"` with `debug-code` or `debug-capture-code`. Select `view="ram"`
for guest data bytes or `view="execute"` for the bytes fetched with active
instruction layers. At a stopped real-mode CPU, decoded instructions include
their runtime CS and IP. A source address may include an explicit project CS.

A QEMU capture with `metadata.static_promotion="qualified-source-capture"`
can be passed to `debug-promote-code` after the session closes. It must cover
ordinary, unpaged RAM inside the selected process's original verified module.
Promotion checks the loader mapping, producer, active layers, and stored byte
extent before creating a child. A capture that splits or changes a relocation
cannot be normalized. Real-mode linear, physical, task-private and older QEMU
captures remain available as observation artifacts.

### Protected-mode DOS LE instructions

For a stopped 32-bit LE application inside a DOS carrier, bind the original
source and capture the instruction at a guest linear address. After closing
the guest, reopen the same project and analyze the artifact offline.

```python
debug.dos_source_bind(expected_source_sha256=doom_exe_sha256)
pc = int(debug.registers()["linear_pc"], 16)
capture = debug.capture_code(pc, space="linear", view="execute", length=15)
# Later, with the original project and its private source store:
with Project(database) as project:
    decoded = project.debug_analyze_le_code(capture["artifact"])
```

The one-shot command is `fdisbull debug-analyze-le-code PROJECT CAPTURE_ID`.
It decodes the first complete instruction in the capture. The result identifies
the LE application, object and offset, the CS selector and its descriptor, and
the instruction in both runtime and preferred-address coordinates. Each
normalized offset32 operand includes its target object and offset and the
fixup record's position in the original carrier. The original MZ disassembly
and version history stay intact.

Capture requires a live protected-source binding, an unpaged 32-bit code
segment and file-backed executable bytes in ordinary RAM. A complete internal
offset32 fixup must point into a target object with a verified runtime
placement. A changed relocation operand, a truncated instruction, or an
unsupported fixup stops analysis. Each capture retains the evidence from its
own run and checkpoint epoch. To take a new capture after a cold restore, use
the fresh binding returned by `load_le_source_state`.

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
