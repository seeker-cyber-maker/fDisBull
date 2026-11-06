# Browser UI and delivery review — 5 November 2026

## Scope and source identity

This is an actual Chrome interaction pass through the Sites managed preview at
`http://terminal.local:4173/`, plus the separately retained actual-app Node
integration harness. The JSON companion pins the final host/runtime sources.
It does not qualify AppKit or newly re-observe the original DOS executable.

## Observed interactions

- Default seed 42 displayed fingerprint `ba2a25023d51ede2` and two givens.
- A candidate removal changed its accessible state to eliminated; Undo restored
  the board. The generated seed accepted `18446744073709551615` without
  precision loss and displayed fingerprint prefix `7a1faf53`.
- Seed42's first offered move removed Houses 3 from column 4 (one-based UI).
  Show why displayed supporting clue 4, a SAME_COLUMN relationship, and the
  explicit qualification that existing marks are assumptions.
- Acceptance applied the removal and charged30 seconds. A 20-second countdown
  reached Time expired after acceptance; the target removal was still visible.
- Pause concealed both board and clue cards. A fresh accessibility tree contained
  zero candidate buttons, zero clue buttons and no Agent JSON panel. The clock
  stayed stopped. Resume restored the puzzle.
- Clue 1 moved to the Other bank. Save game produced a real10,420-byte download;
  reload resumed that bank and the two retained undo entries.
- The file chooser accepted local ORGINAL.SHI and reported all 46 images decoded.
  A later source refresh correctly discarded tab-local art. The receipt does
  not claim a full screenshot/pixel comparison of the rendered imported art.
- The JSON panel accepted an independently solved seed 42answer while the live
  board stayed at 2/36. Analyze emitted the canonical CLI fields, including
  source, fingerprint, solutions_found, solution_count_is_exact and node_budget,
  with no witness solution.
- A 390px iframe provided a 375px content width after its scrollbar. Root
  scrollWidth and clientWidth both measured 375px; all six picker buttons were
  44×44px. Selecting a cell and using its large picker removed the chosen
  candidate. Desktop and narrow screenshots were visually inspected.

## Corrections made during review

The initial pause overlay hid only the board; it now conceals clues, inspector,
cell tools and diagnostics as well. Fixed givens retain normal image opacity,
and the overlay Resume button has readable dark text. Saved native generation
reports are checked against regeneration, bare challenge imports acquire the
canonical report, over-capacity clue layouts fail before adoption, and the
closed session/capture wrappers reject unexpected fields. The separate
protocol adapter now emits the native CLI JSON schema exactly. Pending hint
captures preserve the frozen displayed clock separately from actual elapsed
milliseconds.

## Hosting and remaining gates

The exact eight runtime files were packaged into the private Site and the
self-contained Space fragment. The Sites service reports successful deployment;
the Page service read back the executable embed and its full-width layout.
`hosting-receipt.json` identifies both destinations.

The cloud browser was signed out of ChatGPT. It reached the normal sign-in
pages for both the private production Site and the Space, so actual production
viewer interaction and real Space-state synchronization remain unperformed.
This is a bounded host qualification gap, not a failure of the tested game.
The minimal-DOM integration harness separately checks Space-state precedence,
shared-update rejection, pending restore and the same registered UI handlers.

No browser console failure from the game was observed. The browser extension
logged metadata transport errors; these were not attributed to the app. No
Apple-SDK build, Safari/iOS execution, browser image editor, audio or celebration
animation is qualified by this pass.
