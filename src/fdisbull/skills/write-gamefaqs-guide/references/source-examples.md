# Source examples and requirement rationale

Research date: **2026-10-29**. These examples motivate the guide-writing
requirements; they are not a new analysis of the games or a promise of acceptance
by GameFAQs. Use the references for structure and explicitly attributed context,
not as text to reproduce or as evidence that this project recovered a fact.

## Contents

- [Requirement key](#requirement-key)
- [Source catalogue](#source-catalogue)
- [Scope and access limits](#scope-and-access-limits)
- [Applying the examples](#applying-the-examples)

## Requirement key

These are this skill's design decisions, not purported GameFAQs rules.

| ID | Requirement | Motivation |
| --- | --- | --- |
| R01 | Declare the product and its coverage: knowledge review, route, mechanics reference, or a combination. | A readable account of known material can be useful before a complete walkthrough exists. |
| R02 | Identify game release, platform, language, patch/mod and target evidence; preserve exclusions and variant differences. | Similar names and a shared hosting page do not establish equivalent behavior. |
| R03 | Attribute recovered, observed, external, inferred and unresolved claims; retain their evidence lineage. | Imported research and code-like prose cannot demonstrate independent reverse engineering. |
| R04 | Use navigable headings, stable search labels, a glossary and appropriately sized tables. | Readers need to find an answer without reading a disassembly or the entire guide. |
| R05 | State route prerequisites, actions, expected outcomes, hazards, branches and recovery limits. | A plausible sequence is not a validated playable route. |
| R06 | Preserve numerical meaning: variables, units, order, rounding, bounds, randomness, comparisons and exceptions. | Small arithmetic or precedence differences can change advice. |
| R07 | Qualify completeness and maintain corrections, conflicts and unanswered questions. | Detailed presentation does not establish exhaustive or correct knowledge. |
| R08 | Reuse useful prior work and generate consistent views without inheriting unsupported claims or boilerplate. | Formatting, research and verification have separate evidence requirements. |

## Source catalogue

### S01. GameFAQs Contributor Central

[Contributor Central](https://gamefaqs.gamespot.com/contribute) is the official
contribution entry page. **Access:** indexed primary page text; inspected during
this research. No publication revision date was established.

The page distinguishes its HTML editor, with rich elements, from text submission
through upload or a simple editor. This supports choosing a delivery format
explicitly (**R04, R08**). It does not establish that arbitrary Markdown or an
arbitrary HTML document can be uploaded unchanged. This skill defaults to a
human-readable review; site submission is a separate task with its own current
requirements.

### S02. Historical staff announcement about text submissions

[Contribution Changes: ASCII FAQ Editor, Image Submission Update](https://gamefaqs.gamespot.com/boards/2000094-gamefaqs-contributors-faqs-and-guides/78092692),
by **Dev**, identified on the page as Lead Moderator. **Access:** indexed primary
post text and author identification. The exact posting date was not verified.

The announcement discusses an ASCII editor, an 80-character text width and
unsupported word-processor uploads. Treat it as historical staff guidance, not
an independently verified statement of every present submission rule. A
79-column target for a classic text export is our conservative layout choice
(**R04, R08**); elaborate banners and dot leaders are optional. It is not a
universal requirement for Markdown reviews or proof of compatibility with every
viewer.

### S03. Lost in Time walkthrough

[Lost in Time — FAQ/Walkthrough](https://gamefaqs.gamespot.com/pc/564643-lost-in-time/faqs/55450),
**Koruchan**, version **1.1**, updated **2015-05-14**. **Access:** indexed primary
guide text; direct opening was restricted.

The sampled text uses numbered navigation, recognizable item/location terms,
and warnings about spoilers, timed events, deaths and situations that prevent
progress. It motivates identifiable actions and warnings placed before the
relevant decision (**R04, R05**). Use its structure as an example, not its prose
or embedded manual transcripts. It does not establish behavior in every language
or release of Lost in Time (**R02**).

### S04. King's Quest reference organization

[King's Quest: Quest for the Crown — FAQ/Walkthrough](https://gamefaqs.gamespot.com/pc/565065-kings-quest-quest-for-the-crown/faqs/7199),
**Tom Hayes**, version **1.1**, updated **2008-08-21**. **Access:** indexed primary
guide text. A [separate VGA guide](https://gamefaqs.gamespot.com/pc/581149-kings-quest-i-quest-for-the-crown-vga/faqs/32097)
was also identified; its existence is a release-scope example, not evidence that
the two routes agree.

The sampled guide separates the route from characters, items, points, maps,
secrets and debugging information, and distinguishes individual score changes
from totals. Adopt navigable player and reference sections, score reconciliation
and separation of ordinary play from assisted/debug behavior
(**R01, R02, R04, R05**).

### S05. Zork I as an explicitly bounded route

[Zork I — Walkthrough](https://gamefaqs.gamespot.com/pc/564446-zork-i/faqs/52010),
**Stanley E. Dunigan / sdunigan**, version **1.01**, updated **2009-04-01**.
**Access:** indexed primary guide text.

The author describes an optimized route rather than a complete reference
catalogue and names the 1991 Lost Treasures of Infocom package used. This
motivates explicit route objectives and target identity (**R01, R02, R07**).
A short solution, a maximum-score route and a catalogue of all interactions have
different coverage obligations. Do not expand one into the others by changing
the title.

### S06. Final Fantasy IV Algorithm FAQ

[Final Fantasy IV — Algorithm FAQ](https://gamefaqs.gamespot.com/snes/588330-final-fantasy-iv/faqs/54945),
**Deathlike2**, version **1.51**, updated **2009-01-06**. **Access:** parsed primary
guide; selected introduction, algorithm, uncertainty, credits and revision
sections inspected.

This is a strong candidate for the technical FF4 guide recalled by the user,
not a confirmed identification. It names covered SNES/SFC/GBA releases and
unverified ports, orders calculations, distinguishes port-specific precedence,
and leaves some probability estimates qualified. Credits identify an editor,
earlier guides, datasheets and contributors who inspected code. Adopt precise
version scope, numerical semantics, local uncertainty and research attribution
(**R02, R03, R06, R07**). Do not convert an author's estimate into a measured
probability or an external finding into this project's own discovery.

### S07. Earlier Final Fantasy II technical FAQ

[Final Fantasy II — FAQ](https://gamefaqs.gamespot.com/snes/522596-final-fantasy-ii/faqs/5494),
**Ben Siron / BSiron**, second edition, **1995-09-19**. **Access:** parsed primary
guide; introduction, contents, definitions and partial algorithms inspected.

This concerns the North American SNES title for FFIV, not the unrelated game
that shares its number. It credits earlier material and contributed corrections,
defines abbreviations, and explicitly leaves parts of the hit/defense formula
unresolved. Adopt a glossary and preserve the boundary between a known result,
an approximation and a missing function (**R02, R03, R04, R07**). Its age and
historical importance do not make every claim a current oracle.

### S08. Final Fantasy III/VI Algorithms FAQ

[Final Fantasy VI — Algorithms FAQ](https://gamefaqs.gamespot.com/ps/562865-final-fantasy-vi/faqs/13573),
**Terii Senshi**, version **2.3**, website update **2004-04-17**. **Access:** parsed
primary guide; contents, notation, calculations, credits and revision history
inspected. The accessible URL is under PlayStation, but the guide labels itself
SNES; an attempted SNES URL was restricted.

The guide defines integer and random-range notation, stages calculations,
states early exits and cross-references shared mechanics. Its revision history
records changes to inequalities, probabilities, ordering and encounter lists.
Adopt precise arithmetic and substantive correction records
(**R02, R04, R06, R07**). Hosting-platform metadata is insufficient to establish
the mechanics' scope. Our requirement to distinguish signed truncation from
floor, where relevant, is a strengthened analysis contract, not a claim that
this guide explains every such case.

### S09. The user's earlier AI-written guide experiment

[AI-Generated Game Walkthroughs](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/tree/3af2bc50f922d5923ed7c8643492b649ac4734d6),
pinned to **`3af2bc50f922d5923ed7c8643492b649ac4734d6`**. **Access:** repository file
contents at that commit. This is prior project work, not GameFAQs policy or an
independent validation source.

Reviewed examples and supporting material:

- [README](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/README.md)
  and [sources](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/SOURCES.md).
- [Formatting template](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/templates/gamefaqs-formatting-standard.md)
  and [run log](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/templates/run-log.md).
- [Police Quest I](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/walkthroughs/police-quest-1-agi.md),
  [Gobliiins](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/walkthroughs/gobliiins-1.md)
  and [Dune II](https://github.com/seeker-cyber-maker/ai-generated-game-walkthroughs/blob/3af2bc50f922d5923ed7c8643492b649ac4734d6/walkthroughs/dune-2-ai-and-mechanics.md).

Retain command-focused routes, score ledgers, search labels, multiple readable
formats and the run-log fields. The source register explicitly includes outside
route references. A template's demands for exhaustive tables or binary
forensics cannot supply the evidence those claims require. Declared hashes,
completion labels and C-like examples need traceable support. Select relevant
sections instead of requiring every game to have the same forensic material
(**R01, R03, R05, R07, R08**). The user's attribution of the earlier experiment
to Gemini does not establish the provenance of individual claims.

### S10. OpenDUNE as a scoped comparison source

[OpenDUNE](https://github.com/OpenDUNE/OpenDUNE/tree/ebea79aeba025be2fe9004570e9255044aacc0be),
pinned to **`ebea79aeba025be2fe9004570e9255044aacc0be`**, including
[`src/table/unitinfo.c`](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/table/unitinfo.c).
**Access:** repository source at that commit.

Its explicit data fields offer a useful comparison for the earlier Dune II
guide. Differences require release/mod and field-semantics reconciliation:
the guide also claims coverage of Super Dune II. OpenDUNE source alone does
not establish the contents of a different original executable. Similar naming
does not prove copying; disagreement does not prove independent analysis or
identify which target is correct. Require specific source locators and target
correspondence before attributing a claim to recovered original-game behavior
(**R02, R03, R06, R07**).

## Scope and access limits

The official help pages for formatted FAQs and markup, and the submission
endpoint, were inaccessible during this review. No current AI-specific
acceptance or prohibition rule was verified. Do not turn that lack of access
into either a claim of permission or a ban. Bounty-program conditions, if
consulted later, apply to that program unless the source explicitly says more.

Indexed primary text is sufficient to identify the sampled format features
reported above; it is not a full current-policy audit. Retrieved guides were
sampled, not independently replayed or exhaustively checked. Source dates and
guide revisions identify the reviewed material, not its present correctness.

## Applying the examples

Keep the guide readable and put compact evidence links beside material claims.
Preserve known useful content from earlier drafts, then qualify or correct only
what the evidence supports. Make uncertain mechanics, missing route validation
and source conflicts visible without filling gaps with plausible prose.

Use these examples to justify requirements and evaluate a draft. Do not clone
their wording, assert the earlier guides are entirely correct or incorrect,
invent an author's research history, or present the review as a completed
GameFAQs submission.
