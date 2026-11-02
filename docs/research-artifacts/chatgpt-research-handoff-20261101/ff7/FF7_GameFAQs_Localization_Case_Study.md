# FF7 GameFAQs: cross-edition guide reuse

**Revision in progress. Documentation comparison, 30 October 2026 (America/Toronto).**

This follows the FF7 example in PR #51. The user meant GameFAQs text guides,
not a commercially printed book. The sources below were read and compared;
no PS1 executable, field script, memory trace or live game was analyzed here.
Reported mechanics are research leads, not newly recovered executable facts.

## 1. The provenance is more specific than the initial recollection

Kao Megura / Chris MacDonald's GameFAQs FAQ v2.2 records that its August 1997
start used his Japanese FAQ and that the September 1997 edition inherited it.
It also records later corrections for the English game. That is direct evidence
of guide lineage, not a stylistic guess. The inspected revision does disclose
it; it does not establish which copy the user originally read. [G1]

Shoji Iwata's English-written walkthrough v1.06 explicitly targets the Japanese
PlayStation release. [G2] An older mirror of Megura's English/American v1.3 also
retains the lineage and clock-difference discussion. It is another copy/revision
of that author's work, not another independent corroborator. [G5]

The relevant distinction is therefore:

- **Language of explanation:** English.
- **Edition being described:** original Japanese, North American English, or
  a separately identified release such as Japanese International.
- **Guide revision and inherited sources:** which claims were updated, which
  came from earlier work, and which are still speculative.

These fields must not be inferred from one another. The exact forgotten FAQ
revision and the claim that it failed to disclose its origin remain unresolved.

## 2. Eight concrete comparisons

The following entries distinguish documentary findings from proposed checks.
They are not a new walkthrough. Locations and mechanic names are search leads;
there are no recovered addresses, item IDs, executable guards or click targets.

### FF7-C01: clock controls, not a different dungeon

**Documented contrast:** Iwata describes direction plus coarse movement choices.
Megura's English guide describes direct hand adjustment; his version-changes FAQ
explicitly calls the US puzzle simpler. Both walkthroughs retain a twelve-exit
clock scene, and both describe an automatic spin option. The difference is not
simply that only Japan has a spinning clock. [G1, G2, G3]

**Reuse:** keep the provisional clock scene and passage graph. Fork the control
procedure into edition-specific candidates rather than discarding the dungeon.

**Next discriminator:** identify the same field in two authorized, identified
builds; compare dialogue choices, input-to-hand transitions and exit conditions.
Preserve any later assistance state separately. Do not import a precise fall
count or random-number rule from an unsourced summary.

### FF7-C02: Chocobuckle arithmetic

**Documented contrast:** the changes FAQ reports escapes multiplied by caster
level in the original Japanese release, versus escapes alone in the US release.
A separate first-person Japanese-version test also reports a 9,999 cap. [G3, G6]

**Reuse:** one ability identity, alternative arithmetic contracts. A name match
must not silently select a formula from a different release.

**Next discriminator:** use low values below the cap, then separate boundary
cases. For example, ten escapes at level twenty predict 200 versus 10 under
these reported formulas. That arithmetic is an authored probe expectation,
not a newly observed FF7 result. Qualification must also establish the input
counter, level source and relevant modifiers, rather than assuming the prose
is a complete combat specification.

### FF7-C03: Gaea's Cliff difficulty

**Documented contrast:** Megura reports that maintaining body temperature is
easier in the US version. Iwata describes the Japanese temperature-management
interaction. No exact cooling-rate constant is established here. [G1, G2, G3]

**Reuse:** preserve the climb/warm-up action model. Mark rate, threshold and
input cadence as unresolved target-specific properties.

**Next discriminator:** compare equivalent starting states and controlled input
sequences using a declared time base. A qualitative difficulty comparison does
not justify inventing a precise timing constant or copying regional frame timing.

