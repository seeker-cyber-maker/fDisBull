# Execution-bound pose reconstruction packet

`binding_scene_trial.py` collects one native execution of a short contiguous
LOGIC fragment under the explicit [VIEW binding profile](VIEW_BINDING_PROFILE.md).
It supplies an authored load prologue, a declared reset state and an immutable
resource catalog. The original fragment ends at the first expected unsupported
instruction. That instruction is reached but does not retire or commit.

This moves view, loop, cel and geometry selection into native execution within
that model. Background selection remains an explicit preview input. A packet
does not establish the original room's inherited state, full entry path, actor
visibility, priority occlusion, animation advancement or picture presentation.

## Collection

```sh
python native/qemu-agi/binding_scene_trial.py \
  --binary /private/native/qemu-system-agi \
  --game-dir /private/authorized/development-game \
  --case-json /private/case.json \
  --output /private/new-collection
```

Case JSON has exactly these fields:

| Field | Meaning |
| --- | --- |
| `id` | Short lowercase case name |
| `logic` | Selected original LOGIC resource number |
| `picture` | Explicit diagnostic background resource number |
| `payload_span` | Half-open, instruction-aligned original span, at most 256 bytes |
| `views` | One to eight VIEW IDs made available in the immutable catalog |
| `actors` | One to eight actor IDs selected for the reconstruction task |
| `horizon` | Explicit reset-model horizon, 0..167 |
| `stop_opcode` | Exact final original opcode expected to remain unsupported |

There is no loop or cel input. The collector validates the original LOGIC
layout, refuses branch relocation or skipped instructions, and prepends actual
`load.view` instructions for the selected catalog IDs. The copied fragment has
an exact source mapping and digest. Authored prologue/return bytes have no
original source address. The initialization guard outside the fragment is not
executed. At most 64 original straight-line actions, 128 cel references and
4 MiB of decoded cel pixels are admitted. A child runs once with an 80-instruction
budget and a 0.1..30-second operation timeout. Existing output is never replaced;
failures retain their stage and bounded native diagnostics.

`binding_catalog.encode_catalog({view_id: payload_bytes}, horizon=...)` uses
the shared, bounded VIEW parser to produce the native FDBAGIV1 metadata file.
`decode_catalog` validates the file structure separately. Native startup
independently validates all bounds and retains an immutable catalog copy.

## Packet contents

The private `helper/packet.json` uses schema
`fdisbull-agi-binding-scene-packet-1` and carries:

- Original input/resource identities, copied instruction sites, exact fragment
  mapping, authored load prologue and explicit authored return bytes. Concatenating
  the prologue, copied sites and return recovers the complete native code digest.
- The catalog digest and all loop/cel geometry. `catalog.bin` retains the exact
  startup input. Catalog entries are distinct from `guest.loaded_views`.
- Complete initial and stopped native snapshots, plus the matching DISASM and
  SCENE journal. Every actor's current state comes from the stopped snapshot.
- A `stop_boundary` with `retired: false` and `committed: false`.
- Decoded indexed pixels for **every** cel in the selected catalog, with exact
  resource hashes, effective mirroring, dimensions and transparent color.
  The packet does not preselect a designer loop or cel.
- An explicit preview background, priority-map asset and diagnostic render
  contract. The priority map is retained but not applied as an engine renderer.
- Both this document as `README.md` and `VIEW_BINDING_PROFILE.md`, with byte
  sizes and digests in `documents`. The detached packet contains its own complete
  interface and semantic contract.

The capture validator checks source, profile and catalog identity, complete
scalar/actor state, loaded membership and geometry of every bound actor. It
does not reconstruct missing history or make this profile compatible with the
old position-only consumer. Collection requires complete observation coverage;
the native profile's authoritative snapshot remains usable when a different
caller deliberately disables observations or exhausts its journal.

## Independent reconstruction task

A fresh helper receives only one complete packet directory. It should:

1. Verify file sizes/hashes and catalog/native identity.
2. Derive each selected actor's effective VIEW, loop and cel from the stopped
   native snapshot. Cross-check the SCENE transition history and DISASM source
   sites. Identify which values came from reset state and which commands changed
   them. Never substitute a label or infer a missed `set.cel`.
3. Choose the corresponding asset from `cel_assets`, verify its dimensions and
   resource identity, and reconstruct one transparent RGBA 160×168 actor layer
   per selected actor. Pixel `(0,0)` is top-left; AGI coordinates are a lower-left
   baseline, so the cel top row is `y-height+1`. Clip only the diagnostic canvas;
   source transparent pixels have alpha zero.
4. Composite those layers over the supplied background in the explicit diagnostic
   `draw_order` and save one RGB 160×168 preview. This order is authored preview
   policy, not native renderer evidence.
5. Save a compact reconstruction JSON with the derived binding/coordinates,
   source sites, unsupported boundary and limitations. Report missing information
   instead of filling it from outside game knowledge.

The controller freezes its independent expected images and bindings before
giving the packets to helpers, then compares all output pixels and claims.
Packet sufficiency for this bounded task does not demonstrate reconstruction of
a whole playable scene. PQ1 and KQ1 are development inputs; SQ1 and LSL1 remain
reserved for later held-out tests.
