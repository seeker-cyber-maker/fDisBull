# Native sparse retained renderer probes

This optional ninth patch reads selected RGB pixels from a publication already
retained by the [native renderer observer](../qemu-media/README.md). Apply the
exact clock, media, input, retrace, input-retrace, keyboard-press, keyboard-type
and mouse-click patches first. The [source manifest](source-manifest.json)
pins those eight prerequisites, this patch and its two changed native files.
Earlier patches and their existing commands retain their original bytes.

Select `qemu_clock='virtual'` and inspect `renderer_probe`. This capability
requires the existing native clock/display commands and the new
`x-fdisbull-probe-display` command. Precise retrace is unnecessary. An
eight-layer executable retains `renderer_capture` and its existing renderer
operations while refusing the new sparse helper.

The public method is
`display_probe(points, *, window=None, update_id=None, timeout_ms=1000)`.
JSON uses `debug-display-probe`; saved scripts use `display-probe`. It requires
a stopped owned machine and a project outside a caller-owned transaction.
Observation is passive: the caller must already have started display
observation and explicitly executed enough guest time to produce a publication.

## Native request and response

| Argument | Contract |
| --- | --- |
| `token` | Current owned display-window token |
| `update-id` | Exact positive ID of the current retained publication |
| `points` | Zero through 256 ordered `{x, y}` objects with strict signed integer coordinates |

Each coordinate must lie within the retained image: `0 <= x < width` and
`0 <= y < height`. Those dimensions are already bounded to 8192 pixels and
16 MiB of packed RGB storage by the original observer. The entire list is
validated before a result is allocated or a sample is read. An invalid suffix
therefore cannot return a partial successful prefix. Empty lists are valid but
still require a publication and exact identity. Request order and duplicate
coordinates are preserved.

The result contains exactly these structured components:

```json
{
  "display": {"...": "existing FdisbullDisplayInfo receipt"},
  "samples": [
    {"x": 10, "y": 10, "r": 255, "g": 0, "b": 0},
    {"x": 20, "y": 10, "r": 0, "g": 255, "b": 0}
  ]
}
```

`display` retains the existing publication ID, window, native clock epoch,
dimensions, publication timestamp and stopped observation time. Each RGB
channel is an unsigned byte. Sampling reads the observer's owned packed RGB24
buffer under BQL, using a checked coordinate and a `size_t` offset. It does
not read a potentially mutable VGA surface or guest VRAM.

The existing stopped native-clock guard remains authoritative. It refuses a
running machine, pending native stop, armed/fired clock budget, invalidated
observer or lost clock epoch. Token, stale-ID, coordinate and count errors
preserve a valid observer and its publication. There is no new timer, event
handler, migration mechanism or publication state.

## Host identity and bounds

Public points are ordered `[x, y]` pairs. Optional `window` and `update_id`
must be supplied together and must match the current publication exactly;
when both are omitted the helper selects the latest retained publication.
The native request always carries the selected token and exact update ID.
An empty list does not bypass the identity or publication checks.

Complete signatures and values validate before host lock admission. Saved
scripts validate capabilities, signatures and literal arguments across the
whole plan before earlier effects; resolved values validate again. One host
deadline covers admission, native reads, validation and journal persistence,
intersecting any tighter incoming deadline.

The host compares the full returned display receipt to its stopped prequery,
checks every requested coordinate and RGB byte, and brackets the operation
with unchanged native clock epoch, instruction counter and virtual time.
At most the previous probe's 256-point sample map is retained for overlap
consistency checks. This bounded check does not establish integrity of unseen
pixels. Malformed evidence, broken channels or failed persistence close the
owner without retry; a journal that committed before a late failure remains
evidence and is returned where available.

No image artifact, temporary PPM, file export, screen refresh, clock advance,
guest run, sleep, input action, implicit wait, retry or fallback occurs. The
sparse receipt does not invent a whole-raster hash. Use `capture_display()`
when the complete retained image and its pixel SHA-256 are needed.

## Coordinate and publication scope

Coordinates name pixels in the **retained renderer image**. They are not
guest mouse coordinates, an INT33 mapping, a mode ID or an application frame
number. `completed_guest_frame` and `guest_frame_id` remain unknown. The
existing `frame_probe`, `click`, `click-frame` and their scene contracts remain
unchanged and unavailable on this native path.

Guest VRAM, palette and mode changes can occur after publication. A probe
still reads the older private RGB copy until a later observer callback
publishes a replacement. An ordinary `capture_surface()` refresh does not
replace that copy. A stopped observation window can therefore retain pixels
and dimensions from a mode the guest has since left. The receipt retains
the original publication time and reports its age instead of assigning it
current mode or retrace metadata.

Publication IDs increase within a host-owned window, and a new window starts
empty. The host creates fresh UUID tokens rather than adopting an unsolicited
native window. The raw native start command does not maintain a global token
history; arbitrary external token reuse is not a global identity guarantee.
Reopened journals retain historical evidence, not a live observer or VM.

RGB equality at selected coordinates does not establish equality of complete
images or publication identities. Renderer completion does not establish
completed guest drawing, VBlank, display scanout, UI readiness, cursor position,
input consumption or hardware timing parity. `completed_guest_frames`,
`absolute_mouse`, `timed_input` and `guest_time_control` remain false. DOSBox
remains the default and all 127 promotion qualifications remain open.

## Reproduce the native source

Begin with the official QEMU 10.0.13 archive and private build prerequisites
in the [clock README](../qemu-clock/README.md). The archive identity is pinned
in every native manifest. From the fDisBull checkout, apply all nine layers
to a fresh extracted source tree:

```sh
python3 - "$FDB_QEMU_SOURCE" <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys

source = Path(sys.argv[1]).resolve()
root = Path('native').resolve()
layers = ('clock', 'media', 'input', 'retrace', 'input-retrace',
          'keyboard-press', 'keyboard-type', 'mouse-click', 'display-probe')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name in layers:
    directory = root / ('qemu-' + name)
    record = json.loads((directory / 'source-manifest.json').read_text())
    assert (source / 'VERSION').read_text().strip() == record['qemu_version']
    for dependency in layers:
        key = 'requires_' + dependency.replace('-', '_') + '_patch'
        if key in record:
            path = root / ('qemu-' + dependency) / record[key]
            assert digest(path) == record[key + '_sha256'], path
    patch = directory / record['patch']
    assert digest(patch) == record['patch_sha256'], patch
    for item in record['files']:
        path = source / item['path']
        assert (not path.exists() if item['base_sha256'] is None
                else digest(path) == item['base_sha256']), path
    subprocess.run(['patch', '--batch', '--fuzz=0', '--forward', '-p1',
                    '-i', str(patch)], cwd=source, check=True)
    for item in record['files']:
        assert digest(source / item['path']) == item['patched_sha256'], item['path']
print('All nine native source layers verified')
PY
```

Use the private `x86_64-softmmu`, TCG and Pixman build recipe in the clock
README. Source round-trip, complete QAPI generation, native compilation,
controlled guest observations and installed-package checks are separate
evidence boundaries. Their dated results belong in the
[handoff log](../../docs/DOS_QEMU_HANDOFF.md). Native binaries, firmware, DOS
images and private project databases stay outside Git and tool packages.
