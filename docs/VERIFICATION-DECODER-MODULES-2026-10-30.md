# Direct decoder modules: bounded verification

2026-10-30. This is an engine-development candidate and a separate PR against
main `f94a5cd74b153b58f56c9fdb6c653d2e295f5ee6`, not a release or installation.

## Implemented and checked

- Explicit trusted-object module registration, pinned module/processor
  descriptors, finite bounded metadata, immutable built-in byte snapshots and
  separate source-occurrence keys. Duplicate registration, descriptor drift,
  malformed metadata, inconsistent program hashes and foreign entry spaces are
  refused. Captured bindings reject metadata-only or coordinated code/hash
  changes with an inherited lifter. This is an API consistency guard; trusted
  module code is not sandboxed. There is no input-controlled Python import.
- Projectless AGI v2 resource and raw Z-machine v3 openers, using their existing
  processors. Static traversal preserves source spaces, exact instruction bytes
  and supplied edges. Unknowns, bad spans/targets, overlaps and exhausted budgets
  keep coverage incomplete; a closed static cycle is not termination evidence.
- Direct AGI `assignn`/flag `set`/`reset` to existing UDL/UIL primitives, with an
  explicit final logic-return boundary and exact typed initial-state witness.
  The source resource is revalidated before lifting. Neither native ASM nor a
  native project is used. A subprocess with Python `-S` also completed this
  CLI lift with no site-packages available; no decoder substitutes were used.
- Independent authored expected states cover 512 byte/flag initial-state cases,
  all 256 encoded immediate constants, repeated ordered writes, separate
  variable/flag namespaces and boundary indices. Reversing repeated writes
  changes the observed result. Unsupported control flow/opcodes, truncated or
  trailing code, stale source metadata and missing/wrong-width witnesses refuse
  qualification. These are scalar state-projection tests, not AGI engine parity.

The nominal scalar semantics were cross-checked against ScummVM's AGI
[command implementation](https://github.com/scummvm/scummvm/blob/master/engines/agi/op_cmd.cpp).
Game-specific workarounds and other runtime side effects are outside this model.

## Private original-resource checks

The private PQ1 and KQ1 copies remained outside the repository. Every present
LOGDIR reference passed volume-number, resource-header and declared/code bounds
checks: PQ1 had 118 present entries out of 120; KQ1 had 90 out of 105. Absent
sentinel entries were retained as absent, rather than reported as malformed.

The new module directly opened logic 0 in each copy under the explicitly
selected `2.917` subset profile. Each produced 13 decoded candidate instructions
before unsupported paths stopped traversal. **Both results were incomplete.**
The facts matched the existing partial AGI inspector, and reopening the captured
input produced the same readback. This is a regression check, not an independent
oracle for every instruction. All source container hashes remained unchanged.
No native game executable, database, DOSBox or game runtime was opened.

This validates resource input and bounded static decoding. It does not confirm
either target's interpreter revision, complete logic/scene recovery, a source
lift of these entire resources, or original-game execution. Raw instruction
outputs, resource hashes and local paths stay in private receipts; no original
resource bytes are added to the PR.

## Local checks

Genuine CPython 3.13.17 on macOS ARM64, existing private development environment:

```text
python -m pytest -q -p no:cacheprovider \
  tests/test_decoder_modules.py tests/test_agi.py tests/test_agi_lift.py \
  tests/test_agi_layout.py tests/test_agi_picture.py tests/test_processor.py \
  tests/test_zmachine_processor.py tests/test_zmachine_processor_acceptance.py \
  tests/test_zmachine_analysis.py tests/test_interaction_il.py \
  tests/test_agent_skill_gate.py tests/test_agent_discovery.py \
  tests/test_distribution.py tests/test_language_cli.py

241 passed, 1 skipped
```

The skip requires a case-sensitive filesystem for a duplicate-case VOL fixture.
The bundled skill's frontmatter validator also passed. The source skill gate
checks selective retrieval and its references in the test set above. Linux CI
is a separate PR gate; local checks do not stand in for it. No tag, release,
system update or runtime compatibility claim is part of this change.
