# fDisBull 0.16.0

The standalone DOS follow-up adds [bounded saved-script observation waits](OBSERVATION_WAIT.md)
and [DOS analysis knowledge](DOS_KNOWLEDGE.md): 182 licensed, provenance-bound
runtime signatures; OMF extraction and reusable project signature catalogs;
37 explicit DOS/BIOS service descriptions; enums/flags, unions, bitfields,
aliases and declared function types with near/far Pascal profiles. These do
not require an IDA installation. The [local acceptance record](VERIFICATION-DOS-KNOWLEDGE.md) and sealed receipts distinguish tested source from GitHub release qualification.

This candidate implements the three next recommendations after saved
experiments: [explicit temporal code interpretations](RUNTIME_CODE.md),
[shared observation semantics](DEBUGGER_SEMANTICS.md), and a
[real runtime doctor](RUNTIME_DOCTOR.md).

Qualified code captures can become preserved child interpretations, with fresh
analysis/xrefs/CFG and visible provenance, without fabricating a replacement
EXE. Trace views compare actual bytes and address context against those
interpretations. Native stop/completion differences remain explicit. The doctor
uses authored targets and exports machine-readable evidence without retaining
private states or databases. Wine images must be rebuilt for the newly checked
self-test source.

Comparison hardening rejects unequal capture counts and mismatched identities
before pairing trial observations. The regression was reproduced with malformed
helper input; it was not demonstrated in a supported native game route. Existing
observed trace-count differences and incomplete-trial handling are retained.

Reverse execution, deterministic record/replay, whole-program execution proofs,
reconstructed patched disk images, typed kernel object inspection and DTrace
providers remain outside this scope. Release promotion requires both exact-commit Linux workflows to pass before tagging; publication is a separate step.
Ordinary and native Linux GitHub CI must pass on the eventual release commit
before tagging. Game files, native states, databases, VM images and compiled
target fixtures stay out of Git and tool distributions.
