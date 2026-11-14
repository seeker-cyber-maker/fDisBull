# DOS launch contracts and RTLink/Plus overlay analysis

## Purpose and interfaces

This change fixes concrete Dragonsphere intake friction without modifying the
original game or inventing a DOS extender. It adds `fdisbull-dos`, also available
as `python -m fdisbull.dos_tools`, plus the Python modules `fdisbull.rtlink` and
`fdisbull.dos_launch_profile`. The indexed installed skill reference
`references/formats-and-media.md` contains the detailed DOS format decision tree.

```sh
fdisbull agent-skill --reference references/formats-and-media.md
fdisbull-dos methods
fdisbull-dos rtlink-inspect /private/SPHERE.EXE
fdisbull-dos rtlink-disasm /private/SPHERE.EXE --overlay 16 --offset 0xce --count 32
fdisbull-dos rtlink-export /private/SPHERE.EXE /private/new-view
```

This is an additive command surface. Existing `fdisbull debug` flags and its
backend selection remain unchanged. The RTLink reader is not registered as a
production runnable image loader or a universal unpacker. It uses fDisBull's
canonical DOS validator, x86 decoder, bounded source reader, private output
ownership rules and standard compact output-artifact protocol.

## Correct DOS identification

Start from bytes, not suffixes or a guessed engine. The Windows GOG installer,
extracted DOS executable, loaded resident image, overlay bank and runtime dump
are different objects with different hashes and address spaces.

A COM file has no magic. Its conventional DOS entry is PSP:0100h and its code,
data and initial stack share a segment. A classic MZ file specifies its header,
loaded module, entry and relocation sites. MZ can also be the front of a Windows
NE/PE or a protected-mode LE/LX program; validate a secondary header rather than
searching for two letters. MZ-signature bytes need to be at the relevant object
boundary, not necessarily somewhere in a resource dump.

For MZ, header bytes are `e_cparhdr*16`; declared file extent is `e_cp*512` when
`e_cblp==0`, otherwise `(e_cp-1)*512+e_cblp`. The declaration includes the header.
Each relocation is a little-endian offset/segment pair identifying a word in
the loaded module. Runtime load relocation and original file offsets are not the
same address. In real mode a segment denotes a paragraph base; protected-mode
selectors require descriptor lookup rather than multiplication by16.

Old-style MZ relocation tables can start at 0x1c or 0x1e. When their entries occupy
0x3c, that location is not independently available for a modern `e_lfanew` field.
Use the existing structural secondary-header validator. The historical reversed
`ZM` signature is recognizable, but the current canonical MZ loader does not
admit it. Do not silently normalize original inputs to obtain a passing load.

BAT files describe commands, arguments, directory changes and environment. SYS
headers describe DOS drivers; OBJ/LIB records are linker inputs. OVL/DRV/DAT or
extensionless names cannot reliably distinguish these. Packed executable code,
self-extracting containers, a DOS extender, an overlay manager and a game script
VM are separate mechanisms. None is established by an unexplained appended tail.

### Worked source example

For the supplied Dragonsphere SPHERE.EXE: `e_cp=212`, `e_cblp=187`, and
`e_cparhdr=416`. Therefore the declared MZ file extent is 108,219 bytes and
its resident file-backed module is 101,563 bytes, after a 6,656-byte header.
The 553,068-byte original has 444,849 appended bytes. The embedded-v2 table
identifies 105 banks and 12,799 bank relocation records. Four declared bytes
at the last paragraph have no file backing; the report's
`all_declared_payload_bytes_backed` is false. These are source-specific facts,
not constants hardcoded into the parser or a publisher-authenticity claim.

A module dumped after DOS loading normally lacks the MZ header because DOS does
not load that header as executable code. Missing MZ in such a dump is expected,
not evidence that the original EXE needs a stub. Conversely, seeing 386 registers
or operand-size prefixes does not by itself prove a 32-bit protected-mode program;
instruction capability, default operand width and CPU mode must be distinguished.
The classic `e_ovno` field is not a universal directory of dynamically loaded
banks. Follow a qualified overlay format instead of extrapolating from that word.

## Native launch repair

`open_dos_session(project, executable, game_dir, arguments=[...], cd_image=...)`
uses the normal `DebugSession` ownership/evidence path and its transport hooks.
It supplies the caller's validated command tokens through the existing native
`session.start` API instead of silently discarding them. It optionally adds one
explicit `imgmount D ... -t iso` startup request to the same DOSBox executable.
There is no host shell or wrapper script, no arbitrary startup command string,
and no alternate emulator or fabricated runtime.

```sh
fdisbull import /private/DRAGON/MAINMENU.EXE /private/mainmenu.fdb
fdisbull-dos debug /private/mainmenu.fdb --executable /private/backend/dosbox \
  --game-dir /private/DRAGON --argument=-p --cd-image /private/GAME.INS
```

