# Real-resource scene reconstruction development trial

PQ1 and KQ1 supply two development cases for a resource-backed scene packet.
Each packet combines decoded original picture/sprite pixels, static instruction
locations, explicit designer choices and native observations of a small copied
position fragment. A reader can reconstruct the prescribed diagnostic preview
without the game files or the collector implementation.

This adds a useful scene-design seam. It does not establish a full executing
AGI room or an original-engine frame. SQ1 and LSL1 remain reserved for later
held-out evaluation and were not opened, analyzed or executed for this trial.

## Components and evidence boundaries

`resource_scene_trial.py` uses the existing V2 resource reader, LOGIC boundary
reader and picture decoder. The new shared
`fdisbull_core.agi_view.decode_view_cel` supplies a bounded, standard-library-only
DOS AGI 2.917 EGA VIEW decoder. It validates referenced structures and RLE,
retains transparency and effective loop mirroring, and returns exact source
identity. Empty unselected loops are admitted; an absent selected cel is not.
The shared package imports neither product.

The collector verifies four explicit instruction sites: `draw.pic`, `set.view`,
literal `position`, and `draw`. Matching resource/actor identities establish
static source association, not a path that executes all four sites. Optional
`view` and `original_position` expectations must match the source; unknown case
keys are rejected.

The picture variable's value and the loop/cel pose are explicit designer
choices. Only the selected four-byte position instruction is copied into the
native test, followed by one authored return. The original and proposed edited
fragments run once each in separate zero-reset children. Each retires exactly
two instructions. `AGISceneHarness` captures stopped state; the shared literal
planner proposes the replacement without writing the original game.

| Information | What establishes it |
| --- | --- |
| Picture/cel pixels | Decoding exact selected resource payloads |
| Source instruction locations and view ID | Static instruction boundaries and operands |
| Picture binding and animation pose | Explicit designer selection |
| Original/edited fragment coordinates | Stopped native state and SCENE witnesses |
| Five-byte fragment identity | Complete DISASM bytes and SHA-256 |
| Original room entry, branch execution, visibility, priority order | Unknown |

The original resource identities are collector attestations to a helper because
full payloads are withheld. The helper can independently hash the supplied
indexed assets and recover the complete five-byte fragments from DISASM. A
matching hash records byte identity, not publisher authenticity or proof of
native execution.

The [helper protocol](RESOURCE_SCENE_PACKET.md) is the complete input contract.
Original source payload offsets include the two-byte LOGIC prefix. Raw code PCs
subtract two. Fragment PCs 0–3 map to the selected source instruction; PC 4 is
authored and has no original source address. The native pilot's logic ID is
always zero; the actual game LOGIC resource number is separate.

## Reproduce with private inputs

Use the already qualified native executable and matching
`fdisbull-core==0.1.0.dev6`; this does not require a QEMU rebuild. The case JSON
accepts these fields:

| Field | Meaning |
| --- | --- |
| `id` | Short lowercase case identifier |
| `logic`, `picture` | Selected resource numbers |
| `actor` | Pilot actor slot, 0–15 |
| `picture_offset`, `view_offset`, `position_offset`, `draw_offset` | Exact LOGIC payload instruction offsets |
| `loop`, `cel` | Explicit designer pose |
| `edit_position` | Two requested byte coordinates |
| `view`, `original_position` | Optional expected source values; mismatches reject the case |

From the checkout root, with the product's ordinary Python dependencies already
available:

```sh
PYTHONPATH=src:packages/fdisbull-core/src \
python native/qemu-agi/resource_scene_trial.py \
  --binary /absolute/path/to/qemu-system-agi \
  --game-dir /private/agi-game \
  --case /private/case.json \
  --output-dir /new/private/resource-scene --timeout 10
```

Each admitted case creates at most two children, one resume each, with observation
mask 3, capacity 16 and step budget 8. Existing output directories are refused.
`collection.json` retains partial runs and structured operation receipts on
failure. A failure during final packet export does not erase successful native
captures. A source position `(0,0)` produces no effective-change witness from
the pilot's zero reset; this collector fails closed at edit planning instead of
inventing one. No original resource is edited.

The five helper files are `PROTOCOL.md`, `packet.json`, `background.idx`,
`priority.idx` and `cel.idx`. They contain private game-derived data and belong
outside the checkout and public review uploads. Supply only those files to a
fresh helper; withhold the collector, original inputs, reference renderer and
other submissions.

