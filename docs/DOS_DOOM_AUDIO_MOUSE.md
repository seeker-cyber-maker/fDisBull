# Doom PC-speaker and DOS mouse qualification

The local QEMU route can combine an original DOS Doom executable, a real DOS
mouse driver, physical PS/2 input, retained PC-speaker PCM and explicit LE
checkpoints/capture histories. Each part needs its own guest-consumption or
restore witness. A QMP input acknowledgment or a nonempty audio file alone
does not establish application behavior or parity. DOSBox-X remains the default
backend and is retained. These procedures dispatch no CI.

This page defines the reproducible inputs, procedure and claim ceiling. Dated
results, exact candidate identities and sanitized receipts belong in the
[handoff log](DOS_QEMU_HANDOFF.md) and GitLab !117. The root controller publishes
the campaign result there after its native, cold-restore and cleanup gates;
the recipe itself is not a native acceptance result. Keep commercial binaries,
WADs, project databases, checkpoint payloads, screenshots and audio private.

## Pin and install a real DOS mouse driver

The minimal FreeDOS component contains the kernel and FreeCOM, without a mouse
driver. QEMU's physical mouse API supplies relative PS/2 events; it does not
implement DOS INT33. The current witness uses this exact locally available
FreeDOS package:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| FreeDOS 1.4 `FD14-LiteUSB.zip` | 17,671,175 | `857dcd2ebf9d3d094320154db5fb5b830acba6fb98f981a95a0ca7ab3350338b` |
| Its `FD14LITE.img` | 33,554,432 | `f539d456b792594bc3ca59d4e0f4c23d4f1fee73370c1390b2da245400718d36` |
| Image member `/PACKAGES/base/ctmouse.zip` | 275,825 | `dd378ddfe5b6948d3073c12acaf0ca31bf60d0898f1cd708b6858083a14a41c7` |
| Package member `BIN/CTMOUSE.EXE` | 5,829 | `822cf550c9e19a22785722d2306aa08ede10ff20bfe931d5a81a15f77c5f363e` |

The FAT partition in this particular image begins at byte 32,256. A separately
prepared `mtype` can read the package without booting or modifying the image:

```sh
"$MTOOLS/mtype" -i "${FD14_LITE_IMAGE}@@32256" \
  ::/PACKAGES/base/ctmouse.zip > "$PRIVATE_MOUSE_DIR/ctmouse.zip"
```

Use a new private output path and verify the image/package hashes before
extracting members. Preserve `APPINFO/CTMOUSE.LSM`, the documentation and
`SOURCE/CTMOUSE/SOURCES.ZIP` with the private package. The source archive contains
`COPYING`. The package LSM identifies CTMouse 2.1b4 and GPL version 2; its older
`CTMOUSE.TXT` introduction still says v2.0. Retain that distinction instead of
treating the older documentation as an executable version measurement. No
driver binary or source package is included in the tool wheel or this test.

For a fresh mouse-enabled launch, derive a **new private boot image** from the
verified FreeDOS component or test baseline. Add the pinned `CTMOUSE.EXE` and
append a startup command such as `C:\CTMOUSE.EXE /P` to its existing
`FDAUTO.BAT`, using the actual boot drive (`A:` for the test floppy). `/P`
selects PS/2 without serial-port search. Preserve the existing startup prefix
and CONFIG files. Pin the derivative and retain the parent/driver hashes and
exact appended command. Do not alter the original component image or rewrite
its manifest to describe a different image.

The existing public launcher accepts this derivative without a new runtime
format:

```python
with project.debugger(
    qemu, game_dir, backend='qemu-dos',
    dos_boot_image=private_mouse_image,
    dos_directory=game_dir, dos_mcopy=mcopy,
    dos_startup_batch='FDAUTO.BAT',
    qemu_firmware=firmware, qemu_transport='pipe',
    qemu_clock='virtual', qemu_audio='pc-speaker',
    qemu_checkpoint_tool=qemu_img,
    dos_arguments='-warp 1 1 -skill 2 -nomonsters -config D:\\DEFAULT.CFG',
) as debug:
    ...
```

Omit `freedos_runtime` when choosing the explicit derived boot image. The
workspace launcher records it as a caller-owned FreeDOS template, places the
captured game directory on `D:`, and preserves its existing startup commands
before appending the process loader. A startup recipe is not proof the driver
installed: the guest must observe the driver and consume input.

## Authored INT33 driver and recovery gate

