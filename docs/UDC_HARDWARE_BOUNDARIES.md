# Hardware boundaries for DOS UDC modules

DOSBox remains the target environment. This note records what the original
DinoPark code depends on and proposes contracts for later UDC consumers,
including a consumer using host mouse/audio facilities. It does not implement
or qualify a native host device backend.

UDL identifies an original operation and its code/module evidence. UIL can
express its intent and state effects. A UDC chooses an implementation and must
qualify that implementation against the same observation contract. Rust, JS,
Python, retained original code and other implementations have the same proof
obligations. A different implementation is not equivalent merely because it
uses the same operation name.

## What the original code shows

The static study uses original DINOPARK.EXE SHA-256
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
These are stored native instructions and register facts, including linked
library code. They establish potential dependencies; they do not certify that
every path runs in an ordinary playthrough. Unknown register/port values
remain unknown.

| Boundary | Original-code evidence | Contract needed by a UDC consumer |
|---|---|---|
| Mouse | Three INT33 sites: AX=0, 3 and 4 | Driver presence/reset, button state, virtual position and position setting; preserve coordinate conversion. |
| Keyboard | Four INT16 sites plus direct port 60h access and PIC port 20h | Ordered press/release and scan/character semantics, peek versus consuming read, key state, modifiers and interrupt acknowledgement. |
| Graphics | Eighteen INT10 sites, including mode 13h; direct VGA ports 3C0h, 3C4h, 3CEh, 3D4h, 3C8h and 3DAh | Video mode, register state, indexed palette, planar/banked memory behavior and retrace timing; a generic flat bitmap is insufficient without qualifying these effects. |
| Time | INT1A AH=0 and PIT ports 40h/43h | Guest ticks and timer scheduling, including audio/BIOS interrupt sharing. |
| Sound and music | INT66 callers and dynamically loaded DIGPAK/MIDPAK/AIL modules | Sample/sequence identity, buffer lifetime, acceptance, active/completed state, callbacks and capability/version guards. |
| Joystick | Seven stored accesses to port 201h | If a reachable path needs it, model buttons and timed analogue-axis polling. No live joystick support is qualified by this discovery. |
| Expanded memory | INT67 AH=41h–45h variants | EMS page-frame identity, allocation handles, logical-to-physical page mapping and errors. |
| Extended memory | INT2F AX=4300h/4310h and INT15 AH=87h/88h | XMS discovery/entry binding, BIOS memory size/copy and observable status, with address and ownership rules. |
| DOS process/resources | INT21 memory, file, vector and termination services | Guest addresses and handles, module load/unload identity, old-handler restoration, retained resources and selected-process exit. |

In the stored main-program I/O facts, 48 port accesses have unresolved port
values. The resolved ports above are a bounded inventory, not a complete bus
model. Driver modules add their own I/O. For example, SBPRO.COM contains DMA
channel-1 programming, DSP/mixer work and interrupt-mask manipulation. Treat
unsupported direct bus operations as opaque/unknown until a binding exists.

## A native mouse adapter

The smallest useful DinoPark slice is a virtual mouse implementing reset,
poll and set-position. The game reads INT33 AX=3, stores BX buttons and CX/DX
coordinates, then arithmetic-shifts the stored horizontal coordinate right by
one. Its setter doubles its input x before INT33 AX=4; y is unchanged. The
stored mapped call sites are 0x175BF and 0x1764C respectively. This conversion
must occur exactly once when comparing the original DOS interface with a
rendered 320-pixel-wide view.