### FF7-C04: materia-management interface

**Documented contrast:** Megura's English walkthrough explicitly says the
original Japanese game lacked the materia Exchange option. [G1]

**Reuse:** retain the intent of moving materia between characters. Permit a
version-specific sequence of interface operations to realize that intent.

**Next discriminator:** compare resulting allocations and allowed operations,
then qualify each edition's menu path separately. More clicks need not imply
different game meaning; a new constraint or side effect would.

### FF7-C05: additional encounters and resources

**Documented contrast:** the changes FAQ reports added Emerald/Ruby encounters,
a playable Diamond battle, and related item/materia changes for the US release.
[G3]

**Reuse:** maintain an edition-specific encounter/resource inventory. An early
Japanese guide's silence about added encounters is not enough to make its other
areas unusable, nor does absence from a guide establish absence from a binary.

**Next discriminator:** inspect target encounter/event dispatch and resource
availability. Do not treat a stored but unreachable resource as a normal action.

### FF7-C06: snowboarding is not one universal score table

**Documented contrast:** AbsoluteSteve provides separate US, PAL, Japanese and
PC ranking tables. At Course A time 52.500, his labels give SUPER for US and
GODLY for both original Japanese and Japanese International. He also records
original-Japanese versus International menu differences. [G4]

**Reuse:** keep the timed-course concept; version the rank mapping and available
options. Japanese International must not be assumed identical to US in every
subsystem merely because it incorporated many US additions.

**Next discriminator:** test just below, at and above a rank boundary; compare
labels, rank IDs, rewards/unlocks and time units separately. A translated rank
name alone is not a semantic distinction, but a changed threshold can be.

### FF7-C07: Magic Pot strategy

**Documented contrast:** Megura says the Japanese Angel Whisper shortcut for
killing Magic Pots no longer works in the English release. This is an explicit
single-guide contrast here, not independently executed evidence. [G1]

**Reuse:** preserve the encounter and item-interaction hypothesis, but retain
edition-specific candidate responses to the same ability.

**Next discriminator:** bind the enemy's relevant response/immunity logic and
compare the action under matched state. A failed strategy should challenge
that tactic, not erase the enemy or the rest of the area from the blueprint.

### FF7-C08: names can differ without different objects

**Documented contrast:** Iwata uses Last Elixir; Megura identifies it with
Megalixir and notes an untranslated acquisition message in the English game.
[G1, G2]

**Reuse:** record an alias candidate instead of inventing two items. Preserve
which text came from the guide, pickup message or inventory screen.

**Next discriminator:** compare resource/item identity and actual effects.
Literal text matching is a lookup aid, not the equivalence criterion.

## 3. A useful negative control: Test 0

Megura reports a Japanese Test 0 encounter. AbsoluteSteve explicitly leaves its
presence in the Japanese game uncertain. [G1, G4] This review therefore does not
list it as an established regional difference or resolve the historical rumor.

Use this as a disputed claim: seek edition-bound encounter data and provenance
of the observation. Do not convert repeated testimony, a debug-only enemy, a
modified copy or an unavailable encounter into a normal reachable scene. The
important result is the retained disagreement, not a convenient verdict.

## 4. A claim-level transfer model

The provisional model should distinguish:

| Kind of difference | Keep | Recheck or specialize |
| --- | --- | --- |
| Naming/translation | Candidate logical identity | Alias mapping and meaning |
| Interface procedure | The requested outcome | Inputs, menus, readiness and intermediate effects |
| Numeric/timing rule | Operation identity | Formula, domain, units and rate |
| Content availability | Other independently useful scene leads | Added/removed/unreachable operations and resources |
| Guide defect or uncertain report | Source and contradiction | The affected claim and its dependents |

A useful draft, deliberately not an adopted runtime format, is:

```
scene candidate: temple.clock
shared hypothesis: clock hands connect a set of exits
control candidates:
  original-JP: reported coarse direction/movement choices
  US-English: reported direct adjustment
source bindings: unresolved
next check: field dialogue and input-to-state transitions
```

