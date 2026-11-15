---
name: fdisbull
description: Choose the fDisBull skill for program investigation, progressive cooperative-play harness building including Dot/cloud workers, or writing a guide from recovered game knowledge.
---

# fDisBull — skill router

Start here when you have a vague fDisBull request. Do not load every skill. Select exactly one matching child skill and load it; its `SKILL.md` and `references/` provide all the detail.

## Choose the right child skill

| If you need to… | Load this skill |
|---|---|
| Build a Z harness during cooperative play, work as Dot or a parallel cloud worker, investigate files/state or recover behavior | `fdisbull-investigate` |
| Write a readable GameFAQs-style guide, route, walkthrough, or technical FAQ | `write-gamefaqs-guide` |

## Load only what you need

Read the chosen child's entrypoint with `fdisbull agent-skill --skill NAME --reference SKILL.md`, substituting the selected name. Load only the specific reference needed for the current decision. For cooperative play or a cloud harness worker, the investigation entrypoint routes to `references/cloud-harness.md`; prepare the current scene and next likely transition, then grow the harness while play continues.

## Do not combine the two child skills

These two skills do different jobs:

- **Investigation and progressive play harness** (recover facts, capture controls, extend the next playable scene) → `fdisbull-investigate`
- **Writing** (organize established knowledge into human-readable prose) → `write-gamefaqs-guide`

Do not serve a writing request with the investigation skill, or serve an investigation request with the writing skill. If the user wants both, provide them sequentially: investigate first, then write using the investigation output.
