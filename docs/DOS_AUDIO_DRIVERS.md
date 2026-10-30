# DOS audio driver inspection

fDisBull recognizes the byte structure of Miles AIL 2 real-mode driver
libraries, commonly named `.ADV`. Recognition validates the copyright/family
header, terminated function directory, mandatory driver entries and file-backed
routine offsets. The filename extension is not used as proof. Unknown function
IDs are retained; shared routine offsets retain all directory aliases.

```text
fdisbull identify /private/game/SBPFM.ADV
fdisbull inspect /private/game/SBPFM.ADV
fdisbull import /private/game/SBPFM.ADV /private/music.fdb --image ail
fdisbull analyze /private/music.fdb --max-instructions 10000
fdisbull exports /private/music.fdb
fdisbull analysis-status /private/music.fdb
```

Validated AIL bytes also import automatically. An AIL library has no DOS
process entry point. Exported routines become deferred recursive seeds using
the normal discovery queue; a budget stop remains incomplete. The selected
image is `AIL`, x86/16-bit, and its addresses are explicitly **module-relative**
offsets. Runtime segment binding, relocation, code executed during installation
and hardware support are separate observations. Base/segment/slice overrides
are rejected instead of presenting an invented runtime mapping. An explicit
analysis entry is available when investigating a known file-backed routine.

Inspection exposes the directory as named exports (`AIL.describe_driver`,
`AIL.initialize_driver`, `AIL.start_sequence`, etc.). It also attempts a bounded
descriptor inference from the describe routine's immediate return value. The
descriptor includes device names, minimum API version, instrument suffix,
default hardware parameters and requested service rate. This inference is
labeled a candidate and does not execute the routine. Failure to infer a
descriptor leaves it unknown without discarding a valid directory.

The original blob remains in the project. Ordinary code patch versions,
restart and stored-state SVG/PNG rendering work without launching the driver.
Header/layout edits retain the usual warning to reimport for a different
mapping. The original import metadata is not a live module binding.

## Named DIGPAK and MIDPAK services

The DOS interrupt catalog names documented INT66 audio services and displays
them alongside stored DOS disassembly when the full AX selector is known.
Native bytes, raw operands, comments, authorship and version-specific register
facts are preserved. An unknown/ambiguous AX stays unknown; AH alone does not
select a service.

```text
fdisbull dos-services --vector 0x66 --ax 0x688
fdisbull dos-services --vector 0x66 --ax 0x702
```

The JSON method accepts register facts for parameter inspection:

```json
{"method":"dos-services","params":{"vector":102,"registers":{"ax":1672,"ds":4660,"si":86}}}
```

This describes `DIGPAK.play_sample` and its DS:SI sample descriptor. The
authored SNDSTRUC layout is 12 bytes: far sample pointer, 16-bit byte length,
far playing-status pointer and 16-bit frequency. `MIDPAK.register_xmidi`
instead uses CX:BX for its data pointer and DI:SI for the high/low byte length.
`MIDPAK.load_driver` requires the ADV segment in BX, CX=0 and the instrument
bank at DX:SI. These are distinct ABIs.

Catalog coverage includes DIGPAK 0688h–06A0h and documented MIDPAK
0700h–0714h/0716h; 0715h remains unknown. Individual installed driver versions
can implement fewer selectors or reject a capability. Legacy operations remain
named as such. Unspecified register and memory effects remain unmodeled.

Every audio description retains `handler_verified=false`,
`runtime_observed=false` and `outcome=unknown`. Naming a selector describes a
candidate contract: INT66 is privately assignable, so a different resident
handler can use the same numbers. Independently bind the resident signature,
loaded module hash, segment and callable extent before treating it as an
original driver operation. The disassembler does not silently execute or
install drivers to establish that binding.

## Use by a DOS UDC module

These interfaces supply analysis metadata and parameter layouts. They do not
add a host audio synthesizer or change UDC qualification. The original-backed
DOS compiler can retain original driver/resource bytes in its resource closure;
the qualified runtime continues to be DOSBox.

A future effect binding should distinguish request, returned acceptance,
active playback and completion. File reads certify resource access only. For
example, MIDPAK play-sequence AX=0 accepts playback; sequence status can later
report stopped/playing/done, but must be bound to the same request and module
lifetime. DIGPAK sample-status memory and callbacks need the same ownership.
Foreground and background implementations need separate timing qualification.

Keep host audio muted with `SDL_AUDIODRIVER=dummy`, mixer `nosound=true`, and
MIDI `mididevice=none` during quiet original-game tests. Preserve guest sound
services and their timers/callbacks. See
[hardware boundaries](UDC_HARDWARE_BOUNDARIES.md) for the related mouse, video,
clock, memory and interrupt contracts.

Sources: [Miles AIL declarations](https://github.com/Tronix286/AIL2/blob/master/AIL.INC),
[DIGPAK descriptor/API](https://github.com/jratcliff63367/digpak/blob/master/DIGPLAY.H),
[DIGPAK implementation](https://github.com/jratcliff63367/digpak/blob/master/SHELL.ASM),
[RBIL audio services](https://fd.lod.bz/rbil/interrup/sound/index.html).