The diagram's common structure is still a hypothesis until qualified. It can
nevertheless guide source searches immediately. Record prospective observations
that would contradict it. Do not mutate an original game or declare a successful
UIL implementation merely because the draft executes consistently with itself.

## 5. Guide provenance and revision traps

These sources are not eight independent witnesses. G1, G3 and G5 share an author;
G5 is an older mirror. G4 credits contributors for some regional findings. Keep
claim-level dependencies and unknown lineage rather than counting domains.

Host-page metadata is separate from document history. G3 is presented with a
2015 page-update date while its body includes period-era discussion of an
unreleased PC port. GameFAQs also exposes the same FAQ identifier under multiple
platform routes. A page header is not proof that every passage was retested for
that platform or recently reverified. [G3]

The supplied recollection suggested a real issue, but the documentation pass
also corrects it: the inspected guides disclose Japanese scope or inheritance.
A useful research method should be willing to correct its initiating hypothesis.

## 6. Proposed follow-up, not performed

Freeze the guide packet and target fingerprints before comparing workflows.
Use a shared-scene/different-procedure case (clock), a small arithmetic case
(Chocobuckle), a timing/ranking case (cliff or snowboard), and an alias-only case.

Compare the preliminary Z prediction, source-bound UDL/UIL relation and original
runtime observations separately. Count accepted and rejected hypotheses,
remaining unknowns, source discovery time and correction effort. A successful
guide-assisted run is not a cold-recovery benchmark. Keep a genuinely blind
worker separate from this now-informed research context.

No PS1 game run, FF7 decompilation, formal equivalence proof or benchmark was
performed. The proposed discriminators are not executed tests. The document
adds no processor, player capability, UIL schema or executable authority.

## Sources and exact sections

Primary author documents; brief facts are paraphrased, not reproduced guides.
Displayed dates identify retrieved revisions, not guarantees of correctness.

- **G1:** [Kao Megura / Chris MacDonald, GameFAQs FAQ 2376, v2.2](https://gamefaqs.gamespot.com/ps/197341-final-fantasy-vii/faqs/2376), displayed 2004-05-16. Introduction; revision history 0.0, 0.1 and 1.0; Disc 1 Temple of the Ancients and Shinra escape; Disc 2 Gaea's Cliff; Magic Pot and Test 0 entries.
- **G2:** [Shoji Iwata, GameFAQs FAQ 3895, v1.06](https://gamefaqs.gamespot.com/ps/197341-final-fantasy-vii/faqs/3895), displayed 1997-04-16. Header identifies Japanese PS1; Disc 1 section 28 (clock controls and exits); mountain-climbing temperature section.
- **G3:** [Kao Megura, GameFAQs Release Changes FAQ 3890, v0.3](https://gamefaqs.gamespot.com/ps/197341-final-fantasy-vii/faqs/3890), host displays 2015-03-06. Sections 2 and 3.1, US versus Japanese changes and the clock/cliff discussion.
- **G4:** [AbsoluteSteve, GameFAQs FAQ 45703, Final](https://gamefaqs.gamespot.com/ps/197341-final-fantasy-vii/faqs/45703), displayed 2007-07-07. Snowboarding Time Attack ranking tables; Japanese Version Differences, credited to Shademp; Test 0 discussion.
- **G5:** [Historical mirror, Kao Megura English/American FAQ v1.3](https://otakuworld.com/games/psx/ff7.htm). Revision history 0.1 and Temple clock section. Not a separate author or corroboration family.
- **G6:** [Shademp, GameFAQs first-person Chocobuckle test](https://gamefaqs.gamespot.com/boards/197341-final-fantasy-vii/57095163). Opening post explicitly identifies the original Japanese version and reports the formula and damage cap; no recording or target hash was independently checked here.
