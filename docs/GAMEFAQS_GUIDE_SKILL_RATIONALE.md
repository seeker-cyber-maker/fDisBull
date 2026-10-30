# Why the game-guide skill has these requirements

Research date: **2026-10-29**. The implemented companion skill is
[`write-gamefaqs-guide`](../src/fdisbull/skills/write-gamefaqs-guide/SKILL.md).
Its purpose is a human-readable review of established game knowledge, including
partial walkthroughs and technical mechanics where the evidence supports them.
It consumes investigation findings and preserves their limitations.

This extends the investigation-skill work in PR #27 at
`0fcd3999ba403d21b2fd305a33d948d5c048b18a`. It preserves that skill's evidence,
readiness, partial-effect, source/IR and original-game qualification boundaries.
It adds authoring guidance and projectless discovery; it does not implement an
automatic solution extractor or validate a shipped game's completion route.

## Source-to-requirement decisions

The packaged [source examples](../src/fdisbull/skills/write-gamefaqs-guide/references/source-examples.md)
contain ten annotated exemplars, with authors, revisions, links, access modes,
scope limits and requirement IDs R01-R08. They distinguish official material,
historical guidance, observed practice and our design decisions.

| Source or observation | Decision in the skill | Implemented location |
| --- | --- | --- |
| Contributor Central's separate text and HTML workflows (S01) | Default to Markdown for repository review; treat any actual site submission as a separate format/authorization task. | `guide-structure.md`, render formats |
| Historical staff description of 80-column text (S02) | Offer an optional 79-column text target; report actual width/encoding checks without claiming site acceptance. | `guide-structure.md`, text export |
| Adventure walkthrough navigation and local warnings (S03-S05) | Use searchable sections, exact interaction vocabulary, prerequisites, observable outcomes and warnings before consequential actions. | `guide-structure.md`, consequential steps |
| FFIV/FFII/FFVI technical FAQs (S06-S08) | Preserve numerical semantics, release scope, uncertainty, research credit and substantive corrections. | `technical-mechanics.md`; `evidence-and-provenance.md` |
| Earlier generated routes, score ledgers and run-log template (S09) | Retain useful organization and reusable verification fields. | `guide-structure.md`; `evidence-and-provenance.md`, routes |
| Completeness headings exceeding displayed material (S09) | Require scope and denominators; distinguish a selection, strategy overview, supported route and full catalogue. | `evidence-and-provenance.md`, coverage |
| Exact-looking original-code claims without inspectable derivation (S09) | Distinguish implementation listings by provenance and preserve learned/compared/recovered lineage. | `technical-mechanics.md`, code and models |
| Differences between an earlier guide and pinned OpenDUNE (S09-S10) | Require target and field correspondence; keep mismatches unresolved where original inputs are unavailable. | `evidence-and-provenance.md`, source ports |

The technical FFIV example is **Deathlike2's Algorithm FAQ, v1.51**; it is a
strong candidate for the user's recollection, not a confirmed identification.
The older Ben Siron FAQ provides a second plausible historical reference. We
sampled their presentation and evidence practices rather than verifying every
mechanics assertion they contain.

Some help/editor endpoints were inaccessible. Consequently this work does not
claim a comprehensive current GameFAQs submission specification or invent an
AI-specific acceptance rule. The primary-source entry page and historical staff
post support the particular format distinctions recorded in the source catalogue.

## What the previous AI experiment contributes

Reviewed repository:
[`seeker-cyber-maker/ai-generated-game-walkthroughs`](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/tree/3af2bc50f922d5923ed7c8643492b649ac4734d6),
pinned to `3af2bc50f922d5923ed7c8643492b649ac4734d6`.
Samples included Dune II, Police Quest I and Gobliiins, plus the repository's
formatting, sources and run-log documents. The repository was read, not changed.

### Retain the useful presentation

Command-first steps, location/item checklists, score checkpoints, search tags,
reference appendices and correction history make technical findings usable.
The [run-log template](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/templates/run-log.md)
also offers a compact route-verification record. These motivate the new skill's
reader-facing organization and optional evidence appendix.

The sampled Dune II, Police Quest I and Gobliiins text files each had a maximum
line length of 79, no tabs and no em dashes. That is evidence of those formatting
properties only. Other Unicode characters remain, so it is not an ASCII-only
certification. Multiple formats are useful when requested; their factual content
and caveats should come from one reviewed source, with abridgments identified.

### Qualify the inherited specification

The [earlier formatting standard](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/templates/gamefaqs-formatting-standard.md)
mixes layout checks with requirements for a fixed 12-18-step short route and
forensic/history sections for every game. Its checker also declares general
site compliance from a small set of text checks. The new skill keeps useful
layout conventions while choosing content according to the actual game and
available evidence. It does not promise universal rendering or site acceptance.

In the [Police Quest I sample](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/walkthroughs/police-quest-1-agi.md),
the dictionary section reports 1,126 vocabulary words in 358 groups under a
completeness heading, but displays 18 core token rows followed by radio terms.
This is useful selected vocabulary; the displayed material is not the advertised
full inventory. The new skill separates reported/extracted coverage from
published coverage and requires headings that describe what is actually supplied.

The [source register](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/SOURCES.md)
explicitly acknowledges outside route references and says PQ1 archive extraction
was private. The inspected tracked tree contains a run-log template but no
populated run logs, extraction scripts or disassembly/runtime receipts. This
limits what the public record demonstrates; it does not establish that private
analysis never happened. The writing skill preserves that distinction.