The preview uses an explicit EGA RGB palette and a 160×168 logical canvas. The
actor position is the lower-left baseline: `top = y - height + 1`. Transparent
pixels leave the background unchanged and out-of-canvas pixels are clipped.
This draws one unoccluded diagnostic sprite layer. The supplied priority plane
does not by itself establish correct engine occlusion or a complete draw list.

## Observed development cases: 2026-11-21

The user-provided archive contained PQ1 EGA 2.0G (1987-12-03) and KQ1 DOS 2.0F
(1987-05-05). Input hashes matched retained edition records; both selected
resource sets use the explicit AGI 2.917 profile. Only their allowed AGI files
were materialized.

| Case | Selected LOGIC / picture / VIEW | Actor and pose | Original → edited position | Source payload offset / code PC |
| --- | --- | --- | --- | --- |
| PQ1 | 5 / 5 / 116 | Actor 9, loop 0, cel 0; 9×7 | (129,155) → (119,150) | 94 / 92 |
| KQ1 | 53 / 53 / 53 | Actor 14, loop 0, cel 0; 18×31 | (30,90) → (42,96) | 50 / 48 |

Four fresh native fragment children completed eight instructions in total.
Two independent helpers, each given only its five-file packet, produced original
and edited RGB previews that matched a separately implemented cel/composition
reference pixel-for-pixel. The reference reused the existing picture decoder;
background decoding was therefore not independently qualified against another
engine. PQ1 changed 50 composite pixels and KQ1 changed 328. Both helpers
reported one implementation pass, one reader execution and no clarification.
Those are attributed usability observations, not independently instrumented
effort metrics or a general benchmark.

The helper packets preserve source mapping and unknowns. Full resource hashes
cannot be independently rechecked without the withheld originals. Packet-level
coverage metadata is present; raw native mask and dropped-event counters remain
in the coordinator's complete collection receipt, rather than being duplicated
in the helper packet. A future audit-oriented packet can expose those fields
explicitly without changing the pixel recipe.

A separate static census decoded 118 PQ1 LOGICs (26,105 instructions) and 90
KQ1 LOGICs (11,452 instructions), with no LOGIC/layout errors or budget stop.
KQ1 sound entries 34–37 have truncated resource headers. They remain recorded
as input-integrity errors; the selected visual resources are valid. This census
is static evidence, not completed game execution.

Whole selected LOGIC probes used the complete raw code bodies, fresh zero-reset
pilot state and a 256-instruction budget. They stopped explicitly at the first
unsupported executed condition:

| Case | Retired before fault | Raw code PC / payload offset | Missing condition |
| --- | --- | --- | --- |
| PQ1 LOGIC 5 | 2 | 248 / 250 | Spatial `posn` |
| KQ1 LOGIC 53 | 3 | 99 / 101 | Parser `said` |

These are admission/frontier probes, not normal startup or room initialization.
Unsupported instructions were not skipped. Extending condition semantics alone
would still leave resource actions, calls, parser state, animation and other
engine effects to qualify before claiming a complete room.

## Verification and next qualification

Authored fixtures exercise resource identity, exact boundaries, static/designer
distinctions, rendered asset layouts, edit proposals and native fragment results.
Failure tests cover configuration receipt retention, late export failure and
zero-change witness refusal. Decoder tests cover shared pointers, empty loops,
transparent tails, effective mirroring, bounds, truncation and structural overlap.
Run them with an explicit binary so native cases are not skipped:

```sh
FDISBULL_QEMU_AGI=/absolute/path/to/qemu-system-agi \
PYTHONPATH=src:packages/fdisbull-core/src \
python -m pytest -q tests/test_qemu_agi_resource_scene_trial.py \
  packages/fdisbull-core/tests/test_agi_view.py
```

The native CPU, observation ABI and disabled-channel code generation are
unchanged. Resource decoding occurs on explicit host-side collection, not on
every instruction. There is no new performance or original-DOS QEMU parity claim.
Core dev6 is pinned by both products; fDisBull and DotBox retain separate
orchestration, board projects and acceptance policies.

Use PQ1/KQ1 findings to stabilize the resource and source-mapping contract.
Before later SQ1/LSL1 tests, freeze the decoder, packet protocol, qualification
criteria and helper instructions, then evaluate without tuning to those games.
Faithful scene reconstruction additionally requires checkpoint-aligned resource
selection, visible membership, loop/cel state, priority/overlay order and a
qualified original-engine comparison. A successful diagnostic preview does not
satisfy those conditions.
