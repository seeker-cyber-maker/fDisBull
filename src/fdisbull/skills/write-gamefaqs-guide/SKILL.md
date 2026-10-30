---
name: write-gamefaqs-guide
description: Write or revise a human-readable GameFAQs-style knowledge review, walkthrough, mechanics FAQ or reference guide from a game's existing investigation evidence. Use for explaining what reverse engineering has established, auditing earlier generated solutions, or turning supported findings into player-facing prose with release scope, provenance, uncertainty and useful navigation. Support Markdown by default and a requested legacy text rendition; do not imply a completed playthrough or GameFAQs submission.
---

# Write a GameFAQs-style game guide

Turn established game knowledge into useful original prose. Lead with what the
reader can understand or do, preserve the evidence behind consequential claims,
and make incomplete knowledge visible. The default deliverable is a review of
what is known at a stated investigation cutoff. A useful review can describe
recovered mechanics and unresolved progression without claiming a complete
solution.

## Choose the next reference

Read the entrypoint, then only the reference needed for the current decision.

| Need | Reference |
| --- | --- |
| Qualify claims, earlier AI output, source ports or a files-only experiment | [Evidence and provenance](references/evidence-and-provenance.md) |
| Organize a readable review, route, tables or optional plain-text rendition | [Guide structure](references/guide-structure.md) |
| Explain formulas, timing, random behavior, pseudocode and worked examples | [Technical mechanics](references/technical-mechanics.md) |
| Inspect the official guidance and concrete guides motivating these requirements | [Source examples and design lessons](references/source-examples.md) |

For a new investigation question, use the separate `fdisbull-investigate` skill.
This writing skill consumes its findings; it does not add a game interpreter,
walkthrough generator, native runner or automatic truth validator.

## 1. Establish the writing contract

Identify the game, platform, release, language, mod/patch and relevant settings
from supplied evidence. Reuse existing artifact identities. If an identity is
missing, say so; do not invent a hash or rehash an unchanged collection merely
to write prose. Record the guide revision and evidence cutoff separately from
the game's release version.

Choose the requested product: known-knowledge review, mechanics reference,
partial walkthrough, supported route, or a combination. Default to a readable
Markdown review with a contents list, compact source appendix and explicit
coverage statement. Include a spoiler notice appropriate to the material.
Produce extra text/HTML formats only when requested or useful to the task.

If the user is testing recovery from game files alone, preserve that experiment
boundary before reading external game facts. Formatting examples are permitted
presentation evidence; guides and source ports are outside factual evidence.
Record any already consulted material and distinguish later cross-checks from
independent recovery. Do not claim model memory was absent or prove independence
from an agent's assurance.

## 2. Build the claim and coverage ledger

Reuse the investigation's source registry, claims, traces, resource inventories
and unresolved questions. Add only the writing-specific fields or missing
links. For each consequential assertion, retain a stable claim ID, applicability,
evidence locator, actual method, evidence kind, validation limits and any
conflicting account. These records can be a compact appendix or a companion
ledger; do not expose every address in the player's main narrative.

Distinguish **recovered**, **observed**, **external reference**, **derived**,
**hypothesized** and **unknown/conflicting** knowledge. These describe provenance
and support, not a confidence ranking. Static extraction can establish a table;
one runtime example cannot establish every branch; a source port needs a
demonstrated correspondence to the selected original release.

Inventory the material areas already investigated and map them to guide sections.
Do not silently drop awkward findings, exceptions, partial effects or unresolved
contradictions to make the prose smoother. Distinguish unexamined areas from
examined but unresolved ones. If calling a list or route complete, state its
denominator and scope. A budget stop, polished old guide or arbitrary chapter
count cannot supply missing coverage.

## 3. Write from gameplay meaning

Explain the useful result before the technical derivation. Organize around
player goals, places, systems and lookup questions. Give stable searchable
section IDs, consistent item/location names, localized aliases where relevant,
and explicit units in tables. Match the depth to the known material and the
reader's question; do not force every game into the same chapter template.

For consequential instructions, preserve the starting conditions, action or
parser command, observable success, state change, hazards and recovery. Place
timed or irreversible warnings before the action. Separate required progress,
optional scoring, alternate solutions and debugger-assisted observations. A
static candidate route remains a candidate until its relevant reachability and
execution obligations are supported.

For mechanics, give the practical implication, exact applicable conditions,
calculation order and exceptions, then a worked example when supported. Label
unknown terms instead of filling them from familiarity with another game or
release. Classify implementation and algorithm listings as actual disassembly,
decompiler output, source excerpt, reconstructed pseudocode or an illustrative
model. Label player commands, captured output and data listings by their actual
purpose and source.

Use short local qualifiers and source IDs where they change how the reader
should use a claim. Keep the fuller provenance in the appendix. Write original
explanations; credit learned and compared findings, and preserve actual author
and license choices. Do not invent play experience, a biography, human
authorship or claims of independent reverse engineering.

## 4. Check meaning before presentation

Review every consequential numerical, route, exception and completeness claim
against its source. Check prose against tables, formulas and pseudocode. Preserve
differences between versions and competing sources. If public receipts are
missing, report what the available record establishes without asserting that
private analysis never occurred.

Check that compressed routes retain required dependencies or explicitly point
to the detailed route. Do not promote a checklist to an optimal, no-damage or
full-score route without the corresponding evidence. Check section references,
table headings, caveats, spoilers and revision notes. When exporting a second
format, derive it from the same reviewed facts and retain their qualifications.

Use cheap deterministic checks for navigation, table consistency, supplied
arithmetic examples and requested text width. Keep factual verification distinct
from formatting checks. Fresh-agent review of a consequential section can expose
unsupported leaps; give the reviewer the sources and draft, not the answer it
is expected to reach.

## 5. Deliver the review and its limits

Deliver the full supported review, not merely a proposed outline. Include the
investigation cutoff, material unknowns, source credits and changes to previously
published conclusions. Name a completion claim only at the scope established by
the evidence. A static-only review is a valid result when identified as such.

Do not make writing conditional on a new exhaustive playthrough. When a gap
affects a material instruction, resolve it from available evidence, qualify or
withhold that instruction, and state the smallest next discriminating question.
Perform additional investigation only when it belongs to the user's task.

Treat this as authoring and review. A text-width check does not establish
GameFAQs acceptance; Markdown is not the site's submission syntax. If actual
publication is requested later, refresh the applicable submission instructions
and act only within that authorization.

## Work efficiently without reducing coverage

Reuse settled facts and source locators. On an update, revisit claims affected
by changed inputs, interpretation or runtime evidence, then inspect their linked
sections. Parallelize independent topic drafts with a shared terminology and
claim ledger; have one editor reconcile applicability, contradictions and
cross-references. Avoid independently regenerating each output format or
repeating an investigation whose evidence is already adequate.
