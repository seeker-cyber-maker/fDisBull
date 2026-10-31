# Additional executable scaffolds: bounded verification

The local engine branch `codex/mz-zmachine-scaffolds` extends the standard DOS
compiler candidate with an MZ output scaffold and a separate source-backed
Z-machine v3 target. Its base is PR #54 correction commit
`5556f8181be656b29db6297913ae9ae0a82cd859`. No release, tag, main merge or system
installation update is part of this work. The new scaffold changes have not
been attributed to the base PR's Linux results.

## Prerequisite CI correction

PR #54's original head `d2225d5` failed one stale scene test: its exact resource
set omitted the newly published `references/block-orchestration.md`. Ordinary
and both native profiles reported that same node; the inspected native logs
showed no compiler or backend test failure. The unified dependent job was
skipped, so those workflows were not green.

The isolated correction updated only that expected set, preserving the exact
catalog assertion. The parent reran 84 affected checks successfully and pushed
`5556f81` to the existing PR. Its
[ordinary Linux run 41147057303](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41147057303)
passed. The corresponding
[native run 41147057312](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41147057312)
was still queued at the recorded snapshot; no completed native CI claim is made
for that correction or for these local extensions.

## New MZ container

`udc-dos-compile --container mz` wraps the already checked COM-source layout in
a new resident MZ executable. It emits a header, fixed allocation/stack contract
and one DOS-loader segment relocation. The startup sequence preserves AX, flags
and SP while initializing DS/ES; near code/data port IPs remain unchanged.
Output file offsets and the container/layout identities are recorded separately.
This is not an arbitrary MZ-source relinker, overlay writer or general DOS ABI.

An independent header test loads the output at segments 1000h and 2345h and
checks the relocated word, entry, stack/allocation, port identity and file
offsets. The native acceptance test runs three generated MZ files in separate
DOSBox processes:

| Selected implementation | Observed result |
| --- | --- |
| Retained default blocks | 17 |
| Longer implementation with the declared AX projection | 17 |
| Intentionally changed experiment | 34 |

Each native run checks startup at 00F7h and 0100h, unchanged AX/flags/SP across
the scaffold, DS=ES=SS=CS, and the actual loader-relocated word. It then checks
the ready-loop's taken and untaken paths, result registers/memory, repaired near
pointer and independently read `A3 82 01` store bytes. It stops before HLT and
does not execute indirect dispatch. Processes are reaped.

## Z-machine story scaffold

The new projectless capture/compile APIs retain a checksum-qualified entire v3
source and a bounded initial fallthrough catalog. Baseline output is byte
identical. An experiment must identify whole expected-old instructions; only
small scalar constants in admitted same-size arithmetic/logical encodings can
change. Opcode, variable selectors, store target and control destinations stay
fixed. Checksum repair, source/definition digest validation and re-decoding are
required. Alias and scalar-not-address assertions remain caller obligations.

An independent review reproduced a JSON-integrity defect where Python equality
treated version `3.0` as `3`. A regression now requires rejection; canonical
definition digest validation runs before deterministic source recapture. Source
hex and edit hex are bounded before allocation/decoding.

The authored source, exact baseline and scalar experiment were executed in an
independent Frotz interpreter. They printed exactly `17\n`, `17\n` and `34\n`,
respectively, with exit code zero, empty stderr and no timeout. The source and
interpreter bytes remained unchanged. Frotz was built privately with `make dumb`
from [official upstream commit 042d7bc](https://gitlab.com/DavidGriffith/frotz/-/tree/042d7bcadc1e2a8090cf737c841d8b7fc14b6eff);
its local executable SHA-256 was
`98dca470a01536c06fa1f6843542bbfee929ba7609ed29dc63caec04f911e80f`.
Nothing was installed. Native Linux configuration now pins that same source and
runs the authored gate when the new configuration is exercised; that is a gate
definition, not an already completed Linux result.

The legacy DOS Zork interpreter is a separate observation. An unchanged private
retail copy reached “West of House” and a stable prompt. Authored variants were
mapped into that interpreter but did not display their expected values within
the attempted host budgets. Their requested 10,000 guest milliseconds were not
completed: approximately 1,649–1,719 guest milliseconds elapsed before five-second
host deadlines. Failed attempts and traces were preserved privately. Neither
compatibility nor incompatibility with that interpreter is established by those
attempts; the successful Frotz result does not substitute for it.

## Actual game inputs and integrated checks

Private source controls retained Eternam's 110,888-byte MZ file exactly through
the existing original-layout native UDC, and Zork I's 92,160-byte v3 story
exactly through the new story baseline. Their respective SHA-256 identities were
`1ed9504e918da578465b227fec06fd9d13fe3ffc4a0f99dbc7fee46cb9062cbc` and
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.
The Zork catalog stopped after its first control transfer; no original-game
scalar edit or whole-game equivalence was claimed.

The final integrated affected selection passed **321 tests, zero failures,
errors or skips**, using genuine Python 3.13.17, the compatible ARM64 DOSBox
backend and the private Frotz executable. It covered backing/layout/native UDC,
COM and MZ compilation/CLI/native tests, Z-machine processor/analysis/scaffold
and Frotz checks, scenes, skills and distribution guards. The four existing COM
native sessions, three MZ sessions and three Frotz invocations are included in
that count, not additional pytest cases. A projectless large-capture test also
forces artifact-backed delivery and retrieves the source identity without
expanding the story. All 19 frozen candidate paths matched their before/after
hashes. Skill syntax and workflow YAML checks also passed.

Original game/story files, emitted binaries, runtime states, project databases,
interpreter builds, screenshots and raw traces stayed in private workspaces.
Candidate files contain authored source, fixtures and this sanitized record.
No AGI, NE/Win16, LE/extender or PE writer is inferred from these two scaffolds;
those require their own qualified loader/runtime and interface contracts.
