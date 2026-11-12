# CHIP-8 QEMU classic CPU, devices, RNG and layers

This profile connects a newly compiled QEMU TCG CPU/machine to fDisBull's
persistent source analysis and debugger. It is a bounded architecture experiment.
It does not change the DOS backend selector: DOSBox-X remains the default and
retained fallback. The dated [handoff](DOS_QEMU_HANDOFF.md) records actual local
build/test results and remaining gates.

## Reuse of the earlier architecture and sweding work

The classic opcode patterns and declared quirks come from the existing
[CHIP-8 pilot](../examples/chip8_pilot/README.md). The production static decoder
is compared with its classic classifier over all 65,536 words. That agreement
does not provide an independent historical execution oracle.

The earlier [Python UDC proof of concept](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/3e437a9e9ca313a2a24d18ef928a40fc5084b5f7/examples/chip8_pilot/PYTHON_UDC_POC.md)
remains on `agent/chip8-python-udc-poc-20261103`. Its hash-pinned opcode catalog,
manually sweded templates and trace-specialized outputs are useful conversion
work. Its generated Python still falls back to the authored interpreter, and
its intent records are candidate UDL/UIL rather than admitted common UIL. That
branch is preserved separately; it is not silently merged or relabelled as a
finished native conversion.

The new seam is source ROM → ordinary persistent FDB facts → a real QEMU
CHIP-8 CPU → fDisBull register/RAM/control/checkpoint operations. The
[G0–G8 end-to-end plan](milestones/2026-11-03-chip8-package-end-to-end-acceptance.md)
still governs qualification of source semantics, common UIL, registered UDC
providers, standalone emitted executables and reuse on held-out programs.
Building this debugger seam does not close those later conversion gates.

## Explicit source admission

For this source candidate, run the CLI from the checkout with
`PYTHONPATH=src python -m fdisbull` in place of `fdisbull` below. A shared
installation has its own payload and is not activated by these source tests.

```sh
fdisbull import /private/probe.ch8 /private/probe.fdb --arch chip8
# Equivalent explicit profile:
fdisbull import /private/other.ch8 /private/other.fdb \
  --profile chip8-classic-pilot-default-v1
```

The source is a caller-owned raw ROM of 2..3,584 bytes, mapped at `0x200` in
4 KiB of RAM. Source bytes and hash remain immutable in the original version.
No filename or host CPU inference selects the architecture. An odd-length data
tail is allowed; instruction starts must be even and contain a complete
big-endian 16-bit word. The persistent decode context is `chip8:16:big`.
An explicit base/entry override must still be `0x200`.

The static decoder recognizes the 34 non-legacy classic families. SYS calls,
SCHIP/XO extensions, invalid and truncated words remain undecoded. Skips retain
the taken `PC+4` and fallthrough `PC+2` edges when those destinations are in
range; an out-of-RAM taken target stays unresolved. Calls/returns remain distinct;
the V0-indexed jump stays indirect. I-based memory access facts keep their
address unknown unless the caller supplies an established I value. No address
is silently wrapped or invented from a missing register.

## Native CPU contract

The executable is a separately built `qemu-system-chip8`, with machine
`chip8-test` and profile `chip8-classic-pilot-default-v1`. The retained
[CPU-only patch](../native/qemu-chip8/README.md) identifies itself as
`fdisbull-chip8-cpu-smoke-1`. The optional
[device extension](../native/qemu-chip8-devices/README.md) uses
`fdisbull-chip8-classic-devices-2` and environment model
`fdisbull-chip8-display-keypad-timers-1`. The optional
[complete classic extension](../native/qemu-chip8-classic/README.md) identifies
as `fdisbull-chip8-classic-complete-3` with environment model
`fdisbull-chip8-display-keypad-timers-rng-2`. The experimental layer extension
identifies as `fdisbull-chip8-layers-hooks-4`, environment
`fdisbull-chip8-display-keypad-timers-rng-layers-3`, and layer model
`fdisbull-chip8-native-layers-1`. Bounded authored native witnesses passed locally on macOS arm64. A raw ROM
loads through `-kernel` at `0x200`.
There is no DOS image, PC firmware, guest OS or hidden interpreter process.

