# Native publication-bound relative mouse motion

This optional eleventh patch adds one passively armed relative PS/2 motion
batch. Apply the exact clock, media, input, retrace, input-retrace,
keyboard-press, keyboard-type, mouse-click, display-probe and VGA-configuration
patches first. The [source manifest](source-manifest.json) pins all ten
prerequisites, this patch and its four changed or new native members. Earlier
patches retain their original bytes.

Select the existing `qemu_clock='virtual', qemu_retrace='precise'` profiles and
inspect `mapped_mouse_motion`. The public method is:

```python
debug.mouse_move_mapped(
    dx_pixels, dy_pixels,
    counts_per_pixel={'x': [1, 1], 'y': [1, 1]},
    window=window,
    update_id=update_id,
    configuration_generation=generation,
    timeout_ms=1000,
)
```

JSON uses `debug-mouse-move-mapped`; saved scripts use `mouse.move-mapped`.
The native command is `x-fdisbull-arm-display-motion`. A ten-layer executable
retains its existing operations and refuses this separate capability.

The mapping is the caller's declaration of QEMU relative input-event units
per retained-image pixel. Positive X means right and positive Y means down.
It describes the requested relative displacement, with no origin, endpoint,
observed cursor position, calibration registry or absolute-coordinate claim.
The host requires exact integer division and retains the declaration; native
code receives only the computed relative counts and the expected binding.

## Bounds and admission

The host accepts strict integer pixel displacements in -8191..8191 and a dict
with exactly `x` and `y`. Each axis is a two-integer list containing a signed
nonzero numerator with magnitude 1..32767 and a denominator in 1..32767.
Fractional conversion is refused rather than rounded. After observing the
retained image, `abs(dx_pixels) < width` and `abs(dy_pixels) < height` bound
the displacement only; they do not establish valid endpoints.

Each resulting native relative count must be in **-127..127**, and the pair
must be nonzero. These bounds are independently enforced by native code.
The batch contains nonzero X first and nonzero Y second, with one final
sync. Its `event-count` is one or two; zero-valued callbacks and button
events are never invented.

Admission requires an owned, explicitly stopped, nonempty renderer window
and the admitted exact primary VGA under the virtual/precise profiles. Its
current configuration and frozen publication configuration must have the
same generation and raw values. The host also requires all native clock,
input, display, retrace, configuration and motion commands, no pending input,
no owned held leases, no other bound schedule, and a project outside a
caller-owned transaction. The operation does not stop an observer implicitly.

An active observer can publish again at its cadence even if its pixels and
configuration are unchanged. Requiring an already stopped window makes the
retained publication an explicit stable anchor while the caller later runs
the guest. It does not make that retained image a current-frame oracle.

## Native expected fields and receipt

`x-fdisbull-arm-display-motion` accepts `token`, signed `dx`, signed `dy` and
an `expected` object of type `FdisbullDisplayMotionExpected`:

| Expected field | Required interpretation |
| --- | --- |
| `epoch` | Positive admitted native virtual-clock epoch |
| `virtual-ns` | Exact stopped acceptance timestamp |
| `device` | Exact admitted canonical primary VGA path |
| `model` | `qemu-vga-configuration-fdisbull-v1` |
| `configuration-generation` | Positive current and published generation |
| `window` | Exact retained renderer owner token |
| `update-id` | Positive publication ID within that window |
| `published-ns` | Exact historical publication timestamp |
| `width`, `height` | Exact retained image dimensions |

Native code compares every expected field with a fresh atomic observation
before preparing the input batch and accepting its token. Console and head
remain zero. The private model's declared configuration raw vector, mutation
boundaries and exclusions are defined by the
[VGA-configuration extension](../qemu-vga-configuration/README.md).

The existing input API1 receipt gains an optional `motion` descriptor:

| Field | Meaning |
| --- | --- |
| `dx`, `dy` | Immutable relative input-event counts |
| `delay-ns` | Fixed 2000000 ns delay from arm |
| `armed` | Full immutable display/current/published observation at acceptance |
| `checked` | Optional full immutable observation at the actual timer callback |

Both observations reuse `FdisbullVgaConfigurationInfo`. In `armed`, current
and display timestamps are stopped observations. In `checked`, those
timestamps describe the running callback. The published configuration always
retains its historical timestamp and raw values. Querying input never
refreshes these observations or relabels them with a later stopped clock.

The `motion`, `retrace`, `press`, `typing` and `click` descriptors are mutually
exclusive. Every accepted arm clears incompatible descriptors. Rejected
arms preserve the preceding receipt and do not consume the proposed token.
All modes share the existing migration blocker, query/cancel commands and
bounded process-lifetime 4096-token history.

## Callback guard and disposition

