# Semantic ports and replaceable service backends

**REVISION IN PROGRESS. Clarification, 30 October 2026.**

This refines [labels and UDC orchestration](LABELS_ORCHESTRATION_AND_ROUNDTRIPS.md)
and [RFC 0002](../0002-executable-rosetta-contracts.md). It changes no production
schema or runtime. In particular, it corrects the earlier emphasis on trying to
use a wide handle inside an unchanged DOS execution environment.

## 1. The intended target is a new native program

TiGa's intended route is:

```
16-bit original -> executable UDL and source bindings -> UIL meaning
    -> UDC for native x64 Windows + PE32+ scaffold -> new native program
```

The original addressing mode is a source implementation choice, not a mandatory
property of the recovered application. The new program may use native 64-bit
pointers, ordinary flat allocations and modern file/media services. It need not
reproduce segment-register manipulation, overlays, scratch-buffer reuse or a
small-file streaming scheme merely because the source used them. Windows x64
supports 64-bit addressing and eight-byte pointers; PE/COFF supplies the target
image and linking conventions [S1, S2]. This is semantic regeneration, not an
unchanged DOS binary placed behind a new executable header.

The source backing remains available as a reference and for exact-original
reconstruction. A portable native implementation must replace the relevant
backings and services. A hybrid may retain an explicitly declared emulator for
unresolved regions, but must not advertise those regions as native x64 recovery.

Preserve observable arithmetic independently of storage width. A logically
wrapping u16 counter may reside in a wider cell and still wrap at 65536. A
segment:offset pair used solely as a locator may disappear; meaningful aliasing
or externally encoded pointer values need an appropriate state/encoding mapping.
No requirement to preserve hidden source addresses is introduced by that mapping.

## 2. Prefer clarity over inherited resource-saving machinery

A UDC profile may deliberately use more storage, fewer buffer aliases, explicit
intermediates, straightforward control flow, predecoded media or whole-file
loading to obtain a simpler and more inspectable realization. This is a valid
objective distinct from minimizing bytes or native instruction count. Do not
assume that reproducing an old optimization is a prerequisite for fidelity.

Examples of candidate transformations, admitted under their relevant behavior
and resource domain, are:

| Source machinery | Possible new realization |
| --- | --- |
| Repeated 4 KiB reads of one stable 256 KiB asset | One logical read-all result, with a whole allocation or another implementation chosen internally |
| Several logical objects sharing a scratch window | Independent allocations with stable logical identities |
| Packed state used to save storage | Separate fields while retaining required bit/range and alias semantics |
| Decoder and device-driver bookkeeping | An imported media service and a selected codec/device backend |
| Overlaid code and far-call setup | Ordinary linked code and the target's chosen calling/continuation mechanism |

The extra space is deliberate redundancy, not permission to change wrapping,
object identity, required events or errors. Limits remain target policy rather
than a reason to encode every buffering mechanism into UIL. Resource failure
behavior and any required timing remain part of the admitted operation profile.
No performance improvement is claimed without measurement.

## 3. UIL calls describe a service, not its machinery

The intended program-level notation can remain this small:

```
contents = read_file("foo")
play_video("bar")
play_sound("blah")
```

These examples are illustrative, not added v1 opcodes. The operation names
resolve to imported, versioned definitions. A definition module may contain both
its exported meaning and its target-specific realization, with their identities
recorded separately. UIL need not hard-code a universal file API, codec catalog,
OS ABI or one implementation of sound. The UDC supplies the implementation and
orchestration behind the selected definitions.

There is nevertheless a distinction between defining what a service promises
and choosing how it fulfills that promise. The imported definition states only
what callers need to rely on: for example, the returned content or error for a
file read, or the observable playback/lifecycle behavior of a media request.
Those rules and defaults are written once, not repeated as a large descriptor
at every call site. The language core need not know how a codec works.

For a defined read-all operation on a stable ordinary file, internal chunk size,
number of native read calls and buffer placement can change while the returned
bytes and relevant errors remain the same. A streaming device or a concurrently
changing file requires a different admitted context; a read-all result must not
silently claim a snapshot the original operation never supplied. Any repeated
reads or callbacks that actually affect the game remain behavior, not disposable
bookkeeping. Windows ReadFile accepts a requested byte count; its low-level
completion/short-read handling can be hidden inside the service implementation
rather than copied into every UIL caller [S3].

For playback, expose completion, stop, repetition, synchronization or errors
only as required by the imported operation and its consumers. An implementation
can decode on demand, preload, or use an external library. Replacing a video
backend must not lose a completion signal that releases the next scene, or erase
simulation work performed while the original video ran. These are service
obligations, not a demand to preserve the old decoder's instructions.

Resource labels resolve through declared package/runtime mappings and granted
access. A simple file call does not give an imported untrusted blueprint
unrestricted host-filesystem authority. This remains an orchestration concern.

