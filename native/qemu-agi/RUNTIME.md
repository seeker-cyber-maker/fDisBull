# Native AGI CPU runtime

`agi-2917-runtime-1` executes the complete fixed catalog of actions **0–173**,
predicates **0–18**, IF and GOTO through the native AGI target in QEMU. It
includes resource banks, LOGIC calls, parser and inventory state, actor motion
and cycling, pictures and VIEW composition, sound sequencing, text windows,
menus, resumable device requests and same-build snapshots. The three earlier
raw-code pilot profiles remain available with their existing contracts.

This is an explicitly selected, bounded **nominal AGI 2.917 / Sarien-compatible
runtime**. The compatibility decisions below are part of the profile. Completing
its command catalog does not establish original-DOS parity or compatibility
with every AGI game and interpreter variant.

## One native authority

The canonical parser in `decode.c` supplies instruction extents, typed operands,
conditions and control-flow facts to both execution and static disassembly.
`runtime.c` executes those facts. The actor, scene and sound components own
their respective state transitions and resource decoding. Python transports
QMP, validates identities, packages immutable resources and consumes native
records; it does not execute a second AGI interpreter.

The runtime TCG path calls one bounded native instruction helper. Guest LOGIC
and PC live in the runtime, while the QEMU code page is an operand-free
trampoline. Changing LOGIC banks therefore cannot reuse stale translated
operands. This path is distinct from the older pilots' per-instruction TCG
operations. No runtime performance parity or original-machine timing is
inferred from build success.

`DISASM=1` and `SCENE=2` remain optional observation channels. Their mask,
capacity, counters and records are outside architectural guest state. The
disabled path performs no observation recording. A full journal retains its
prefix, counts dropped records and continues execution. Sound commands are
device output and remain active independently of these diagnostic channels.

Static listings select a specific LOGIC through `agi-decode-logic`. Each record
binds the selected code SHA, size, LOGIC number, profile and package SHA. A
call's static continuation remains an assumption until execution demonstrates
it. The same typed seam is available for future UIL emission; this module does
not yet emit UIL.

## Resource package

Startup uses `-M agi-test,runtime-package=/private/package.json`. It cannot be
combined with the legacy VIEW catalog or deferred-draw profile. The package
schema is `fdisbull-agi-runtime-package-1`, and every array is required:

| Field | Contents |
| --- | --- |
| `logics` | ID, exact code hex and SHA-256, ordered literal messages; message slot zero is unused |
| `views`, `pictures`, `sounds` | ID, exact raw resource bytes in lowercase hex, SHA-256 |
| `words` | Literal lowercase printable ASCII vocabulary and 16-bit synonym/group IDs |
| `objects` | Names and initial room bytes; array index is object identity |
| `entry_logic` | Explicit initial LOGIC, 0–255 |

The native loader validates the complete bounded JSON document and every blob
hash before constructing the CPU. The exact package bytes, including JSON
whitespace, define its identity. Missing referenced resources cause a stopped
fault; the engine does not synthesize a callee, VIEW, ego pose or input.

`runtime_pack.py` can package an explicitly supplied AGI v2 resource directory:

```sh
PYTHONPATH=src python native/qemu-agi/runtime_pack.py \
  --game-dir /private/authorized-game \
  --entry-logic 0 --output /private/authorized-game-runtime.json
```

Present but malformed resource-directory entries fail complete packaging.
`package_from_raw()` and `build_package()` support an explicitly chosen subset;
its omissions must stay visible. A selected room fragment is not a recovered
full game. Original game bytes, snapshots, decoded scenes and resource packages
belong outside the source checkout and tool distributions.

Native text is CP437. QMP exposes its Unicode representation and exact byte
hex; text that cannot be represented in CP437 is rejected. Resource parsing
supports v2 LOGIC payloads and their message tables, v2 pictures, VIEW cels and
four-stream SOUND resources. It does not select AGI v3 compression, mouse
extensions or platform-specific opcode remapping.

## Executed state and limits

| Area | Native ownership |
| --- | --- |
| Control and scalars | LOGIC/PC, 64 call frames, per-LOGIC scan entries, 256 byte variables and flags, arithmetic and indirection |
| Parser and input | 25 strings of up to 40 CP437 bytes, up to 20 parsed words, vocabulary matching, ordered short-circuit predicates, keys and controllers |
| Resources and persistence | Loaded membership, ordered VIEW/picture retention, replay byte pairs, inventory, explicit save/restore/restart semantics |
| Actors | 256 actors, view/loop/cel geometry, placement, priority, block/control-line rules, movement, direction, wandering/following, cycling and completion flags |
| Scene | 160×168 visual and priority planes, vector picture drawing, overlay, add-to-picture, native VIEW RLE/mirroring and ordered actor composition |
| Audio | Explicit PC speaker or four-channel Tandy device, per-channel countdowns, tone/divisor, envelope, attenuation and completion flags |
| Text and menus | 40×25 CP437 cells with attributes, saved window regions, text/graphics mode, status/input rows, menu headings/items and enable state |
| External requests | Source-bound typed requests, exact one-time completion, cancellation, text/number/selection replies and explicit device results |

