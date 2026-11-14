# Authored PE32 and Win16 offline qualification plan

This is an execution plan, not a native test receipt. Use the existing serialized
executor and a private external workspace; retain source, compiler, executable,
runtime and output hashes. Do not place executables, databases, machine states,
screenshots or private user targets in Git. These checks qualify only the authored
fixtures in the selected runtime. Preserve the already accepted PE64/DOS kit.

## Admission and runtime inputs

1. Check the exact source commit and tracked cleanliness; create a new private
   workspace on an admitted external filesystem. Before each bulk phase run
   `python3 /Users/tiga/.codex/bin/storage_admit.py --path <existing-parent> --expected-bytes <conservative-phase-maximum>`;
   stop on refusal. Allow for separate reconstructed initramfs and native state
   sidecars, and re-admit before material additional growth. Do not reuse an
   existing evidence directory.
2. Bind the retained QEMU, firmware, kernel and full Windows base and recipe by
   their recorded hashes. The retained 0966 donor acceptance is PE64 evidence;
   neither its label nor the presence of a manifest proves PE32 or Win16 support.
   The original full image is 1,239,330,025 bytes, SHA-256
   `2a4dee4b32c4a392f83fe187e65f82d452be6fac1b896f834f2d7361e849f2c0`;
   verify the actual chosen donor and lineage before reuse. A complete read-only
   scan of that exact image reached EOF with 29,416 entries and 11 CPIO trailers
   (member entry counts 21,266; eight empty; 8,144; six). The earlier scan that
   stopped at the first trailer was incomplete and its absence claim is withdrawn.
3. Inventory the complete relevant CPIO streams without extraction to determine
   whether the base actually contains a Wine 11 new-WoW64 runtime, Xvfb, Python,
   the x86-64 MinGW compiler and dependencies needed by `wine_guest/init.sh`,
   plus Wine i386 `kernel32.dll`, `winevdm.exe`, and `krnl386.exe16`. The complete
   scan found all these paths and the i686 compiler and libraries in member 10;
   Xvfb, Python 3.12 and x86-64 MinGW were found in member 1. See the exact path
   expectations in `scripts/ci/retained-runtime-base.py` `REQUIRED`.
   The i686 compiler in that capability inventory is needed to build the PE32
   fixture, but guest init treats it as optional when the fixture is supplied
   externally. A filename inventory is admission evidence, not proof that Wine
   loads the programs. If required runtime components are absent, stop and locate
   a provenance-bound, compatible retained Wine 11 new-WoW64 donor; do not silently
   download or alter the accepted donor. Rebuild a **new** runtime using the
   candidate's `src/fdisbull/wine_runtime.py` resources and a corresponding new
   `fdisbull-chat-windows-recipe-v1` hash receipt. The existing 0966 recipe pins
   both its resources and output and must not be rewritten to fit another image.
4. The Win16 build needs a separately available genuine Open Watcom SDK; it is
   not required at guest runtime. The complete archive scan found `/opt/watcom`
   and its `binl/wcc` and `binl/wlink` in member 10. Their first 4 KiB identify
   both as i386 ELF32 ET_EXEC with no PT_INTERP or PT_DYNAMIC: their ELF headers
   indicate static linking, but Linux i386 compatibility and execution remain
   untested. The documented recipe expects Open Watcom 1.9 headers, libraries,
   and `WATCOM=/opt/watcom`. Inspect provenance and hash the SDK/toolchain first. If it is
   unavailable, record that blocker: obtaining and staging the official SDK is a
   separate authorized preparation, not a download during offline qualification.
   Existing installed or retained i686 MinGW must likewise be identity-checked.

## Future fixture build, once inputs and storage are admitted

Run these commands only on the selected Linux x86-64 builder, in a new private
workspace with the explicitly verified SDK and compiler available. The snippet is
an execution recipe, not evidence it has run. Substitute absolute paths without
changing the pinned source checkout or accepted runtime. Capture exit statuses,
compiler version, source and executable hashes in a private build receipt.

