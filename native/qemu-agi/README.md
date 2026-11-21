# Optional AGI observations in QEMU

This experimental target runs a bounded AGI scalar/position instruction subset
through QEMU TCG and selectively records information for a disassembler or scene
tool. It is a separate `qemu-system-agi` executable built from clean QEMU
**10.0.13**. It does not change either product's normal backend selection.

The experiment asks whether useful source-linked observations can be selected
without charging every instruction for unused channels. Its native execution
tests and benchmark use authored raw bytecode; a full AGI game engine, resource
loader, renderer, scene editor and original-format resource writer are separate
work.

## Observation control

`agi-observation-mask` is a host-owned two-bit control register. It is separate
from the 256 AGI variables and 256 AGI flags.

| Value | Selection | Records |
| --- | --- | --- |
| `0` | Off, the default | None; generated TCG has no observation-helper calls |
| `1` | `DISASM` | Completed instructions, original code location/bytes, actual successor |
| `2` | `SCENE` | Committed actor-position changes with before/after state and their instruction location |
| `3` | Both | The same two channels, with completion before scene change |

The mask is part of the target's translation-block identity. Translation emits
observation helpers only for selected instructions. Different masks can retain
separate cached versions of the same instruction; a stopped mode change selects
the matching version. The pilot uses one instruction per block with no direct
block chaining. Restart preserves the immutable code and cached blocks, allowing
the same locations to be tested under repeated mode changes.

Observations append to bounded fixed-size storage. A full buffer drops newly
eligible records, increments explicit total and per-channel counters, and lets
execution continue. It does not overwrite the retained prefix. Every eligible
record receives a sequence number, including dropped records. With one slot
left in both mode, a completion may be retained and its scene record dropped;
the channel counters expose that loss.

Observation helpers do not allocate memory, format JSON, write files or call a
UI. Original source bytes and JSON are resolved when the stopped host reads the
records. Disabled observation is therefore different from enabled observation
whose buffer is full. Reserved buffer memory and cached mode variants still
exist; this is not a claim of zero total memory or control cost.

## Input and semantic limits

The machine accepts `-kernel` containing **raw LOGIC code bytes**, starting at
code-relative PC zero. It does not accept a complete LOGIC resource, its
two-byte code-length prefix, compressed resources or game archives. Source
identity is the SHA-256 and size of those exact raw bytes, with logic ID zero
and profile `agi-2917-scalar-position-pilot-1`.

The profile covers scalar actions 1–8, direct flag set/reset/toggle (12–14),
root return, signed GOTO, scalar IF conditions (1–7), actor positioning (37/38)
and `get.posn` (39). Conditions allow AND, OR and NOT, bounded to eight predicates
and 64 encoded bytes. Repeated NOT markers, unclosed/empty OR groups and
unsupported predicates fault explicitly. Its 16 actors start at zero.
Positioning updates `x`, `y`, `prev_x` and `prev_y` without viewport clamping.
An unchanged position produces no scene-change record. Calls,
animation cycles, parser predicates, resource access and engine effects are
outside this profile. Unsupported or malformed instructions stop with an
explicit fault; they never appear as completed instructions.

The target's ordinary execution bookkeeping remains enabled in all modes:
instruction budgets, stop/fault handling and native timing are part of the
pilot. Its absolute throughput is not a measurement of a fully optimized AGI
engine, and TCG JIT execution is not standalone C export or UDC qualification.

## Build the isolated target

Use a new source/build workspace and prepared local dependencies. This recipe
does not download, install, publish, dispatch CI or rebuild another backend.
The upstream archive identity used by this experiment is:

```text
qemu-10.0.13.tar.xz
141718608 bytes
sha256 4a59b74dac7ead8b162a7c4595dcbbeebe989b90c89cfe6bb4dec5447342f6fa
```

Extract it safely. The archive contains the known external symlink
`roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack` pointing at `/opt/X11/include`;
exclude that link. No EDK2 rebuild is needed. Keep temporary files and caches on
the admitted build filesystem. Check free storage and memory before extraction
and compilation; two compiler jobs are sufficient for the bounded experiment.

Apply the overlay to the clean source (use `--check` for a read-only preflight):

```sh
python native/qemu-agi/apply_overlay.py /path/to/qemu-10.0.13
```

Then configure a separate build
directory with an explicit compiler, Python, Ninja and dependency discovery
environment. The minimal target configuration is:

```sh
/path/to/qemu-10.0.13/configure \
  --target-list=agi-softmmu --without-default-features \
  --enable-system --enable-tcg --enable-pixman \
  --disable-user --disable-tools --disable-docs --disable-guest-agent \
  --disable-containers --disable-download --disable-install-blobs \
  --disable-debug-info --disable-qom-cast-debug --disable-rust \
  --audio-drv-list=
ninja -j2 qemu-system-agi
```

The upstream archive contains the Meson and pycotap wheels needed by QEMU's
private configuration environment. An offline build can use those with
`PIP_NO_INDEX=1`. Compiler and library identities, configuration, source overlay,
failed attempts and final binary hash belong in the build receipt. A successful
local experiment is separate from release/native parity qualification.

## Stopped QOM interface

Launch with one CPU and QMP on standard input/output:

```sh
qemu-system-agi -M agi-test -accel tcg,thread=single \
  -kernel authored-code.agi -S -display none -serial none -monitor none \
  -nodefaults -no-user-config -qmp stdio
```