The first target uses one instruction per TCG block and a bounded native C
execution helper. It tests QEMU CPU/debugger integration; it is not an optimized
per-operation TCG backend or a newly qualified common-UIL representation.

Implemented words are `00EE`, `1nnn`, `2nnn`, `3xkk`, `4xkk`, `5xy0`, `6xkk`,
`7xkk`, `8xy0/1/2/3/4/5/6/7/E`, `9xy0`, `Annn`, `Fx55` and `Fx65`.
The declared pilot-default quirks use Vy for shifts, clear VF after logic,
and increment I after register transfers. Operands are read before writes,
including VF aliases. V0–VF are 8-bit; I, PC and return-stack entries are
stored as 16-bit values; SP has a maximum of 16. A valid final-byte transfer
can leave I at `0x1000`; a later out-of-range transfer faults rather than
wrapping. PC may advance beyond RAM and then fault on the next fetch.

Unknown/unsupported words, out-of-range fetch/transfer, stack under/overflow
and odd fetch addresses produce an inspectable sticky fault. Faulting
operations do not commit partial CPU/RAM updates. This aligned-fetch and
atomic-fault policy is an explicit implementation limit: the earlier authored
Python pilot permits odd fetches and can advance PC before some traps.
Successful-case comparisons with that pilot do not erase those differences.
Faults survive debugger edits, further resume and checkpoint restore; reset or
a fresh launch clears them. Editing PC is not implicit permission to clear a
recorded native fault.

`query-chip8-fault` binds the profile/subset and exposes fault code, source PC
and word. The debugger checks that identity and the complete GDB register XML;
it reads the CHIP-8 PC directly. A native fault takes precedence over a
breakpoint at the same PC. A timeout remains a timeout, without another guest
continue. Its late stopped-state inspection is a separate operation.

## Launch and inspect through fDisBull

```sh
fdisbull debug /private/probe.fdb \
  --backend qemu-chip8 --game-dir /private \
  --executable /external/build/qemu-system-chip8 \
  --qemu-checkpoint-tool /path/to/qemu-img
```

The same route is available through `debug-launch` and
`Project.debugger(..., backend="qemu-chip8")`. Select it explicitly. DOS/PC
clock, firmware, directory and device options refuse on this profile.
Original, unpatched CHIP-8 projects are admitted for execution; source patches
remain separate static versions and do not silently replace the running ROM.

For the authored ROM `6001 7002 A300 F055 1208`:

```python
with project.debugger(qemu, rom_directory, backend="qemu-chip8",
                      qemu_checkpoint_tool=qemu_img) as debug:
    point = debug.breakpoint(0x208)
    result = debug.run(timeout_ms=5000)
    assert result["outcome"] == "breakpoint"
    assert debug.registers()["registers"]["v0"] == "0x3"
    assert debug.memory(0x300, length=1)["hex"] == "03"
    debug.delete_breakpoint(point["breakpoint_id"])
    saved = debug.save_state()
    debug.write_memory(0x300, "7f", expected_hex="03")
    debug.load_state(saved["artifact"])
    assert debug.memory(0x300, length=1)["hex"] == "03"
```

Guarded register/RAM edits validate all guards before dispatch and read back
their effects. An uncertain mutation closes the owner rather than allowing
unobserved guest state or hidden breakpoints to remain live. Debug runs and
execution events are persisted in the FDB; an ended run is not a live session.

## Display, keypad and timers in the device extension

The device runtime adds `00E0`, `DxyN`, `Ex9E`, `ExA1`, `Fx07`, `Fx0A`,
`Fx15`, `Fx18` and `Fx29` to the retained CPU instructions. The display is
64 × 32 monochrome pixels in native machine state. Sprite coordinates wrap
to the display bounds before drawing; the sprite then clips at the right and
bottom edges. Drawing XORs pixels and sets VF on collision. VX/VY are captured
before VF is written, including coordinate aliases. A sprite read outside RAM
faults before changing the display or CPU. The font starts at `0x50`; `Fx29`
selects the low nibble of VX from the declared classic font.

