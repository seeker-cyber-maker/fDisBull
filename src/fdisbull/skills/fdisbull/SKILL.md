---
name: fdisbull
description: Select and load the correct fDisBull skill for the task at hand. Use when multiple fDisBull skills exist and the user has not named one; routes to investigation, guide writing, or format/container handling.
---

# fDisBull — skill router

Start here when you have a vague fDisBull request. Do not load every skill. Select exactly one matching child skill and load it; its `SKILL.md` and `references/` provide all the detail.

## Choose the right child skill

| If you need to… | Load this skill |
|---|---|
| Investigate a program or game, understand files/state, decode what got found, build a Z/Z-harness | `fdisbull-investigate` |
| Write a readable GameFAQs-style guide, route, walkthrough, or technical FAQ | `write-gamefaqs-guide` |

## Load only what you need

Read the router's multi-skill guidance, then read the chosen child's `SKILL.md` with `fdisbull agent-skill --reference <path>` and load only the specific `references/` file needed for the current decision.

## Do not combine the two child skills

These two skills do different jobs:

- **Investigation** (decode, verify claims, recover facts, build harness) → `fdisbull-investigate`
- **Writing** (organize established knowledge into human-readable prose) → `write-gamefaqs-guide`

Do not serve a writing request with the investigation skill, or serve an investigation request with the writing skill. If the user wants both, provide them sequentially: investigate first, then write using the investigation output.
