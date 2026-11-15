---
name: fdisbull
description: Select and load the correct fDisBull skill for the task at hand. Use when multiple fDisBull skills exist and the user has not named one; routes to investigation (including formats/containers) or guide writing.
---

# fDisBull — skill router

Start here when you have a vague fDisBull request. Do not load every skill. Select exactly one matching child skill and load it; its `SKILL.md` and `references/` provide all the detail.

## Choose the right child skill

| If you need to… | Load this skill |
|---|---|
| Investigate a program or game, understand files/state, decode what got found, build a Z/Z-harness | `fdisbull-investigate` |
| Identify or unpack a format/container | `fdisbull-investigate`, then its formats/media reference |
| Write a readable GameFAQs-style guide, route, walkthrough, or technical FAQ | `write-gamefaqs-guide` |

## Load only what you need

Select the child explicitly; omitting `--skill` defaults to investigation:

```sh
fdisbull agent-skill --skill fdisbull-investigate --reference SKILL.md
fdisbull agent-skill --skill write-gamefaqs-guide --reference SKILL.md
```

Use the same `--skill` when requesting `--index` or a particular reference.
When reading an agent-installed copy, resolve relative references beside that
copy; a newer guide does not add methods to an older runtime. Load only the
reference needed for the current decision.

## Do not combine the two child skills

These two skills do different jobs:

- **Investigation** (decode, verify claims, recover facts, build harness) → `fdisbull-investigate`
- **Writing** (organize established knowledge into human-readable prose) → `write-gamefaqs-guide`

Do not serve a writing request with the investigation skill, or serve an investigation request with the writing skill. If the user wants both, provide them sequentially: investigate first, then write using the investigation output.