`tests/test_qemu_dos_mouse_native.py` uses a separately prepared native QEMU and
the caller's exact pinned driver. Its authored COM performs INT33 initialization,
reads horizontal/vertical motion with AX=000Bh, and samples button bits with
AX=0003h. It does not replace the driver, handle IRQ12 itself, fabricate a
callback, or write guest state from the host.

Supply these absolute local paths, using a fresh private external output
directory for each attempt:

```sh
export FDISBULL_QEMU_CLOCK=/absolute/path/to/prepared/qemu-system-x86_64
export FDISBULL_QEMU_DOS_BOOT_IMAGE=/absolute/path/to/FD14-144m-x86BOOT.img
export FDISBULL_QEMU_DOS_MCOPY=/absolute/path/to/mcopy
export FDISBULL_QEMU_DOS_FIRMWARE=/absolute/path/to/pc-bios
export FDISBULL_QEMU_IMG=/absolute/path/to/qemu-img
export NASM=/absolute/path/to/nasm
export FDISBULL_CTMOUSE_EXE=/private/path/to/BIN/CTMOUSE.EXE
export FDISBULL_REQUIRE_QEMU_CLOCK=1
export FDISBULL_REQUIRE_QEMU_MOUSE=1
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=/private/external/short-temp-directory
python -m pytest -q tests/test_qemu_dos_mouse_native.py \
  --basetemp "$NEW_MOUSE_TEST_OUTPUT"
```

`NEW_MOUSE_TEST_OUTPUT` must be a new path: pytest owns its basetemp directory.
Use the current host policy and one controller for the VM phase. Preserve the
`mcopy` invocation name when using an mtools multicall binary. The campaign's
existing native QEMU pin is
`d04993299ae8155d33e33644d1144f39e64d6224145c4671eef737e829e9815d`;
an alternate build needs its own qualification. Environment selection is not
substituted for recording the executable/firmware/tool identities in the run.

The test checks:

- Actual guest driver presence, then physical `+3,0` motion and left-button
  press/release, with literal INT33 counts and button bits observed in guest RAM.
- Pending motion and a held button refusing checkpoint capture without consuming
  the queue, altering the paused CPU or losing the live owner.
- A neutral-input process checkpoint, a distinct `+2,0` right-button interval,
  hot restore and another independently dispatched interval.
- Project close/reopen, a new launcher, cold checkpoint restore, exact CPU/report
  recovery, fresh capture epoch/source binding and another input interval before
  actual DOS termination with exit code 42.
- Original program, driver and input boot-image immutability, plus byte-exact
  cold checkpoint export. The private output includes `native-mouse.json`.

These literal packet magnitudes deliberately use an independently specified
driver branch. In the pinned package's `CTMOUSE.ASM`, `DefArea` initializes
`senscoeff` to 256 on both axes. `updateposition` bypasses sensitivity scaling
for absolute packet motion at most four when that coefficient is at least 256;
AX=000Bh then drains the accumulated `mickeys` fields. Thus the expected totals
are three before capture and five after the next two-count packet. This driver
also applies adaptive gain before updating those fields for larger packets:
at the default coefficient, a twelve-count packet becomes 36 mickeys. AX=000Bh
is consequently not a generic raw PS/2 packet-byte interface. The small-packet
test neither fits an expectation to a native result nor qualifies arbitrary
acceleration curves.

Here, cold means a reopened Project and fresh native launcher in the same test
process. This real-mode horizontal-mickey/button gate does not establish
protected callbacks, arbitrary coordinate mapping, Doom behavior, audio, or
separate-host-process recovery. Ordinary mouse leases and pending motion remain
unsupported checkpoint inputs; the test verifies their refusal, not restoration.

## Original Doom mouse and PC-speaker witness

Use the user's original Doom EXE
`4970b0d1fefa45836a5723777d2bb41e7932965782678aca6c2bbeec705b38d4`
and WAD
`6fdf361847b46228cfebd9f3af09cd844282ac75f3edbb61ca4cb27103ce2e7f`.
Create a new private configuration and keep its derivation/hash. The bounded
campaign selects `use_mouse=1`, `snd_musicdevice=0` and `snd_sfxdevice=1`, with
the launch arguments shown above. It leaves the original EXE/WAD untouched.
Older prepared runs using `-nomouse` cannot qualify an enabled mouse by restoring
their machine state; initialize the driver and game through a fresh boot.

