# Native AGI v2 picture and scene runtime

`overlay/target/agi/runtime_scene.c` provides portable native picture replay,
VIEW cel decoding and complete scene composition for the wider CPU runtime.
It consumes raw, uncompressed resource payloads and explicit actor state.
No opcode decoder, global interpreter, display driver or wall clock is embedded
in this component.

## Upstream source and licensing

The implementation adapts the AGI 2.x, 160×168 path from
[cmatsuoka/sarien](https://github.com/cmatsuoka/sarien) at the exact commit
[`aaef5e667757385b5b3650cc1f7365908720f7e6`](https://github.com/cmatsuoka/sarien/commit/aaef5e667757385b5b3650cc1f7365908720f7e6).
The original notices credit Stuart George and Claudio Matsuoka. The dated
fDisBull adaptation is 2026-11-22.

| Upstream source | Git blob SHA | Adapted behavior |
| --- | --- | --- |
| [src/picture.c](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/src/picture.c) | `93083e8bc9d76767cfb42fddc65871fb9166aaa7` | Integer line raster, corner/relative strokes, flood admission, circle masks, splatter map/start table, brush traversal and picture command behavior. |
| [src/view.c](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/src/view.c) | `bb9ed18abe83dee982c288dc18b0f65f0625ca4a` | VIEW loop/cel offsets, geometry, transparency and the original-loop mirror selector. |
| [src/sprite.c](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/src/sprite.c) | `3553a2145d8542297c89897660a79b3b01f6523f` | Cel row RLE, priority/control read-through, stationary/updating ordering, fixed-priority sort position, persistent `add.to.pic` pixels and control margins. |
| [doc/COPYING](https://github.com/cmatsuoka/sarien/blob/aaef5e667757385b5b3650cc1f7365908720f7e6/doc/COPYING) | `a43ea2126fb6b114bff5f8e003ee118e045dacf1` | The GPL version 2 text already supplied as `COPYING.sarien.txt`. |

The upstream files grant redistribution and modification under the GNU General
Public License without naming a version; their `docs/COPYING` reference refers
to the supplied `doc/COPYING` file. As in the existing Sarien scene kernel,
this adaptation elects **GPL version 2** under the original grant and section 9
of that license. It is marked `GPL-2.0-only`. Preserve the original grant,
attribution, modification notice, and license text when redistributing it.
No GPLv3 ScummVM code was copied into this component.

The existing host `sarien_scene.c` ABI remains unchanged. The native overlay
needs its own compiled raster primitive because its resource/world interface
and build inputs are independent of that host module. Within the native unit,
one `blit_pixel` rule is shared by single-cel blitting, full composition and
`add.to.pic`; placement/motion are delegated to `runtime_actor.c`.

## Picture execution

`agi_runtime_decode_picture` supports every AGI v2 picture command F0–FA and
the FF terminator:

- Independent visual and priority color selection and disable commands.
- Alternating horizontal/vertical corners, absolute lines, and signed relative
  displacements using Sarien's integer line algorithm.
- Flood filling with the visual-white or priority-four admission rule. When
  visual drawing is enabled, the visual plane controls the region, even if
  priority drawing is also enabled.
- All eight pen sizes, circular and rectangular masks, and the deterministic
  splatter table/seed traversal. There is no host random-number dependency.
- Clear mode initializes visual 15 and priority 4. Overlay mode replays the
  original vector commands **against the supplied existing planes**. Its fills
  therefore respect existing boundaries; overlay is not a static mask of a
  separately decoded picture.

Inputs are limited to 2 MiB and work to 20,000,000 units per transaction. Every
consumed byte, attempted pixel, flood admission and brush position contributes
to this bound. A canvas-sized queue replaces the original fixed-size flood
stack. Pixels are marked when enqueued, so a pixel enters a fill queue at most
once. All coordinates are checked before indexing a plane.

The operation requires FF and reports the bytes consumed through it. A suffix
after FF is left unconsumed. Unknown commands, malformed coordinate pairs,
truncation, memory failure and exhausted work return an explicit error. Raw
color bytes retain the upstream low-nibble behavior. Both planes and the
optional receipt remain unchanged on failure, including a late overlay error.

The nominal raster follows the pinned Sarien implementation. Its line endpoint
clipping and brush tables are not a claim that every original Sierra release
has identical edge behavior. Signed brush traversal safely clips the left edge
instead of preserving Sarien's unsigned-index underflow there. Out-of-bounds
initial stroke/fill points cannot wrap into neighboring rows. No high-resolution
mode, AGI v3 nibble unpacking, platform workaround or picture-format writer is
included.

## VIEW resource decoding

`agi_runtime_view_geometry` and `agi_runtime_view_cel` share one parser. It checks
the raw header, loop and cel directories, dimension bounds, selected structure
boundaries, and the selected cel's complete row RLE. Description offsets, when
present, require a bounded NUL terminator. Invalid or truncated selected rows
are rejected before output is committed; nonzero zero-length runs and runs
beyond the declared width are errors.

A selected cel has width 1–160 and height 1–168. Short encoded rows are padded
with the declared transparent palette index. If the mirror flag names a
different original loop, each decoded row is reversed once. The caller receives
already oriented pixels and must not mirror them again. Shared cel offsets are
supported without mutating the original resource or creating a mirror cache.

The geometry API implements the actor callback's partial-selection contract:
an out-of-range loop yields the resource's loop count and zero remaining fields;
an out-of-range cel additionally yields the valid loop's cel count. A valid
selection gives dimensions after checking its RLE. Empty loops can therefore be
reported explicitly. The decoder checks directory/header bounds for all loops
and cels; it does not decode every unselected cel's RLE on each query.

The cel API requires a valid selection and adequate caller storage, writes
exactly `width * height` bytes, and preserves unused output capacity. Outputs
must not alias the resource. Neither API opens a volume, resolves a resource
directory, decrypts LOGIC messages, or changes load membership; the CPU resource
bank owns those operations.

## Composition and persistence

`agi_runtime_scene_compose` rebuilds the image from explicit persistent visual
and priority backgrounds and the current `AgiRuntimeWorld`. Rebuilding removes
previous sprite pixels after movement, a cel change, erase, or resource discard,
without depending on stale saved rectangles.

The compositor selects animated-and-drawn actors whose VIEW is loaded. It
requires valid bound geometry and verifies it against the actual selected VIEW
cel. The complete cel rectangle must fit the scene; actor position repair takes
place before rendering. A missing resource, invalid later cel, or geometry
mismatch leaves the entire output and receipt unchanged.

Stationary actors render first, followed by updating actors. Each group sorts
by baseline; fixed-priority actors use the last row whose priority band is below
their explicit priority. Equal sort keys preserve ascending actor ID. The
actor's stored priority is authoritative for raster admission. The receipt
records the resulting actor order, admitted nontransparent pixel count, and
per-actor hidden result. It supports the complete 256-slot actor world.

Priority values 0–2 are control lines. A sprite pixel reads down its column
through those controls to obtain effective priority, defaulting to 4 if the
column ends first. It passes when its priority is at least that value. Passing
pixels preserve controls 0–2, while water 3 and ordinary priority values are
replaced by sprite priority. Transparency never changes either plane.

`agi_runtime_add_to_picture` applies the same raster rule directly to persistent
backgrounds. Priority zero selects the supplied baseline band. Margins 0–3
create a control rectangle spanning the nominal twelve-row band start plus one
through the effective baseline, preserving preexisting controls 0–3. Margin
values of at least four omit this rectangle. The historical plus-one behavior,
including a baseline exactly on a band boundary, is retained. A cel extending
above the canvas is moved down to top zero as in Sarien; right/bottom clipping
is bounded and never wraps into another row. The anchor itself must be within
the canvas. Subsequent ordinary actor erasure cannot remove these background
pixels or their control margin.

These APIs do not choose when to draw, tick, commit or present a frame. The CPU
and its service adapter own those lifecycle decisions. A successful composition
is a pixel/state result, not proof that a host display was presented or that an
external instruction completion was committed.

## Validation and limits of the evidence

`tests/test_qemu_agi_runtime_scene.py` compiles this production source as strict
C99 with warnings treated as errors. Its **37 authored cases** cover entire
visual/priority outputs; picture overlays and flood boundaries; pen and splatter
pixels; missing terminators and malformed/truncated inputs; finite-work rollback;
VIEW aliases, mirroring, RLE, partial geometry and maximum-sized cels; control
read-through; all 256 actor slots and ordering; move/erase/discard reconstruction;
late composition rollback; persistent margins; clipping and output alias checks.
These cases passed locally with no game assets or QEMU dependency.

A separate private reference batch compiled the relevant routines directly from
the pinned, unchanged `src/picture.c` with a small context adapter. All **2,544
authored cases** matched both complete planes: 1,920 splatter combinations,
16 solid brushes, 256 absolute strokes, 256 relative strokes, 48 corner/fill
programs and 48 overlay fills. Those cases use valid, in-bounds inputs and
establish agreement with that Sarien pin. They do not establish original-DOS
parity, whole-game correctness, commercial-resource qualification, or completion
of the parent CPU's resource, tick, observation and presentation integration.

A separate AddressSanitizer/UndefinedBehaviorSanitizer executable passed 5,000
authored picture mutations and 5,000 VIEW mutations, checking failure rollback,
palette bounds and output canaries. Leak detection was unavailable in this
execution environment: LeakSanitizer terminated with its documented ptrace
restriction. That failed attempt is retained separately; the successful
address/undefined-behavior run disabled leak detection and makes no leak-check
claim.

The implementation uses temporary heap storage where a parser or resource
callback can fail after work begins. Its maximum internal picture transaction
uses two indexed planes and one canvas-sized 16-bit queue. Composition uses
three indexed planes plus one decoded-cel temporary at a time. Static tables
are immutable; there is no mutable global engine state or I/O. Callers must
supply valid accessible C objects and pure resource callbacks as documented in
`runtime_scene.h`.
