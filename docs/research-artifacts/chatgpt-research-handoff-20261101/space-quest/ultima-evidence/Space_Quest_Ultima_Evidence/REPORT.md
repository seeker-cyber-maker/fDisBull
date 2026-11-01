# Space Quest I patch inspection and Ultima IV reconnaissance

**29 October 2026. Static, read-only inspection of the three supplied installers.**

## Findings at a glance

The Space Quest patch contains **36 complete compressed replacement targets**: 33 files in the VGA remake directory and three GOG metadata files. Every decompressed target is **byte-for-byte identical** to the corresponding file extracted from the supplied full installer, build 88857. That full installer already includes this patch's target data. The patch is not an additional game-data upgrade on top of that installer.

Ultima IV is a different, broader recovery problem, but it is not an undocumented blank slate. The uploaded package exposes small structured map, conversation and party-template files. Existing reconstructed DOS C/assembly and file-format documentation provide potential assistance. Neither outside source has been established as equivalent to this exact executable.

## Input identity

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| `patch` | 9,531,080 | `7b3ae423b768c1176229ad0c43260c677de615a17f6e8cedb75509ac3fa2815c` |
| `space_quest` | 450,025,368 | `99dc2a147e55d49c77e0dd83084118601fb1a2e958cb06dad34a064087beeb94` |
| `ultima` | 12,806,032 | `0a1274103fa6cad2dc79982be6623c091e9d2489c9e4ed059deeee35ff7d31a9` |

The JSON receipt records the full filenames. All three originals were rehashed at the end and remained unchanged. These are integrity identities, not an Authenticode signature/authenticity validation.

## What the Space Quest patch carries

The filename describes the transition from package `2.2 galaxy hotfix (20261)` to `2.2 GOG v2 (88857)`. Its 36 target payloads expand to **5,845,403 bytes**.

The VGA set includes the SCI interpreter, RESOURCE.MAP and five resource volumes, sound/input/video drivers, configuration and installation files, two V56 resources, and accompanying patch/readme files. The other targets are `goggame-1207661413.hashdb`, `.info` and `.script`.

All 36 payloads decode as full zlib replacements, with compressed and expanded MD5 checks matching the embedded metadata. The installer also bundles xdelta/patch helper code, but that alone does not make these payloads binary deltas. None of these 36 targets requires the older game bytes to decode. This is a statement about the identified replacement payloads, not a complete reconstruction of every installer code path.

The root AGI files, including AGI, AGIDATA.OVL, LOGDIR, OBJECT, WORDS.TOK and the original VOL files, are not in this replacement set. Configuration affecting the original launch is still present in the metadata.

### Launch and configuration behavior declared by the payload

The new `.info` declares a primary ScummVM task using `sq1.ini` and target `sq1`, plus a separate VGA task using `sq1_vga.ini` and target `sq1sci`.

The `.script` declares ten installation actions: create the original and VGA save directories; copy both INI files from the support directory with **overwrite enabled**; set each game path and save path; set `updates_check=0` in both ScummVM configuration sections. These are statically read action definitions. No installation was executed, and availability of an older installation's support files was not tested. Treat customization of those INIs as potentially overwritten when applying the package.

### What remains unknown without build 20261

This comparison proves that the full installer already contains all 36 targets. It does **not** prove which target was absent or different in the old installation, identify an individual fixed puzzle, or prove whether all VGA data was newly added rather than replaced. Determining those historical changes requires the older installer or an independently identified old installation. The entire Inno/Pascal control flow and all registry/shortcut side effects were not reconstructed.

## Space Quest: two distinct recovery targets

The package contains an original AGI version and a separate SCI VGA remake. The AGIDATA.OVL bytes contain the interpreter version string **2.917**; `vga/VERSION` contains **2.000**. The package's `2.2 GOG v2` label is not the same identifier as that VGA game version.

The original version is a useful transfer test for existing AGI work on KQ1/PQ1. It is not an engine-family holdout. The VGA remake should have a separate source identity, adapter scope and benchmark manifest.

A preserved fDisBull **0.22.0** offline environment was installed locally. Its bounded AGI inspector was run against three real original-game logic resources, using profile 2.917:

