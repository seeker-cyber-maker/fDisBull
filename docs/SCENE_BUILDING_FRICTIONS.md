# Scene-building friction and small improvements

The first two proposals now have a shared source implementation in
[bounded control and receipt assembly](BOUNDED_NATIVE_SCENES.md). Its runtime
qualification is reported separately from the original investigation. The
remaining proposals below are not implemented capabilities.
Priorities weigh the expected reduction in repeated setup against implementation
cost and confidence from the examples. Keep one active question and preserve
the checks needed for that question; the aim is less redundant work, not a
weaker evidence boundary.

| Priority | Friction and proposed improvement | Benefit / cost / confidence |
| --- | --- | --- |
| 1 | **Reusable receipt assembly — source slice implemented.** `ReceiptAssembler` shares ordered observation/input/frame checks, hash-once bounded snapshots, explicit completed edge endpoints and artifact roles. Each scene retains its own material source/outcome guards. The bridge exporters now consume it; other scene exporters can migrate as needed. | High / medium / high: fresh KQ1 export qualifies the slice; no whole-game or supplied-record authenticity claim. |
| 2 | **Shared bounded native controller — source slice implemented.** `BoundedNativeController` shares guest/wall budgets, keyboard settlement, uncertainty latches and raw-result retention. The AGI adapter preserves its source stop observers and execution gate; common cleanup retains independent callback failures. Qualified pending states remain in the route. | High / medium / high: fresh KQ1 route/control and authored failure checks qualify the slice; other backend/route qualification remains separate. |
| 3 | **Cheap coordinate alignment.** Provide an optional bounded alignment helper that records the actual sampled position, guest time, settling and overshoot. Use a coordinate watch only when an exact write matters; use an admissible range when the source and collision geometry support it. Never set the coordinate to make a route pass. | Medium / medium / medium: sampled movement can coast past a requested point, while not every route needs pixel-exact proof. |
| 4 | **Explicit frame/state coherence.** Make it easier to request a fresh frame only at a meaningful visual boundary and to retain the frame ID, mode and capture time alongside memory reads. A last-completed frame and a later state read are not automatically atomic. Preserve both when a modal or interrupted action leaves only partial evidence. | Medium / medium / high: avoids expensive frame capture on every poll without inventing freshness. |
| 5 | **Coordinate-domain adapters.** Offer narrowly scoped adapters that derive source-backed picture, viewport and collision extents for supported engines, then show what is known or unknown. A future NES adapter should qualify its own camera and pixel transforms from the target and observation; it must not infer them from the platform name or turn an edge candidate into a teleport route. | Medium / medium–high / medium: useful across games, but engine and camera conventions vary. |

For each proposal, success means an author can reuse a qualified binding and
produce the same bounded, source-linked scene with fewer repeated operations.
It does not mean automatic whole-game recovery, mandatory fresh native runs, or
replacement of a protocol's per-stop checks. A scene should exercise its actual
player actions and relevant stale/refusal behavior; full-suite or repeated
success runs need a project requirement, a new risk, or a changed conclusion.
