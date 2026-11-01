# Scene-building friction and small improvements

These are proposals, not implemented capabilities or new verification claims.
Priorities weigh the expected reduction in repeated setup against implementation
cost and confidence from the examples. Keep one active question and preserve
the checks needed for that question; the aim is less redundant work, not a
weaker evidence boundary.

| Priority | Friction and proposed improvement | Benefit / cost / confidence |
| --- | --- | --- |
| 1 | **Reusable receipt assembly.** Scene builders repeatedly bind the same source, backend, ordered observations, delivered inputs, frame identities and artifact hashes. A small receipt builder could validate those common fields once, expose incomplete pieces, and let each scene add its own material guards. For example, a KQ1 water action needs its observed source/message/effect link; ordinary movement polls need not rehash the same source. | High / medium / high: repeated across existing AGI scene exporters. |
| 2 | **Shared bounded native controller and transition stages.** Consolidate guest-time budgets, ordinary-input delivery, foreign-stop handling, cleanup and retention of known partial effects. Keep game-specific conditions in the route. Include qualified pending stages: the bottom-row collector first stopped at the expected west-border flag, then during normal new-room initialization before the actor was drawn. Neither was an original-game failure. Reuse must not hide an unknown reply, resume after a foreign stop, or label a restored continuation fresh. | High / medium / high: common logic appears across the bridge, cave and quest collectors. |
| 3 | **Cheap coordinate alignment.** Provide an optional bounded alignment helper that records the actual sampled position, guest time, settling and overshoot. Use a coordinate watch only when an exact write matters; use an admissible range when the source and collision geometry support it. Never set the coordinate to make a route pass. | Medium / medium / medium: sampled movement can coast past a requested point, while not every route needs pixel-exact proof. |
| 4 | **Explicit frame/state coherence.** Make it easier to request a fresh frame only at a meaningful visual boundary and to retain the frame ID, mode and capture time alongside memory reads. A last-completed frame and a later state read are not automatically atomic. Preserve both when a modal or interrupted action leaves only partial evidence. | Medium / medium / high: avoids expensive frame capture on every poll without inventing freshness. |
| 5 | **Coordinate-domain adapters.** Offer narrowly scoped adapters that derive source-backed picture, viewport and collision extents for supported engines, then show what is known or unknown. A future NES adapter should qualify its own camera and pixel transforms from the target and observation; it must not infer them from the platform name or turn an edge candidate into a teleport route. | Medium / medium–high / medium: useful across games, but engine and camera conventions vary. |

For each proposal, success means an author can reuse a qualified binding and
produce the same bounded, source-linked scene with fewer repeated operations.
It does not mean automatic whole-game recovery, mandatory fresh native runs, or
replacement of a protocol's per-stop checks. A scene should exercise its actual
player actions and relevant stale/refusal behavior; full-suite or repeated
success runs need a project requirement, a new risk, or a changed conclusion.
