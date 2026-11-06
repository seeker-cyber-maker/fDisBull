# Research and qualification

## Documentation first

This example follows the bundled `fdisbull-investigate` skill's
[reconstruction recipe](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d193dad26837985cd1a05556e6b7a2ab226385f5/src/fdisbull/skills/fdisbull-investigate/references/reconstruction.md)
and [research checkpoint](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d193dad26837985cd1a05556e6b7a2ab226385f5/src/fdisbull/skills/fdisbull-investigate/references/recovery-research.md).
The rule contract was written from the supplied edition's help before the
Python implementation. [RULES.md](RULES.md) records mathematical predicates,
distinguishing examples and source anchors; the original help remains private.

The supplied Sherlock 7 shareware archive contains
`Sherlock7 SHAR.app/Contents/Resources/HELP/HLP_English.txt`. The help's SHA-256 is
`790a48aef5c547a896023517b5ae93a9680e57e5d272616eeaf657790b4adab9`.
Line references in RULES.md use that UTF-8 file's original line numbering.
This identity establishes which document was consulted, not publisher
authenticity, runtime correspondence or redistribution permission. The source
title and its documentation are attributed to Everett Kaser and the authors
identified in the owner's supplied files. Only authored semantic descriptions
are included here; no original manual, executable, media or puzzle table is
part of this example.

## Prior work and edition boundaries

The earlier [native C example](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d193dad26837985cd1a05556e6b7a2ab226385f5/examples/recovery/sherlock_native/README.md) and its
[JavaScript companion](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d193dad26837985cd1a05556e6b7a2ab226385f5/examples/recovery/sherlock_native/web/README.md), contributed through
[GitLab MR !97](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/97)
at source revision `d193dad26837985cd1a05556e6b7a2ab226385f5`, concern the owner's
Sherlock **1.50 UK/DOS** reconstruction. They supply prior authored common
semantics and constraint-solving approaches. Sherlock 7's three-image negative
vertical clue and exclusive same-column OR were researched in this edition's
help before being added to the new model.
Their finite C-to-JavaScript comparisons and original observations retain
their documented boundaries. Those receipts do not qualify this Python
implementation or establish correspondence with Sherlock 7.

Watson was an earlier conceptual lead, pinned in the project research to
`koro-xx/Watson` commit `7b20d4725d5d1599e9681679e060528504d596df`.
The prior work also studied Bombe's hint-support ideas, as recorded in the
skill's research checkpoint. These are sources of questions about clues,
deductions and explanation support. No Watson or Bombe code or assets were
imported into this example, and neither program was executed for this slice.

This Python model uses the Sherlock 7 help to define its supported clue
semantics and dimensions. Its generated puzzles, identifiers, solver and
benchmark protocol are authored additions. A generated puzzle is not an
original numbered puzzle, and a uniqueness certificate does not assign the
original Type A or Type B difficulty classification.

## Qualification ledger

| Edge or claim | Evidence and current boundary |
| --- | --- |
| Sherlock 7 documentation to rule contract | Source-attributed paraphrase with exact clue predicates and counterexamples. |
| Live Sherlock 7 to rule contract | **Unqualified:** no matched original-runtime observations were collected for this slice. |
| Rule contract to Python | The independent test oracle enumerates all 216 legal 3×3 boards for each of nine clue forms, plus mixed constraints and generated cases; its separate predicates matched the implementation in this contribution's local checks. This research note defines the scope; the contribution handoff records the exact tested revision. |
| Earlier C/JavaScript to Python | Earlier receipts are useful context; they establish no new implementation parity here. |
| Complete Sherlock 7 replica | Unqualified: generation identity, native sessions, original scoring, UI, media and timing are outside this headless rule contract. |

Independent checks should enumerate small row permutations and evaluate
predicates without calling the implementation's solver or relation helper.
Include satisfiable, contradictory and ambiguous puzzles, malformed answers,
budget exhaustion, and a deliberately wrong Not Between predicate. A finite
match qualifies the tested model boundary only. Keep inconclusive search
distinct from unsatisfiability and uniqueness.

## Research mechanics as they appear

Repeat a bounded documentation pass whenever a newly encountered mechanic
leaves a material implementation choice unresolved. Use this record:

1. Name the concept and competing interpretations.
2. Pin the edition and primary source, including an anchor or revision.
3. Write the mathematical predicate or transition contract.
4. Give a small example that separates the alternatives.
5. Record the actual qualification: documentation, static inspection, finite
   model comparison or original-runtime observation.

For example, Not Between still constrains the outer items to distance two;
negating the entire Between predicate loses that requirement. Similarly,
uniqueness, single-clue solvability and explainable hint support are separate
properties. Related games can suggest candidate mechanisms, but the selected
edition's evidence decides the contract. Revisit the record when a
counterexample appears; additional genre research is useful when it changes
the next implementation decision.