The target witness starts in fresh E1M1, queues public relative motion/button
input, and separates dispatch from application effects. For example, a bounded
left-button shot requires the observed ammunition change from 50 to 49, rather
than treating a click receipt as a shot. Relative turning needs its own stopped
frame/application observation. Preserve interrupted input receipts; explicitly
resolve retained leases/schedules without replaying a delivered click.

The `pc-speaker` profile requires the virtual clock. Start a bounded native audio
window, execute the chosen guest interval, then export its retained samples:

```python
started = debug.audio_start(max_frames=320000)
# Queue an action and execute once under a finite public run/clock budget.
observed = debug.audio_observe()
wav = debug.capture_audio('doom-speaker.wav')
project.debug_export(wav['artifact'], private_wav_path)
```

The format is 32,000 Hz, unsigned 8-bit mono PCM with host playback disabled.
Require a nonempty, nonconstant sample payload and inspect capacity/drop/overflow
facts. The retained output is a native mixer observation, not proof of audible
host playback or sample-perfect onset timing. Export does not execute the guest
or synthesize missing silence. See the [timing contract](DOS_QEMU_TIMING.md).

For LE-qualified protected stops, capture an explicit LE source checkpoint and
stopped history nodes A/B, then compare full CPU, stored PNG and retained PCM at
hot restores of the explicit checkpoint and selected nodes. Reopen separately
for cold restore and byte-exact exports, rechecking actual current source
qualification and fresh owner/binding/epoch identities. The
[LE checkpoint/history contract](DOS_LE_SOURCE_CHECKPOINTS.md) defines these
joins. `source_binding_restored` stays false for the original MZ mapping;
fresh protected source qualification and restored machine state are separate
facts. Neither source handles nor allocation/task lifetime are resurrected.

## Remaining parity boundaries

Sound Blaster PCM, SB16 DMA/IRQ behavior, OPL/FM music and their checkpoint
persistence remain separate work. PC-speaker SFX with music disabled does not
qualify those paths. Existing layers, hooks, IRQs and stronger source-bound
checkpoint rules retain their own admission and preservation tests.

DOSBox-X's current `input.mouse.move` is absolute INT33 cursor placement. It
does not update relative mickey counters through `Mouse_CursorMoved`; the
AX=000Bh path also depends on mouse-lock state. It is therefore not a paired
relative Doom movement witness. A true relative native input seam and an actual
AX=000Bh/game-consumption gate are needed before claiming that comparison.
Its button route has a separate protected/paged INT33 consumption witness in
`tests/test_protected_mode_native.py`; that authored program is not Doom.

The earlier DOSBox-X `nosound` baseline supplies no comparable retained PCM
capture. Matching input dispatch, screenshots or nonempty WAVs cannot establish
one-to-one audio/mouse parity across these different interfaces. Keep the
remaining paired Doom and device/persistence gates open in the handoff and !117;
do not remove or change the default DOSBox-X backend on this evidence alone.

## Separate digital SB16 checkpoint slice

The later [SB16 qualification](evidence/qemu-sb16-checkpoint-2026-11-16/README.md)
uses a new exact native binary and `qemu_audio='sb16'`, with
`snd_sfxdevice=3`, `snd_musicdevice=0`, mouse enabled and the matching
`BLASTER=A220 I7 D1 H5 T6` guest environment. Derive a new private config and
boot image, preserving their originals and the existing startup prefix. The
observed Doom driver opens an unsigned 8-bit **stereo 11,025 Hz** voice; the
retained capture remains **mono U8 32 kHz**. Merely selecting the PC-speaker
profile does not qualify this driver graph.

The application witness holds left mouse for 500 ms and continues for 600 ms.
This is long enough to repeat firing: the actual frames show 50→49 at A and
48 at B after the next 600 ms. Keep physical dispatch, observed ammo, retained
PCM and source qualification as separate evidence. A current 96-byte window
can be unmatched; `dos_source_bind()` already performs a fresh admission and
must refuse that stop. A separate `dos_source_admit()` is useful for inspecting
eligibility, not an authorization token or a way to bypass binding checks.

Explicit LE A and capture-history nodes A/B are restored in hot and separate
Python hosts. Selected saved CPU/site/PNG/device/clock/PCM must match exactly,
with fresh owners and neutral input. Future PCM is checked separately from
CPU stop identity: the accepted history-root continuations reproduce PCM,
chunks, device state and PNG but do not reproduce the original future CPU
endpoint. This slice does not qualify deterministic instruction replay,
OPL/FM music, paired DOSBox-X audio or overall replacement parity.
