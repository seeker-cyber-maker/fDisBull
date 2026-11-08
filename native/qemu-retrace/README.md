# Native QEMU precise retrace observation, API and model 1

This optional patch adds a passive observation of **QEMU 10.0.13's precise VGA
retrace model**. Apply the current clock, media and input patches first. The
[source manifest](source-manifest.json) pins those dependencies, this patch,
and every changed source member. The Python package does not install QEMU,
firmware or a DOS image.

Select `qemu_clock='virtual', qemu_retrace='precise'` for a fresh paused PC
boot. The explicit native configuration is:

```text
-vga std,retrace=precise -global VGA.x-fdisbull-retrace=on
```

`qemu_retrace='standard'` is the default and adds neither argument. The new
property defaults to false and exists only on the exact primary PCI device
type `VGA`. Enabling it without `retrace=precise` is a realization error.
Ordinary dumb VGA and ordinary precise VGA without the property retain their
existing behavior.

The public operation is `retrace_observe(timeout_ms=...)`; its native command
is `x-fdisbull-query-retrace` with no arguments. It does not resume the guest,
run a renderer, arm a timer, wait for an edge or read a guest I/O port. Timing
auto-sync remains deferred. A modeled retrace phase does not establish the
whole VBlank interval, visible scanout, guest application frame completion,
input readiness, display publication or cycle parity.

## Exact source and reproduction

Begin with the official QEMU 10.0.13 archive identified in the clock manifest.
Keep source, build products and runtime inputs outside the fDisBull checkout.
From the checkout, this sequence verifies and applies all four layers to a
fresh source tree:

```sh
python3 - "$FDB_QEMU_SOURCE" <<'PY'
from pathlib import Path
import hashlib, json, subprocess, sys
source = Path(sys.argv[1]).resolve()
root = Path('native').resolve()
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
for name in ('clock', 'media', 'input', 'retrace'):
    directory = root / ('qemu-' + name)
    record = json.loads((directory / 'source-manifest.json').read_text())
    assert (source / 'VERSION').read_text().strip() == record['qemu_version']
    for dependency in ('clock', 'media', 'input'):
        key = 'requires_' + dependency + '_patch'
        if key in record:
            path = root / ('qemu-' + dependency) / record[key]
            assert digest(path) == record[key + '_sha256'], path
    patch = directory / record['patch']
    assert digest(patch) == record['patch_sha256'], patch
    for item in record['files']:
        path = source / item['path']
        assert (not path.exists() if item['base_sha256'] is None
                else digest(path) == item['base_sha256']), path
    subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)],
                   cwd=source, check=True)
    for item in record['files']:
        assert digest(source / item['path']) == item['patched_sha256'], item['path']
print('All native retrace source layers verified')
PY
```

Use the private `x86_64-softmmu`, TCG and Pixman build recipe in the
[clock README](../qemu-clock/README.md). The patch contains a QMP error stub
for builds without standard PCI VGA; it does not claim phase support on those
targets. Source archives carry authored patches and manifests, not emulator
binaries or private runtime media.

## Observation contract

Every successful response contains these fields:

| Field | Meaning |
| --- | --- |
| `api-version` | Private wire protocol version, `1` |
| `model` | Exact selected model, `qemu-vga-precise-fdisbull-v1` |
| `epoch`, `virtual-ns` | Native clock epoch and actual stopped virtual timestamp |
| `device`, `device-type` | Canonical QOM path and exact type `VGA` |
| `console`, `head` | Owned console index and head, both zero |
| `timing-generation` | Monotone identity for changes to the returned register/model state |
| `raw` | Stored timing registers and the VBE enable register |
| `timing` | Exact cached native timing parameters |
| `phase-supported` | Whether this current model has an eligible phase |

When supported, `phase` contains the modeled position, retrace flags and
status-register timing bits. Otherwise `phase` is absent and
`unsupported-reason` is one of these values, in this precedence order:

1. `uninitialized`: the native timing cache is entirely zero.
2. `vbe-enabled`: Bochs VBE is enabled, so no legacy phase is attributed to it.
3. `invalid-timing`: the initialized legacy tuple has an invalid divisor,
   total, overflowing product, or wrapped/outside horizontal or vertical
   retrace interval.

An unsupported result is valid evidence and leaves the owner usable. Support
is determined from the current tuple, not from an assumed BIOS mode number.
Legacy text or graphics configurations can qualify, but not every ordinary
VGA mode does: a native end coordinate beyond its line or period is explicitly
unsupported in this increment. No clipped interval or legacy phase is invented
for it.

Missing opt-in, a wrong model/device, an incoherent cache, generation overflow,
reset or epoch loss is an error. The live Python owner rejects malformed or
contradictory receipts and closes an uncertain machine.

## Registers, arithmetic and phase

`raw` contains exactly `msr`, `sr1`, `cr00`, `cr04`, `cr05`, `cr06`, `cr07`,
`cr10`, `cr11` and `vbe-enable`. The first nine are stored bytes;
`vbe-enable` is a stored 16-bit register. `sr1` is the **effective** sequencer
clock-mode register, using `sr_vbe[1]` while VBE is enabled. It need not equal
the register visible through ordinary sequencer-port reads in VBE mode.
No status latch, attribute-controller flip-flop, palette or index register is
read through guest I/O or included in this tuple.

