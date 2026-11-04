# Format modules and bounded media variants

A **format module** names a versioned file/header specification and its linked
reader capabilities. A decoder module names code which interprets instructions,
resources or media. Keep these identities separate: a recognized signature does
not prove a complete supported decoder, valid executable loading or native game
compatibility.

## Start with bytes

```text
fdisbull format-modules
fdisbull file-identify /private/input
fdisbull file-identify /private/input --catalog /private/formats.sqlite
fdisbull format-modules --catalog /private/formats.sqlite
```

The SQLite catalog retains minimal signature/field facts, module revisions,
static API bindings, provenance and limitations. The tool writes no inspected
file bytes and loads no executable plugins. An exact shipped catalog reports
`contains_file_payloads: false`; custom/future content is preserved within the
metadata bounds and reports `null` because its content is unverified. The default
catalog is in memory; an explicit path persists/reopens the same versioned facts.
Catalog metadata cannot authorize importing arbitrary Python code or executing
an input.

Identification reports architecture where supported, available embedded image
views, declared metadata and scoped recognition/validation status. For an MZ
container, preserve the distinction between its real-mode loader, a secondary
LE/NE/PE image and an unexplained tail. A valid stub is not a loaded protected-
mode engine; an overlay's presence is not a recovered overlay directory.
Large-file sampling is bounded and labelled. Unknown formats remain unknown;
unsigned formats such as COM need an explicit selection rather than a guessed
architecture based on their suffix.

Before web research or writing another parser, inspect the catalog's available
reader and codec entry points. It connects the existing binary/image-view,
console, archive and media seams. If a format or variant is missing, add its
minimal header facts with provenance and explicit unsupported capabilities,
then implement a bounded reader with authored fixtures. Do not label a codec
implemented merely because its signature is recorded.

## Frame native SMK2 movies

```text
fdisbull media-inspect /private/original.smk --adapter smacker
fdisbull smk-frame /private/original.smk /private/new-framed-output
```

The output directory must be new, beneath an existing private parent outside
Git. The default keeps 32 opening and 32 ending images. Native FULL blocks
reproduce retained indexed pixels and palettes; native SKIP blocks hold the
preceding image between them. Geometry, frame numbering and timing stay the
same. Original compressed audio packets stay at their original frame positions.
This reduces storage; it does not necessarily reduce playback time.

Framing requires working FFmpeg and ffprobe tools. The command verifies complete
source and derived video decoding, every retained image and its palette, and
complete decoded audio before accepting an output. A manifest records input/
output identities, retained positions, native tree/index reconstruction and
qualification limits. It does not patch or launch an executable.

The first implementation deliberately bounds source/output size, frame count,
pixel count, retained image memory and decoder work. Unsupported ring/scaling
layouts and unexplained packet extents refuse instead of being rewritten.
`--keep-frames`, `--max-movie-bytes` and `--timeout` control bounded behavior;
they do not authorize storage growth. Follow the caller's storage admission
rules before generation.

## Qualify the consumer separately

For an original-game check, hash executables before/after, use a private writable
runtime tree and show that the original program consumed the exact derived file.
Record entry/selection, frame progress, full completion versus user skip, and
return to the expected screen. Independently decoded pictures or opening a file
in a standalone player do not establish this integration.

Prepared-state/RAM-assisted invocation is useful for a late ending, but label it
beside the result. A movie routine returning is not a natural campaign playthrough.
Preserve failed baseline routes and distinguish decoder output, rendering,
audible output, arbitrary seeking and whole-game behavior. Canonical inputs
stay separate from the compact variant and all licensed media stays private.