## 4. Codec substitution does not require a scene rewrite

Bind a logical resource label to an implementation-specific asset and decoder:

```
UIL:     play_sound("blah")
Profile A: "blah" -> MP3 asset + compatible playback backend
Profile B: "blah" -> Ogg/Vorbis asset + compatible playback backend
Profile C: "blah" -> predecoded PCM asset + playback backend
```

The call and logical resource identity may remain unchanged. The chosen UDC,
asset recipe and runtime dependencies change, and their receipts belong to the
build. Selecting another decoder may require packaging/converting the asset;
renaming the extension does not transcode it. Ogg is a container; Vorbis is one
codec it can contain [S7].

Equivalence is at the selected service observation boundary, not automatically
at compressed-byte or decoded-sample identity. A gameplay-level profile may
permit perceptually equivalent renditions while preserving required duration,
loop points and completion behavior. A sample-exact profile needs appropriate
assets/decoding and a stricter comparison. MP3 and Vorbis are lossy, so
transcoding does not by itself establish sample equality [S7]. An approximate
profile must state its tolerances; it is not silently promoted to exactness.
The source assets/backings can remain privately retained for exact restoration.

Swapping an eligible implementation preserves meaning. Intentionally changing
volume policy, duration, repetition or completion semantics beyond that contract
is an explicit definition/profile edit, also allowed, but not a transparent
replacement. Extensibility requires neither a frozen primitive set nor hidden
changes to the meaning of existing programs.

## 5. Application buffers are not OS pages

Three granularities must not be conflated: application I/O chunks, filesystem or
device blocks, and virtual-memory pages. The target may load the entire 256 KiB
file into one logical buffer even while the OS maps that allocation through many
pages. The application need not issue a read for each page or mention pages in
UIL. Ordinary buffered I/O differs from unbuffered device I/O, which can impose
alignment requirements [S3, S4].

Pages still support translation, protection and sharing, not only operation with
small RAM. Windows documents page-level protection and copy-on-write, transparent
physical-memory management, and separate large-page facilities [S5, S6]. More
RAM does not remove those purposes. A UDC/runtime can choose suitable allocation
or mapping policies; the blueprint normally sees the requested bytes or media,
not the OS mechanism. A flat virtual buffer is not a demand for physically
contiguous RAM, and 64-bit virtual addressing is not unrestricted physical access.

## 6. Prospective acceptance cases

These clarify the intended design; they are not executed tests.

| ID | Case | Required result |
| --- | --- | --- |
| SVC01 | Port a recovered 16-bit slice to native x64 Windows | Same declared behavior with target-native addressing; no false claim of DOS binary compatibility. |
| SVC02 | Wider storage for a logically wrapping u16 field | Preserve the wrap boundary and related signedness independently of pointer width. |
| SVC03 | Replace chunked reads of a stable asset with read-all | Same content/error contract; no per-chunk observable effects lost. |
| SVC04 | Replace source scratch-buffer reuse with distinct storage | Same logical state and meaningful aliases; accidental reuse need not remain. |
| SVC05 | MP3 backend replaced by an Ogg/Vorbis backend | Unchanged UIL call; updated asset/dependency binding; selected fidelity and lifecycle checks pass. |
| SVC06 | Backend loses playback completion or changes looping | Dependent scene test detects the changed observable behavior. |
| SVC07 | Unsupported residual code remains emulated in a PE64 package | Report the hybrid boundary; do not count packaging as native translation. |
| SVC08 | Chunk/page size or media backend changes | Recheck dependent implementation receipts, not unrelated scene meaning or logical labels. |

## References and scope

Primary documentation inspected 30 October 2026:

- S1: [Microsoft x64 conventions](https://learn.microsoft.com/en-us/cpp/build/x64-software-conventions), addressing and scalar layout.
- S2: [PE/COFF format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).
- S3: [ReadFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-readfile), requested byte counts and completion behavior.
- S4: [File buffering](https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering), buffered versus unbuffered I/O constraints.
- S5: [Virtual address space and physical storage](https://learn.microsoft.com/en-us/windows/win32/memory/virtual-address-space-and-physical-storage) and [memory protection](https://learn.microsoft.com/en-us/windows/win32/memory/memory-protection).
- S6: [Large-page support](https://learn.microsoft.com/en-us/windows/win32/memory/large-page-support).
- S7: [Xiph Ogg](https://www.xiph.org/ogg/) and [Vorbis FAQ](https://www.xiph.org/vorbis/faq/), container/codec distinction and lossy conversion.

No native PE64 port, file-service replacement, media transcode/playback, new
runtime, full repository test suite or performance measurement was executed for
this documentation clarification. Existing source/execution claims remain bound
to their prior artifacts and domains. The PR remains under revision.