A possible implementation outside DOSBox would receive events inside the
consumer's own window, maintain virtual pointer/button state, and return the
DOS-visible registers at the guest operation boundary. SDL provides both
[window-relative pointer state](https://wiki.libsdl.org/SDL2/SDL_GetMouseState)
and [relative motion](https://wiki.libsdl.org/SDL2/SDL_GetRelativeMouseState).
That supplies host input; the adapter still owns guest semantics:

- Translate named buttons. SDL's common left/middle/right order differs from
  DOS BX's left/right/middle bits. Copying the raw host mask swaps meanings.
- Convert window pixels through viewport scaling/letterboxing into guest
  coordinates, then apply the chosen DOS mode's range and granularity.
  Position, relative motion (mickeys) and accumulated motion counters are
  different quantities.
- Model reset, cursor visibility, range, sensitivity, press/release counters
  and motion-counter consumption when the supported program uses them.
  Polling a host snapshot alone can lose events needed by a counter API.
- INT33 set-position updates virtual guest state. A consumer may choose a
  window-local warp, but must avoid feedback that duplicates motion and should
  not treat guest movement as a request to control the global desktop pointer.
- Keep input events and guest execution ordered. Pointer movement, button
  down, button up and the resulting game action are separate observations.

The Microsoft-compatible [reset](https://fd.lod.bz/rbil/interrup/io_mouse/330000.html),
[poll](https://fd.lod.bz/rbil/interrup/io_mouse/330003.html) and
[position](https://fd.lod.bz/rbil/interrup/io_mouse/330004.html) contracts specify
the register boundary. A positive reset result also has button-count variants;
presence must not be inferred from the host having a pointer device.

Other programs can register a [mouse callback](https://fd.lod.bz/rbil/interrup/io_mouse/33000c.html)
with an event mask and a FAR code address. That requires controlled delivery
with the specified registers, module lifetime and calling convention. A host
event thread cannot call a guest segmented pointer directly. A callback is
also distinct from the underlying hardware interrupt entry/return. No such
INT33 callback site was found in this bounded DinoPark inventory.

[DOSBox-X's mouse implementation](https://dosbox-x.com/doxygen/html/mouse_8cpp_source.html)
is useful architectural evidence: it translates host events into virtual
state, applies mode/range/granularity rules and implements INT33 separately
from PS/2/IRQ delivery. The published source is not a byte-identity assertion
about the separately pinned acceptance backend. Programs using BIOS PS/2 or
controller ports instead of INT33 need an additional lower-level binding.

## Interconnections an adapter must preserve

**Video and mouse:** cursor position is expressed in a mode-dependent virtual
coordinate space. Changing video mode, page, range or viewport can change the
mapping. Cursor drawing also interacts with the framebuffer and saved
background. A frame hash must state whether the cursor is included.

**Video and time:** a loop reading VGA status port 3DAh can wait for retrace.
Returning a constant status can hang a translated loop. A native renderer
needs a guest-time model for such status reads, or a separately qualified
replacement at a higher-level wait/present boundary. Palette and plane writes
remain part of the observable image state.

**Keyboard and interrupts:** a program can poll BIOS keys while also keeping
its own scan-code state through a hardware handler. Text injection alone does
not reproduce that behavior. Preserve key-up events, queue consumption,
modifier state and handler ownership at the supported boundary.

**Audio and time:** the AIL descriptor's service-rate request and DIGPAK's
timer/DMA paths share guest execution with other devices. Host mute must leave
the guest's completion path intact. A foreground driver and an asynchronous
driver can have different blocking semantics. Sample buffers and playing-flag
memory must remain valid until the corresponding request is complete.

**DMA and memory:** the original driver can depend on DMA address/count/page
registers, buffer boundaries and completion interrupts. A higher-level host
sample player can replace those details only under a declared and tested
contract. It cannot silently claim original DMA behavior.

**Memory and callbacks:** guest far pointers, EMS windows and XMS handles are
not host pointers. Keep checked guest address translation and handle/module
generation identity. Reuse of a segment after unload does not identify the
same code. Original drivers can replace and chain interrupt vectors; shutdown
must release the correct instance and restore the prior handler.

**Observation and effects:** some apparent queries consume state. Keyboard
reads dequeue; mouse motion/button-counter queries can clear counters; a poll
routine can advance a music engine. A metadata description is read-only, but
executing a described API is not automatically read-only. For passive Z
readback, inspect supported stored/live state without replaying an action or
injecting a query with unmodeled effects.

**Persistence:** a park save, a UDC resource closure and a complete machine
checkpoint have different contents. A device-aware checkpoint may need cursor
state, input queues, palette/VRAM, interrupt vectors, module bindings, timer
phase, sample position and pending callbacks. Do not call a gameplay-field
comparison complete device-state equivalence.

## Suggested qualification ladder

1. Keep the original DOSBox path as the reference and retain original module
   hashes, file offsets, runtime bindings and actual call/return observations.
2. Bind a small operation family, beginning with mouse reset/poll/set or a
   selected audio request. State unsupported services explicitly.
3. Compare unchanged-state controls, register results, ordered input events,
   virtual time, frames and completion under that same declared boundary.
4. Add callbacks, error/capability paths and save/reload only when the earlier
   slice has evidence. Preserve unknown or interrupted requests.
5. Compare alternate compiler implementations and optimizations under the same
   contract. Faster execution alone does not establish equivalent behavior.

Current implemented seams are [AIL inspection and named audio contracts](DOS_AUDIO_DRIVERS.md).
The existing [DOS UDC](UDC_DOS.md) retains original-backed bytes and qualified
blocks; this note does not expand its executable semantics to a native host
mouse, VGA, EMS/XMS or audio renderer.

Additional primary protocol references:
[BIOS extended-memory copy](https://fd.lod.bz/rbil/interrup/bios/1587.html),
[RBIL memory-management interfaces](https://fd.lod.bz/rbil/interrup/memory/index.html),
and [DIGPAK source](https://github.com/jratcliff63367/digpak).