## The Dune II comparison and its limits

The [earlier Dune II guide](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/walkthroughs/dune-2-ai-and-mechanics.md)
contains detailed mechanics and C-like listings. We compared a small selection
with [OpenDUNE's unit table](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/table/unitinfo.c)
at `ebea79aeba025be2fe9004570e9255044aacc0be`.

| Unit | Earlier guide: HP / range / damage | OpenDUNE raw fields: `hitpoints` / `fireDistance` / `damage` |
| --- | --- | --- |
| Combat Tank | 300 / 3 / 60 | 200 / 4 / 25 |
| Siege Tank | 550 / 4 / 140 | 300 / 5 / 30 |
| Devastator | 800 / 4 / 200, with an additional blast annotation | 400 / 5 / 40 |

These are source-level differences, not an original-game adjudication. The guide
also claims coverage of Super Dune II; raw versus aggregated damage and build/mod
correspondence must be checked before equating fields. OpenDUNE's
[README](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/README.txt)
requires original 1.07 data and documents regional variants and an enhancement
toggle. The compared source alone cannot prove every original release's behavior.

An internal example in the guide labels two modulo-nine coordinate draws
Gaussian without showing a Gaussian construction. That motivates checking prose
against its own algorithm listings, independently of any source-port comparison.
It does not establish the original game's scatter distribution.

The comparison supports neither a plagiarism allegation nor a claim of
independent binary recovery. It motivates claim-level locators and actual method
records. A bibliography, a hash without a named artifact, a realistic function
name or an agent's assurance cannot replace those records.

## Preserve the files-only experiment

If a future task asks whether an agent can recover a solution using only game
files, declare the allowed input set before consulting external game facts.
Formatting exemplars can inform presentation. External guides and source ports
belong to a separate, recorded comparison phase unless the user allows them in
the recovery phase. If previously consulted, retain that fact. A later matching
binary finding may support a reference-guided conclusion without proving blind
rediscovery or absence of model prior knowledge.

This requirement preserves the meaning of the user's original experiment while
still allowing useful research in ordinary guide-writing work.

## Delivery and compatibility

The companion consists of five independently retrievable Markdown resources:
the entrypoint and four references. It uses the repository's existing packaged
skill layout. Discovery supports:

```text
fdisbull agent-skill --list
fdisbull agent-skill --skill write-gamefaqs-guide --index
fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md
```

Omitting the selector still returns `fdisbull-investigate` with the existing
envelope and index format. Names and paths are allowlisted per skill. The new
catalogue does not transfer guide text. Selective reads and full exports use the
existing response budget/artifact behavior. There is no personal-skill install,
GameFAQs account action or game-data publication in this change.

The distribution gate requires the new resources. The installed-package gate
accepts a selected skill, and both ordinary package CI and the existing native
offline-kit workflow now check both skills. Original investigation guidance is
retained; proposed game/runtime capabilities remain at their prior status.

## Verification record

Verification checks the skill's delivery and behavior on authored scenarios.
It does not independently validate the mechanics in the sampled external guides,
play a shipped game or measure an investigation speedup.

| Check | Result |
| --- | --- |
| Focused discovery, gate, distribution, projectless access and output-artifact tests | **90 passed in 1.82 seconds**. |
| Wheel / source distribution / tool ZIP checks | Passed, with **153 / 481 / 473** entries respectively. |
| Wheel payload versus reviewed package source | All **148** package payload files match. |
| Isolated installed investigation-skill gate | Passed: **10** Markdown resources, **27** local reference links. |
| Isolated installed guide-skill gate | Passed: **5** Markdown resources, **4** local reference links. |
| Installed catalogue / guide index responses | **413 / 780 bytes**; content is retrieved selectively. |
| New guide resource sizes | **52,096 bytes** total; largest reference **13,059 bytes**. |
| Skill frontmatter, workflow YAML and diff checks | Passed. |

Focused command:

```sh
python -m pytest -q \
  tests/test_agent_discovery.py tests/test_agent_skill_gate.py \
  tests/test_distribution.py \
  tests/test_scenes.py::test_bundled_investigation_skill_is_readable_without_project \
  tests/test_scenes.py::test_bundled_skill_selective_read_and_invalid_paths \
  tests/test_output_cli.py
```

The artifact tests used an existing private non-Git temporary root because the
environment's ordinary temporary roots have Git ancestry. The artifact-storage
guard remained enabled. Builds used the configured setuptools backend directly
in this environment; the checked-in CI retains its normal `python -m build`
commands. The installed-wheel checks use isolated Python and no source-checkout
imports. Both workflows now run the companion's installed gate as well.

Two fresh agents used the skill on authored evidence packets, without the
reviewer's expected answers. The integration owner read the complete outputs:

- **Adventure review:** preserved the observed opening-before-fuel-loss order,
  the cost of refusal, unexamined acquisition paths, unobserved traversal and
  an unlinked victory string; corrected an older fuel claim without inventing
  a completed route.
- **Mechanics review and text rendition:** preserved a calculation-order
  conflict, matched a supplied witness, kept scheduler/attack timer decrements
  and unknown success probability, and separated decoded from displayed table
  coverage. The text was ASCII with no tabs; ordinary lines met the 79-column
  profile, with one disclosed 86-column intact source-URL exception.

These scenarios test reasoning and presentation on supplied summaries, not
native behavior or all possible future guide requests. Independent diff review
found a wording ambiguity that classified command transcripts as implementation
listings; it was corrected before publication. No material integration or
accepted-content conflict remained in that review.
