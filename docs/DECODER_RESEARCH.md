# Decoder research and SNO integration

Research checked 2026-10-22. The working addition is a bounded, read-only comparison of iced-x86 and Capstone. CPU fuzzing and an x86 superoptimizer adapter are future work; no generated instruction was executed for this investigation.

## Research lineage

| Work | Verified attribution and scope | Consequence for fDisBull |
|---|---|---|
| Sandsifter / Breaking the x86 Instruction Set | Christopher Domas, Battelle; Black Hat USA 2017. The repository identifies its Battelle origin. | Compare decoder predictions with independent evidence; retain instruction-length disagreements. |
| REcon 2015 M/o/Vfuscator; REcon 2016 Movfuscator-Be-Gone | Domas's obfuscating compiler, followed by Kirsch and Jonischkeit's recovery work. | Valid instructions can hide program structure; ordinary frame signatures and direct-branch traversal are incomplete. |
| Rosenbridge / God Mode Unlocked, 2018 | Domas's separate, processor-specific research. The project limits the affected scope to VIA C3 and says later generations lack the feature. | A result on one historical processor family cannot become a universal x86-64 decoding rule. |

The verified Sandsifter release venue is Black Hat 2017. The primary REcon pages found concern the related compiler/recovery work; this investigation did not establish a REcon Sandsifter presentation. Battelle's official July 2017 announcement independently confirms its involvement.

Sandsifter measures actual instruction-fetch length and exception behavior, including observations in 64-bit mode. Its 2017 paper reports an Intel/AMD difference involving operand-size-prefixed relative calls/jumps. These are historical, scoped observations, not a substitute for current vendor documentation and measurements. A disagreement in a present decoder can also reflect extension support, reserved encodings, formatting or mode selection.

## Working software comparison

`fdisbull.decoder_check.compare_decoders(data, bits, address=0, arch='x86', scan_offsets=False, max_candidates=16)` consumes at most 4,096 bytes and compares one start, or at most fifteen starts at offsets 0 through 14. Each decoder receives at most fifteen bytes per start. It records exact bytes, mode, address, package/runtime versions, validity, consumed size and its original text.

Results distinguish validity disagreement, length disagreement and text difference. Text differences include harmless syntax and mnemonic aliases; they are not equivalence results. Default decoder policies are recorded rather than claiming a selected CPU model. ARM64 is rejected because iced does not provide an independent ARM decoder.

The function executes no input bytes and changes no project facts. Offset alternatives are unconfirmed proposals: agreement does not prove code, and disagreement does not prove an undocumented instruction. The focused suite has 15 passing cases, including a real difference for `0f0dc0` under the pinned libraries and a separate formatting-only example. This observation says nothing about execution on a CPU.

For a later hardware evidence importer, record vendor, family/model/stepping, microcode, CPUID features, execution mode, privilege, OS, hypervisor/translation layer, exact bytes and initial state. Preserve measured length, fault, register/flag/memory effects and timeout separately from decoder expectations. A Rosetta, emulator or VM result describes that environment; it is not bare-metal evidence about an Intel/AMD chip. A container does not make CPU-hang experiments safe. Hardware fuzzing needs a separate dedicated-host plan.

## Reusing SNO's proposal mechanism

The current accessible repository is [SNO–QP2A Neural Superoptimizer](https://github.com/seeker-cyber-maker/sno-qp2a-neural-superoptimizer). Its current README and Gamer-Codex method keep candidate proposal separate from exact verification; the learned SNO arm is parked. The cross-integration design already describes finite instruction/operand grammars and counterexample-guided survivor reduction. Those are useful mechanisms to adapt. The inspected debugger source is a bounded QP2A machine, not an x86 semantics implementation.

Two different products should remain explicit:

- **Interpretation proposals:** original bytes stay fixed; vary a proposed start, execution mode or representation and collect evidence. The decoder comparison supplies this surface now.
- **Replacement proposals:** generate different byte sequences intended to match an original block. This requires a new x86 grammar/encoder and a semantic validator before accepting a replacement. It is a future SNO adapter, not a capability established by QP2A results.

A useful first adapter would synthesize small straight-line blocks with declared live-in/live-out registers, allowed opcodes, memory footprint, byte/instruction bounds and CPU profile. Rank candidates, reject counterexamples cheaply, and retain survivors for independent validation. Test-set success is provisional. Equivalence must account for defined flags, partial-register effects, stack/ABI obligations, memory aliasing, control flow and exceptions under stated preconditions. Undefined behavior must not silently become an equality requirement or permission to change observable behavior. Unsupported semantics mean unknown.

[STOKE](https://github.com/StanfordPL/stoke) supplies a relevant x86-64 precedent: proposal search and verification are distinct, with explicit live-outs and bounded/formal strategies. Its own README calls it a research prototype, reports instruction/validator limitations and says the code base is not actively developed. It is research material to evaluate, not a ready universal validator. Accepted replacements would become explicit child byte versions; representation changes continue to preserve the original bytes.

## Primary sources and inspected provenance

- [Sandsifter repository](https://github.com/xoreaxeaxeax/sandsifter) and [2017 paper](https://www.blackhat.com/docs/us-17/thursday/us-17-Domas-Breaking-The-x86-Instruction-Set-wp.pdf).
- [Battelle's July 13, 2017 announcement](https://inside.battelle.org/blog-details/addressing-hardware-cybersecurity); [Black Hat 2017 program](https://blackhat.com/us-17/briefings.html#breaking-the-x86-instruction-set).
- [REcon 2015 M/o/Vfuscator](https://recon.cx/2015/schedule/events/55.html); [REcon 2016 Movfuscator-Be-Gone](https://recon.cx/2016/talks/%22Movfuscator-Be-Gone.html).
- [Rosenbridge project](https://github.com/xoreaxeaxeax/rosenbridge).
- [Intel architecture manuals](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html), [iced](https://github.com/icedland/iced), [Capstone](https://www.capstone-engine.org/), [STOKE](https://github.com/StanfordPL/stoke).
- Current SNO `main` files read through the connected repository: [README.md](https://github.com/seeker-cyber-maker/sno-qp2a-neural-superoptimizer/blob/main/README.md) (blob `37e234ee9eb391d52d2dcf6995d2ebb12028c0c7`), [GAMER_CODEX_METHOD.md](https://github.com/seeker-cyber-maker/sno-qp2a-neural-superoptimizer/blob/main/GAMER_CODEX_METHOD.md) (`18637cdfecef0a6d112498179e0cd03c2f2febe0`), [cross-integration design](https://github.com/seeker-cyber-maker/sno-qp2a-neural-superoptimizer/blob/main/COMPLETE_UNIVERSE_ORACLE_CROSS_INTEGRATION.md) (`2b5e2e1c5fa1ffc10d52fab865a077cb572479e2`), and [debugger source](https://github.com/seeker-cyber-maker/sno-qp2a-neural-superoptimizer/blob/main/scripts/qp2a_model_debugger.py) (`4f35b5ce6c5b9335286ef03494cbd6bdd88af3ca`). These identify the inspected files, not a new qualification of that project.