The keypad stores a held mask of the sixteen logical hex keys. `Fx0A` consumes
the lowest held key, including key zero. With no held key it stops at the same
PC with outcome `key_wait`. Changing the key mask prepares input; the caller
explicitly runs or steps to continue. A restored architectural wait does not
carry ownership of an earlier debugger stop. Values above fifteen never match
a pressed key in `Ex9E`/`ExA1`.

DT and ST decrement at 60 Hz on QEMU's virtual clock while the machine runs.
Stopped debugger time does not advance that clock. Rational timer phase,
absolute next deadline and separate virtual/manual tick counters are observable.
This does not qualify a wall-clock CPU rate or historical nonblocking key-wait
timing: the owned `key_wait` stop pauses the machine. ST exposes `sound-active`
while nonzero; audio waveform/output is unavailable.

Stopped-state controls are available through Python and the foreground JSON
workspace. Every key/tick mutation checks the native generation and reads back
CPU and complete device state. Uncertain mutations close the owner and must not
be replayed blindly.

```python
environment = debug.chip8_environment()
debug.chip8_keypad([0, 10])  # complete held set: hex 0 and A
debug.step()               # explicit execution; setting keys does not resume
debug.chip8_keypad([])      # release every key
debug.chip8_tick(2)         # deterministic decrement by two 60-Hz units
frame = debug.frame_rgba()  # exact 64 × 32 RGBA bytes, hash and native receipt
png = debug.screenshot()   # stored PNG artifact derived from native pixels
```

`chip8_tick(1..65535)` decrements/clamps DT/ST through the native timer routine
without executing CPU instructions or advancing virtual time, deadline or phase.
It records manual ticks separately. The JSON methods are
`debug-chip8-environment`, `debug-chip8-keypad` (`keys`) and `debug-chip8-tick`
(`ticks`), with the selected `run`. Existing frame/screenshot routes use the
same device state. No GUI is needed for a capture. Framebuffer-bearing receipts,
PNG bytes and checkpoint bytes use the private external object store; keep
that store available when reopening the FDB.

## Complete classic profile and checkpointed RNG

This extension has a locally built macOS arm64 runtime with executed classic
instruction and RNG checkpoint witnesses. The retained CPU-only and device
binaries remain unchanged. Linux/other-host and arbitrary-ROM compatibility
remain unqualified.

The classic extension implements all 34 non-legacy instruction families admitted
by this profile. It adds the four remaining families to the CPU/device runtime:

- `Bnnn` jumps to `nnn + V0`, without wrapping at the 4 KiB RAM boundary.
  An out-of-range or odd destination faults on its next fetch.
- `Fx1E` adds VX to I modulo 65,536 and leaves VF unchanged. VX is read before
  updating I, including when X is F. This preserves the declared pilot quirk.
- `Fx33` writes the hundreds, tens and units of VX to I..I+2 without changing
  I or VF. The complete three-byte extent is checked before any write.
- `Cxkk` advances the native RNG once and writes its masked byte to VX.
  A zero mask still consumes a draw; VF is preserved unless it is the destination.

Legacy `0nnn` calls require a different host-machine execution contract and
remain unsupported. SCHIP/XO words remain outside this classic profile. Full
opcode-family implementation does not qualify arbitrary ROMs, historical timing
or every dialect/quirk combination.

The native RNG is explicitly `fdisbull-lcg32-high8-v1`. Its seed and state are
32-bit integers; reset starts both at zero. For each draw:

```text
state = (1664525 * state + 1013904223) modulo 2^32
byte = state >> 24
VX = byte & kk
```

The draw counter saturates at the maximum uint64 value. This is a deterministic
analysis generator, with no cryptographic claim or claim to reproduce the Python
pilot's `random.Random` stream. The receipt binds the RNG model, seed, current
state and draw count. Fresh sessions repeat the same default stream; callers
choose other seeds explicitly.

```python
before = debug.chip8_environment()
seeded = debug.chip8_seed_rng(123)  # uint32, including zero
assert seeded["rng-state"] == 123 and seeded["rng-draws"] == 0
checkpoint = debug.save_state()
# Explicit run/step executes Cxkk; restore returns to the same stream position.
debug.load_state(checkpoint["artifact"])
```