One virtual timer is due 2 ms after arm. Arming does not execute the guest;
the caller chooses a later bounded run, clock advance or explicit clock-sync
step. The timer first preserves existing profile/epoch checks, pending
debugger/native stop precedence and reached/equal clock-budget precedence.
An equal budget deadline wins regardless of timer insertion order. The first
actual VM stop cancels an unfired attempt.

Before any relative callback, an internal BQL-only helper observes the
already admitted VGA and retained display owner. It supports running
callbacks without calling the public stopped-only configuration query,
admitting a new owner, initializing/rearming a display timer, rendering or
reading guest I/O. It preserves valid empty, replaced or observing-window
evidence so policy changes can be reported without substitution.

The scheduler retains that actual `checked` observation. Impossible history
and contradictory observations fail before choosing a cancellation reason:

- A current generation increase cancels with
  `display-motion-configuration-changed`, including an unobserved A-to-B-to-A
  transition. This reason has priority if the publication also changed.
- With the same current generation, a changed window/publication or an
  observer that is no longer stopped cancels with
  `display-motion-publication-changed`.
- Regressed or invalid native identity, unexplained raw-state history, and
  contradictory values under the same generation fail.
- With the same publication identity, every immutable display field and the
  full published configuration stamp must remain unchanged. Contradictory
  dimensions, timestamps or raw stamps fail.

Stop/budget precedence can cancel before sampling, leaving `checked` absent.
An unavailable native owner can fail without a new snapshot. A successful
guard is followed by the existing exact PS/2 device/handler preflight, all
relative callbacks and one sync under BQL. The native receipt establishes
callback/sync completion only. Completion does not itself stop the guest.

There is no implicit run, refresh, observer stop, rebase, replay, continuation,
cleanup button event or automatic retry. A cancelled public mapped plan
remains bound; ordinary and retrace scheduling must refuse to convert its
pending records into an unguarded request. Call `input_cancel_pending()`,
then make a fresh mapped request with a new binding. Independently requested
lower-level relative input retains its separate contract.

## What remains unknown

The -127..127 bound avoids requesting a count larger than one standard
packet component, but does **not** establish one-packet delivery. Existing
mouse accumulators and held buttons can alter packets or make motion part
of a drag. A disabled mouse can ignore callbacks, remote mode can retain
motion without a stream packet, and FIFO capacity can prevent emission.
The operation neither inspects nor normalizes those conditions.

The public `fdisbull-mapped-mouse-motion-1` descriptor retains the declaration,
derived counts, full arm/check evidence and dispatch binding result.
`device_queue_accepted`, `guest_consumed`, `guest_pixel_displacement`,
`guest_pointer_position`, `mapping_verified`, `raster_coherence` and
`target_reached` remain unknown. No button event is requested; existing
physical button state remains unknown.

Equal configuration does not establish equal current pixels: palette,
VRAM/fonts and guest application state can change without a configuration
generation change. A stopped retained image remains historical. Even an
unchanged publication and configuration cannot validate the caller's scale,
guest acceleration, clipping, cursor location, INT33 semantics or readiness.
Independent fixture packets and application coordinates qualify that fixture
only, not arbitrary guests or mappings.

One shrinking host allowance, default 1000 ms with strict range 1..600000,
covers lock admission, observations, arm, validation, persistence and final
return. Direct signature/value validation precedes lock/I/O; scripts
preflight visible values before earlier effects and validate resolved values
before deadline clamping. An uncertain accepted arm, malformed receipt,
late result or persistence failure closes ownership with available evidence
and no replay. Journal reopening restores history, not a live input owner.

Legacy coordinate/frame clicks and scenes remain unqualified. Broad
`absolute_mouse`, `timed_input`, `guest_time_control` and
`completed_guest_frames` remain false. DOSBox is still the default, and all
127 promotion qualifications remain open.

## Source reproduction and evidence

Use the official QEMU 10.0.13 archive and private prerequisites documented in
the [clock extension](../qemu-clock/README.md). Apply all eleven pinned layers
in order. The following verifies each patch dependency and each touched
source member before and after applying its layer to a fresh source tree:

```sh
python3 - "$FDB_QEMU_SOURCE" <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys

source = Path(sys.argv[1]).resolve()
root = Path('native').resolve()
layers = ('clock', 'media', 'input', 'retrace', 'input-retrace',
          'keyboard-press', 'keyboard-type', 'mouse-click', 'display-probe',
          'vga-configuration', 'display-motion')
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
print('All eleven native source layers verified')
PY
```

The source-only patch proof uses private copies of the three changed prior
members and the new internal header. QAPI generation, compilation, native
guest witnesses, installed-package execution and retained regression remain
separate evidence boundaries. Dated root integration results belong in the
[handoff log](../../docs/DOS_QEMU_HANDOFF.md). Source inspection is not runtime
qualification. Private binaries, firmware, DOS media, emulator states and
runtime databases stay outside Git and tool packages.
