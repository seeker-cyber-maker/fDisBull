# CPU semantics and measured cost profiles — November 4, 2026

Review of [Theo's discussion with Casey Muratori](https://www.youtube.com/watch?v=jC_z1vL1OCI),
published January 17, 2025. Acquisition retrieved metadata and automatic English
captions, not audio or video. Caption timing covers the 12,001-second duration;
all packet hashes verify. The review indexed that full transcript and examined
the sections relevant to fDisBull. Automatic captions remain noisy evidence.

## Selected source observations

| Video time | Topic paraphrased from the captions |
| --- | --- |
| [18:45](https://youtu.be/jC_z1vL1OCI?t=1125) | Instruction decoding and internal micro-operations are distinct. |
| [36:34](https://youtu.be/jC_z1vL1OCI?t=2194) | An instruction encoding can compactly describe work expanded inside a CPU. |
| [56:26](https://youtu.be/jC_z1vL1OCI?t=3386) | Latency and throughput answer different performance questions. |
| [1:40:34](https://youtu.be/jC_z1vL1OCI?t=6034) | Cross-ISA emulation also encounters memory-ordering and flags differences. |
| [2:06:50](https://youtu.be/jC_z1vL1OCI?t=7610) | Branch prediction uses observed runtime patterns. |

These are discussion claims, not a new hardware qualification. The speaker
qualifies some vendor-specific examples; this review does not promote those
examples to current processor specifications.

## Primary-source corroboration

Arm describes the ISA as a hardware/software interface and distinguishes it
from its implementation in a microarchitecture. That supports keeping semantic
contracts separate from implementation details. [Arm ISA definition](https://www.arm.com/glossary/isa).

The uops.info researchers measure latency, throughput and port usage across
microarchitectures, including operand dependencies. Their machine-readable
results are potential cost-model inputs, not equivalence proofs or guaranteed
end-to-end application costs. [Paper](https://arxiv.org/abs/1810.04610),
[measurement table](https://uops.info/table_overview.html).

Intel also maintains architecture references separately from processor-specific
optimization and latency/throughput resources. [Intel optimization resources](https://www.intel.com/content/www/us/en/developer/articles/technical/intel64-and-ia32-architectures-optimization.html).

## Recommended applications to this project

The following are project recommendations inferred from those distinctions,
not features implemented by this contribution.

1. **Keep UIL's semantic contract stable.** UDL should preserve original-code
   evidence and map effects into UIL; a UDC supplies a realization. Hardware
   micro-ops should remain optional analysis facts rather than become UIL's
   universal instruction set. Widths, flags, exceptional outcomes, memory and
   device effects belong in the explicit contract where behavior needs them.

2. **Make optimization winners contextual.** Preserve each candidate lowering
   and its correctness evidence. Attach a separate measured profile keyed by
   target ISA, CPU when known, backend/runtime, compiler/options, workload and
   source identities. This makes the user's learning/selection idea reviewable:
   a faster candidate wins for a qualified context while other realizations
   remain available. Instruction count alone should not select a winner.

3. **Benchmark whole Z actions and individual stages.** Track one-action
   latency, batch throughput, memory, startup and shutdown separately. Keep
   guest time distinct from host wall time. For screenshots, measure acquisition,
   wire transfer, validation, decode, persistence and recognition separately,
   then retain the complete-call result. This extends the existing indexed-PNG
   experiment without assuming a CPU-level optimization fixes protocol cost.

4. **Require effects and commit evidence before cost comparison.** For example,
   compare two bank implementations only after guards, cash/debt effects and
   exceptional outcomes agree. Include boundary and held-out states rather than
   only frequent successful paths. Shutdown is a useful counterexample: reaping
   a native process cannot substitute for a successful guest-stop receipt.

5. **Use profiles to prioritize analysis, preserving cold unknowns.** Dynamic
   frequency can guide the next probe or optimization. It cannot establish that
   an unhit function or asset is unused. Standing selective breakpoints and the
   unresolved DinoPark inventory retain their existing evidentiary boundaries.

A useful next RFC addition is therefore a cost-profile attachment to an existing
UDC qualification: semantic identity, lowering identity, input/workload identity,
environment identity, correctness receipt and measured metrics. It would allow
Rust, JavaScript, Python, original-code passthrough and later backends to compete
on comparable evidence without changing UDL/UIL terminology.

## Evidence scope

The private caption packet is under
`/Volumes/CACHE/fDisBull-scene-indexed-20261103/video-jC_z1vL1OCI-20261104/`.
Normalized transcript SHA-256:
`d8073752889eb69a9dee62a70bd7e39202678b0123c5ddcb861804bc0e0334d7`.
Raw captions and the complete transcript stay outside Git. This source note
contains selected paraphrases, primary-source links and authored recommendations.
It does not alter a compiler definition, assert cycle accuracy, or qualify a
new reconstruction backend.