`debug-chip8-seed-rng` exposes the same operation through JSON with `run` and
`seed`. The native `x-chip8-seed-rng` command requires a stopped VM and matching
generation. Successful reseeding resets seed/state/count and advances the state
generation once; it does not execute CPU instructions or change RAM, pixels,
keys or timer state. Stale/invalid updates refuse before effects. The existing
keypad/tick controls preserve the RNG stream.

## Checkpoints and capabilities

The machine has no guest storage. With an explicit `qemu-img`, a private,
guest-unattached qcow2 node holds QEMU's full native snapshot. The snapshot
binds the exact source version/hash, CPU profile/subset, QEMU binary/version,
machine/RAM configuration and checkpoint-tool hash. CPU registers, stack,
fault state and all 4 KiB RAM are checked after load in a fresh QEMU process
before replacing the previous owner. Device snapshots also compare every pixel,
held keys, wait state, DT/ST, sound-active, timer phase/deadline, virtual time
and both tick counters. Ephemeral ownership of the earlier wait stop is cleared.
Restore across QEMU binaries or CPU profiles is refused. Host files are not restored.

Remove ordinary user execution breakpoints before saving or loading a checkpoint.
The v4 profile may retain hook-owned traps as described below. A reopened
FDB can restore its artifact after explicitly launching the same ROM and native runtime. A checkpoint is not permission to guess a
different source, dialect, device state or engine binary.

The retained CPU-only runtime and its `fdisbull-qemu-chip8-state-1` artifacts
remain supported with their exact original binary. The retained device runtime
uses `fdisbull-qemu-chip8-state-2`. The complete classic runtime uses
`fdisbull-qemu-chip8-state-3`, including RNG model, seed, state and count. It
restores the exact future RNG sequence along with CPU/RAM and device state.
The v4 layer extension uses `fdisbull-qemu-chip8-state-4` with native fetch
state and a sidecar for the active layer stack and hook controls. A bounded authored fresh-owner witness checks CPU, RAM, device/RNG state,
native fetch state and immutable definition identities before replacing the
old owner on macOS arm64. These formats do not imply
cross-binary restore.
Device capabilities are enabled only after checking the native subset identity
and required command set. The older runtime continues to refuse device calls.

## Experimental CHIP-8 layers and hooks

The v4 profile adds immutable, version-bound flat 4 KiB layer definitions and
stopped native activation. `debug.layer_patch(name, address, expected_hex=...,
data_hex=..., kind="ram" | "execute")`, `debug.layers(active=[...])`,
`debug.layer_enable(...)` and `debug.code(..., view="ram" | "execute")` use
the existing layer routes. Source addresses are limited to the original ROM;
physical and linear addresses refer to the same flat RAM. Ordered stacks use
the last patch at a byte independently for RAM and instruction fetch. Guards
must agree on the base bytes. Guest changes to an active RAM layer refuse a
transition by default; clearing with `conflict="keep_changed"` retains changed
bytes. A changed fetch backing or latched native layer fault stops execution
with `layer_conflict` until a successful reconfiguration clears it. A checkpoint
can preserve that fault and backing state without claiming it was repaired.

`debug.hook(address, actions=[...], once=..., max_hits=...)` installs a bounded
execution breakpoint with paused-RPC layer-stack or guarded non-PC register
actions. `debug.hooks()`, `debug.delete_hook(...)`, and
`debug.run(stop_on_hook=True)` expose the controls. Faults, layer conflicts,
ambiguous stops and key waits do not dispatch hook actions. The v4 checkpoint
sidecar records logical hook IDs, hit counts and pending step-over state; restore
reinstalls hook traps on the fresh stopped owner. Bounded authored native witnesses passed locally on macOS arm64, including
RAM and fetch views, guarded hooks, conflicts, fault preservation and
fresh-owner restore. They do not establish general game compatibility or parity.

All profiles support stopped inspection, bounded run/step, execution breakpoints,
guarded edits and native checkpoints. The three earlier profiles continue to
use their exact matching binaries and do not acquire v4 or v5 controls. CHIP-8 audio
output, predicates, watchpoints, redirects, task-private views, selected undo
and comparative trials remain unavailable in this target. IRQ/PIC and
QEMM/DESQview task semantics remain DOS-profile work; DOSBox-X remains the
default and retained fallback.

