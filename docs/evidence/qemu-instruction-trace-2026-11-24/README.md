# QEMU bounded before-fetch trace evidence

This evidence records the current bounded QEMU trace slice and its remaining
qualification boundary. The paired guest is an authored COM loop; no private
boot image, emulator state, or runtime output is included.

## Verified candidate results

The final plugin-enabled QEMU 10.0.13 executable has SHA-256
`105a9ecbd5f2d52a63da4f68608df6fbba2cf79b9a07f1d2a7c2c1d868059c58`:

- Paired DOSBox-X/QEMU before-fetch cases: 2/2 passed on the exact executable.
- Native regression selection: 5/5 passed on the same executable.
- Combined host and native batch: 30 passed, no skips, in 19.49 seconds.
- Plugin-enabled x86 system build: native owner reported pass; root verified the final executable hash.

The final QAPI comment rebuild left the executable hash unchanged. The combined
batch was rerun after that rebuild. The private JUnit receipt and its hash are
recorded in [verification.json](verification.json).

An independent review found that a running-guest `trace.stop` rejection closed
the VM. The host now checks for a stopped guest before native dispatch, leaves
the capture active on that precondition failure, and permits a later stop. The
reviewed combined batch includes this regression test.

## Breakpoint-boundary correction

The initial breakpoint comparison produced seven QEMU trace events against
eight DOSBox-X events. The missing record was the GDB breakpoint PC: a TCG
instruction callback does not run for an instruction stopped before translated
block dispatch. The native candidate added a separate breakpoint-pre-dispatch
record before `EXCP_DEBUG`, tagged `origin=breakpoint-pre-dispatch`. Normal
translated instruction observations use `origin=tcg-dispatch`.

The paired authored COM case expects the ordered PCs
`0100, 0103, 0104, 0103, 0104, 0103, 0104, 0106`. The last PC is the breakpoint
boundary. The breakpoint record and TCG callback are distinct observation
origins; the extra event does not claim an additional completed instruction.
The final paired rerun also checked seven `tcg-dispatch` origins followed by
one `breakpoint-pre-dispatch`; the count-three case had only `tcg-dispatch`.

## Wider local test result

An unconfigured full macOS run finished with 18,075 passed, 11 failed, 23 setup
errors, and 1,250 skipped. Nine failed cases passed on a focused rerun with
`PYTHONPATH=src:tests`. The remaining two failures and 23 setup errors use
Linux ELF compiler/linker fixtures through macOS `/usr/bin/gcc`. This run is
not a green full-suite gate and does not alter trace or overall parity status.

## Scope and limitations

The native ring provides bounded sequence, vCPU, guest-virtual PC, reason, and
origin fields. The current event schema omits per-event instruction bytes, CPU
mode, segment selector/base, and canonical source identity. The host keeps the
PC in virtual address space and preserves both origins. Instruction completion
and retirement remain unknown for every event.

The paired test independently reads the unchanged authored COM bytes from each
stopped guest. That confirms the test input and does not turn the trace records
into byte, source, or instruction-retirement evidence. Faults, partial REP,
interrupt and timer differences, overlays, broader source departures, and full
DOSBox parity remain open. DOSBox-X remains the default backend.

Source checks are in `tests/test_qemu_dos_before_fetch_trace_native.py`; host
cursor and loss-bound checks are in `tests/test_qemu_fetch_trace.py`.
