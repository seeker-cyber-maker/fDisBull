# QEMU translated instruction context evidence

This packet records a bounded native trace extension for the exact QEMU
candidate below. The parity item remains **unqualified**; DOSBox-X remains the
default backend. No CI, release, installation, or broad-suite claim is made.

## Exact candidate and local results

- QEMU candidate SHA-256: `6f969d1bbe8f8e4398412bcd3ee24e88984f2e6be869267450b0bb5523bcc641`
- Native QEMU patch SHA-256: `3dc2ecb6c2cacd3ed1d179eb4a06552064f2510e81deeb9534f25dbf96829fd1`
- Paired authored self-modifying COM witness: **1 passed** on this candidate.
- Combined host/native selection: **38 passed, 0 failures, 0 skips** in 22.27 seconds.
- Private JUnit receipt SHA-256: `b4446f88da27b95c8d4424e5cf15df36ed4dcb9fba7fccd383642c47413671ce`.

The combined selection is the stated local gate only. The broad full suite was
not rerun on this v2 candidate.
The two original paired loop cases also passed against the frozen v1 binary
after the host adapter change, preserving the older trace schema's unknown
byte/context behavior. The private v1 compatibility receipt is hash-bound in
[verification.json](verification.json).

## Authored COM witness

The test fixture is the authored COM byte sequence
`b9020040c606030143e2f8ebfe`. It starts with `INC AX` at `0103h`, then writes
`43h` to that code address, so the second visit translates `INC BX`. Both
engines observed the ordered PCs
`0100, 0103, 0104, 0109, 0103, 0104, 0109, 010B` and stopped at the final
breakpoint boundary. The stopped guest memory contains the modified `43h`.
The DOSBox-X side is used for PC order and stopped-memory comparison; this
packet makes no per-event DOSBox byte claim.

For QEMU's seven TCG dispatch events, the trace retained translation-bound
instruction bytes. At `0103h` the first translated byte is `40h` and the later
translation is `43h`. The breakpoint-pre-dispatch event at `010Bh` explicitly
reports bytes unavailable because no translated instruction callback ran.
The witness also checks 16-bit code width and the observed CS selector/base.

These bytes are copied from translation metadata after the translated block's
final size is known. They are not a reread of guest memory at each runtime
event and do not establish canonical source identity. The 16-bit context is a
bounded x86 code-context observation; it does not qualify other CPU modes.
Instruction completion and retirement remain unknown.

## Corrected capture boundary and remaining scope

The initial v2 byte capture sampled at `translator_st` before the translated
block size was final, which left multi-byte instructions incomplete. The
candidate used for the result copies bytes at `plugin_gen_tb_end`, after the
final size is available. The earlier implementation result is not promoted to
the v2 evidence claim.

The final candidate rejects parallel TCG before trace state changes. A paused
VM with one active vCPU and `max_cpus=2` received the explicit `CF_PARALLEL`
refusal and remained alive. This closes the asynchronous TB-flush path before
the previous translation payload slab is released. Parallel TCG trace capture
is outside this candidate's supported scope.

Fault and partial-REP semantics, interrupt/timer policy, overlays, source
departures beyond the admitted COM/MZ or explicit embedded-LE views, checkpoint
restoration, live producer-epoch invalidation, canonical source identity,
broader CPU-mode coverage, and full DOSBox byte parity remain open. No event
claims execution completion or retirement.

The machine-readable counts and claims are in
[verification.json](verification.json). The paired source is
`tests/test_qemu_dos_before_fetch_trace_native.py`; the host contract tests are
`tests/test_qemu_fetch_trace.py`.