## V4 full-checkpoint histories

The v4 `fdisbull-chip8-layers-hooks-4` runtime also supports bounded native
histories when launched with the explicit QEMU checkpoint tool. Histories use
the existing full `fdisbull-qemu-chip8-state-4` checkpoints; they do not replay
instructions or store inverse CPU/RAM deltas. Each checkpoint covers the
CHIP-8 CPU and 4 KiB RAM, native fault, display/key/timer/RNG state, native code
layer state, and the portable logical hook state. Hook-owned breakpoints are
recreated with fresh runtime IDs during restore. No host files are restored.

```python
root = debug.rewind_start(max_steps=16, max_bytes=512 * 1024 * 1024)
first = debug.rewind_record()  # one stopped native step and full checkpoint
debug.rewind(history=first['history'], node=root['cursor'])
branch = debug.rewind_record(advance='capture')  # explicit stopped boundary
```

`rewind_start`, `rewind_status`, `rewind_record`, and `rewind` are also exposed
through JSON `debug-rewind-start`, `debug-rewind-status`, `debug-rewind-record`
and `debug-rewind`. Saved scripts use `rewind-start`, `rewind-status`,
`rewind-record` and `rewind` with backend `qemu-chip8`. A normal record advances one native
step; a known stop can be checkpointed without claiming that an instruction
completed. `advance="capture"` captures one explicit stopped boundary and
labels the interval as unobserved. It does not claim a step occurred. Recording
by step refuses while a hook is pending; explicit capture remains available.

Histories are immutable manifest revisions over a retained DAG: rewinding to
an older node and recording again creates a branch while preserving later
nodes. A reopened FDB can attach to a history, but its live cursor starts
invalid; restore an explicit node before recording steps. Explicit capture can
add the current stopped state as an unobserved boundary. Checkpoint data and
its metadata sidecar are both hash-bound. Restore verifies the ROM/version,
QEMU binary and profile identity, checkpoint bytes and metadata, then checks
the full restored CPU/RAM/device/layer/hook state before accepting the new
owner. After dispatch, an uncertain step, capture, restore or journal publication
leaves an unresolved pending operation and is never automatically replayed.
Known admission refusals occur before recording intent or changing the guest.

The history accepts at most 128 nodes and 1 GiB of cumulative checkpoint
artifact payloads. Each state artifact is bounded to 128 MiB, and the FDB's
256 MiB runtime-artifact cap can reduce the usable history budget further.
Growth of the live private QCOW2 file is measured separately and is not
covered by that history byte quota. Ten bounded authored native v4 history
cases passed locally on macOS arm64. They do not qualify CHIP-8 game
compatibility, conversion, frame sampling, deltas, selected undo, trials, or
promotion of the DOS backend.

## V5 virtual-tick frame histories

The separate v5 `fdisbull-chip8-frames-5` runtime adds a sample fence at the
next native 60 Hz virtual timer tick. With the explicit checkpoint tool,
`timeline_start`, `timeline_status`, `timeline_advance`, `timeline_rewind`,
`timeline_image`, `timeline_pin`, and `timeline_stop` record full-checkpoint
nodes and immutable PNG artifacts. JSON methods use `debug-timeline-start`,
`debug-timeline-status`, `debug-timeline-advance`, `debug-timeline-rewind`,
`debug-timeline-image`, `debug-timeline-pin`, and `debug-timeline-stop`;
saved scripts use the corresponding `timeline-*` names with backend
`qemu-chip8`. The history preserves CPU/RAM, device and RNG state,
layers, hooks, display pixels, timer phase/deadline, and virtual-tick counters.
Rewind restores a selected retained node; recording from an older node keeps
the later branch.

Each node binds the PNG pixel hash to the saved pixel state and checkpoint
metadata. The native receipt distinguishes the consumed tick deadline, the
actual virtual time at which the timer callback sampled pixels, and the later
stopped virtual time. Callback lateness is recorded; the sample does not claim
historical wall-clock timing, guest drawing completion, VBlank, or a completed
guest frame. `completed_guest_frame` remains null. The fence is process-local:
checkpoint save/load is refused while armed or completed, including after the
owned stop, until the fence is cancelled. A reopened history has no valid live
cursor until an explicit node restore succeeds.

