# Linux native-state CRC correction — statefix1

The two additional Linux state-restore failures from the original 0.14.0 offline
probe are fixed in the direct Linux DOSBox backend. The published host packages,
release tag and earlier sealed deliveries remain unchanged. This is a separate
local backend correction and versioned offline kit, not a replacement GitHub
release or a claim that the external DeepSeek environment was modified.

## Cause and correction

The native ZIP output adapter forwarded a zero-byte write with a null buffer
to minizip. zlib's `crc32(previous_crc, NULL, 0)` returns its initial CRC value,
zero. When the optional VGA scanline buffer was unallocated, that empty write
reset the nonzero running CRC halfway through the `Vga` record. The record's
data bytes were complete but its stored CRC covered only the suffix.

Instrumentation checked the archive immediately after native save and again
before native load. Its SHA-256 was identical across database storage and the
`Vga` record was already invalid at capture. An independent CRC implementation
agreed with zlib on all calls; the defect was forwarding the empty write.

The complete layers patch now returns zero immediately from
`zip_ostreambuf::xsputn()` when the requested count is zero. It does not alter
state layout, guest execution or CRC validation. The real adapter/minizip
regression fails against the old header and passes with the fix for both stored
and deflated archives; intentionally changed payload data still returns
`UNZ_CRCERROR`. No corrupt saved state is repaired or silently accepted.

The source manifest contains all 28 changed-file hashes. A fresh selective
replay of the complete patch against the declared upstream Git blobs matched
every file. The layers native-CI job is configured for Python **3.13.5** and
includes the new ZIP regression; required-native mode fails if its source
checkout is missing. Hosted ordinary and native Linux CI form a separate gate
from the local receipts recorded below.

## Fresh Linux verification

Both runs used genuine CPython **3.13.5** x86-64 and the unchanged published
0.14.0 wheel, with no network interface and offline, hash-locked dependencies.

- Clean Linux source build and native suite, QEMU CPU `max`: **52 passed**,
  no failures or skips. This includes the actual native ZIP regression.
- Fresh copied-kit Linux session, QEMU CPU `qemu64`: **51 passed**, no failures
  or skips. It used the copied executable, private loader/libraries and a new
  offline environment.
- Both original failing cases repeated three additional times: **6 passed**,
  no failures or skips.

The copied-kit suite exercised register/memory restoration in a fresh session,
editable native state forks, RAM/fetch views, self-modifying code, read/write
watches, breakpoints, clicks/grids, traces, project restart, static patch
isolation, and real offline PNG/trace exports. Its save/load archive audit
performed **40 checks**, with zero invalid members. Saved states,
private databases and authored compiled targets stayed inside private QA storage.

The exact compiler, source, executable, launch-script and dependency identities
are retained with the receipts. The launcher verifies the pinned executable's
SHA-256; its changed hash also distinguishes checkpoint compatibility from the
old launcher. Capture new checkpoints with this backend. Do not assume old
states are portable across emulator identities.

## Delivery and installation

The new ready folder is:

```text
/Users/tiga/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-linux-dos-offline-0.14.0-statefix1/
```

After copying/extracting the kit into Linux, run these commands from its folder:

```bash
/opt/pyvenv/bin/python3 VERIFY-DELIVERY.py
/opt/pyvenv/bin/python3 INSTALL-OFFLINE.py --venv ../fdisbull-014-statefix1-venv --with-tests
../fdisbull-014-statefix1-venv/bin/fdisbull --help
../fdisbull-014-statefix1-venv/bin/python fdisbull_delivery.py
```

The installer refuses an existing destination. `dos_options()` selects the
corrected private Linux backend and libraries including SDL2_net. The POSIX
launcher uses the normal Linux `sha256sum` tool; no system library is replaced.
The actual external `/opt/pyvenv` environment was not accessed or modified.

The sibling ZIP is `fdisbull-linux-dos-offline-0.14.0-statefix1-2026-10-25.zip`, size **56926586 bytes**, SHA-256:

```text
e709ddecc12ed0c9a294fd3cb9e2e280a18c8846a888f0cb60d4e56fcad1f558
```

`DELIVERY.json` binds **326 payload files**. Directory verification,
ZIP CRCs, every entry's SHA-256, executable permissions and payload exclusions
passed before the Linux latest pointers were updated. `LATEST-LINUX-DOS.json`
selects this kit; `LATEST.json` keeps the original full Mac/QEMU bundle and
selects statefix1 under `linux_offline_kit`. The original full bundle's runtime
images remain unchanged; this kit corrects direct Linux DOSBox.

No game files, in-game saves, captured native/emulator states, project databases,
compiled target fixtures or runtime images are included. Selected [fresh
verification evidence](../experimental/dosbox-x/evidence/linux-state-crc-2026-10-25/)
contains metadata, test reports, an offline frame/grid and a bounded trace;
it contains no state or database payloads. The earlier failed receipts remain
historical and byte-for-byte intact.
