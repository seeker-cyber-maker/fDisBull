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
The companion `dinopark-act-sequence` inspector reports sequence boundaries and
unsupported opcodes; `dinopark-animate` runs a bounded subset on explicit logical
ticks, without assuming Hz or rendering a scene. `dinopark-abt-playback` binds
the explicit original DigPak/SBPRO mono timing profile. WAV export can select
`--playback-profile dinopark-digpak-sbpro-mono-v1`, preserving requested integer
PCM timing separately from exact rational device timing. Palettes remain external.
Native mixer recording requires the separate optional audio-capture backend and
session-owned bounded controls; a closed capture does not prove a sample ended.
Preserve normal-gameplay observations separately from pure decoding or simulation.
See `docs/DINOPARK_ANIMATION_PLAYBACK.md` for the consumer profile and limits.
Civilization PIC is a different family. Other
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

## Frame old Interplay MVE and inspect Castles II SLB

```text
fdisbull media-inspect /private/movie.mve --adapter mve
fdisbull mve-frame /private/movie.mve /private/new-framed --keep-frames 32
fdisbull media-inspect /private/SND190.SLB --adapter castles2-slb
fdisbull media-inspect /private/SND190.SLB --adapter castles2-slb-playback
fdisbull media-decode /private/SND190.SLB /private/new-sample \
  --adapter castles2-slb --slot 515 \
  --playback-profile castles2-ail-sb-mono-v1
```

MVE header recognition is separate from the explicit old indexed 0x06/0x10
writer. Framing preserves codec family, frame numbering, audio and controls;
first/last N images are checked exactly. Original ending packets restore needed
references within a bounded search. Read pure-hold, warm-up and retained ranges
from the manifest. A 16-bit packet length is not proof of native input-buffer
capacity; no rewritten chunk may exceed the original maximum. Native tests must
count presentations and check the actual ending and return, not just success.

SLB has no global magic. Its explicit reader preserves original directory slots
and duplicate-key variants. The playback profile maps selectors 11/22 to DSP
time constants 166/211, keeping rational device timing separate from integer WAV
rate and buffer-drain completion. Exports require the original slot and explicit
profile; unknown selectors are not guessed. All current-query native flags stay
false. See `docs/CASTLES2_MEDIA.md` for the implemented scope and native gates.
