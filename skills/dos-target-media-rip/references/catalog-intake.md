# Catalog-backed intake and format recovery

Run one filesystem inventory kernel for a single game or explicit collection
roots. Do not scan an entire private package containing analysis databases,
generated variants and runtime aliases merely to discover the current roster.
Select the preserved game/resource roots from its manifest or receipts.

```text
fdisbull intake-inventory /private/game --catalog /private/formats.sqlite
fdisbull --output-artifact-dir /private/intake-reports intake-inventory /private/game-a /private/game-b --catalog /private/formats.sqlite
fdisbull file-identify /private/representative-file --catalog /private/formats.sqlite
fdisbull format-modules --catalog /private/formats.sqlite
```

Use `--max-files`, `--max-read-bytes` and `--max-binary-bytes` when bounding a run.
With the same profile and sufficient budgets, per-file facts should agree
between batch and individual inventories.
Keep the returned root/member provenance, file identity scope, available reader
bindings and recovery queue with the private intake receipt. Put the catalog and
report outputs outside the inventoried roots, so a repeat does not inventory its
own metadata or mutate an input tree. Persistent catalog creation/reopen follows
complete source enumeration and source/catalog alias checks. An incomplete walk
uses an in-memory catalog and reports the requested persistent catalog as not
written; do not claim that discovery was persisted.

A large reply can return a durable output
reference instead of inline file entries: retain and read that artifact with the
tool's output APIs. Redirecting stdout alone can capture only the reference.
Delivery completeness and inventory completeness are separate; do not rerun a
completed operation merely because its large result needs an artifact read.

## Read the result before selecting a transformation

The report's `complete` field covers filesystem accounting only. It is false for
I/O/budget stops, skipped directory symlinks or special files; it never means all
formats were decoded or a whole game was recovered.

A filesystem inventory does not expand nested archives, disc images or custom
resource bundles. It does not import a program, run a game or validate every
codec stream. Catalogued files can therefore coexist with unresolved contained
media. Use a qualified container reader, preserve carrier/member identities,
then inventory the recovered members in a new private stage. Never execute a
Windows installer just to list its contents when an archive reader is available.

Traversal/read-budget stops and source I/O failures are incomplete observations;
retain them separately from format refusals. Directory symlinks are not a license
to recurse into external trees or cycles. If the selected root is a directory
symlink, verify its target, inventory that concrete root explicitly and retain
the requested-alias provenance. A sampled-region digest identifies the
observed regions only. Obtain a complete source hash before claiming exact file
identity or deduplication. A completed inventory can still contain unsupported
formats and pending recovery work.

The catalog stores versioned signatures, header fields, endianness, provenance,
reader APIs and limits. Recognition means only its reported header/extent checks.
A linked structural reader is not automatically a full image/audio decoder or
writer. Shipped metadata contains no inspected target payloads; preserved custom
catalog content is unverified, and API strings never execute as plugins.

## Work the recovery queue

Use the inventory's `recovery_queue` to select one missing boundary at a time:

| Finding | Next investigation |
|---|---|
| Unknown bytes or a suffix-only media hint | Inspect representative bounded headers and the original consumer; keep the tentative type explicitly unverified. |
| Known signature, malformed header/extents | Compare the complete preserved source, declared lengths and a known variant; distinguish truncation from a different layout. |
| Recognized unsupported layout or size | Qualify that profile or a bounded streaming/container reader; do not relax a limit until the reader can enforce it. |
| Header recognition without a qualified decoder | Recover packet types, indexes, palettes/deltas or audio parameters and add a bounded decoder with authored fixtures. |
| A linked decoder is available but has not been run | Run its bounded validation/admission step with the required dependencies; a link is not a completed decode. |
| A container is recognized but members were not inventoried | Use its qualified member reader and preserve carrier/member identities, then inventory the private recovered stage. |
| Opaque executable tail/overlay | Retain it with its executable; recover its directory/consumer separately. A valid MZ stub does not qualify the protected-mode engine or tail. |

Related unknown files may share one recovery question, but preserve every game,
member and identity in the receipt. Similar names, suffixes or sampled prefixes
do not establish byte equality or semantic equivalence. Ordinary text/data is
still accounted for; do not call all unknown data corrupt movies.

Add or revise the minimal format definition, its versioned module binding and
meaningful valid/truncated/contradictory/unsupported fixtures when implementing
support. Keep header, structural, complete decode, writer and original-consumer
qualification separate. Re-run the original single and batch inventories to
show that the gap is now recognized at the intended scope. Do not clear a queue
entry merely because a signature or descriptive API string was registered.

