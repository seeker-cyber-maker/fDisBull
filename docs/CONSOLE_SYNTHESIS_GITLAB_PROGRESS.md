# Console synthesis: progress and GitLab handoff

**Revision in progress. Repository inspection and publication test: 1 November 2026.**

This handoff preserves the [first-party synthesis plan](CONSOLE_RECOMPILER_INTEGRATION_PLAN.md)
and [acceptance protocol](CONSOLE_RECOMPILER_ACCEPTANCE.md) from GitHub PR #79,
revision `7dd9a5013bd33edb1d7baae7a1377a3b12f22155`. It documents later local
implementation and route-audit work without claiming new runtime qualification.

## Repository progress

The inspected GitLab main is `a6ac7ac7f60fc97bc1bf69db7368ff07ff27301e` in
`brewster-jennings-group/fdisbull` (project 88349936). All six files under
`src/fdisbull/console_synthesis` have the same Git blob identities as the source
in the delivered `First_Party_Console_Synthesis.zip`: `__init__.py`, `compare.py`,
`mapping.py`, `model.py`, `recover.py` and `targets.py`. This is a fresh source
identity check, not a fresh execution against current-main dependencies.

The imported branch `pr/79/console-recompiler-integration-20261031` still points
to the research revision. No MR for that branch existed at inspection, and the
integration-plan document was absent from the inspected main. This new branch
preserves that history. It does not rewrite the imported branch, duplicate the
already integrated implementation or change main.

## Implemented slice and prior evidence

The October 31 delivery implements immutable source backings, logical bindings,
bounded 6502 recovery, existing shared UDL/UIL documents, exact backing retention,
C and JavaScript realizations, bank/context selection, stale-selection rejection
and first-divergence reporting. It does not wrap the surveyed recompilers.

Historical validation: 80 focused tests; 56 encoding/decoder checks; 393,216
arithmetic cases under each of three compiler configurations (1,179,648 total
comparisons, not triple input coverage); 768 JavaScript/evaluator comparisons;
and three symbolic checks. Those results used the supplied 0.26.0 wheel and
the delivered overlay. They are not new GitLab CI results. No original console
CPU or physical console ran in that local pilot. Other agents' later console
results do not retroactively qualify this pilot's missing edges.

## Route audit and next work

The attached audit records the October 31 local delivery, not all of current main.

| Route | Observed local status | Missing connection |
| --- | --- | --- |
| Selected 6502 bytes -> shared UDL/UIL -> C -> host | Implemented bounded route; one fresh case matched | Independent original-CPU check and broader profiles |
| Selected x86-16 bytes -> C statements -> UIL | Exact shared-document round trip for a narrow arithmetic example | General functions, memory, branches, flags and ABI |
| ROM -> C -> UIL | Not a connected general route | Binary-to-C provider and compatible typed C frontend |
| ROM -> C -> compiled ASM -> UIL | C emitted x86-64 assembly; no return lift connected | Target-aware lifting and composed qualification |
| ROM -> ASM -> C | Supported fragments only | Broader discovery, control flow and device behavior |

The proposed next adapter should reuse Ghidra rather than create another general
decompiler. Keep these experiments distinct:

```
Ghidra raw/analyzed p-code -> supported UDL/UIL mapping
Ghidra C -> typed C frontend -> supported UDL/UIL mapping
Ghidra C -> compiled object -> Ghidra p-code -> supported UDL/UIL mapping
```

These connections have not been executed by this handoff. Preserve original
executable UDL, source mappings, numeric widths, effect ordering and unresolved
operations. P-code is an optional analysis representation, not an exact-byte
archive or automatically recovered game intent. The C path must consume C,
not relabel a parallel p-code path. Two paths using the same processor model
share assumptions. Do not restart scaffolds or make C mandatory for all UIL.

## Browser and file-delivery test

The requested side-browser returned an error requiring the originating browser
context and connected extension. No browser navigation or drag-and-drop upload
succeeded. Direct GitLab access is available, but the exposed upload action only
downloads existing uploads; it does not create new Markdown attachments.

The fallback under test is a repository file linked from the MR, not a GitLab
`/uploads/` attachment. The first combined binary commit failed with an unexpected
EOF and left no branch behind. Text and a small binary probe are therefore tested
separately. Final server readback and actual outcomes belong in the MR note.

The small probe contains only authored Markdown, no game content or credentials.
The historical route audit contains authored code/UIL, compiler-output text and
scoped observations. Original ROMs, game assets, private states and byte-retaining
databases must remain outside Git. Larger runtime deliveries must not be committed
merely to bypass the absence of an upload facility.

## Agent publication procedure

Read project guidance and existing work; commit reviewable changes to a branch;
create/update a draft MR; link evidence at an immutable commit; verify file size
and content identity after publication; report access failures accurately.
This removes manual copying for supported repository-file delivery. It does not
establish a general browser attachment uploader or an unbounded binary channel.

No tests, benchmarks or source-CPU runs were performed for this publication
change. Hosted CI was not requested; any automatic pipeline is separate. No
merge, release, account-setting change or shared installation is part of this MR.