| Logic resource | Code bytes | Decoded/frontier records | Unsupported frontier records | Complete |
| --- | ---: | ---: | ---: | --- |
| 0 | 4,175 | 109 | 22 | No |
| 1 | 2,083 | 237 | 36 | No |
| 2 | 1,300 | 20 | 7 | No |

Every decoder command returned successfully, but every result explicitly says **partial static decode, not execution**. These are not three recovered rooms or playable scenes. Unsupported branches retain unknown successors; no instruction lengths were guessed across those points. This describes the tested 0.22 environment, not a claim about the latest repository's complete capabilities.

The SQ.COM loader import decoded 469 instructions in its implemented static traversal. A settled loader-analysis queue does not establish whole-game recovery.

### Why the full installer is roughly 450 MB

The validated installer metadata assigns about **434.5 MB of stored payload** to three runtime/support groups: the `scummvm-2026.1.0.zip` bundle, `scummvm.exe`, and `Game Configurator.exe`. Together that is about **96.6%** of the installer. The large ScummVM groups were not expanded or executed in this intake; the size attribution comes from the parsed group metadata. The ZIP filename by itself is not treated as proof of its internal contents or purpose.

## Ultima IV: a bounded starting point

The supplied files include a 98,208-byte `AVATAR.EXE` and 44,672-byte `TITLE.EXE`, both recognized as DOS MZ executables. Resource inspection found:

| Data | Observation from supplied bytes | Scope |
| --- | --- | --- |
| `.ULT` | 17 files, each 1,280 bytes | Compatible with documented town-map/NPC-table layout |
| `.TLK` | 16 files, each 4,608 bytes | 256 record slots under the documented 288-byte layout, not 256 proven active NPCs |
| `WORLD.MAP` | 65,536 bytes | Compatible with the documented world-map layout |
| `PARTY.NEW` | 502 bytes | Identical to the packaged default PARTY.SAV; an installer template, not a live player save |

The town coordinates decoded under the documented layout all fit 0..31. Static initial NPC positions are not current runtime positions and are not automatically click coordinates. Candidate party fields such as food, gold, keys and torches were identified using external layout documentation; their semantics and freshness remain unqualified against the original executing game.

### Existing code assistance

The `ergonomy-joe/u4-decompiled` project's author describes reconstructed C and assembly for AVATAR.EXE and TITLE.EXE, built with Microsoft C 4.00 and reported as very close to the original executables. That is the author's report. No rebuild or byte-equivalence check against this GOG release was performed here, and no complete game algorithm was adopted from that code. XU4's file-format notes were used as a structural hypothesis source, not as proof of original behavior.

### What the native analysis does not yet settle

The initial AVATAR entry pass decoded only **17 startup instructions** before a far return. Its static queue reports stable only under the implemented rules, with explicit stack/segment uncertainty. It does not establish that the full executable was analyzed. TITLE's 2,000-attempt pass decoded 1,562 instructions and stopped with work pending.

A productive first Ultima slice would be **one town, one conversation and a few read-only party/HUD fields**, followed by a source-backed transition. Whole-game virtues, combat, world simulation and persistence need not block that slice. This is a scope recommendation, not completed gameplay.

## Implications for the held-out study

Use the original Space Quest AGI edition for a new-game/same-engine transfer trial. Use the SCI edition and a small Ultima slice as separate architectural challenges. An Ultima run supplied with reconstructed C or format documentation belongs in the **code-assisted** condition. This conversation has now seen resource layouts and package evidence, so it should not later be labeled a fresh blind investigator for these inputs. Other games and fresh contexts can remain withheld.

The new packaging friction and AVATAR startup boundary are concrete tool questions. Neither justifies counting a guide skeleton, table census, or successful import as code-accepted game behavior.

## Method, checks and limits

A purpose-built Python reader was guided by the published innoextract record layouts. It was not the innoextract executable. It located exactly one valid Inno 5.6.2 Unicode primary/secondary header pair per input, verified header/subblock CRCs, followed contiguous file records covering every secondary data index, and checked selected stored entries against their SHA-1.

