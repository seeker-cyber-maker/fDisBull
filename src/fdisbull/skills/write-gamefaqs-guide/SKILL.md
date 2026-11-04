---
name: write-gamefaqs-guide
description: Write or revise a human-readable GameFAQs-style guide from a game's reverse-engineering evidence. Cover mechanics and event probabilities, bugs and exploits, cheats and easter eggs, recovered unused code, alternate routes, speedrun and completionist goals, file and media specifications, embedded interpreters and transferable engine knowledge. Use for reviews of established knowledge, partial walkthroughs, technical FAQs or audits of earlier solutions, preserving release scope, provenance, uncertainty and navigation. Default to Markdown with optional legacy text; do not imply completed playthroughs, rule compliance or site submission.
---

# Write a GameFAQs-style game guide

Turn established game knowledge into useful original prose. Lead with what the
reader can understand or do, preserve the evidence behind consequential claims,
and make incomplete knowledge visible. The default deliverable is a review of
what is known at a stated investigation cutoff. A useful review can describe
recovered mechanics and unresolved progression without claiming a complete
solution.

Treat the guide as a review of the recovered game, including material beyond
its intended winning route. Explain useful discoveries for ordinary players,
speedrunners, completionists and readers investigating the implementation.
Unused code, unconfirmed exploits and partial format specifications remain
valuable when their evidence and limits are explicit.


## Keep game files out of publication

Do not upload original or modified game binaries, game assets, story images,
saves, emulator states, or raw game-containing FDBs/archives to GitLab, GitHub,
local hubs or tool packages, except for repository-authorized freeware and
homegrown targets. That exception includes new targets, binaries, assets, source
and generated variants, with license/provenance notices preserved; eligible
fixtures still stay out of tool-only distributions. Commercial/private saves,
states and object stores remain private. Semantic UIL/game representations are allowed pending
sanitation; complete originals embedded in memory arrays, hex caches or nested
archives are excluded. Review contents, not names. New FDBs retain exact
size/SHA-256 identities and loader provenance with payloads in a private
external store; that store must never be uploaded. Hash equality verifies
recorded byte identity, not publisher authenticity, safety, ownership or
permission to distribute.

Use `source-candidate` for a changed binary. Obtain the user's explicit approval
for that exact project/base/candidate receipt before calling `bind-source` with
it; receiving or echoing the receipt is not consent. An approved binary is a
distinct provenance-bound layer, with bytes still external and the base
preserved. Without approval leave it unattached, and create a separate analysis
only if explicitly chosen. Declining must not execute the candidate. Legacy
FDBs require read-only `storage-info` and an explicitly requested new derivative
via `migrate-external`; never silently rewrite an original. Other exports can
still embed target data and need separate review. See repository
`docs/EXTERNAL_TARGETS.md` for the full storage and compatibility contract.

## Choose the next reference

Read the entrypoint, then only the reference needed for the current decision.
Check the experiment's information policy before opening either source-examples
reference; both contain external game facts. General writing references can be
used with supplied evidence alone during a files-only recovery pass.

| Need | Reference |
| --- | --- |
| Qualify claims, earlier AI output, source ports or a files-only experiment | [Evidence and provenance](references/evidence-and-provenance.md) |
| Organize a readable review, route, tables or optional plain-text rendition | [Guide structure](references/guide-structure.md) |
| Explain formulas, timing, random behavior, pseudocode and worked examples | [Technical mechanics](references/technical-mechanics.md) |
| Cover unused content, bugs, cheats, secrets, alternate routes, speedrun rules and completion goals | [Routes and discoveries](references/routes-and-discoveries.md) |
| Specify recovered files/media, identify engines or interpreters, and qualify transfer to related games | [Formats and engine reuse](references/formats-and-engine-reuse.md) |
| Compare concrete external engine/layout/edition examples, only when the experiment permits external game facts | [Engine source examples](references/engine-source-examples.md) |
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

For a speedrun or minimal route, name the objective, allowed actions and
applicable ruleset; fewest actions, fastest time and least required progress are
different goals. For completion, define what counts and whether mutually
exclusive outcomes require multiple runs. An unexplored category is a coverage
gap, not evidence that the game has no such content.

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

Include material findings across these areas where the investigation has them:
progression and alternative solutions; random events and timing; programming
bugs and potential exploits; cheats, easter eggs and debug features; unused or
conditionally reachable code/assets; optional and missable content; recovered
file/media layouts; engine/interpreter structure and transferable knowledge.
Record present, understood, reachable and observed separately. Do not silently
discard a recovered branch because it cannot yet support player instructions.

Consume structured `fdisbull-investigate` artifacts without inflating their
scope: keep binary-claim verdicts split across stored value, width/signedness,
writer, trigger and reader on the pinned decoded edition; retain two-stage world
and resource censuses (`agi-scenes` `outline`/`resolve`, Zork `zork-scenes` or
`(z-world ...)` projections, and read-only save/map snapshots) with explicit
residual IR; report standing-probe hit counts separately from bounded no-hit
runs (zero hits in examined play never prove dead code); keep finalized AVI
`capture-audit` frame hashes and video timestamps distinct from guest ticks; and
distinguish console ROM/disc/multicart header metadata from verified unique
playable games.

For native save/load findings, preserve the component meaning: selecting a UI
command, entering an original routine, returning through its continuation,
writing a file, updating live state and refreshing a displayed value are
separate observations. A prefix transfer does not establish a whole-save
operation. Keep prepared harness use, independent binding recovery and assisted
continuations distinct. Compare timings only with named start/stop clocks and
the same completion criteria; report incomplete required questions visibly.

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

Publish speedrun shortcuts with their entry/exit state, dependencies, costs,
failure risks, provenance and category eligibility. Keep intended solutions,
glitches, built-in cheats and external state edits distinguishable; a bug can be
legal in one category and disallowed in another. Preserve candidate techniques
as candidates. Completion checklists should identify mutually exclusive choices,
missables and recovery, separating obtainable content from archival discoveries.

For mechanics, give the practical implication, exact applicable conditions,
calculation order and exceptions, then a worked example when supported. Label
unknown terms instead of filling them from familiarity with another game or
release. Classify implementation and algorithm listings as actual disassembly,
decompiler output, source excerpt, reconstructed pseudocode or an illustrative
model. Label player commands, captured output and data listings by their actual
purpose and source.

For implementation findings, include a readable technical appendix with the
recovered byte layout, known invariants, unknown fields and original consumer
behavior. Distinguish container, codec and playback contracts. Identify which
engine, VM or native-code layer implements a behavior and which evidence makes
part of the analysis reusable in a related release or game.

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

Check that unused-code labels state their reachability scope, bugs include their
trigger and actual effects, probabilities name their conditioned event and draw
model, and completion totals exclude or label unobtainable/exclusive entries.
Do not call a route category-legal without the relevant rules, or a media file
safe to shorten merely because a standalone decoder accepts it. Reuse across
games requires correspondence at the claimed layer, not just a shared title,
series, extension or source-port engine name.

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
