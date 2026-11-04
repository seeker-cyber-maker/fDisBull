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

## Use the same catalog for single-game and batch intake

```text
fdisbull --output-artifact-dir /private/reports intake-inventory /private/game --catalog /private/formats.sqlite
fdisbull --output-artifact-dir /private/reports intake-inventory /private/game-a /private/game-b --catalog /private/formats.sqlite
```

The inventory phase never extracts, executes or modifies inputs. Keep the
catalog and report/artifact directory outside every input root. Bounded
enumeration/alias preflight precedes catalog writes. Incomplete enumeration uses
an in-memory catalog and records that requested persistence was not performed.
`complete` describes filesystem accounting only; archives and embedded resources
are separate recovery items. Regular-file links retain opened descriptor identity;
directory links are reported without recursive traversal. Never follow a runtime
`SWARS -> .` alias while archiving or recursively scanning.

Inspect `recovery_queue`: unknown formats/context candidates, unsupported or
invalid variants, unexpanded containers/embedded media, decoder recovery and
available readers awaiting validation are distinct. Read/entry/file/depth budget
stops and I/O errors are incomplete observations, not unsupported formats.
Record companion dependencies before any rewrite. Filename/consumer profiles
have no magic and remain candidates even when a whole game shares a suffix.

Large replies use output artifacts; stdout redirection may capture a reference.
Retain/read the artifact through the existing output APIs rather than rerunning
intake. Preserve executable hashes and the private selected-program roster.

## Inspect FLI/FLC and proprietary resource profiles

```text
fdisbull media-inspect /private/intro.fli --adapter flic
fdisbull media-inspect /private/movie.vid --adapter flic --index-path /private/movie.idx
```

The FLIC reader checks packet/subchunk extents and explicitly distinguishes the
128-byte standard header, Bullfrog's compact 12-byte header and TFTD's audio-bearing
VID/IDX profile. Counts may include a ring-frame candidate or opaque prefix.
Structural correspondence does not qualify pixels, audio, seeking or shortening;
the SMK framing writer cannot edit FLIC. Unknown chunks stay recovery obligations.

DinoPark's original intake has no FLI. It uses UNC2/UNCS actors, UNCP pictures,
headerless ABT sounds and IFF XMIDI. Shipped `dinopark-act`, `dinopark-pic` and
`dinopark-abt` adapters now decode bounded sprites/opacity, padded image rows/raw
palettes and sample bytes. `media-inspect` returns hashes/scalars; `media-decode`
exports a selected image or explicitly timed WAV into a new private directory.
ACT sequences remain opaque, palettes are external, and ABT rate/channels are not
guessed. Use explicit palette and WAV adapters; preserve original-game evidence
separately from a pure decoder result. Civilization PIC is a different family. Other
observed resource cohorts (Coktel ITK/LTK/IMD, MADSPACK, Eternam, AGI/SCI, Bullfrog,
X-COM, platform fonts/resource forks and embedded assets) have separate catalog
context profiles and explicit recovery gaps. Private recovered code is evidence;
it is not automatically a shipped decoder.

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
