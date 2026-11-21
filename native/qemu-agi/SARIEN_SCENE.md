# Reused AGI position and priority kernel

The host scene library reuses a cohesive part of the original Sarien AGI
implementation: position validity, peer collision, control-line checks,
spiral position repair and priority-aware cel rasterization. It avoids a new
opcode-by-opcode renderer. The implementation is C99 with explicit inputs,
no engine globals, no allocator, and a bounded repair search. See
[provenance and retained semantics](SARIEN_PROVENANCE.md) and the accompanying
[GPLv2 text](COPYING.sarien.txt).

This component is separate from QEMU's translator. Changing its host adapter
does not require rebuilding an unchanged, already qualified QEMU executable.
The existing [ScummVM sidecar](../../experimental/scummvm/README.md) remains a
possible reference executor for complete engine scenes. Its GPLv3 source is
not copied into this component.

## Build once, reuse across scenes

On Linux with an existing C compiler and the 40 GiB free-space reserve:

```sh
python native/qemu-agi/build_sarien_scene.py --output /private/new-scene-library
```

The new directory contains `libagi-scene.so`, compiler logs and `receipt.json`.
The receipt binds the library hash to the C/header/license inputs. This small
build downloads and installs nothing. The recipe does not overwrite an existing
output directory; a failed build remains available for diagnosis. Other host
platforms have not been qualified.

The source distribution and tool source ZIP include this adapter, the native
sources and the Sarien license. Build from either extracted source package;
the application wheel does not include this experimental source interface or
a precompiled scene library.

Load that explicit library and its recorded SHA-256 with
`SarienScene(library, expected_sha256=...)` from `sarien_scene.py`. One loaded
instance serves the complete behavior/scene batch.

| Operation | Inputs | Result |
| --- | --- | --- |
| `place` | Priority/control plane, explicit priority bands and horizon, complete actor context, selected actor, candidate budget | Repaired pose/priority and ego trigger/water facts, or explicit budget exhaustion |
| `blit` | Visual and priority planes, already decoded/oriented cel, valid baseline placement, transparency and actor priority | New planes, admitted pixel count and raster-hidden result |
| `preview` | Complete scene context and an explicit ordered list of cel layers | Detached model with successive placement and priority composition, or rollback to the original complete scene on budget exhaustion |

The Python adapter copies inputs. The C placement operation is read-only;
the C blitter validates its entire request before modifying the supplied
output planes. The adapter rejects Python integer narrowing and boolean aliases.
ABI version and library identity are checked before use.

## Explicit scene assumptions

The kernel needs a 160 by 168 priority/control plane, 168 priority-band values,
a horizon, current/previous actor baselines, geometry, and the relevant actor
flags. Its C flags are declared in `sarien_scene.h`; they are not a copy of a
QEMU actor's serialized flag layout.

For a detached draw-intent packet, `scene_packet_preview.preview_packet`
reuses the existing source, reset-state and journal validators, verifies the
actual stopped endpoint and its draw-request declaration, verifies the selected
indexed assets, and binds cels to native VIEW/loop/cel state. The
caller must provide priority bands and a policy for **every actor** containing
the missing drawn, object/block, water/land and fixed-priority state. Animation
and horizon flags come from native state and cannot be overridden by that
policy. The packet's existing external preview order is retained.

Sarien's initial priority table is `max(4, y // 12 + 1)`, but the adapter does
not silently assume that the original game still uses that table. A caller can
choose it explicitly for a seeded experiment. The same distinction applies
to assuming no previously drawn peers.

`preview` processes the caller's layer order, updates its detached actor model,
and marks successful layers as drawn peers for subsequent placement. It is
not the engine's static/updating sprite-list scheduler. Raster-hidden describes
this supplied composition only. Every result keeps `native_draw_committed`
and `presentation_established` false. The original native pending draw and
guest remain untouched. A seeded repair does not establish original-room
state, advance execution past the pending instruction, run a cycle, or present
a screen.

## Batched verification policy

Use [the compact native behavior batch](BEHAVIOR_BATCH.md) for the unchanged
QEMU boundary. It combines setup/binding/cycling interactions into complete
programs and inspects their journals, reusing each owned child across observation
variants. Keep terminal faults and startup rejection cases isolated.

The scene-kernel suite loads its explicit library once and groups complete
placement, collision, terrain and layered-composition cases. A private
differential batch compares feasible cases with the pinned upstream functions;
bounded impossible layouts use explicit rollback expectations because the old
upstream repair loop has no bound.

The exhaustive existing opcode/catalog suites remain available. Rerun their
affected groups when native code, catalog admission, schema or instrumentation
changes. A packet or host-preview change does not invalidate a byte-identical
native executable's earlier qualification. Diagnose a failing group before
splitting it into smaller cases; do not automatically replay a whole campaign.
