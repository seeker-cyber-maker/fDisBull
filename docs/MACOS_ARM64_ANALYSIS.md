# macOS ARM64 investigation boundary

This source branch adds a bounded investigation path for an exact ARM64 slice
of a thin or universal Mach-O executable. The base 0.27.0 loader and Capstone
decoder already import, traverse and persist native instruction facts. These
additions preserve exact source backings, offer optional Ghidra comparison and
decompiler diagnostics, and permit one explicitly requested LLDB launch to a
named breakpoint. The analyzer remains the owner of traversal and the FDB.

Keep the executable and FDB private outside Git. Read
[external target policy](EXTERNAL_TARGETS.md) and the bundled
`fdisbull-investigate` skill before investigating an external application.

## Static path

```text
fdisbull identify /private/program
fdisbull inspect /private/program --slice-arch arm64
fdisbull import /private/program /private/program.fdb --slice-arch arm64
fdisbull analyze /private/program.fdb --max-instructions 10000
fdisbull analysis-status /private/program.fdb
fdisbull code-backings /private/program.fdb --entry 0x100001000
fdisbull render /private/program.fdb /private/entry.png --address 0x100001000 --lines 20
```

Select the actual entry or another stored candidate address; `0x100001000`
is illustrative. `code-backings` now supports Mach-O ARM64 as well as its
existing x86 profiles. For ARM64 it retains 4-byte decoded instructions,
selected-slice identity, original-container file offsets and bytes, mapped
addresses, byte version and unresolved indirect transfers. It validates
against the retained source and mapped version after reopening the project.
An incomplete graph or a stopped analysis budget remains incomplete. The
raw x86 `code-blocks` and `code-layout` realization paths are not ARM64 paths.

On a fresh import, the loader also records candidate seeds from Mach-O
`LC_FUNCTION_STARTS` and unwind function offsets. It resolves their relative
offsets against `__TEXT` and accepts only aligned, file-backed addresses in
declared executable instruction sections. These are traversal candidates,
not confirmed function semantics. An FDB imported before this source change
keeps its original seed set; import a new FDB to use the additional seeds.
Analyze with a bounded instruction budget and inspect pending work before
calling the graph stable.

`inspect` may return a private output-artifact reference for a large Mach-O.
Use `output-select` or `output-read` on that artifact to retrieve the needed
fields rather than repeating the inspection.

## Optional Ghidra fact and C diagnostic

Ghidra 12.2's headless loader, AArch64 disassembler and decompiler were
qualified locally on an authored ARM64 fixture and two selected instructions
from the installed Simple Menu STATUS executable. The command requires an
imported original-version project and a file whose size and SHA-256 match its
recorded source. It does not change the project or execute the target.

```text
fdisbull ghidra-arm64 /private/program.fdb /private/program \
  --address 0x100001000 \
  --analyze-headless /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless \
  --java-home /opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home \
  --decompile-entry 0x100001000
```

Ghidra receives a temporary byte-identical thin slice. A restricted decode
returns only caller-selected preferred static addresses, with original fat-file
offsets and bytes alongside Ghidra's loaded bytes. Chained fixup overlap and
uncertain fixup enumeration remain visible. The optional `decompiler_diagnostic`
is a separate bounded C listing from a 4 KiB entry window; its output is not
used to assert instruction facts or semantic equivalence. Static preferred
addresses are not runtime addresses. Ghidra facts are diagnostic output; the
FDB analyzer continues to own stored traversal and annotations.

## One-stop LLDB observation

`macos-observe` explicitly launches the supplied exact-source executable under
Apple LLDB, stops at one named symbol breakpoint, records bounded register,
memory, instruction and image-map facts, then ends that child. It does not
attach to a running process or create a persistent debugger session. Run this
only with an executable whose execution is authorized. Validation used an
authored ARM64 fixture; the installed Simple Menu STATUS app was not launched
or attached by this backend.

```text
fdisbull macos-observe /private/program.fdb /private/program \
  --symbol main --memory-bytes 32 --instruction-count 8
```

The receipt distinguishes breakpoint stop, unresolved symbol, permission
denial, unexpected stop, timeout and unconfirmed or mismatched identity. It
includes the source and selected-slice hashes, Mach-O UUID when available,
runtime image base and ASLR slide. `pc_static_va` is a preferred virtual
address, not a file offset. Runtime output is an observation of one launch,
not an authentication proof for an adversarial executable.

## Path to an app-level UIL candidate

These tools establish source bytes, selected native code and a bounded runtime
address mapping. Translating a SwiftUI app requires additional evidence:

1. Resolve Swift metadata, protocol witnesses, Objective-C selectors, dynamic
   dispatch and framework calls into candidate app actions and state.
2. Observe each selected control through input delivery, state change, redraw
   and persistence in the original runtime, including controls that do not
   produce direct code references from the entry point.
3. Define the UIL interface contract for visible controls, focus, enabled
   state and event completion. The linked-interface proposal in
   [PR #7](https://github.com/seeker-cyber-maker/fDisBull/pull/7) is still a draft.
4. Bind each authored semantic rule to original byte spans and runtime
   observations, then validate an exported candidate against named original
   behaviors. The general UIL exporter described in [UIL_BOUNDARY.md](UIL_BOUNDARY.md)
   is not implemented by these probes.

A small entry-point disassembly, Ghidra C text or a matching screenshot is
insufficient to call the application translated or interface-parity complete.