The patch extracts the existing calculation into a helper without changing
its arithmetic. With `//` denoting integer division:

```text
dots = 8 if (msr & 1) else 9
hz = [25175000, 28322000, 25175000, 25175000][(msr >> 2) & 3]
ticks_per_char = 1000000000 // (hz // dots)
htotal = (cr00 + 5) << ((sr1 >> 3) & 1)
vtotal = (cr06 | (((cr07 & 1) | ((cr07 >> 4) & 2)) << 8)) + 2
total_chars = htotal * vtotal
hstart = cr04 + ((cr05 >> 5) & 3)
hend = hstart + (cr05 & 31) + 1
vstart = cr10 | ((((cr07 >> 2) & 1) | ((cr07 >> 6) & 2)) << 8)
vend = vstart + (cr11 & 15) + 1
freq = 0
```

These are QEMU's model formulas, including the MSR-bit-0 dot choice, two
integer divisions and inclusive end coordinates. Model 1 preserves those
approximations. A nonzero frequency override is not accepted by this model.

An initialized eligible tuple requires positive `ticks-per-char`,
`total-chars` and `htotal`; `total-chars` must be divisible by `htotal`;
the period product must fit a signed 64-bit integer; and:

```text
0 <= hstart <= hend < htotal
0 <= vstart <= vend < total_chars // htotal
```

At the returned `virtual-ns` timestamp:

```text
period_ns = ticks_per_char * total_chars
phase_ns = virtual_ns % period_ns
character = phase_ns // ticks_per_char
line = character // htotal
line_character = character % htotal
vertical_retrace = vstart <= line <= vend
horizontal_retrace = hstart <= line_character <= hend
status1_timing_bits = (8 if vertical_retrace else 0) |
                      (1 if vertical_retrace or horizontal_retrace else 0)
```

`status1-timing-bits` reports only bits 3 and 0. In particular, bit 0 is not a
claim about the entire visible or blanked region. The phase is anchored to
QEMU's absolute virtual clock as its existing status-read implementation is;
it is not a count of guest frames or cycles since the last timing write.

The public validator independently reconstructs both the raw-to-cache model
and this phase arithmetic. It does not infer timing from renderer publication
IDs or convert an instruction count into virtual time.

## Coherence and generation identity

In the original source, `vga_precise_update_retrace_info()` reads CR10, but
the CRTC write-refresh switch omits CR10. VBE transitions and derived
effective sequencer changes can also leave the cached model behind the
registers. The private property enables a write-time commit at the end of
`vga_ioport_write()` and `vbe_ioport_write_data()`. It refreshes changed model
inputs after the complete write, including the protected-CR7 branch and
VBE-derived register changes. This changes only the explicitly opted-in model.

The same commit compares the returned raw tuple, cached timing tuple and
initialization state before and after the write. A change advances
`timing-generation`. Two effective writes A→B→A therefore advance identity
even if no query occurs between them. Index selection, ignored writes and
already-initialized no-op writes do not advance it. Full stored register bytes
are included, so identity can conservatively change even when a changed bit
leaves the calculated period unchanged.

The counter never wraps: exhaustion latches an error. Reset also advances
native model identity and invalidates the admitted clock/owner epoch. Query
recomputes expected parameters into a local copy and compares them with the
live cache. A mismatch is an error; querying never repairs it or changes its
generation.

This is a timing-model identity, not a complete guest display-mode identity.
VRAM writes, palette changes and page contents can change pixels without
changing the tuple. A retained renderer publication can also predate the
current timing observation. The retrace receipt remains separate from
`capture_display()` and does not relabel that publication with current timing.

## Ownership, stops and qualification

The query requires the native clock API 1 profile: fixed icount, one stopped
TCG vCPU, a supported stopped runstate, no replay/migration, no pending native
stop, and no armed or fired clock budget. A rejected armed-budget query leaves
the existing token, deadline and clock untouched. There is no native retrace
timer and no additional stop request.

First successful admission verifies exactly one realized primary device of
exact type `VGA`, pins the actual object and its canonical path, and adds a
process-lifetime migration blocker. The primary type is not hotpluggable.
Subsequent queries revalidate the same object, unique-primary condition,
console ownership and clock epoch. Admission bookkeeping and the migration
restriction protect ownership; they do not advance CPU time or operate guest
I/O. This slice defines no serialization or cold-restoration contract for the
generation counter.

The native witnesses are authored in `tests/support/qemu_retrace_fixture.py`
and exercised by `tests/test_qemu_retrace_native.py`. They are separate from
the host protocol/deadline adversaries in `tests/test_qemu_retrace.py`. Native
qualification compares guest-read registers and actual status-port behavior,
checks attribute-controller flip-flop preservation, CR10 changes and unseen
ABA writes, and exercises unsupported modes, stop/epoch guards and ownership.
Their execution results belong to the exact-source build and runtime receipts;
schema parsing and patch roundtrip alone do not establish a native pass.
