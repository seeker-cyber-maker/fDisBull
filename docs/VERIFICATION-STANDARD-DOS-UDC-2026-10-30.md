# Standard DOS UDC engine verification

This record separates the published-source CI result from the new local
compiler candidate. No release, tag or system installation update is part of
this engine task.

## Exact-commit Linux CI

Commit `f94a5cd74b153b58f56c9fdb6c653d2e295f5ee6` passed both push workflows:

- [Tests and tool packages, run 41135976947](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41135976947): success.
- [Native debugger acceptance, run 41135977084](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41135977084): success.

All three native jobs completed successfully: stable DOS backend, layers DOS
backend, and the installed-wheel unified DOS/boot/PE64 job. Both required-native
DOS test steps passed. The layers job passed genuine-Z3 offline-kit
verification; that step was intentionally matrix-skipped for stable. The
dependent job passed the real PE64 watches/layers/native-state checks and the
DOS-in-QEMU/boot-context acceptance. No CI failure required a repair or rerun.

These results apply to **f94a5cd**, not the later standard compiler candidate.
Small CI evidence identities were inspected separately from package payloads;
this task did not publish or deliver packages.

## New local engine target

The candidate on `codex/standard-dos-udc` adds a bounded COM16/i386 target:

- Immutable standard compiler definitions tied to the retained native UDL
  source, logical block plan, declared fixed data and typed references.
- Independently versioned, variable-size straight-line implementations with
  expected block-revision guards and explicit successor ports.
- A generated headerless COM image with a neutral entry jump, separate code
  placement, fixed data offsets, near branch widening, typed MOV-immediate and
  near-pointer-table repairs, and independent final target decoding.
- Explicit experiment versus narrowly proved register-projection status. The
  artifact itself remains `structural_only`; compilation never claims native
  execution or whole-program equivalence.
- Python, JSON and CLI entry points, a scoped agent reference and the
  [standard target contract](STANDARD_DOS_UDC.md).

The [original-layout native pass-through](NATIVE_UDL_UDC.md) stays unchanged as
the exact-byte baseline. No physical byte insertion is performed by logical
block splitting.

## Reference and profile hardening

Adversarial review reproduced and closed the following gaps:

1. A known caller outside a captured graph could be omitted. The standard COM
   target now refuses those edges. Reverse incoming inventory covers **every
   captured instruction**, including interior joins, using bounded batched
   lookups. Budget exhaustion or unresolved target context remains incomplete.
2. Stored MOV pointer evidence could be ignored if the caller omitted its
   relocation declaration. A matching native-field typed fixup is now required.
   Fixed memory/address evidence must also agree with decoded fields and data.
3. A pointer learned after capture could leave a stale capsule apparently
   valid. Validation now compares semantic operand reference facts as well as
   source bytes and control edges; label-only changes remain presentation.
4. A register projection proved before immediate rewriting could misdescribe
   emitted values. Source/candidate immediate fixups are excluded from this
   narrow proof profile, and proofs are rechecked on readback and compilation.
5. The real-mode target could otherwise admit privileged mode/control-state
   operations. Those instructions are refused except explicit terminal HLT;
   MOV CR0 and LMSW regressions are static and were never executed in a guest.

Multiple captured roots require an explicit boot entry. Unknown/far/call
transfers, unsupported replacement ports, collisions, stale expected bytes,
overlapping fixups, bad field widths and escaped data remain refused.

## Fresh local checks

The frozen 17-file source/test/workflow/document cut has SHA-256
`c00d282f011e0f1b205157b61143a6722581f0c2a8b7e0d20166e10896b8068c`,
computed over the canonical file-record list. All recorded files matched
before and after the full run. The environment used genuine Python 3.13.17,
iced-x86 1.21.0, Capstone 5.0.9, LIEF 1.0.0 and Z3 5.3.2 on macOS ARM64.

| Check | Result |
| --- | --- |
| Four standard DOS compiler test files | **47 passed**, zero skipped/failures. |
| Eight overlap/backing/native-UDC test files | **74 passed**, zero skipped/failures. |
| Native standard compiler fixture | **One test, four isolated DOSBox runs passed**, with a separate required-native receipt. |
| Full frozen-source suite | **2,238 passed, two failed, 23 errors, 21 skipped** out of 2,284; exit 1. |

