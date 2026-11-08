# Classic WAD and Genesis structural discovery

This extends the shared read-only structural-discovery candidate. It does not
add an emulator, a complete Doom/Shadowrun lifter, or a game-specific scraper.

## Agent entry

```sh
fdisbull structure-scan /private/game-or-resource --output /private/new-leads
fdisbull structure-info /private/new-leads/report.json --pattern linked-scene-records --limit 1
fdisbull structure-intents /private/new-leads/report.json --limit 3
```

An input can be a raw ROM, a content-identified Genesis ROM ZIP, an IWAD/PWAD,
or an extracted directory. Installers still go through existing intake.
The default individual input limit is now 32 MiB, with an explicit maximum
of 64 MiB and the existing 64 MiB default aggregate limit. A smaller caller
budget remains binding. ZIP expansion counts toward the aggregate limit.

## Reuse boundary

- `structure_68000` translates bounded CPU evidence into the existing shared
  selector/mask/branch/effect facts. It contains no title names or known menu
  offsets. The matcher and its rule definitions are unchanged.
- The existing Sega header reader identifies raw images and flags truncated,
  byte-swapped, interleaved and 32X variants. An ordinary, zero-based <=4 MiB
  cartridge supplies a *candidate* linear ROM mapping and vector roots.
  Checksum matches are not authentication or proof of an unchanged edition.
- `structure_wad` supplies format-defined record families and relationships.
  It is a source/spec-assisted reader, not statistical inference of the WAD
  layout. The same reader applies across compatible IWADs/PWADs and maps.
- The native source-view path checks bounded nested MZ/LE envelopes. Nested
  file offsets are translated back to the unchanged outer input. The DOS
  wrapper is retained separately from embedded protected-mode code. LE fixups
  remain unapplied. 16-bit LE objects are identified but not decoded as if
  their selectors were real-mode paragraph segments.

## What a WAD draft says

A map marker plus the classic lump sequence provides THINGS, LINEDEFS,
SIDEDEFS, VERTEXES, SEGS, SSECTORS, NODES and SECTORS record populations.
The reader retains directory order and duplicate names, source offsets,
strides, hashes, type/option values, bounds and selected reference checks.

Two-sided line references provide sector-adjacency candidates. They do not
establish a traversable opening: height, collision, flags, dynamic geometry
and actor properties matter. A sector is not automatically a semantic room.
Map THINGS are spawn definitions, not a census of live actors. Difficulty,
mode, destruction, spawning and later execution can change that population.

Nonzero line specials and tag matches provide event-investigation leads.
The trigger, dispatch handler and effects remain unknown. Inspect the shared
consumer before naming one of these a door, exit, pickup or switch. A switch
can change geometry without leaving the scene; an exit can require cleanup
and deferred continuation. Neither follows merely from a numeric tag match.

The current reader does not validate BSP acyclicity, BLOCKMAP/REJECT contents,
resource resolution, spawn conditions, collision or event semantics. Selected
reference failures remain explicit on the draft. BEHAVIOR/TEXTMAP markers
refuse the classic interpretation rather than treating Hexen/UDMF bytes as
classic Doom records. It does not combine a multi-file override namespace.

## 68000 scope

The producer retains big-endian operands, operand width, absolute-short sign
extension, PC-relative displacement origins, 24-bit bus locations, local
value/condition dependencies and explicit direct/indirect continuations.
Calls do not transfer presumed register or flag meanings to their return
paths. Joins and overlapping decodes prevent short-arm dependency claims.

STOP/traps retain continuation uncertainty. Known ROM/cartridge-control
writes stop the candidate walk. Unknown indirect stores have no invented
address and are counted; subsequent code is still conditional on the declared
fixed-ROM hypothesis. No dynamic banks, register alias analysis, Z80/APU,
VDP timing or input-port protocol is reconstructed. Device references are
investigation avenues, not named controller-button events.

## Source references and evidence boundaries

Layout references: id Software's published `linuxdoom-1.10/w_wad.h`,
`doomdata.h` and `p_setup.c` at https://github.com/id-Software/DOOM .
The public Linux source is a format/architecture reference, not a byte-exact
symbol map for the supplied DOS executables.
The Genesis platform boundary is also consistent with the original project
header reader and https://github.com/ekeeke/Genesis-Plus-GX . No upstream
emulator code or game payload is copied into these modules.

Tests use authored miniature WADs, cartridge headers and instruction sequences.
Source scans are deterministic finite observations, not native gameplay proof.
Original DOS runtime checks belong to the accompanying research report, not
this parser's execution capabilities. Private ROMs, WADs, traces, frames,
checkpoints and generated original-derived drafts stay outside public Git.
