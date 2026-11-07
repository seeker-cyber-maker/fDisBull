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
headerless ABT sounds and IFF XMIDI. Actor opacity/sequence behavior, external
palettes, six-bit palette scaling, even picture stride and compressed rows need
consumer-qualified readers. Civilization PIC is a different family. Other
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

## Installer and image intake

Separate archive extraction, disc framing/filesystems, executable unpacking and
installer execution. Do not run a setup program simply to obtain its files.

1. Run `fdisbull-unpack catalog` and `fdisbull-unpack inspect /private/input`.
2. Extract admitted layers with `fdisbull-unpack extract /private/input
   /private/new-output --recursive`. Preserve `layers.json`, original sources,
   companion descriptors and explicit omissions. Never describe a partial tree
   as a complete disc or installed game. Avoid repeated extraction/hashing once
   an unchanged source's retained evidence answers the question.
3. For GOG/BIN, retain CUE/INS. Select a data track explicitly when ambiguous.
   ISO files, raw sector images, filesystems and audio tracks are different
   objects. Unsupported NRG/MDF/CCD/VCD or floppy layouts need a separately
   qualified provider; renaming them to .iso is not conversion.
4. Concatenated ZIPs need independent directory/offset validation. An ordinary
   ZIP reader returning a few files does not establish whole-file accounting.
   MPSLABS.001 contains three ZIP groups, not proof of three installation disks.
5. Use the EXEPACK provider only for its admitted profiles. It reconstructs an
   analysis envelope, not an automatically qualified runnable executable.
   RTLink overlays are a different mechanism; do not add a DOS extender stub.
6. Installer hardware investigation is opt-in native execution:
   `fdisbull-installer-probe /private/INSTALL.EXE /private/new-capture
   --executable /tools/dosbox-x --max-fetches 50000 --timeout-seconds 30`.
   Only selected files are copied into scratch C:. Use `--companion` and JSON
   `--arguments` explicitly. Do not mount the source directory or consume a
   supplied autoexec/config. DOSBox alone is not a hostile-code host sandbox.
7. Distinguish fetched calls, matched caller returns, inferred intent and missing
   branches. DOS/BIOS/mouse/EMS/port observations describe emulated hardware, not
   the host Mac. Static strings are hypotheses, not observed detection. Capture
   OS version, video, mouse, memory and storage witnesses before changing the
   environment; follow with bounded one-variable experiments as needed.
8. Generic changed-code capture is packer-independent but does not establish an
   original entry or recover arbitrary relocation/import tables. Preserve source
   identity and use an explicit `--stop-offset` for a justified load-relative
   boundary. Breakpoint captures are snapshots, not executable rebuilds. Keep
   raw RAM/traces/game files outside Git, and do not publish extracted fonts.

These installed entry points also work as `python -m fdisbull.unpack` and
`python -m fdisbull.installer_probe`. They are not aliases for new shared JSON
request methods. Read `docs/INSTALLER_LAYER_INTAKE.md` for profiles, test scope,
provider contracts, limitations and the actual Dragonsphere/Ultima evidence.