The focused counts are subsets of the full run and are not added to it.
The 25 failed/error node IDs exactly match the prior f94 Mac run and the
unchanged installed baseline. They are Linux ELF fixture/compiler-linker
assumptions encountering Apple clang/Mach-O on this host. There were no new
problem nodes. The 21 prerequisite skips remain skips. This is **not** a green
full-suite claim on macOS; the exact-source Linux CI result above is separate.

## Authored native behavior

The native fixture uses a declared ready byte, a CMP/JE spin loop, an AX
calculation, a word store, a near-pointer table and a final HLT instruction.
The compatible Mac DOSBox backend SHA-256 was
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
The source and three generated variants ran in separate private projects:

| Program | Selected implementation | Observed result word |
| --- | --- | --- |
| Authored source | Original | 17 |
| Generated COM | Default retained blocks | 17 |
| Generated COM | Longer MOV AX,17; MOV AX,17 body | 17 |
| Generated COM | Experiment: MOV AX,34 | 34 |

All runs observed the ready=0 taken loop, released ready once, then observed
the untaken loop edge and the declared pre-HLT breakpoint. AX, flags and
result memory were read independently. The repaired pointer-table word was
checked against the placed store port, and actual guest bytes at its target
were checked as `A3 82 01`. No indirect dispatch or executed-HLT completion is
claimed. A separate structural test forces a continuation beyond short-branch
range and re-decodes the widened target.

The register-equivalence proof covers the declared AX projection only. Flags,
memory, control flow, ABI, timing and partial effects are excluded from that
model; the native observations are separate evidence for the authored states.
The deliberately changed experiment stays unverified rather than acquiring
the source-equivalence label.

## Program composition guidance and PR follow-up

The investigation skill now routes to a focused
[block orchestration reference](../src/fdisbull/skills/fdisbull-investigate/references/block-orchestration.md).
It treats behavior, implementation, adapter, port and layout identities
separately. Before placement, qualify inline versus callable boundaries,
calling conventions, stack ownership, register/flag preservation, memory and
ordered effects, language semantics, runtime initialization and error exits.
Plan only the required adapters; an already compiled C function owns its frame.
Then size the graph, place it, repair typed references and qualify adjacent
boundaries and the composed result. General adapters remain methodology rather
than a capability of the current call-free COM target.

After this guidance and its catalog entry were added:

- **97 engine cases passed**, zero failures/errors/skips, across
  `test_code_backings`, `test_code_layout`, `test_native_udc`,
  `test_native_udc_cli` and the four `test_dos_udc*` files. This fresh selection
  includes the four real native runs described above; it is a different
  selection from the earlier focused run.
- **83 skill/distribution cases passed**, including source API discovery,
  selective reference retrieval, local-link validation and rejection of an
  archive missing the new reference. The skill-creator syntax validator passed
  using an existing genuine Python/PyYAML environment. The new reference is
  indexed and covered by the existing package-data pattern and archive guard.
- A fresh Luna evaluation followed the skill routes for an inline-to-C
  interface and an incompatible 32-bit implementation. It identified the
  necessary argument/flags/DF/cleanup obligations, avoided a duplicate C
  prologue, and correctly refused to claim that the current compiler emits
  calls or CPU-mode bridges. No C adapter or cross-mode native run was claimed.

The compiler sources still match the frozen full-suite cut. Removing only the
new catalog line from `cli.py` reproduces that cut's exact CLI hash; the other
changes since it are skill guidance, resource packaging checks and this record.
The earlier full-suite counts are retained as evidence for that compiler cut,
not relabeled as a fresh full run of the PR. New Linux results must be checked
on the PR's exact commit.

## Scope and exclusions

The target has no MZ writer, general DOS extender/compiler, call/far adapters,
automatic UIL lowering or exhaustive hidden-pointer discovery. Data stays at
declared fixed IPs; register-addressed memory needs a specific caller-domain
assertion. Registering source pointer replacement interfaces beyond the
supported profile remains further work. Passing these authored checks does
not establish original-game compatibility or whole-game recovery.

All runtime programs, generated COM files, project databases, state artifacts
and raw logs stayed in private workspaces outside Git. Candidate source files
contain authored fixture builders and sanitized evidence only. No original
game/story files, saved states or private databases are included.
