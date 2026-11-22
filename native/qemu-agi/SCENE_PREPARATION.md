# Prepared AGI scene composition

The runtime and resource parsers already exist. This interface separates the
facts needed to compose one scene from the larger state and evidence used to
derive those facts. It reuses existing implementations and preserves the full
runtime capture APIs.

## Existing preparation components

`runtime_pack.package_from_v2()` uses `V2Resources`, the existing directory and
volume reader, LOGIC message extraction, vocabulary and object parsing.
`package_from_raw()` accepts selected complete LOGIC payloads, while
`build_package()` accepts exact extracted code and resource records. Original
resource conversion and package-JSON parsing are different preparation stages.

Composition reuses `fdisbull.agi_picture.decode_picture`,
`fdisbull_core.agi_view.decode_view_cel`, and `SarienScene.blit`. The native
runtime retains its own canonical execution/decoder authority. These adapters
do not introduce a second interpreter, source-value solver or placement policy.
The Sarien attribution and license remain in [SARIEN_PROVENANCE.md](SARIEN_PROVENANCE.md).

## Minimum sufficient plan

The versioned `fdisbull-agi-minimal-scene-plan-1` representation contains:

| Field | Meaning |
| --- | --- |
| `schema`, `profile` | Interpretation, including the 160×168 indexed canvas and blank-plane defaults |
| `package_sha256` | Exact source-package identity, including its original JSON bytes |
| `background` | Explicit blank (`null`) or a selected `{picture: id}` |
| `layers` | Selected actors in final back-to-front composition order |
| Each layer | `actor_id`, `view`, `loop`, `cel`, `x`, baseline `y`, resolved `priority` |

The referenced picture and VIEW bytes must also be available and verified.
Width, height, transparent color, effective mirroring and cel pixels come from
the existing VIEW decoder. They need not be repeated in every plan. Actor IDs
support stable editing; the blit itself needs only the asset selection, pose,
priority and order. Selection is implicit in membership, so this representation
does not repeat a `drawn` flag or a separate layer-order array.

This is a minimal sufficient contract for the supported composition path,
not an information-theoretic minimum or a complete description of execution.
Actor motion, collision, priority-band rules, flags and horizon can be needed
to derive or recompute the final pose and order. Omitting them from a finished
plan does not make them unnecessary for semantic edits or animation.

Only full `draw_picture` replacement histories are reduced to the final
picture. Overlay and add-to-picture operations are explicitly unsupported by
this detached prepared renderer; they must not be discarded. The native
runtime's own compositor continues to support them.

## Reuse without reusing executed facts

`PreparedSceneAssets` validates exact package bytes with `runtime_pack`, builds
immutable raw resource indexes and uses a `DecodedAssetCache` for lazy picture,
VIEW geometry and selected-cel preparation. A `PreparedSceneRenderer` keeps one
admitted Sarien library loaded and returns fresh output planes.

Cache identity includes exact asset content, selected loop/cel, profile and
decoder identity. Resource ID alone is insufficient: two packages can use the
same number for different bytes. Reusing an immutable asset does not reuse a
previous guest state, actor pose, selected background, execution trace or
completed output frame.

`project_recipe()` separates the minimal plan from completion and provenance.
Its evidence envelope binds the original recipe and canonical plan hashes,
case identity, status, endpoint, unresolved facts and manual choices. An exact
blank rendering of a blocked recipe remains blocked. Pixel equality does not
establish that execution reached a requested endpoint.

`export_raw_bank()` emits only referenced picture/VIEW payloads with their
hashes. `PreparedSceneAssets.from_raw_bank()` verifies that bounded bank and
its expected digest; LOGIC code is not needed to render an already derived
plan. A raw bank is an asset subset bound to a package identity, not a new
executable package or independently authenticated publisher record.

With `src`, `packages/fdisbull-core/src` and `native/qemu-agi` on `PYTHONPATH`,
the reusable composition seam is:

```python
from prepared_scene import (
    DecodedAssetCache, PreparedSceneAssets, PreparedSceneRenderer, project_recipe,
)

cache = DecodedAssetCache()
renderer = PreparedSceneRenderer(scene_library, expected_sha256=library_sha256)
assets = PreparedSceneAssets(exact_package_bytes, cache=cache)
plan, evidence = project_recipe(exact_recipe_bytes)
first = renderer.render(plan, assets)  # selected assets decoded on demand
again = renderer.render(plan, assets)  # same assets reused; fresh composition
assert first["visual"] == again["visual"]
assert first["priority"] == again["priority"]
```

The caller supplies the verified library and exact input bytes. Preserve
`evidence["status"]` alongside the result; this renderer does not promote a
partial or blocked source analysis to completed execution.

## Compact native evidence

`agi-runtime-checkpoint-json` uses schema
`fdisbull-agi-runtime-checkpoint-1`. It carries source/current-LOGIC identity,
endpoint, pending/fault state, retirement and revision counters, cycle and
clock information, input-enabled state, v10 as `cycle_delay`, observation
accounting, and the same architectural digest/size/encoding as full state.
The digest is the existing native ABI representation and is not a portable
cross-build save format.

`agi-runtime-scene-inputs-json` uses schema
`fdisbull-agi-runtime-scene-inputs-1`. It adds actors selected and ordered by
the same `agi_runtime_scene_order()` helper used by native composition, with
their pose, selected resource, geometry and VIEW hash. It exports no pixel
planes and makes no claim that every selected pixel remains visible after
occlusion. Queries require a stopped runtime and do not mutate guest state.

SCENE-only (`mask=2`) capture can retain a complete bounded picture-operation
history without also exporting every instruction retirement. DISASM and BOTH
remain available for detailed analysis. Journal counts, capacity and loss must
be checked. Observation off, late attachment, clear/reset, or dropped rows
cannot be treated as proof that no earlier picture operation occurred.

SCENE also includes explicit host-update observations with `opcode=256`, zero
instruction size and no LOGIC bytes. These may appear before the first guest
retirement. Retain them and bind them to the declared host command schedule and
surrounding checkpoints; they are not bytecode instructions for the static
decoder. A consumer must distinguish these rows from source-bound instruction
observations when proving that a journal is complete.

## Measure preparation separately

Report these costs with their actual boundaries:

1. One-time environment recovery and native compilation.
2. Original resource conversion, when actually performed.
3. Dependency/library admission and exact package parsing/indexing.
4. Fresh native child setup, declared clock/cycle control and execution.
5. State/event capture and extraction of a source-bound plan.
6. Selected asset decoding on cache misses, or lookups on cache hits.
7. Fresh-plane composition, core serialization and optional image/evidence output.

An application-cache-cold process does not guarantee a cold OS file cache.
Prepared rendering of an existing plan is not fresh scene discovery. Compact
SCENE-only production also retains a smaller evidence profile than a full
DISASM/SCENE audit; its time improvement must not all be attributed to faster
guest execution or resource parsing. Measure wrapper wall time as wrapper time,
and avoid adding nested stage intervals twice.