Negotiate `qmp_capabilities` and discover the CPU's `qom-path` through
`query-cpus-fast`. Use standard `qom-get` and `qom-set` on that CPU. Control and
state operations require a stopped VM.

| Property | Purpose |
| --- | --- |
| `agi-observation-mask` | Select bits `DISASM=1` and `SCENE=2`; reject other bits |
| `agi-observation-capacity` | Bound retained records, from 0 through 65,536 |
| `agi-step-budget` | Bound the next execution interval, from 1 through 1,000,000,000 instructions |
| `agi-restart` | Write `true` to reset guest/run/observation state while preserving code, controls and cached translations |
| `agi-observation-clear` | Write `true` to clear observations and advance the trace epoch without changing guest state |
| `agi-state-json` | Read source identity, authoritative guest state, observation counters and last-run timing |
| `agi-events-json` | Read the retained records without consuming them |

Capacity may grow while retaining the existing prefix. Shrinking below the
number of retained records is rejected; clear the observations first if needed.
Return and fault remain sticky across `cont`; such a resume executes no new
instruction and reports a zero-work interval. Restart explicitly begins the
program again.

The state schema is `fdisbull-agi-native-state-1`. `guest` contains the complete
architectural state of this profile. `observation` contains mask, capacity,
retained/eligible/dropped counts, per-channel counts, helper calls, control
generation and epoch. `run` contains the last execution interval's instruction
count, native elapsed nanoseconds and invocation identity. Events use
`fdisbull-agi-native-events-1`, with source identity and epoch outside the record
array. Records carry their generation, PC, opcode, exact bytes, actual successor
and retired-instruction ordinal. Scene records add actor ID and before/after
position fields.

Example using the included owned-process harness:

```python
from harness import QemuAGI

# assignn(v1, 10); assignn(v2, 20); position.v(0, v1, v2); return
code = bytes([3, 1, 10, 3, 2, 20, 38, 0, 1, 2, 0])
with QemuAGI('/path/to/qemu-system-agi', code) as vm:
    vm.configure(mask=2, capacity=16, step_budget=100)
    state = vm.run()
    events = vm.events()
```

`harness.py` launches only an explicitly supplied binary, uses owned QMP
standard-input/output pipes, enforces finite read/write waits and reaps its
child. Stderr is reserved for diagnostics. An optional `transport='unix'`
uses a private Unix socket on hosts that permit it. Native timing in the
target excludes QMP formatting/transport. The harness reports host time for
`cont`, waiting and stop confirmation separately; that host interval excludes
the final state JSON read and any event download.

## Verify and measure

Run the native tests with an explicit binary. An unset environment variable
causes a visible skip; a specified invalid runtime fails.

```sh
FDISBULL_QEMU_AGI=/path/to/qemu-system-agi \
  python -m pytest -q tests/test_qemu_agi_observation.py
python native/qemu-agi/benchmark.py \
  --binary /path/to/qemu-system-agi \
  --output /private/evidence/agi-observation-benchmark.json
python native/qemu-agi/inspect_tcg.py \
  --binary /path/to/qemu-system-agi \
  --output /private/evidence/agi-observation-tcg
```

The benchmark uses three authored loops: scalar-only, sparse actor positioning
and dense actor positioning. It warms each mode's translations, interleaves
mode order, executes the same fixed instruction budget and compares the complete
guest state after every run. Its default 65,536-record buffer is sufficient for
32,768 instructions even when both channels qualify. It records native and
host timings, raw repetitions, event counts, drops and helper calls; summaries
include medians, percentile ranges and paired changes against OFF.

A separate readout phase measures stopped validation, native event JSON
formatting, QMP transport and host parsing. It records the unescaped event JSON
size and readout wall time. These measurements happen after the native timing
samples, so large journal transfers do not contaminate those execution samples.
Native elapsed is a monotonic wall interval, including host descheduling; it is
not isolated thread CPU time. Warmups remove first-translation cost from the
reported execution samples.

First translation order can also affect the placement of generated code. Use
`--warmup-order 2 3 0 1` in a fresh process for a counterbalanced comparison with
the default `0 1 2 3`, and retain both reports. Measured run order remains
interleaved independently. A negative paired timing change does not establish
that observation has a negative marginal cost: these small loops include
dispatch and execute separately placed code variants.

Use a new output path for each attempt. A separate saturation experiment may
use `--capacity 0 --allow-drops`; do not present its dropped-event timing as the
cost of retaining a useful journal. Generated TCG inspection with `-d op` is a
separate check from timing, because logging itself changes execution cost.

## Product use

For DotBox, scene-only observation can support a small source-linked actor model
while the harness becomes usable; full disassembly can be enabled for the next
specific question. For fDisBull, both channels can supply execution witnesses
for program recovery, subject to explicit loss/coverage and source identity.
Neither product may interpret missing observations as evidence that an effect
did not occur when that channel was disabled or records were dropped.

The products keep separate orchestration and acceptance policies. This pilot
does not qualify original-DOS QEMU parity, change DOSBox-X fallback policy or
deliver a complete scene-authoring workflow.

See [source provenance](PROVENANCE.md) for upstream/scaffold identities and
licensing, and `source-manifest.json` for the native input inventory.