Frame histories use full checkpoints and immutable full PNGs. The budget is at
most 128 nodes/captures and 1 GiB of combined checkpoint and image artifacts,
subject to the 256 MiB project artifact cap; private QCOW2 growth is measured
separately and is not included in that quota. Advance admission estimates each
future checkpoint from the previous checkpoint and live QCOW2 size, plus the
configured image limit. A later snapshot can grow beyond that estimate. Actual
combined size is checked before committing its timeline node; exhaustion after
execution closes the owner and retains the pending intent, and already-created
checkpoint/image artifacts may remain unreferenced. This is not a guarantee of
no guest effects for every future byte-budget failure.

The adapter reserves a bounded part of the caller's existing execution allowance
for stop recovery and classification; it does not extend the requested budget.
A recovered short run can return its timeout receipt without exhausting the
outer admission deadline. A genuine overrun still closes the owner. The shared
GDB client's existing emergency Ctrl-C recovery may take up to five extra
seconds, so this is not a hard wall-clock return guarantee.

Sixteen bounded native v5
frame-history cases passed locally on macOS arm64. The retained v4
instruction-history and v1-v4 native runtime identities remain separate; no
cross-binary VMState restore is claimed. This does not qualify
CHIP-8 game compatibility, VBlank or historical replay, frame deltas, selected
undo, comparative trials, IRQ/task-private behavior, audio, other hosts,
arbitrary ROMs, end-to-end conversion, or DOS backend promotion.

## V6 frame-key ownership and input restore

The separate `fdisbull-chip8-frame-keys-6` runtime adds owned logical edges for
CHIP-8's sixteen keypad values. It uses VMState6, host state format6 and
`fdisbull-qemu-chip8-frames-v2` timelines. The original v1-v5 binaries, state
formats and v5 frame-history format remain separate. Old histories must use
their recorded runtime; cross-binary VMState restore is not supported.

`frame_inputs(edges)` applies one stopped atomic batch without running the
CPU or advancing virtual time. Each edge has exactly `key` and `pressed`:
keys are lowercase hexadecimal strings `0` through `f`, and `pressed` is a
boolean. At most sixteen distinct keys are allowed in a batch. Pressing an
already held key or releasing an unheld key is refused. This API does not
model a physical keyboard, PS/2 FIFO, typematic repeat or guest consumption.
The receipt reports the held set and native ownership/counter proof.

```python
debug.frame_inputs([{'key': '0', 'pressed': True}])
print(debug.keyboard_state()['keyboard']['frame_keys'])
debug.frame_inputs([{'key': '0', 'pressed': False}])

root = debug.timeline_start(max_frames=8)
recorded = debug.timeline_advance(frames=3, inputs=[
    {'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]},
    {'frame': 2, 'edges': [{'key': 'a', 'pressed': False}]},
])
debug.timeline_rewind(frames=3)
```

A schedule applies edges before the indexed sample interval. The complete
schedule is validated against the current held set before any earlier frame
runs. Native application compares the owner token, ownership generation and
CPU state generation; malformed, stale and foreign requests are refused
atomically. An active frame fence prevents input mutation. The sixteen-key
mask remains distinct from ordinary `chip8_keypad` control: manual held keys
prevent claiming a frame owner, and frame-owned held keys prevent manual mask
replacement. Once all owned keys are released, the adapter can detach the empty
owner before a manual keypad change.

Each new timeline point binds the full input state to its checkpoint and records
accepted edge receipts. Standalone edges make the live point input-dirty;
`timeline_pin` refuses it, while `timeline_rewind(frames=0)` restores the last
recorded point. Old branches and their input journals remain retained. An earlier
hook, breakpoint, wait or fault creates no false sample: accepted input and the
completed prefix remain explicit evidence and are not replayed automatically.

Checkpoints retain logical owner activity, held keys and accepted-edge counters.
A staged fresh owner verifies the saved state and adopts a fresh process token
and epoch without injecting key edges or executing the guest. Layers, hooks,
RNG, timer phase and framebuffer remain part of the same full restore. A pending
`FX0A` retains its PC and waiting state after key input. Only explicit resumption
permits the instruction to consume that key; a timer sample can precede the next
instruction. Key `0` is valid. A blocked wait with no available key cannot be
credited as a completed sample.