Packages are limited to 64 MiB, each raw image/sound resource to 2 MiB, and
each LOGIC to 65,536 code bytes. The canonical decoder limits one instruction
to 1,024 bytes, 64 predicates, 256 condition tokens and 1,024 condition
operands. There are at most 64 menu headings, 256 items/key mappings and 4,096
replay pairs. Capacity exhaustion, invalid geometry, division by zero,
malformed code and missing resources produce explicit failures.

Guest variable 8 reports free 256-byte pages from the declared 64 MiB native
resource-residency budget, saturated at 255. Loaded code, messages and raw
resource bytes are charged to that report. It is not a measurement of the
original DOS allocator or the process's total heap.

The declared default platform is IBM PC with EGA: v20=0, v22=1, v26=3; v24=38
follows the selected Sarien input-width convention. Sound hardware is a
separate field, selected before execution with `sound_device(0)` for PC speaker
or `sound_device(1)` for Tandy. Guest writes to the report variable v22 do not
replace hardware. Explicit hardware selection survives restart and snapshots.

## Running the CPU

Use the isolated build recipe in [README.md](README.md). It builds the pinned
QEMU 10.0.13 source with the reviewed overlay and two compiler jobs. The runtime
is not selected as either product's default backend.

The source-tree Python interface is directly usable:

```python
from runtime_pack import build_package
from runtime_harness import QemuAGIRuntime

package = build_package(logics=[{
    "id": 0,
    # assignn(v50, 7); return
    "code": bytes([3, 50, 7, 0]),
    "messages": [],
}])

with QemuAGIRuntime("/path/to/qemu-system-agi", package) as vm:
    vm.configure(mask=3, capacity=4096)
    vm.cycle()
    state = vm.run(step_budget=1000)
    assert state["guest"]["variables"][50] == 7
    instructions = vm.decode(0, pc=0, limit=16)
    scene = vm.scene()
    events = vm.events()
```

Use `PYTHONPATH=src:native/qemu-agi` when running an external script from the
checkout. `QemuAGIRuntime` owns one child and its QMP pipes, checks finite
transport deadlines, and reaps that child on close. It does not locate or
install an emulator, advance time, invent input or acknowledge requests during
construction or `run()`.

### Clock, cycles and manual motion

These operations have different purposes:

| Operation | Effect |
| --- | --- |
| `cycle()` | Begin actor preparation and the next entry-LOGIC evaluation; the root return performs one actor completion phase |
| `run(step_budget=N)` | Execute up to N instructions, stopping at return, a request, a fault or quit; a budget stop is resumable |
| `clock(N)` | N system timer pulses at 20 Hz, with three 60 Hz audio ticks per pulse; no actor movement pass |
| `sound_tick(N)` | N audio ticks at 60 Hz, with no system-clock or actor advance |
| `tick(N)` | Explicit manual world steps, including motion, system clock and audio; intended for direct scene experiments |

A normal game controller advances `clock(max(1, v10))` between completed
cycles and then starts the next `cycle()`. It must not add manual `tick()`
calls to that schedule, which would move actors again. A budget-limited LOGIC
resumes with `run()` without beginning another cycle. Scheduling is explicit;
there is no hidden wall-clock thread or claim that accelerated debug stepping
represents physical play.

Pausing blocks timer advancement. Timed modal print uses v21 in half-second
units: the CPU latches 10×v21 system pulses, closes and retires the pending
print once at expiry, clears v21, and leaves the next instruction for an
explicit `run()`. Enter can acknowledge early. A zero v21 waits for explicit
acknowledgement, while f15 selects a nonblocking window and is consumed once.

`input(text)` submits an explicit completed parser line, up to 40 ASCII bytes
within the CP437 transport. This profile's vocabulary and parser accept ASCII;
display strings and typed string replies can use the wider CP437 character set.
It is not an implementation of the original keyboard interrupt queue or
physical line editor. A UI driver owns keystroke editing and its v24/dialogue
width policy. `key(code, pressed)` and `controller(id)` supply explicit events.

## Device requests and the headless service

Pending instructions have an ID, opcode, source LOGIC/PC, next PC, literal
operand bytes, reply type and formatted text. `pending()` returns a ticket
also bound to the owning child, executable and package. `complete()` checks
fresh state before sending the ticket once. Wrong IDs, altered replies,
disabled menu selections and stale tickets do not advance the CPU.

`RuntimeServices` implements a bounded headless capture driver. It records
outputs before acknowledging their native request. Its ledger is actual
output data, not proof that a GUI displayed a frame or hardware played audio.

| Request | Service behavior |
| --- | --- |
| Print, memory/version display, log | Capture text; ordinary modal output can be acknowledged by the capture driver; timed print is captured once and waits for native expiry or explicit acknowledgement |
| Priority display, shake, object preview, actor status | Capture native planes, ordered frame offsets, decoded VIEW pixels/descriptions or complete actor fields, then acknowledge |
| Inventory | Capture names and current locations; interactive inventory requires explicit selection/cancellation and updates v25 |
| String, numeric input and menus | Require explicit text/number/controller choices; cancelled prompted string editing leaves the cleared destination empty |
| Pause, restart and quit | Require an explicit choice unless the bytecode selects its documented immediate path |
| Save/restore | Explicit in-memory slots by default; native simple-save mode selects its nonempty description as the slot name |
| Joystick calibration | Remains pending until the caller supplies an explicit device result or cancellation; no hardware calibration is inferred |

