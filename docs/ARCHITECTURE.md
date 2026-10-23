# fDisBull 0.1 architecture

fDisBull is a local disassembly project whose public interface is structured commands.
Imported code is parsed and decoded; the tool never executes it. Python coordinates
native iced-x86, Capstone and LIEF libraries with SQLite and Pillow.

## Modules

| Module | Responsibility |
| --- | --- |
| `model.py` | Immutable in-memory image, region and seed records. |
| `loader.py` | Bounded raw/ELF/PE/thin Mach-O loading into static virtual-address mappings. |
| `decoder.py` | One-instruction decode and directly recoverable control/data references. |
| `project.py` | SQLite persistence, analysis queue, annotations, queries and version creation. |
| `cli.py` | CLI argument handling, request dispatch and JSON response envelopes. |
| `render.py` | Database-snapshot SVG/PNG export without a graphical desktop. |

## Address and byte identity

A project currently has one architecture, bitness and flat address space. Instruction,
function, cross-reference, annotation and work records carry both a version and a
decode context such as `x86:64:little`. Addresses are zero-padded hexadecimal SQLite
text, preserving unsigned 64-bit ordering without SQLite signed-integer overflow.
Public responses use `0x`-prefixed hexadecimal strings.

Each version stores complete mapped regions as byte blobs, permissions, a parent,
label, origin, timestamp and mapped-image digest. The application preserves existing
byte versions: `patch` creates a child and leaves its parent available. A mapped-image
digest includes region descriptions as well as bytes; it is distinct from the source
file SHA-256. Patches change the project snapshot, not the original executable file.

Imports use preferred static virtual addresses. Runtime relocations and process
load biases are not applied. ELF load segments, PE headers/sections and Mach-O
segments supply the mappings; overlapping or oversized mappings are rejected.

## Analysis and evidence

Entry points and loader-provided function seeds start a persisted work queue. A user
can add a seed with `analyze --start`. Analysis decodes bounded work, follows direct
branches/calls and permitted fallthrough, and persists instructions and references.
Direct call destinations become function candidates. Queue states and details retain
pending work, invalid bytes, addresses outside executable mappings and unresolved
indirect control flow. A budget-limited run can resume from the queue.

Function entries are candidates, not established function boundaries. This release
does not build a complete CFG, infer function ownership, recover jump tables, prove
code/data classification, perform symbolic execution or provide decompilation.
Static references are those the decoder can resolve directly; unresolved segment
bases and indirect targets remain unresolved.

Annotations are versioned names or comments with an author and timestamp. Child
patches inherit them and mark their origin. **Inherited annotations require semantic
revalidation after byte changes.** Child analysis starts with a fresh queue rather
than copying the parent's decoded instructions and cross-references. Manually
supplied byte versions support later SMC work; runtime SMC capture is not implemented.

## Agent interface and views

`serve` reads one JSON object per stdin line and emits one stdout response per request.
Requests carry `id`, `method` and `params`; responses carry `id`, `ok` and either
`result` or `error`. This is a local JSON-lines protocol, not MCP or JSON-RPC, and it
opens no listening socket. One-shot CLI commands use the same dispatcher.

Disassembly queries return stored instruction rows and annotations from one database
snapshot. They do not silently decode gaps. Rendering consumes that snapshot and
exports SVG/PNG with byte-version provenance. Long text wraps; excessive views fail
explicitly. A future native UI should consume the same query/snapshot interfaces.

## Current boundaries

The decoders support flat raw x86 16/32/64-bit and little-endian ARM64 code. Native
executable loading supports the selected x86/ARM64 variants in ELF, PE and thin
Mach-O. DOS MZ segmented loading is missing: raw x86/16 accepts an already extracted
flat code segment, not a complete DOS executable. Fat Mach-O, big-endian images and
relocatable object files also require further loader work. There is no emulator,
debugger connection, multi-address-space model, automatic LLM agent or native UI.
