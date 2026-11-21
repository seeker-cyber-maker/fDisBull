# Reconstructing actor placement from observations

The bounded AGI observations provide enough information for helpers to build
numerical actor-placement scaffolds when capture coverage supports those
positions. DISASM adds executed assignments and exact instruction bytes; a
stopped scene snapshot supplies current positions even after event loss. These
are separate capabilities. Picture resources, actor appearance and visibility
remain unknown.

`reconstruction_trial.py` collects authored test packets for this comparison.
It reuses the caller's explicit native executable and the shared scene consumer;
it does not build QEMU or change the native CPU/core ABI. The
[packet protocol](SCENE_RECONSTRUCTION_PACKET.md) defines the helper input and
result contract. The [scene consumer](SCENE_CONSUMER.md) defines snapshot and
history coverage.

## Collect and evaluate

Use the existing qualified `qemu-system-agi` and Python environment with matching
`fdisbull-core==0.1.0.dev5`. From the repository root, collect into a new private
directory:

```sh
PYTHONPATH=packages/fdisbull-core/src \
python native/qemu-agi/reconstruction_trial.py \
  --binary /absolute/path/to/qemu-system-agi \
  --output-dir /new/private/agi-reconstruction --timeout 10
```

The main collection uses six fresh children, one resume per child, a
16-instruction budget and finite timeouts. It compares native endpoints with
authored expectations and checks unchanged stopped captures. It writes private
`oracle.json` and `collection.json`, plus three helper bundles:

| Bundle | Evidence supplied |
| --- | --- |
| `scene_only/` | SCENE records, source identity, checkpoint counters and collection attestations |
| `scene_disasm/` | The same metadata with both event channels |
| `snapshot_scene_disasm/` | The combined packet plus the existing consumer's stopped scene capture |

Give each fresh-context helper only its bundle's `PROTOCOL.md` and `packet.json`.
Keep the collector, oracle, other submissions and this findings document with
the coordinator. No initial guest snapshot is supplied. Helpers produce a
standard-library reader, its reconstruction JSON and notes; the coordinator
checks claims and admits only bounded literal-position scaffolds for replay.
Source recovery and placement replay are graded separately. Use new authored
cases for another blind trial; these published cases now serve as regressions.

A separate enabled-but-empty SCENE probe is available:

```sh
PYTHONPATH=packages/fdisbull-core/src \
python native/qemu-agi/reconstruction_trial.py \
  --binary /absolute/path/to/qemu-system-agi \
  --output-dir /new/private/agi-zero-change --zero-change-probe
```

This uses two children and one resume each. Existing output directories are
refused. Failures preserve partial receipts; packet-export failures record
`status: failed` and `stage: packet_write` after retaining collected runs.

The focused regression command is:

```sh
FDISBULL_QEMU_AGI=/absolute/path/to/qemu-system-agi \
PYTHONPATH=packages/fdisbull-core/src \
python -m pytest -q tests/test_qemu_agi_reconstruction_trial.py
```

An unset binary visibly skips native checks; an invalid explicit binary fails.

## Observed trial: 2026-11-21

Three fresh-context helpers received protocol notes and one packet each. All
nine condition/case combinations passed the frozen criteria, including correct
withholding of unsupported claims. Six original captures retired 38
instructions. Seven submitted placement scaffolds reduced to five unique byte
programs; coordinator replay retired 58 instructions and matched every supported
placement.

| Condition | Complete captures | Lost-tail capture |
| --- | --- | --- |
| SCENE only | Recovered witnessed final coordinates; untouched slots remained unknown | Preserved historical positions without claiming final placement |
| SCENE + DISASM | Also recovered all 27/19 source bytes, verified by size/hash, and identified unchanged assignments | Declined full-source and final-placement claims |
| Snapshot + both | Recovered all 16 current slot states and the same complete source bytes | Recovered all 16 current states while history remained incomplete |

Both DISASM helpers distinguished actor 3's last effective change at PC 3 from
its later unchanged assignment at PC 14. All helpers reported one bounded
implementation pass, moderate effort and no clarification; these self-reports
are qualitative usability evidence, not an ease or speed benchmark.

The follow-up exposed an omitted numeric-mask legend. The unchanged combined
reader already recovered actor 4 at `(0,0)`, assignment PC 0 and the complete
five-byte source. Documenting `DISASM=1`, `SCENE=2` and minimally updating its
coverage check corrected only the empty SCENE history claim from false to true.
The original submissions stayed unchanged; all three original case results
compared exactly equal after refinement.

Independent review led to a reproduced-and-fixed packet-export receipt defect
and exact packet-projection regression assertions. The final native/core gate
passed 291 tests with zero failures, errors or skips; source inputs and binary
were unchanged during that gate. The native CPU and core dev5 implementation
were unchanged by this work.

## Interpretation limits

SCENE records changes, so its latest witness need not identify the last
assignment. `position.v` operands are variable IDs; witness coordinates preserve
their historical values. Dropped tails require per-channel counters, and
collection attestations establish the interval over which coverage is claimed.
A snapshot repairs current facts without recovering missing history.

This small, authored, straight-line trial supports numerical scaffolds and
limited exact byte recovery. It does not qualify general AGI reconstruction,
branch/loop recovery, a full visual scene or behavioral equivalence. Rendering
needs checkpoint-aligned picture/view resources, visible membership,
view/loop/cel bindings, priorities, dimensions and rendering conventions.
Product backend defaults and original-DOS QEMU parity remain separate.
