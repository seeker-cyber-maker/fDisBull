# Native VGA configuration identity

This optional tenth patch observes a bounded, versioned configuration of the
exact primary standard VGA device. Apply the exact clock, media, input,
retrace, input-retrace, keyboard-press, keyboard-type, mouse-click and
display-probe patches first. The [source manifest](source-manifest.json)
pins all nine prerequisites, this patch and every changed native member.
Earlier patch files retain their original bytes.

Select the existing `qemu_clock='virtual', qemu_retrace='precise'` profile and
inspect `vga_configuration`. No additional launch option is introduced. The
public method is `vga_configuration_observe(timeout_ms=1000)`, JSON uses
`debug-vga-configuration`, and saved scripts use `vga-configuration`.
The native command is `x-fdisbull-query-vga-configuration`.

The result separates current configuration from configuration observed when
the latest retained renderer image was published. A monotone generation
detects changes that dimensions or current register equality alone miss,
including page changes and A-to-B-to-A transitions. This is a native
configuration identity, not a guest BIOS mode number or cursor mapping.

## Atomic observation

The native response has two required fields and one optional field:

| Field | Meaning |
| --- | --- |
| `display` | Existing `FdisbullDisplayInfo` receipt, with its existing schema |
| `current` | Configuration observed at this stopped query |
| `published` | Frozen configuration observed alongside the retained RGB publication; present exactly when that publication exists |

Each configuration snapshot retains `api-version=1`,
`model='qemu-vga-configuration-fdisbull-v1'`, native clock `epoch`,
`virtual-ns`, exact canonical device path, `device-type='VGA'`, console/head
zero, positive `configuration-generation`, and the bounded `raw` vector.
The published timestamp equals the existing renderer `published-ns`.

The command reuses stopped precise-retrace admission, which requires exactly
one realized primary VGA, pins its identity and blocks migration. It then
uses the existing display guard and reads both observations under BQL. It
requires the valid stopped native clock profile, no pending stop, and no
armed or fired clock budget. VBE can be observed even though its precise
retrace phase remains unsupported; configuration and retrace eligibility
are different facts.

There is no guest I/O, GDB instruction or memory operation, render, timer
action, execution, sleep, input, file/image export, implicit clock sync or
replay. Ordinary display query/export/probe responses do not gain fields or
change schemas. A nine-layer executable retains its existing operations but
cannot advertise this command.

## Exact tracked vector

The model deliberately tracks some conservative configuration changes that
do not change visible dimensions or pixels. Both sequencer banks are retained;
the active `sr()` view alone would hide inactive state and derived VBE changes.

| Raw field | Native source and bound |
| --- | --- |
| `sequencer` | Eight stored legacy sequencer bytes, indices 0..7 |
| `sequencer-vbe` | Eight stored VBE sequencer bytes, indices 0..7 |
| `graphics` | Sixteen stored graphics-controller bytes, indices 0..15 |
| `crtc` | All 256 stored CRTC bytes, including cursor, protection and conservatively stored unused controls |
| `attribute-controls` | Five attribute-controller bytes, indices 0x10..0x14 |
| `vbe` | Ten Bochs VBE words, indices 0..9 |
| `misc-output`, `feature-control` | Stored bytes |
| `display-enabled` | Attribute index bit 5 |
| `vbe-start-address` | Derived native VBE origin in four-byte units |
| `vbe-line-offset` | Derived VBE pitch in bytes |
| `vbe-bank-mask` | Native VBE bank mask |
| `bank-offset` | Signed native legacy-aperture byte offset |
| `dac-8bit` | Eight-bit DAC interpretation flag |
| `big-endian-framebuffer` | Native framebuffer byte interpretation |
| `vram-size`, `vbe-size`, `vbe-size-mask` | Allocated/addressable sizes and address-wrap mask |

VBE index `0x0a` is the read-only video-memory-size index outside the ten-word
array. This primary VGA implementation does not store a DAC pixel-mask
register, so the receipt does not invent one.

Excluded state is explicit: DAC RGB palette/cache/index/subindex; attribute
palette entries AR00..0f; VRAM and font contents; ordinary selectors,
attribute flip-flop, status registers and memory latch; renderer caches,
surface dimensions, dirty flags and cursor blink phase. Attribute mode and
color-page controls remain included even though they affect palette
interpretation. Palette contents remain separate image content.

Consequently, equal configuration can accompany different images, and equal
images can accompany different configuration generations. The raw vector
does not establish readiness, application state or a complete GPU state.

## Generation and mutation boundaries

The process/device-local `uint64` generation begins positive after standard
VGA setup. A committed final-vector change advances it once per complete
mutator call; reset always advances it. It is independent of observation
windows and does not reset when display observation stops or restarts.
It never wraps. Overflow invalidates configuration identity.

