# Native platform inspection and calls

fDisBull 0.7 feeds Linux ELF, macOS Mach-O and Windows PE linkage metadata into
the shared static call/flow/effect pipeline. Its current CPU adapters support
x86 16/32/64 and ARM64; each native container still has its own supported machine
and endian constraints. Importing a file never runs its code, loader, imported
functions or initializers. Native macOS host execution has not been verified.

## Start with the supplied projects

```bash
fdisbull calls examples/platform-linux.fdb --kind library
fdisbull call-effects examples/platform-linux.fdb --access write
fdisbull libraries examples/platform-mac-arm64.fdb
fdisbull linkage examples/platform-mac-x86_64.fdb
fdisbull header examples/platform-pe.fdb
fdisbull segments examples/platform-mz.fdb
```

`examples/platforms-v07.json` records their qualification. The Linux example is
compiled C; the universal Mach-O and dual PE/MZ examples are authored fixtures.
Stored static results are not target-program execution traces. Existing
DinoPark 0.6 receipts retain their original scope and are unchanged.

## Choose an image and CPU slice

```bash
fdisbull inspect ./UniversalBinary
fdisbull inspect ./UniversalBinary --slice-arch arm64
fdisbull import ./UniversalBinary mac-arm.fdb --slice-arch arm64
fdisbull import ./UniversalBinary mac-intel.fdb --slice-arch x86_64
fdisbull analyze-module ./universal.dylib module.fdb --slice-arch arm64
```

Unselected FAT inspection inventories slices. Native import requires an
explicit, unique architecture match: `x86` is 32-bit, `x86_64` is 64-bit, and
`arm64` is ARM64. Duplicate matching subtypes are an error rather than an
automatic preference. The same selector on a thin file must match that file.
`--arch` selects flat raw mode and is a different operation.

The full original universal container stays in the project. Selection records
both container and slice identity; section/string/patch file offsets refer to
the original container, while virtual addresses refer to the selected image.
Unselected slices are not decoded or silently modified by a selected-slice
memory patch.

```bash
fdisbull inspect ./program.exe
fdisbull inspect ./program.exe --image mz
fdisbull import ./program.exe native.fdb --image pe
fdisbull import ./program.exe dos.fdb --image mz --load-segment 0x1000
fdisbull analyze-module ./program.exe dos-module.fdb --image mz
```

`--image auto` is the default and selects PE when present. Explicit `pe` requires
that native view. Explicit `mz` selects the declared DOS load image only if its
ordinary MZ header, declared extent, relocations and entry are valid. An MZ magic
prefix does not guarantee a loadable DOS stub. A DOS view uses its declared
module length, not a guessed cutoff at the secondary header. `inspect` reports
`image_views` and unavailable-view reasons. Keep PE and DOS analyses in separate
projects; their mappings and instruction contexts differ.

The JSON equivalents are `slice_arch` and `image` on `inspect`, `import` and
`analyze-module`. `identify` reports container recognition and takes no selector.

## Inspect linkage, then analyze calls

```bash
fdisbull import ./program program.fdb
fdisbull libraries program.fdb
fdisbull relocations program.fdb --limit 50
fdisbull linkage program.fdb
fdisbull auto-analyze program.fdb
fdisbull calls program.fdb --kind library
fdisbull call-effects program.fdb --access write
```

| Container | Established from the file | Kept unresolved |
| --- | --- | --- |
| ELF | GOT cells from JUMP_SLOT/GLOB_DAT; native slot-proven PLT aliases; symbol-version requirements; DT_NEEDED, interpreter and RPATH/RUNPATH; export kinds | Actual provider/load bias; unversioned library attribution; unsupported PLT forms; implicit REL addends not decoded from storage |
| Mach-O | Load-command dependency ordinals; available dyld/chained binding records; exact indirect-symbol pointer/stub identities; export/reexport kinds | Actual dyld target/slide; unsupported or incomplete chains; weak/flat lookup providers; authenticated-pointer behavior |
| PE | Preferred-VA normal IAT slots, exports/ordinals/forwarders and selected native/DOS view evidence | Actual loaded DLL addresses and providers; delay-load imports; automatic forwarded-destination loading |

For ELF, a version requirement can identify a requested library such as
`libc.so.6`; it does not observe which runtime object supplies the symbol.
Unversioned imports keep `module: null` and dependency candidates. A GOT slot
address is the loader's pointer cell. COPY storage and TLS records are not
callable GOT slots; object/absolute exports and IFUNC resolvers are not ordinary
native function entries. Versioned aliases retain their separate identities.

Mach-O lazy/chained pointer contents may be zero, resolver pointers or encoded
fixups. They are not read as resolved external code addresses. Metadata stubs
join calls through exact symbol/slot evidence. Special library scopes, missing
metadata and unsupported cases stay explicit rather than being assigned a dylib
from a similar name.

`calls` and `import_call` xrefs identify a **declared import request**. They do
not prove that the binding is unchanged or that any runtime call occurred.
`call-effects` instantiates a named contract only conditionally. Its
`binding_evidence[].binding_unchanged_under_static_state` means:

| Value | Meaning |
| --- | --- |
| `true` | The available abstract state has no modeled may-write preventing the unchanged-slot assumption. |
| `false` | A modeled possible write or memory taint prevents that proof. |
| `null` | An analyzed state or sufficient proof is unavailable. |

Even a concrete buffer address/length describes an effect conditional on the
declared binding resolving to the contract. `resolved` concerns that buffer
expression, not an observed external target. Use instruction-level
`memory-accesses` alongside bulk summaries and retain the binding conditions.

## ABI and refresh limits

ELF x86-64 defaults to System V; ELF ARM64 uses AAPCS64. Mach-O ARM64 uses the
separate `aarch64_darwin` profile, also selectable as `--abi darwin_arm64`.
It currently describes integer register arguments. Darwin packed stack and
variadic placement require type information and remain uninferred; complete
floating/vector rules and pointer authentication are not modeled. ABI defaults
are analysis assumptions, not recovered source signatures.

```bash
fdisbull refresh-metadata existing.fdb
fdisbull advanced-status existing.fdb
fdisbull auto-analyze existing.fdb
```

Metadata refresh reparses retained ELF/Mach-O/PE source bytes, replaces the
metadata symbol/stub index and makes dependent results stale. It preserves
authored annotations, byte versions and mappings. It needs no original path
when those bytes are retained; a project lacking source bytes needs a new import.
`refresh-facts` separately backfills effects and continuations of stored native
instructions. Neither command loads a runtime library or applies runtime ELF
relocations, dyld slides or fixups.
