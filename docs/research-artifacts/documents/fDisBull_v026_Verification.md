# fDisBull v0.26.0: sandbox installation and focused verification

## Installed baseline

The supplied Linux x86-64 offline kit is installed in a new isolated sandbox virtual environment. Core and player distribution versions are both **0.26.0**, using the kit's pinned dependencies and bundled DOSBox backend. No system-wide or user-machine installation was modified.

Source commit: `8ba24d62b5010d3a6a5d604524aad72e2e047b77`.

Archive SHA-256: `035146ade72ba0a125e765234c988446809298546073428d1b1e9ab605f4931c`.

The uploaded archive's digest and size match the published v0.26.0 GitHub release asset. All **18 internal SHA-256 checks passed**; installation used `--no-index` and required dependency hashes. The manifest identifies a paired source-companion archive that was not supplied/downloaded. This did not block the installation or these checks.

## Checks executed in this session

| Check | Result and scope |
| --- | --- |
| Installation and Z3 sanity | Passed; equivalent and counterexample cases checked. |
| Native DOSBox doctor | **13/13 passed**, including a real authored guest, breakpoint, execution overlay, screenshot, coordinate click, data watch, bounded trace, save/restore, temporal interpretation, and restart/export. |
| Handler-split fixture, using installed v0.26 evaluator | **4,096 input-state cases** across five paths, **6,656 block comparisons**, **16 negative controls**, both **512-byte** native reconstructions exact. |
| Prior delivered fixture regression | **10/10 selected native images, UDL/UIL documents and JavaScript outputs byte-identical**. |
| Packaged production DOS UDC | Authored COM reconstruction exact, including after project reopen. `add 200; decrement` admitted as equivalent to `add 199`; `add 198` rejected. Unsupported memory and branch lifts refused. |
| C -> JavaScript -> C fixture | **65,536 byte pairs**, **52 invalid-input/arity checks**, and missing-wrap negative control passed. External plumbing fixture, independent of fDisBull. |
| Contract witness models | **16/16 passed**; Python-only models, not a production optimizer or reverse compiler. |

## Relevance to our pipeline

The tagged release notes describe original-backed provider recovery improvements, a bounded Z-machine v3 inspection processor, more precise after-access watchpoint semantics, and a consolidated definitions roadmap. Generic native PE64 generation and media-service backends remain implementation work.

Direct comparison of the supplied old 0.22 kit and this 0.26 kit shows:

- `interaction_il.py` and `proofs.py` are byte-identical.
- `udl_blocks.py`, `udc.py` and `il_scenes.py` exist in 0.26 but not that 0.22 wheel. This is a baseline comparison, not a claim that they first appeared in 0.26; the source-backed DOS target is documented as earlier 0.23 work.
- The experimental branching/JavaScript fixture remains compatible, but its adapters are still external to the production compiler.
- The production original-backed UDC retains a narrow straight-line register-equivalence scope. The branch/memory rejection controls confirm that boundary.

Watchpoint records now explicitly describe registers as **after-access**, with instruction completion unknown. A REP instruction may still have work left. An observed access must not be treated as a completed semantic operation.

## Scope

This is installation and focused compatibility qualification, not a full release audit. No full repository suite or new commercial-game playthrough was run, and no PR was modified. Original game archives and earlier packages were preserved.

The next relevant engineering slice is the intended **16-bit source -> executable UDL/UIL -> regenerated x64 code and modern service bindings in a PE32+ program**. Version 0.26 is the installed sandbox baseline; this intake does not claim that port is implemented.

## Evidence and references

The evidence ZIP contains fresh receipts, selected logs, module/source identities, and the authored production-UDC smoke script. It excludes installed wheels, native binaries, games, project databases and screenshots.

- Release: https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.26.0
- Source notes: https://github.com/seeker-cyber-maker/fDisBull/blob/8ba24d62b5010d3a6a5d604524aad72e2e047b77/docs/RELEASE-0.26.0.md
- Installed skill: `fdisbull agent-skill --reference SKILL.md` and `references/udl-uil-udc.md`.