The foreground process emits the usual launch receipt and accepts the existing
JSON-line debugger methods with that run ID. EOF closes/reaps its owned process.
Arguments are at most 32 unquoted ASCII tokens and a 125-byte joined tail. Spaces
inside tokens, quotes, expansion and shell metacharacters refuse. Full DOS shell
quoting, arbitrary BAT execution and environment injection are not implemented.
C: is the selected working game directory; D: is validated read-only CD media.

The `.ins` suffix routes through the existing CUE parser, not raw-sector guessing.
One- and two-digit TRACK/INDEX numbers normalize to the same track/index semantics.
Other layout validation stays intact. CD inputs are regular files, bounded to
2 GiB combined, hashed before spawn and rechecked before session start. Their
reported mount is a request, not a runtime acknowledgment. Verify actual DOS
filesystem access or a game observation. Media changes during execution are not
continuously monitored or locked; preserve the source and use private run copies.

## RTLink supported layout and output

The supported profile is **embedded RTLink/Plus v2**, based on a relocation-backed
resident table and sequential 32-byte descriptors. Each descriptor identifies its
original overlay header and nominal load paragraph. The fixed overlay header
provides total/header paragraph counts and a relocation table. The reader checks
bounds, ordering, table termination, overlap, relocation-word extents and unique
table identity. Budgets: 64 MiB source, 4096 banks, 262144 overlay relocations.

An original final paragraph may end fewer than 16 bytes beyond EOF. Those bytes
remain explicitly unbacked and are omitted from exports/disassembly. They are not
invented or called verified. Other truncation refuses. Header fields not understood
are retained as opaque metadata; static structural acceptance is not a proof that
every bank byte is code or that every possible v2 file will be accepted.

`rtlink-inspect` reports source identity, resident and bank source ranges, bank IDs,
relocations and a limited form of relocation-backed dynamic thunk candidates.
The current thunk form is a far call followed by a far jump with zero segment and
an alias/paragraph adjustment. Its alias is a one-based descriptor ordinal, not
the bank ID itself. Other thunk forms and cross-bank semantics remain unresolved.

`rtlink-export` creates `analysis-flat.bin` and `rtlink-map.json` in a new private
directory outside Git. Resident bytes and each bank receive separate stable
analysis ranges. Original retained ranges are byte-for-byte copies. Alignment
zeros are listed as synthetic. Relocations and operands are **not rewritten**;
this is not a runnable or fully relinked EXE. Use the map to translate analysis
coordinates back to original bank bytes. A flat address is never a live CS:IP.

`rtlink-disasm` decodes a caller-selected bank/range with the existing 16-bit x86
processor. It does not infer reachability or silently bind runtime segments.
Runtime bank observation still needs a source hash, bank ID, reload generation,
observed load range and relocation state. Reused addresses cannot identify banks.

External OVL files, RTLINKST/compressed variants, universal v1/v3 support, heuristic
pointer rewriting and native overlay switching are not implemented. This is not
full feature parity with the upstream RTLink decoder. Unsupported layouts refuse
rather than guessing that every MZ tail has the same structure.

## Source provenance

Format research consulted the ScummVM developer's `dreammaster/tools` repository:
`rtlink_decode/variation2.cpp`, Git blob
`d6dfccff3c143d04fc169bdf2606b99105413b34`, and `rtlink_decode/rtlink_decode.cpp`,
Git blob `b4ddb53854e33df6a24ade5ea7672d23d033e25b` on its `rtlink_decode` branch.
Those sources carry GPL-2.0-or-later notices. No upstream source or executable is
bundled here. This Python implementation retains mappings and opaque fields
rather than copying the heuristic EXE rewriter. Format consultation does not
constitute licensing clearance; review provenance before release.

Primary references:
- https://github.com/dreammaster/tools/tree/rtlink_decode/rtlink_decode
- https://www.delorie.com/djgpp/doc/rbinter/it/94/15.html
- https://learn.microsoft.com/en-us/windows/win32/debug/pe-format

## Verification gates

Authored tests cover tables, bank identities, corruption, relocation bounds,
unbacked tails, non-runnable export mappings, decoder reuse, launch admission,
CUE aliases and installed command discovery. Opt-in native tests use an authored
COM program to inspect its PSP tail and open a file on D:, then verify original
bytes and child cleanup. They are separate from protocol doubles.

Run the focused suite from the source tree with the configured native backend:

```sh
FDISBULL_DOSBOX=/private/backend/dosbox SDL_VIDEODRIVER=dummy \
  python -m pytest -q tests/test_rtlink.py tests/test_dos_launch_profile.py \
  tests/test_dos_launch_profile_native.py tests/test_dosbox_window.py \
  tests/test_cue.py tests/test_disc.py tests/test_dos_loader.py
```

Rebuild wheel/source artifacts, install the wheel in isolation and verify both
`fdisbull-dos` discovery and the installed formats/media skill. Existing privacy
rules still exclude games, analysis-flat images, maps retaining original values,
FDBs, saves and raw private traces from public source/packages. Local selected
checks do not qualify all !95 integration code, macOS, hosted CI or a release.