## FLI and game-specific media

Autodesk FLI/FLC, Bullfrog's compact FLIC header, an FLC-bearing VID plus an IDX
companion, and a game-specific picture/animation container need distinct profiles.
Do not select a writer from `.FLI`, `.FLC`, `.VID` or `.PIC` alone. Preserve frame
sizes, palettes, delta dependencies, ring frames, timing and companion indexes.
A header reader or modern decoder success does not prove native rewrite safety.

Use the shipped structural inspector on a verified regular non-symlink source:

```text
fdisbull media-inspect /private/movie.fli --adapter flic
fdisbull media-inspect /private/movie.vid --adapter flic --index-path /private/movie.idx
```

It inventories bounded packet/subchunk extents for standard FLI/FLC, Bullfrog
compact FLIC and the admitted TFTD audio envelope. Its optional IDX comparison
checks packet-group byte lengths, not seeking/timing semantics. Inspect its
profile, opaque tails, unknown chunk types, ring/count relationship and recovery
notes. `full_decode` and `rewrite_supported` remain false; extended FLX is an
explicit unsupported layout. Do not substitute structural inventory for pixel
or audio decoding, or frame these files with the separate SMK2 writer.

The current roster includes these useful counterexamples:

- X-COM UFO uses FLI resources; its selected profile still needs complete packet
  and original-consumer checks before any rewrite.
- Syndicate Wars' `FLYBY.FLI` uses a compact Bullfrog 12-byte header. Bytes after
  its dimensions start a frame chunk, rather than the standard FLC depth field.
  Its SMK cinematics use the separate supported framing route.
- Terror from the Deep VID resources can carry FLC headers with IDX companions.
  Companion semantics and the exact consumer remain obligations.
- DinoPark's recovered intake uses UNC2/UNCS ACT sprites with optional script
  data, UNCP indexed/PAL PIC containers, headerless ABT delta audio and XMID resources in
  IFF XDIR/CAT containers. These are not FLI/FLC. Its PIC format is distinct from
  Civilization's differently encoded PIC files despite sharing a suffix.

Use the actual catalog definitions and linked reader limitations for the supplied
edition. Headerless ABT requires explicit consumer/profile context rather than a
suffix-based guess. A recovered private script or historical result is evidence
to inspect, not automatic production support or permission to mutate media.
Inspect a recovered script's top-level side effects before reusing a pure reader;
an inventory script can create output even when one of its functions is pure.


## Shipped DinoPark decoder modules

Use `media-inspect --adapter dinopark-act`, `dinopark-pic` or `dinopark-abt` for
complete bounded decoding and metadata/hash reports. Use `media-decode` for a
selected private PNG/WAV export. ACT index and opacity planes are separate;
colored previews require an explicit external PIC palette. Preserve padded PIC
rows and raw six-bit palette bytes; choose host expansion explicitly. ABT WAV
exports require caller-supplied `--sample-rate` and `--channels` or the explicit
`--playback-profile dinopark-digpak-sbpro-mono-v1`. The profile preserves requested
PCM timing separately from exact rational Sound Blaster device timing; it does
not claim current-input native playback. `media-inspect --adapter
dinopark-abt-playback` reports that binding; headerless ABT context stays explicit.

Use `media-inspect --adapter dinopark-act-sequence` for sequence boundaries,
authored operation names and unsupported runtime operations. `dinopark-animate`
runs a bounded subset with explicit caller ticks; it does not infer wall-clock
Hz, select palettes or render a scene. Native graphics and mixer audio require
fresh normal-consumer observations with declared input/state policies. The
optional bounded audio-capture backend controls observe stock PCM with speakers
muted; closed/truncated capture windows are not sample completion receipts.

Before calling a source malformed, distinguish a valid unsupported variant and
an old reader limitation. DinoPark BUS/PEOPLE are valid UNCS resources rejected
by a prior UNC2-only reader. An absent literal filename reference does not prove
a resource is unused. Preserve exact rejected bytes and refusal details; never
rewrite original resources or programs to compensate for a decoder mismatch.

## Interplay MVE and Castles II sound libraries

The catalog recognizes the canonical MVE header and links the explicit `mve`
reader/framer. SLB remains a context candidate with `castles2-slb` directory and
`castles2-slb-playback` timing bindings. Read [the scoped route](mve-slb.md)
before framing or exporting. Decoder availability does not qualify original
playback; unsupported codec families and opaque selectors stay recovery work.
