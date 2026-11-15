# Native QEMU renderer and audio observations, API 1

This optional patch extends the separately built **QEMU 10.0.13** runtime used
by the [native clock profile](../qemu-clock/README.md). Apply the current clock
patch first, then this media patch. Both manifests identify their exact base
and resulting source bytes. These are experimental private QMP interfaces;
the Python package does not install an emulator or host audio driver.

The boundary is a completed synchronous **renderer update**, and complete PCM
frames delivered by QEMU's **audio capture callback**. Neither establishes a
completed guest application frame, VBlank, device queue drain, input consumption,
audible playback or cycle parity. The observers never resume the guest or pace
it against host time. The separate [host clock-sync controller](../../docs/DOS_QEMU_TIMING.md)
does not change media sampling rates, renderer cadence or playback qualification.

## Reproduce the patch

Start with the official archive and private build prerequisites documented in
the clock README. Verify and apply `native/qemu-clock/source-manifest.json`
first. Then, from the fDisBull checkout:

```sh
python3 - "$FDB_QEMU_SOURCE" native/qemu-media/source-manifest.json <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys
source, manifest = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
record = json.loads(manifest.read_text())
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert (source / 'VERSION').read_text().strip() == record['qemu_version']
dependency = manifest.parent.parent / 'qemu-clock' / record['requires_clock_patch']
assert digest(dependency) == record['requires_clock_patch_sha256']
patch = manifest.parent / record['patch']
assert digest(patch) == record['patch_sha256']
for item in record['files']:
    path = source / item['path']
    assert (not path.exists() if item['base_sha256'] is None
            else digest(path) == item['base_sha256']), path
subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)],
               cwd=source, check=True)
for item in record['files']:
    assert digest(source / item['path']) == item['patched_sha256'], item['path']
print('All native media source hashes verified')
PY
```

Use the clock README's private `x86_64-softmmu` build recipe with TCG and
Pixman. QEMU's `none` audio driver and capture mixer are built even with
`--audio-drv-list=`; no ALSA, PulseAudio or physical sound device is required.
Source archives include the authored patches and manifests. Build products,
firmware, DOS disks and runtime databases stay outside source packages.

## Renderer observer

| Native command | Parameters | Result |
| --- | --- | --- |
| `x-fdisbull-start-display` | New `token`, `period-ns` from 1,000,000 through 1,000,000,000 | Empty window; first virtual timer scheduled one period later |
| `x-fdisbull-query-display` | None | Window, latest publication ID, publication time and dimensions |
| `x-fdisbull-stop-display` | Current `token` | Disarmed observer with last pixels retained; repeated stop is idempotent |
| `x-fdisbull-export-display` | Current `token`, new private `filename` | Exact binary P6 of retained pixels; no refresh |

The supported console is index zero, head zero, exact standard VGA device
type, with a synchronous renderer, no GL, display listeners or pending
screendump coroutine. `qemu_console_can_update_headless_sync()` verifies this
under BQL. The timer invokes `graphic_hw_update()`, which completes standard
VGA rendering synchronously. Every RGB row is then copied while BQL remains
held, before publishing the ID and timestamp. A surface/pixman reference alone
would be insufficient because VGA can expose a surface backed by guest VRAM.

Only the latest publication is retained: at most 16 MiB of packed RGB24 and
8192 pixels per dimension. IDs start at one within a unique window token.
The timer remains aligned to `start + N * period`; missed observations are
skipped. The period is the caller's observation cadence, not a frame rate.
A pending debugger/native stop wins. The ordinary clock extension suppresses
idle warping once a CPU has requested a debugger stop, including a normal
GDB continue with no clock budget armed. A merely halted CPU remains eligible
for ordinary virtual timer advances.

`capture_display(after_update=...)` refuses an unchanged publication instead
of waiting or running the guest. The ID belongs to the current window. Its
receipt reports publication time and observed age. `capture_surface()` and
`screenshot()` retain their existing meaning: refresh the current stopped
display, which can include partial guest drawing. Those refreshes do not
overwrite the observer's private RGB copy.

