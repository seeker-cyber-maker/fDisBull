# ChatGPT research handoff, 2026-11-01

Preservation of authored research from ChatGPT chat agents that did not already
have a dedicated review object. This is a research archive, not an acceptance
claim and not a playable-patch delivery.

Source archive:
`fDisBull_Research_and_Implementation_Handoff_2026-11-01.zip`
(`aa3627a4ac061fdccb9f816e0d8e685417275220e60dee119b8a9db655e8fdf2`).

## Included

- `civ/` — Civilization replication plan, reference-match receipt and startup
  correction check. This is a follow-up plan; the merged PR #40 added only
  `docs/CIVILIZATION_RESEARCH_LEADS.md`.
- `ff7/` — Final Fantasy VII GameFAQs localization case study. No matching
  repository file was found on the open PR #51 branch.
- `space-quest/` — Space Quest game-patch comparison, Ultima intake evidence and
  the extracted game-patch/Ultima evidence trees. No repository PR was found for
  this research.
- `pr20/` — the docs-only PR20 game-patch differential study and its original
  patch.

## Deliberately not duplicated

- Console synthesis code is already integrated (`a287d93`); its final docs and
  route audit are on open GitLab MR !28 (`b6132d62`).
- Colonization shared UIL already has GitHub PR #70.
- PR 29 / Rosetta already has GitHub PR #29 and local branch
  `pr/29/rosetta-contracts`.
- Lost in Time, UDL/UIL/UDC, Polyglot and v0.26 evidence already have reviewed
  packs in `docs/research-artifacts/document-packs/`.
- Five historical experiment files were not copied where an existing PR or
  reviewed pack already owns the material.

## Evidence boundary

The source archive's own validation records `fresh_native_or_repository_tests:
false` and `remote_services_queried: false`. No test was rerun for this
preservation branch. The copied results remain attributed to their original
runtime and source revision.

No original `MAIN.EXE`, installer, game archive, private FDB, memory image or
native checkpoint is included. The Space Quest evidence is authored results and
small generated excerpts, not original game payloads.
