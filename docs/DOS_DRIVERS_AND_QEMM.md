# DOS driver analysis and QEMM-aware machine observation

DOS device drivers need a different entry contract from executable programs.
Memory managers add another distinction: the address a DOS instruction sees
may be backed by a different physical page, and the CPU can be in v86 mode
while the program still uses ordinary 16-bit DOS instructions. This feature
adds bounded static driver analysis and an explicit QEMM guest profile to the
existing machine backend.

The installed workflow is available with:

```sh
fdisbull agent-skill --reference references/dos-drivers-and-qemm.md
```

See the [bundled guide](../src/fdisbull/skills/fdisbull-investigate/references/dos-drivers-and-qemm.md)
for CLI/JSON examples, source identities, report interpretation and release of
the observation helper. All target files, disk images, FDBs and run artifacts
stay outside Git. The repository contains authored fixtures and the authored
probe only.

## Supported surfaces

| Surface | Added behavior | Evidence boundary |
| --- | --- | --- |
| `--image sys` and structural auto-recognition | Flat and MZ device headers, bounded chains, character/block metadata, independent Strategy/Interrupt roots | Unknown caller/request state; no invented PSP or process startup |
| Existing static analysis, restart, render and child versions | SYS participates in segmented DOS views with stable source/CS identity | Bounded traversal; explicit mode transitions stop real-mode interpretation |
| `le-driver-inspect` / `le-driver-disasm` | Mixed 16/32-bit object views, page/file fragments, symbolic fixups, optional VxD service ABI | No generic linking, module execution or whole-module CFG |
| `qemm-config` / `qemm-profile` | Read-only CONFIG.SYS preview and actual FAT12/16 image-member admission | Configuration is not boot or installation proof |
| `debug --backend qemu-machine --guest-profile qemm` | Pinned private DOS image, fixed 486/32 MiB/one-CPU policy, snapshot disk | Experimental native QEMM compatibility requires separate qualification |
| `debug-registers` / `debug-memory-translation` | Observed v86/segment-cache context, code width, bounded 386 PDE/PTE walk | Current stopped mapping; no persistent ownership/binding inference |
| `qpi-probe` / `qpi-report` / `debug-qemm-observe` | Reproducible DOS helper, version/status/Stealth/PTE reports, private run provenance | Guest-reported evidence; freshness and native execution remain separate |

The QEMM profile intentionally does not add an option to DOSBox's ordinary
process launch. That path starts a DOS program inside DOSBox; it does not boot
the caller's DOS kernel and CONFIG.SYS. A real memory manager needs the
full-machine boot path. Driver inspection also does not make a SYS file a
directly launchable application.