The exact upstream source explains why this is a renderer boundary: precise
VGA retrace is computed when the guest reads the status register; default
retrace toggles on reads. Ordinary GUI refresh uses `QEMU_CLOCK_REALTIME`.
Neither supplies a stock completed guest-frame event. See upstream
[`hw/display/vga.c`](https://qemu.googlesource.com/qemu/+/refs/tags/v10.0.13/hw/display/vga.c),
[`hw/display/vga_int.h`](https://qemu.googlesource.com/qemu/+/refs/tags/v10.0.13/hw/display/vga_int.h)
and [`ui/console.c`](https://qemu.googlesource.com/qemu/+/refs/tags/v10.0.13/ui/console.c).

## Audio window

Select `qemu_clock='virtual', qemu_audio='pc-speaker'` at launch. The recorded
configuration adds only the PC speaker and an explicit `none` audiodev named
`fdisbull-pc`, with a 10 ms audio timer period and fixed 32,000 Hz mono unsigned
8-bit output. Sound Blaster, OPL/FM and other guest sound devices are not
configured or qualified by this profile. Host playback stays disabled.

| Native command | Parameters | Result |
| --- | --- | --- |
| `x-fdisbull-start-audio` | New `token`, `max-frames` from 1 through 1,920,000 | Empty registered window; no mixer invocation or guest run |
| `x-fdisbull-query-audio` | None | Retained count, format, callback boundaries and dropped count |
| `x-fdisbull-stop-audio` | Current `token` | Detached capture with samples retained; no flush |
| `x-fdisbull-export-audio` | Current `token`, new private `filename` | Exact raw PCM; overflow is refused |

`AUD_add_capture()` registers the observer. Each capture callback retains
whole PCM frames and a contiguous sample index range plus the callback's
`QEMU_CLOCK_VIRTUAL` timestamp. That timestamp describes delivery to the
capture callback, not the precise onset of every sample. Device/mixer buffers
may contain samples generated before capture registration. Inactive intervals
produce no synthetic silence. Concatenated PCM duration is therefore distinct
from elapsed guest time, even though both can be observed.

Capacity is bounded by the requested sample count and 8192 callback records.
Overflow retains a known prefix and counts refused frames; it never silently
wraps or resumes execution. An overflowed window cannot be exported as a
complete WAV. Stop it, inspect the dropped count, and explicitly start a new
window. Starting a new window clears prior samples and never replays them.

`capture_audio()` writes a WAV around those exact PCM bytes with both stopped
clock brackets. Previously exported PCM prefixes must remain unchanged.
`device_queue_drained` and `guest_audio_complete` remain unknown. See upstream
[`audio/audio.c`](https://qemu.googlesource.com/qemu/+/refs/tags/v10.0.13/audio/audio.c),
[`audio/noaudio.c`](https://qemu.googlesource.com/qemu/+/refs/tags/v10.0.13/audio/noaudio.c)
and [`hw/audio/pcspk.c`](https://qemu.googlesource.com/qemu/+/refs/tags/v10.0.13/hw/audio/pcspk.c).

## Ownership and failure

Every command requires the valid stopped native clock profile: one TCG vCPU,
fixed icount, no replay/migration, and no pending clock-budget stop. The live
Python owner creates window tokens, rejects unsolicited windows and validates
native epochs, times, formats, dimensions and contiguous sample boundaries.
After stop, all retained fields freeze except the later observation time.
Repeated pixel exports under one publication ID and retained PCM prefixes
must remain byte-identical. Wrong tokens cannot stop or export another window.

Native reset, incompatible runstate or epoch change invalidates the observers.
Starting either observer installs a process-lifetime migration blocker; this
slice does not define saved-state serialization or cold restoration. The
controller closes on uncertain mutation, malformed native evidence or failed
snapshot reads. Commands and artifact reads share the machine lock and saved
script deadline; a start/stop that exceeds its receipt deadline closes the
machine. There is no automatic retry, fallback or synchronization loop.

The native witnesses are `tests/test_qemu_display_native.py` and
`tests/test_qemu_audio_native.py`, using authored DOS source and separately
supplied runtime inputs. They cover partial drawing versus retained pixels,
publication freshness, graphics/text mode changes, passive reads, tone samples,
inactive output, overflow, token/reset ownership and saved evidence. Public
protocol/deadline adversaries are separate from actual native production tests.
