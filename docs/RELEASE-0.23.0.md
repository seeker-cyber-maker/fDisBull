# fDisBull 0.23.0

The 0.23.0 source adds an original-backed DOS UDC target, bounded ASM/C-to-UIL
readers and a layer-by-layer testing protocol. It also refreshes the human
landing page, portable agent guides and bundled investigation skill.

This file records source finalization. Ordinary and native Linux CI must pass
on the exact commit before tagging. Tag verification, release publication and
system installation are separate steps; their status is not inferred here.

The first compiler definition reconstructs original MZ/COM files from stored
immutable blocks and explicit resources. It accepts shared UIL over its UDL
backing, checks source/definition identities, and refuses unqualified changes.
The original static version is preserved alongside caller patch versions.
This is the baseline for a future generic DOS compiler; generated DOS lowering
is not implemented. See [UDC](UDC_DOS.md) and [the testing protocol](UDC_TESTING.md).

An authored interactive COM was assembled with LLVM, captured as blocks and
emitted through both ASM-derived UIL and a bounded C-view route. The three
native runs observed the same declared score effect. Z3 establishes the
register-boundary relation under explicit assumptions and finds a deliberate
wrong candidate. Original/emitted DinoPark and Zork runs also matched their
declared native observations; their preserved game blocks have no recovered
semantic coverage. See [verification](VERIFICATION-0.23.md).

The [README](../README.md) now presents capabilities and modes for people.
[AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md) and the
[agent quickstart](AGENT_QUICKSTART.md) route agents to actual entry points,
backend requirements and the appropriate evidence contract. The investigation
skill retains cost/reward/confidence prioritization and adds progressive
workflow and UDL/UIL/UDC references. `agent-skill --reference FILE` retrieves
one bundled resource; the existing full export remains available. Source
archives require the portable onboarding files, and wheels require all skill
references. Testing-agent testimony remains a future contribution, not an
invented endorsement in this release.

PR17's fixture gates now remain active under `python -O`. Source archives
include exactly its nine authored fixture files and the three sanitized UDC
receipts. Historical observations remain unchanged; modified checker code has
a separate fresh receipt. The larger compiler-learning RFC remains a draft.

Game and story files, native states, project databases and raw game captures
remain private. Local verification results and their limitations are recorded
explicitly; exact-commit CI is the release gate.