Selected Galaxy groups were decoded with zlib and checked against their compressed member and final target MD5 values. All 78 patch file-table records were verified. The full SQ and Ultima extractions cover 65 and 156 selected logical files respectively; 34 and 16 runtime dependency groups were intentionally skipped. This is not an integrity claim for every expanded full-installer dependency.

A fresh-output reproduction of the included extraction script again produced all **36/36 identical patch targets**. No Windows setup code, installer helper DLL, DOS game, or guest restore was executed. No new gameplay, held-out multi-agent trial, or full project test suite was run. Game binaries, fonts, raw game resources and byte-retaining databases are excluded from the accompanying evidence ZIP.

## Full patch target inventory

| Target | Expanded bytes | Compared with full 88857 |
| --- | ---: | --- |
| `vga/433.V56` | 2,703 | Identical |
| `vga/533.V56` | 1,960 | Identical |
| `vga/ADL.DRV` | 8,070 | Identical |
| `vga/CMS.DRV` | 3,741 | Identical |
| `vga/IBMKBD.DRV` | 537 | Identical |
| `vga/IBMPS1.DRV` | 4,364 | Identical |
| `vga/INSTALL.EXE` | 39,723 | Identical |
| `vga/INSTALL.HLP` | 8,565 | Identical |
| `vga/INSTALL.SCR` | 2,844 | Identical |
| `vga/INSTALL.TXT` | 4,189 | Identical |
| `vga/INTERP.TXT` | 1,636 | Identical |
| `vga/JOYSTICK.DRV` | 607 | Identical |
| `vga/MT32.DRV` | 1,976 | Identical |
| `vga/MTBLAST.DRV` | 3,688 | Identical |
| `vga/PROAUDIO.DRV` | 11,942 | Identical |
| `vga/README` | 1,078 | Identical |
| `vga/RESOURCE.000` | 1,016,436 | Identical |
| `vga/RESOURCE.001` | 1,038,757 | Identical |
| `vga/RESOURCE.002` | 1,169,831 | Identical |
| `vga/RESOURCE.003` | 1,213,262 | Identical |
| `vga/RESOURCE.004` | 1,203,051 | Identical |
| `vga/RESOURCE.CFG` | 173 | Identical |
| `vga/RESOURCE.MAP` | 5,913 | Identical |
| `vga/SCIDHUV.EXE` | 62,238 | Identical |
| `vga/SNDBLAST.DRV` | 9,768 | Identical |
| `vga/SQ1GMPAT` | 1,301 | Identical |
| `vga/SQ1RS.BAT` | 31 | Identical |
| `vga/STD.DRV` | 1,461 | Identical |
| `vga/TANDY3V.DRV` | 3,950 | Identical |
| `vga/TANDY3VD.DRV` | 4,498 | Identical |
| `vga/VERSION` | 7 | Identical |
| `vga/VGA320.DRV` | 4,461 | Identical |
| `vga/VGA320BW.DRV` | 4,369 | Identical |
| `goggame-1207661413.hashdb` | 1,910 | Identical |
| `goggame-1207661413.info` | 1,765 | Identical |
| `goggame-1207661413.script` | 4,598 | Identical |

## References

- Reconstructed original DOS sources and author's scope: https://github.com/ergonomy-joe/u4-decompiled
- XU4 file-layout notes: https://github.com/xu4-engine/u4/blob/master/doc/FileFormats.md
- Inno header-block layout: https://github.com/dscharrer/innoextract/blob/master/src/stream/block.cpp
- Inno file/data layout: https://github.com/dscharrer/innoextract/blob/master/src/setup/file.cpp and https://github.com/dscharrer/innoextract/blob/master/src/setup/data.cpp
- Inno condition and Windows-version layout: https://github.com/dscharrer/innoextract/blob/master/src/setup/item.cpp and https://github.com/dscharrer/innoextract/blob/master/src/setup/windows.cpp
- Inno chunk framing: https://github.com/dscharrer/innoextract/blob/master/src/stream/chunk.cpp

The accompanying receipt records the three input hashes and all 36 target hashes. Outside references describe layouts or claims; computed package findings come from the uploaded bytes.