The JSON routes remain `debug-frame-inputs`, `debug-keyboard-state` and
`debug-timeline-*`; saved scripts use `frame-inputs`, `keyboard.state` and the
corresponding timeline operations with backend `qemu-chip8`. The adapter only
advertises `frame_key_ownership` on v6. Earlier runtimes refuse the capability
before input effects. Full checkpoints and PNGs remain the storage model; this
extension does not add CHIP-8 deltas, selected undo, trials, IRQ/task-private
semantics or completed guest-frame/VBlank timing.

## Local checks

```sh
FDISBULL_CHIP8_QEMU=/external/build/qemu-system-chip8 \
FDISBULL_CHIP8_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8=1 \
python -m pytest -q tests/test_chip8.py tests/test_chip8_project.py \
  tests/test_qemu_chip8.py tests/test_qemu_chip8_native.py \
  tests/test_chip8_qemu_semantics_native.py
```

For the device extension, run the additional local witnesses with an explicit
device binary; keep the retained CPU-only binary selected for its older tests.

```sh
FDISBULL_CHIP8_DEVICES_QEMU=/external/devices/qemu-system-chip8 \
FDISBULL_CHIP8_DEVICES_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8_DEVICES=1 \
python -m pytest -q tests/test_chip8_devices_dispatch.py \
  tests/test_qemu_chip8_devices.py tests/test_qemu_chip8_devices_native.py \
  tests/test_chip8_devices_semantics_native.py
```

Tests use authored microprograms and independent expected states. The static
classifier comparison is labelled separately from executed native cases.
For the complete classic extension, additionally select its separate binary:

```sh
FDISBULL_CHIP8_CLASSIC_QEMU=/external/classic/qemu-system-chip8 \
FDISBULL_CHIP8_CLASSIC_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8_CLASSIC=1 \
python -m pytest -q tests/test_qemu_chip8_classic.py \
  tests/test_qemu_chip8_classic_native.py tests/test_chip8_classic_semantics_native.py
```

For native RAM/fetch layers and paused execution hooks, use the v4 binary:

```sh
FDISBULL_CHIP8_LAYERS_QEMU=/external/layers/qemu-system-chip8 \
FDISBULL_CHIP8_LAYERS_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8_LAYERS=1 \
python -m pytest -q tests/test_chip8_layers_project.py tests/test_chip8_layers.py \
  tests/test_chip8_hooks.py tests/test_chip8_layers_native.py \
  tests/test_chip8_history.py tests/test_chip8_history_native.py \
  tests/test_chip8_history_public.py
```

For v4 checkpoint-backed histories, select that same layers runtime:

```sh
FDISBULL_CHIP8_HISTORY_QEMU=/external/layers/qemu-system-chip8 \
FDISBULL_CHIP8_HISTORY_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8_HISTORY=1 \
python -m pytest -q tests/test_chip8_history.py \
  tests/test_chip8_history_public.py tests/test_chip8_history_native.py
```

For v5 native 60 Hz sample histories, select the separate frames runtime:

```sh
FDISBULL_CHIP8_FRAMES_QEMU=/external/frames/qemu-system-chip8 \
FDISBULL_CHIP8_FRAMES_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8_FRAMES=1 \
python -m pytest -q tests/test_chip8_frames.py tests/test_chip8_frames_native.py
```

Native tests require the actual binary when their `FDISBULL_REQUIRE_CHIP8*` selector is 1; an
optional skipped run is not acceptance evidence. No CI or default switch is
part of this slice.

V6 frame-key checks require their own explicit runtime selection:

```sh
FDISBULL_CHIP8_FRAME_KEYS_QEMU=/external/frame-keys/qemu-system-chip8 \
FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG=/path/to/qemu-img \
FDISBULL_REQUIRE_CHIP8_FRAME_KEYS=1 \
python -m pytest -q tests/test_chip8_frame_keys.py \
  tests/test_chip8_frame_keys_public.py tests/test_chip8_frame_keys_native.py
```