The native `agi-runtime-presentation-json` property provides all device pixels
and resource descriptions. `show.obj` uses the native VIEW decoder, including
mirroring. The host does not parse the original image format. Shake payloads
include their exact restoration plan; capturing that plan does not advance
guest time. Malformed preview resources reject the query without mutating the
pending instruction.

The scene query composes actors against persistent background planes, so moved
or erased actors do not leave old pixels behind. Text cells and saved window
regions are native state; a display device owns font rasterization and the
pixel-level presentation of text borders. Status/input rows and window
restoration are tested as logical cell state.

### Audio output

The portable C embedding API supplies every committed sound command through
`AgiRuntimeSoundSink`. Batches stage output before committing, so a later tick
failure emits no partial command stream. Sound resynchronization after restore
re-emits current tone/gate/attenuation without advancing musical time.

QOM captures a bounded 262,144-command journal, independently of the observation
mask. `sound_events()` returns source-bound ordered rows and explicit
eligible/dropped counters. It raises if output was dropped; use
`allow_dropped=True` only to inspect incomplete evidence. After retaining or
delivering a capture, `clear_sound_events(capture)` acknowledges the exact owner,
epoch and sequence prefix. A stale or altered capture cannot clear newer output.
Drain this journal between bounded runs/timer batches, or use the C sink for
continuous device delivery.

## Save, restore and interruption

Snapshots contain the complete pointer-free architectural state and a header
with magic, ABI size, endian marker, version and package identity. The Python
save service also binds the executable SHA. They are **same-build snapshots**,
not original Sierra save files or a portable cross-platform format.

A snapshot at `save.game` records the post-save continuation. Other pending
interactive requests are not exported as resumable snapshots. Export validates
the projected state; restore validates resource membership/order, actor and
sound state, strings, menus, script bounds and inactive request storage before
committing. Restore starts a new observation epoch, preserves request-ID
uniqueness and resynchronizes audio. Guest restart preserves the chosen hardware
and sound-enable setting, and cannot reset the enclosing instruction budget.

Host output ledgers and save slots are owned by their service instance. They
can be copied/exported explicitly; closing a Python process does not imply a
durable save. Source and qualification receipts should be checkpointed with
their exact identities before work is handed off.

## Explicit compatibility decisions

- The nominal `trace.on` layout consumes zero operands. Tracing commands retain
  metadata rather than reproducing an original debugger window or its
  context-dependent extra-byte consumption. Earlier pilots still reject that
  ambiguous original layout.
- The deterministic xorshift32 RNG is snapshot-owned; it is not original-DOS
  random-number parity.
- The `have.key`/explicit event boundary follows pinned Sarien's consumable
  keypress behavior. Original 2.917 keyboard queue/latching details differ and
  are not qualified by this explicit-input interface.
- String, actor, key and parser capacities are the bounded native profile's
  declared capacities, not a claim about every original interpreter's limits.
- The display projection is EGA. Monitor-toggle state is retained, but this
  profile does not emulate an alternate physical video adapter or font ROM.
- Memory accounting and saves use the native contracts above; there is no DOS
  heap, original LOGFILE writer, host-filesystem save-dialog fallback or original
  platform timer emulation. Log capture retains room and input context.

These differences are stable interface choices and qualification boundaries.
They must not be hidden behind a statement that all original AGI engines behave
identically.

## Verification

Authored tests execute the production C components, the real rebuilt QEMU
binary, and the public Python interface. They cover every descriptor and
predicate layout, cross-family interactions, atomic failures, restart budgets,
timed effects, text backing, device requests, snapshot admission, sound output
and full-state observation neutrality. Independent Sarien picture comparisons
and sanitizer runs are separate evidence, with their exact source scope.

[RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md) describes the resource-bound
qualification controller and independent plane oracles. PQ1/KQ1 are development
inputs. Missing global state, truncated volumes and stopped prefixes remain
explicit; SQ1/LSL1 are held out. A bounded startup or exact room-fragment image
does not claim an entire game was completed.

For an exact candidate, set `FDISBULL_QEMU_AGI` and
`FDISBULL_QEMU_AGI_EXPECTED_SHA256` and run the affected native/runtime suites.
Unset required runtime variables produce explicit skips. Receipts bind the
source manifest, actual compiler/build, binary, package, commands and outputs.
Hosted CI, release packaging/install activation, backend migration and
original-DOS parity remain separate qualifications.

Provenance: [runtime](RUNTIME_PROVENANCE.md),
[actors](RUNTIME_ACTOR_PROVENANCE.md), [scene](RUNTIME_SCENE_PROVENANCE.md),
[sound](RUNTIME_SOUND_PROVENANCE.md), and
[canonical descriptors](OPCODE_COVERAGE.md).
