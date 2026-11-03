# CHimpREC captured-image recovery and PE rebuilding

fDisBull's CHimpREC support separates four jobs that older interactive unpacking
tools often presented in one window:

1. **Capture** a process/module image and loaded-module export map with a
   compatible debugger.
2. **Recover** candidate IAT cells from explicit slots or bounded decoded code
   references.
3. **Repair** ambiguous, redirected or invalid thunk entries with explicit
   decisions.
4. **Rebuild** a PE32 or PE32+ analysis image around the captured bytes, original
   IAT addresses and qualified original entry point (OEP).

The current implementation performs jobs 2–4. Process launch, anti-debugging
handling, attachment, memory capture and export enumeration remain backend
responsibilities. A capture receipt records that boundary instead of allowing a
mapped image to masquerade as a native Windows observation.

## APIs

```python
from fdisbull.chimprec import (
    recover_iat,
    build_import_plan,
    rebuild_captured_pe,
    validate_capture_manifest,
)
from fdisbull.chimprec_pe import inspect_pe_imports
```

`recover_iat` supports PE32 and PE32+ pointer widths, explicit candidate cells,
common decoded x86/x64 import references, ordinals, forwarded-export evidence,
alias preservation and bounded expansion around confirmed export-address
anchors. `code_ranges` can qualify runtime-executable or independently
established code even when a dumped PE section retained stale characteristics.
The override is evidence, not proof that every byte in the range executed.

`build_import_plan` never guesses an ambiguous export. A caller selects an
alternative by index, or marks an invalid candidate as `cut` or `separator`.
Noncandidate expansion noise is retained in the recovery result but never
silently becomes an import.

`rebuild_captured_pe`:

- preserves original IAT virtual addresses used by the application;
- emits new `IMAGE_IMPORT_DESCRIPTOR`, OriginalFirstThunk/ILT, DLL-name and
  import-by-name structures in a `.reimp` section;
- supports named and ordinal imports for PE32 and PE32+;
- sets the qualified OEP;
- clears the invalid Authenticode certificate and stale bound-import metadata;
- defaults to a fixed-base analysis reconstruction by clearing ASLR/relocation
  claims, or retains existing relocation metadata when explicitly requested;
- recomputes the PE checksum and validates the rebuilt import directory with an
  independent reader.

The output is **not** a byte-identical reconstruction of the unknown pre-packer
file. Auxiliary unpacker sections can remain, code/data layout reflects the
captured module, and a valid structure does not prove successful Windows
initialization.

## Capture provenance

`validate_capture_manifest` accepts `fdisbull-chimprec-capture-1` documents. A
record identifies:

- source hash and size;
- process and parent-process topology;
- threads and selected thread;
- runtime regions, protections and optional hashes;
- selected module base/extent and OEP;
- the observed jump, call, resume or thread-start transfer to that OEP.

This supports ordinary single-module unpacking and more complicated cases where
a launcher creates a suspended child, writes an injected region or starts a
remote thread. The receipt contains no captured bytes and does not authenticate
the debugger. It prevents evidence from one process/thread/module generation
being silently applied to another.

## Example: rebuild from supplied capture files

A projectless GOG Galaxy coordinator is exposed as:

```bash
python -m fdisbull.gog_galaxy_cli \
  owned-wrapper.exe mapped-module.bin capture.json loaded-exports.json \
  /private/new-galaxy-rebuild \
  --candidate-slot 0x00473000 \
  --candidate-slot 0x00473004 \
  --decisions thunk-decisions.json
```

The output directory is new and contains:

- `galaxy-wrapper-unpacked.exe`;
- `gog-galaxy-rebuild.json` with source, capture, OEP, import and output hashes.

`--candidate-slot` is repeatable. Omitting it uses bounded decoded references in
runtime-executable regions from the capture receipt. A decisions file maps thunk
addresses to `"cut"`, `"separator"` or `{"alternative": N}`. The coordinator
never downloads a game, launches Galaxy or attaches to a process.

## Historical compatibility cases

The accepted model deliberately covers decisions found in the retained legacy
CHimpREC material:

- OEP transfers through jumps, calls, resumed primary threads and remote-thread
  starts;
- stale file section flags versus actual executable runtime pages;
- named, ordinal, forwarded and aliased exports;
- missing separators, junk thunks and decoy functions;
- rebuilding OriginalFirstThunk arrays while keeping the application's IAT;
- PE32 and PE32+ images;
- multi-process/injected-region provenance.

The implementation does not yet provide a general 32-bit Windows/Wine attachment
backend, automatic anti-debugging defeat, API-emulation classification or a
universal protector tracer. Those remain explicit capture/backend work rather
than hidden heuristics in the writer.

## Acceptance boundary

A rebuilt image is accepted only after its descriptors, lookup tables, original
IAT slots, OEP, section bounds and checksum read back consistently. Meaningful
execution still needs a compatible Windows/Wine environment and genuine loader
state. Proprietary wrappers, memory dumps and reconstructed executables stay in
private workspaces; authored fixtures and source-free receipts belong in Git.