Hooks commit after these native mutation boundaries:

- `vga_ioport_write`, including the protected-CR7 branch and VBE-derived effects.
- `vbe_ioport_write_data`, after normalization, derived registers, DAC width,
  bank changes and memory-access updates.
- PCI QEXT framebuffer-byteorder writes.
- The writable QOM `big-endian-framebuffer` property.
- Common VGA reset, with an unconditional lifetime change.

Legacy and MMIO aliases delegate to these same handlers. Ordinary index
selection, no-op writes, ignored protected writes and palette-only changes
do not advance the generation unless they also change an included control.
In particular, writing the attribute index with a different display-enable
bit does change configuration. Two effective writes A-to-B-to-A advance
twice even when no query occurs between them. Internal assignments within one
VBE operation are represented by the final normalized vector.

A zero-initialized fixed-size native structure retains the committed vector,
including deterministic padding. Each query compares freshly observed state
with that committed vector. An unexplained mismatch invalidates identity;
queries never assign a new generation to repair missing write-time history.

These fields are not added to VMState. The common post-load hook explicitly
invalidates opted-in configuration identity because a restored image cannot
restore its process-local history. Existing clock/display/retrace reset and
epoch rules continue to invalidate live ownership. Overflow and post-load
paths require their own runtime evidence before anyone describes them as
native-qualified; source inspection and a migration refusal are narrower.

## Configuration observed at publication

The display timer takes a direct snapshot of its already pinned selected VGA
under BQL alongside the private RGB copy and before publishing its update ID
and timestamp. This does not require a prior public retrace or configuration
query. A caller can start ordinary renderer observation, run explicitly, and
later retrieve the already frozen configuration snapshot on its first query.

A selected precise publication whose snapshot fails invalidates the observer.
The query refuses a missing or contradictory retained stamp rather than
assigning current configuration to old pixels. A new display window clears
the stamp with the pixels; stopping observation retains both. Unselected
ordinary display observation remains unchanged. Builds without standard PCI
VGA use explicit unsupported snapshot stubs.

The stamp means **configuration observed at publication**. It does not prove
that all image pixels were freshly rendered using that configuration. For
example, the native text renderer can return without rendering during a
transient invalid character count, and blank rendering can preserve an
existing surface. The observer can still complete its callback and copy
those retained pixels. Current and published generation equality is therefore
a configuration guard, not a raster-coherence or completed-frame proof.

The public receipt uses `fdisbull-vga-configuration-1`, preserves both native
snapshots and reports `configuration_matches=None` without a publication.
Otherwise it compares exact generations after enforcing device, epoch, raw
and publication consistency. Equal raw SHA-256 after A-to-B-to-A does not
restore identity. `configuration_sha256` is a canonical JSON hash of this
bounded raw vector, not an image hash or whole-machine identity.

Host validation brackets native reads with unchanged clock epoch, instruction
counter and virtual time. One bounded deadline covers admission, validation
and journal persistence. Malformed/control/persistence failures close the
owner with available evidence and without retry. Reopening a journal restores
historical observations, not a live VM or configuration owner.

`raster_coherence`, `completed_guest_frame`, `guest_frame_id` and
`cursor_mapping` remain unknown. Existing `frame_probe`, `click`, `click-frame`
and scene contracts do not acquire native coordinate support from this patch.
Generic `completed_guest_frames`, `absolute_mouse`, `timed_input` and
`guest_time_control` remain false. DOSBox remains the default, and all 127
promotion qualifications remain open.

## Source reproduction and evidence

Begin with the official QEMU 10.0.13 archive and private build prerequisites
documented in the [clock README](../qemu-clock/README.md). From the fDisBull
checkout, the following verifies every dependency and native source member
before and after applying each layer to a fresh extracted source tree:

```sh
python3 - "$FDB_QEMU_SOURCE" <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys

source = Path(sys.argv[1]).resolve()
root = Path('native').resolve()
layers = ('clock', 'media', 'input', 'retrace', 'input-retrace',
          'keyboard-press', 'keyboard-type', 'mouse-click', 'display-probe',
          'vga-configuration')
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
print('All ten native source layers verified')
PY
```

Use the same private `x86_64-softmmu`, TCG and Pixman build recipe. Exact
source reproduction, QAPI generation, compilation, controlled guest witnesses,
installed-package execution and retained DOSBox regression are distinct
evidence boundaries. Dated results and retained failures belong in the
[handoff log](../../docs/DOS_QEMU_HANDOFF.md). Build products, firmware, DOS
media, game data and runtime databases stay outside Git and tool packages.
