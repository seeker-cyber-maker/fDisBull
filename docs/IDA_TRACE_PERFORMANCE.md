# Bounded IDA trace collection — 2026-10-25

The optional IDA PE64 adapter now collects a bounded instruction trace inside
its Linux controller, using one host request. It preserves fresh instruction
reads, pre-instruction integer registers, explicit RAM-layer identity, project
address mapping and offline trace exports. This is unreleased source work; the
published 0.13.0 packages and existing deliveries are unchanged.

## Measured result

The accepted replay compared two collectors in the **same IDA session**, then
compared the existing custom Wine backend in a separate identically configured
QEMU guest. Both engines used the same authored PE fixture, guest CPU/memory
configuration and guarded NOP/NOP/JMP loop. Each 96-instruction sample returned
to its own starting PC with all general registers and arithmetic/direction flags
unchanged. Every recorded address and instruction byte was checked.

| Trace path | Mean for 96 instructions | Samples | Host requests per trace |
| --- | ---: | ---: | ---: |
| IDA with the host collection reference | 5.800 s | 2 | 385 |
| IDA with Linux batch collection | **2.485 s** | 2 | **1** |
| Existing custom Wine backend with host collection | 3.585 s | 2 | 385 |

The IDA collector change was **2.33× faster** on this workload. The optimized
IDA path used **30.7% less time** than the existing Wine path, or **1.44×** its
throughput. An additional 24-instruction pair took 1.335 s for host collection
and 0.648 s for Linux collection. Collector order alternated for the longer
samples to reduce a simple warm-up bias.

These are small, finite measurements on one fixture, without a statistical
confidence claim. They exclude boot, Wine-prefix initialization, launch and
initial breakpoint placement. They measure runtime trace collection, not
static disassembly. The unbatched IDA path was slower than the existing Wine
path; the observed improvement comes from batching and avoiding repeated work.
It does not establish that the IDA engine is intrinsically faster, or that the
optimized path wins on arbitrary games, thread patterns or trace sizes.

Raw measurements, instruction traces, screenshots and the arithmetic are in
[`experimental/remote-debugger/evidence/2026-10-25-speed/`](../experimental/remote-debugger/evidence/2026-10-25-speed/).
`comparison.json` contains exact times and ratios; each backend's
`benchmark.json` records input hashes and observations.

## Behavior retained

The Linux controller reads code on every fetch; it does not reuse a previous
instruction's bytes. It reuses the observed post-step integer registers as the
next pre-step snapshot. Peer threads are held for the bounded batch and
released on exit. A newly started peer is held before its event is continued.
Only completed native STEP events become trace instructions. Faults and other
stops end collection; a native step that cannot finish within its budget closes
the connection rather than claiming a safely paused CPU.

The accepted real IDA replay also:

- Reached a disassembly breakpoint at the authored fixture's checkpoint.
- Restored the temporary RAM layer's original bytes before the breakpoint test.
- Traced two prologue instructions, stopped before the requested NOP and
  retained the actual native STEP event with `single-step-boundary` origin.
- Resumed exactly one instruction from that breakpoint.
- Returned an incomplete, zero-instruction timeout trace for a 1 ms budget and
  verified that the CPU remained stopped at the same PC.
- Saved a real 320×200 screenshot with an 8px grid, closed the session, reopened
  the project and exported its stored artifacts. The owned QEMU process exited.

A host budget can expire before the batch is sent. The returned trace then
records a stopped timeout while a subsequent status query retains the previous
native stop. That preserves the distinction between a collection deadline and
an observed CPU event.

The source limits remain 10,000 instructions and 600,000 ms. Cleanup,
serialization and transport can extend elapsed host time beyond that budget.
The batch collector falls back to the host path if an execution interception
or watchpoint context is present. This does not add qualification for IDA PE
native states, data watches or execution-only layers; those operations retain
the explicit limits in [the adapter documentation](IDA_REMOTE.md).

## Replay

Use [`examples/synthetic/benchmark_ida_trace.py`](../examples/synthetic/benchmark_ida_trace.py)
with an authored `tests/wine_gui_fixture.c` executable compiled privately with
MinGW at `-O0`. It expects the exported checkpoint prologue and guarded
`experiment_value` bytes; it does not accept an arbitrary game as a benchmark
substitute. Keep the compiled EXE and all output directories outside Git.

Prepare separate matching IDA and ordinary Wine runtimes from the same base,
using `python -m fdisbull.ida_runtime` and `python -m fdisbull.wine_runtime`.
Then run:

```bash
python examples/synthetic/benchmark_ida_trace.py \
  --qemu "$FDISBULL_PE_QEMU" --kernel "$FDISBULL_PE_KERNEL" \
  --initramfs "$FDISBULL_IDA_INITRAMFS" \
  --remote-server "$FDISBULL_IDA_SERVER" \
  --fixture "$FDISBULL_PE_FIXTURE" --output /private/ida-benchmark

python examples/synthetic/benchmark_ida_trace.py --backend wine-qemu \
  --qemu "$FDISBULL_PE_QEMU" --kernel "$FDISBULL_PE_KERNEL" \
  --initramfs "$FDISBULL_PE_INITRAMFS" \
  --fixture "$FDISBULL_PE_FIXTURE" --output /private/wine-benchmark
```

Output directories must be new. The private project databases contain the
fixture bytes and runtime evidence; only selected JSON/PNG evidence is suitable
for the repository. Tool archives exclude examples and experimental evidence.
The vendor server, Linux/Wine images, native states and project databases are
never package members.

Two preliminary benchmark attempts are retained with explicit failure names.
The first correctly hit the static-breakpoint guard when the probe requested a
breakpoint inside its modified loop. The second completed both collectors and
the real breakpoint/resume test but used an incorrect status assertion after a
host deadline. The final probe checks the returned timeout trace and stopped
PC and passes through artifact export. Preliminary attempts are not acceptance
passes.

## Fresh verification of this source

| Check | Result |
| --- | --- |
| Full ordinary Linux suite, `python -m pytest -q` with cache writes disabled | **809 passed, 38 skipped**, 509.92 s |
| Configured real IDA/Wine/QEMU feature gate | **4 passed**, no skip, 209.68 s |
| Combined native DOSBox, wire, collector, layer/grid, package and PE preflight checks | **98 passed, 4 unconfigured PE native tests skipped** |
| Focused tests imported from the built wheel, not the editable source | **40 passed, 1 unconfigured IDA native test skipped** |
| Accepted IDA and Wine trace probes | Both passed through offline exports |

All 135 Python source, test and build-script files in the full Linux snapshot
matched the current files. Documentation was completed after that snapshot.
The four skipped PE tests in the combined run are not an additional native
acceptance claim; the configured IDA gate above was run separately. Native
thread creation and selected-thread exit handling have focused contract tests;
this does not qualify arbitrary Windows threading or exception behavior.

The local wheel, source archive and tool ZIP were built for resource/exclusion
checks only. They are unreleased development artifacts with the unchanged
0.13.0 package version. The archive audit requires the new trace collector and
SDK notice and excludes game files, native states, databases, vendor servers
and runtime images. This work has not been committed, pushed, tagged or
published; these local results are not GitHub CI. See `verification.json` in
the evidence directory for source hashes, test reports and archive checksums.