LE physical pages and logical object-map entries have separate counts. A
zero-fill entry can increase the latter without consuming another physical
page. Fixups use their physical-page index and are associated with the logical
object mappings that refer to it. This distinction is supported by original
loader research in [Geoff Chappell's VXDLDR appendix](https://www.geoffchappell.com/notes/windows/archive/vxdldr.htm)
and exercised by authored zero-fill/alias fixtures. Unsupported mappings and
out-of-extent target expressions stay explicit rather than becoming invented
addresses or edges.

## What QEMM was doing, compared with EMM386

The comparison here is QEMM 97 against Microsoft's MS-DOS 6.x EMM386. Versions
matter: behavior and defaults differ across earlier DOS and later Windows
releases.

Both products use the 386 paging machinery to map physical RAM above 1 MiB
into useful low address ranges. DOS programs execute in virtual-8086 mode,
while a protected-mode manager owns the page tables and mediates relevant
operations. This creates UMBs and EMS windows without requiring those addresses
to be backed by RAM at the same physical location. Microsoft documents this
mechanism for EMM386 and other expanded-memory managers in
[KB Q82298](https://jeffpar.github.io/kbarchive/kb/082/Q82298/).

| Topic | Microsoft EMM386 / MS-DOS 6.x | QEMM 97 |
| --- | --- | --- |
| Core mechanism | v86 plus paging, UMBs and EMS backed by extended memory | Same CPU facilities, with its own management and compatibility policy |
| Service configuration | HIMEM precedes EMM386; RAM/NOEMS and NOVCPI control separate services | QEMM supplies its documented memory-manager services; QDPMI is a separate component |
| Placement | DEVICEHIGH/LOADHIGH and MemMaker configure upper-memory use | Optimize/LOADHI, Squeeze and DOS-Up provide additional placement/residency behavior |
| Firmware address ranges | Inclusion/exclusion, scanning and shadow-related options | Stealth M/F changes ROM visibility around firmware execution to reclaim eligible ranges |
| Extra suite components | DOS memory-manager functionality and its documented Windows interaction | Separate Windows components include MagnaRAM, CacheBack, TurboLoad and FreeMeg |
| Observation interface | Standard services plus provider-specific behavior | Documented QPI exposes status/version, Stealth information, page entries and other services |

Microsoft's [EMM386 command help](https://www.infania.net/misc/dos622help/emm386.exe.html)
describes RAM, NOEMS, NOVCPI, upper-memory exclusions and buffering. Do not infer
that `NOEMS` disables all protected-mode services: DOS 6.x EMM386 still provides
VCPI unless the relevant NOVCPI configuration disables it
([KB Q96625](https://jeffpar.github.io/kbarchive/kb/096/Q96625/)). Microsoft's
[MemMaker help](https://www.infania.net/misc/dos622help/memmaker.html) also makes
clear that automated placement was not unique to QEMM.

The QEMM distinctions above follow the supplied QEMM 97 guide and technical
references: `OPT-TECH.PDF` (installation versus resident sizes), `DOSUP.PDF`,
`STEALTH.PDF`, `WINFEAT.PDF`, `BUS-MAST.PDF` and `QPI.PDF`. They are source
documentation, not claims that those mechanisms have been reproduced here.
EMM386 itself has ROM-related/shadow handling; a blanket claim that only QEMM
ever reclaims such space would be inaccurate. See Microsoft's
[KB Q78557](https://ftp.zx.net.nz/pub/archive/ftp.microsoft.com/MISC/KB/en-us/78/557.HTM).

## Mechanisms worth carrying into fDisBull

The implemented parts use QEMM's mechanisms to improve observation:

1. **Separate address domains.** Keep file/object offsets, segment:offset,
   linear addresses and physical backing distinct. Capture mode, descriptor
   state and page entries with the observation. A changed window mapping must
   not be described as a copy of memory.
2. **Respect entry contracts.** Device Strategy and Interrupt routines are
   independent calls. Their request pointer and stack are caller state, not
   DOS executable defaults. A resident boundary needs observed initialization
   evidence, not a guess from file size.
3. **Use bounded provider adapters.** QPI offers an observation interface for
   QEMM 6.00 onward. The helper calls only GetVersion, GetStatus, GetInfo and
   GetPTE. Original QEMM bytes are not distributed or reimplemented.
4. **Retain uncertainty.** Configuration, helper reports, actual CPU stops,
   complete page loops and native compatibility are separate facts. Reports
   preserve partial failures, raw BCD values and raw PTEs.

Further useful work would track memory-manager allocation/free events,
resident lifetimes, callback chains, mapping changes and independent EMS/XMS/
VCPI/DPMI availability. These need their own observed state and tests. This
change does not introduce an Optimize clone, ROM interception, host-memory
compression or a general virtual I/O layer. The documented QPI I/O callback
interface itself has version/mode/width limits, so it would not be a universal
tracing mechanism.

For a stopped native QEMU machine, `debug-memory-translation` optionally takes
`length` to return `data_hex` and `backing_layer`. It checks a single observed
4 KiB non-PAE mapping, reads the native virtual address and selected extended
RAM backing, and requires matching bytes and an unchanged stopped CPU and
walk. The layer ID follows the physical page within one run and VM epoch. A
guest can select A, then B, then A at the same linear address while both
physical pages keep their contents. A new run or cold restore changes the
identity scope. This read does not change a PTE, switch the guest's mapping,
establish task or allocation lifetime, or replace the separate code patch layers.

## Verification and limits

The focused tests cover authored flat/MZ drivers, malformed chains, persistent
entry contexts, child-header edits, mixed LE object widths and fixups, FAT12/16
admission, profile tampering, v86/descriptor state and page-walk refusal cases.
The QPI helper is rebuilt from GNU assembler source and compared with the
packaged bytes. Optional Unicorn tests execute those actual helper instructions
against explicit DOS/QPI test doubles, including scratch-register destruction,
partial failures and file-output errors. Those doubles are not QEMM.

Native boot qualification requires an actual QEMU executable plus a prepared
bootable DOS/QEMM image. A successful synthetic test, configuration check or
report parse does not satisfy that gate. Windows enhanced-mode execution,
general VxD loading, arbitrary remapped source bindings, complete driver
semantics, DMA device fidelity and whole-game behavior are not qualified by
this feature.