```sh
# REPO is the exact candidate checkout; WORK is a new private admitted directory.
# This source tree has no SDK or compiler bundled.
export WATCOM=/opt/watcom
export PATH="$WATCOM/binl:$PATH"
cp "$REPO/tests/offline_win16_oracle.c" "$WORK/ORACLE.C"
cd "$WORK"
timeout 120s wcc -bt=windows -ml -zW -od -w3 \
  -i=/opt/watcom/h -i=/opt/watcom/h/win -fo=ORACLE.OBJ ORACLE.C
timeout 120s wlink system windows option quiet option map=ORACLE.MAP \
  option stack=16384 option heapsize=8192 name ORACLE.EXE file ORACLE.OBJ
timeout 120s i686-w64-mingw32-gcc -O0 -g -mwindows \
  -o selftest32.exe "$REPO/src/fdisbull/wine_guest/selftest32.c" -luser32 -lgdi32
sha256sum ORACLE.C ORACLE.EXE selftest32.exe
```

Generate the Win16 static profile with the candidate checkout's helper, outside
Git. It rejects missing/nonunique markers, marker segment placement changes and
unsupported NE layouts. A compiler may legitimately emit an incompatible layout;
that is an explicit stop for source investigation, not proof of runtime failure.
The profile's source hash is a declaration and does not prove compiler provenance.

```sh
PYTHONPATH="$REPO/src:$REPO/tests" python3 - "$WORK" <<'PY'
import json, pathlib, sys
from offline_windows_oracles import win16_profile
work = pathlib.Path(sys.argv[1])
profile = win16_profile((work / 'ORACLE.EXE').read_bytes())
with (work / 'win16-profile.json').open('x') as out:
    json.dump(profile, out, indent=2, sort_keys=True)
    out.write('\n')
PY
```

## Future finite acceptance

Use the bound QEMU, kernel and newly verified runtime with networking disabled;
set the private pytest base directories on the admitted external filesystem. Run
one profile at a time under the serialized owner and retain complete receipts.
The owner must supervise and reap its entire QEMU process group, including on
timeout; the shell timeout is a ceiling, not proof that cleanup succeeded.
The exact environment variable contracts are:

```sh
timeout --signal=TERM --kill-after=30s 3600s env FDISBULL_REQUIRE_WINDOWS=1 \
FDISBULL_PE_QEMU="$QEMU" FDISBULL_PE_KERNEL="$KERNEL" \
FDISBULL_PE_INITRAMFS="$WINDOWS_RUNTIME" FDISBULL_PE32_FIXTURE="$WORK/selftest32.exe" \
python3 -m pytest -q --basetemp "$WORK/pe32-evidence" \
  tests/test_windows_native.py::test_real_pe32_original_process_shared_input_scenes_and_dot_mode

timeout --signal=TERM --kill-after=30s 3600s env FDISBULL_REQUIRE_NE_AUTHORED=1 \
FDISBULL_NE_QEMU="$QEMU" FDISBULL_NE_KERNEL="$KERNEL" \
FDISBULL_NE_INITRAMFS="$WINDOWS_RUNTIME" FDISBULL_NE_AUTHORED_FIXTURE="$WORK/ORACLE.EXE" \
python3 -m pytest -q --basetemp "$WORK/win16-evidence" \
  tests/test_win16_authored_native.py::test_authored_win16_native_roundtrip
```

PE32 acceptance requires same-session save/restore and, separately, a new
session restored from that save with requalified address and breakpoint, memory,
frame and a physical click. Win16 requires source-bound segment selectors,
original breakpoint/memory, completed trace, frame, physical key and both same-
and fresh-session restore/replay. A timeout, missing capability, unexpected
profile or absent evidence remains a failed/incomplete qualification. Do not
promote the static profile, scripted unit tests, previous PE64 acceptance, or an
unrelated historical Win16 run into current native evidence.

For an extended offline kit, supply the three explicit inventory roles
`pe32_fixture`, `win16_fixture`, `win16_profile` and opt into
`windows_acceptance: pe64-pe32-win16`. Generate its new recipe and manifest from
these exact candidate resources and fixture hashes. The full offline consumer
verifier must itself run under the existing isolated, no-network acceptance
procedure; building a kit alone is not consumer qualification.
