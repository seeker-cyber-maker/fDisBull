# Scene-building friction and small improvements

The first four proposals now have a shared source implementation in
[bounded control and receipt assembly](BOUNDED_NATIVE_SCENES.md). Its runtime
qualification is reported separately from the original investigation. The new
[alignment/frame-state pair](evidence/native-alignment-coherence-2026-11-01/README.md)
qualifies the bounded KQ1 slice; earlier controller results are not substituted
for those fresh observations. The coordinate-domain
adapter proposal below remains distinct from implemented domain metadata.
Priorities weigh the expected reduction in repeated setup against implementation
cost and confidence from the examples. Keep one active question and preserve
the checks needed for that question; the aim is less redundant work, not a
weaker evidence boundary.

| Priority | Friction and proposed improvement | Benefit / cost / confidence |
| --- | --- | --- |
| 1 | **Reusable receipt assembly — source slice implemented.** `ReceiptAssembler` shares ordered observation/input/frame checks, hash-once bounded snapshots, explicit completed edge endpoints and artifact roles. Each scene retains its own material source/outcome guards. The bridge exporters now consume it; other scene exporters can migrate as needed. | High / medium / high: fresh KQ1 export qualifies the slice; no whole-game or supplied-record authenticity claim. |
| 2 | **Shared bounded native controller — source slice implemented.** `BoundedNativeController` shares guest/wall budgets, keyboard settlement, uncertainty latches and raw-result retention. The AGI adapter preserves its source stop observers and execution gate; common cleanup retains independent callback failures. Qualified pending states remain in the route. | High / medium / high: fresh KQ1 route/control and authored failure checks qualify the slice; other backend/route qualification remains separate. |
| 3 | **Cheap coordinate alignment — source implemented and bounded KQ1 pair verified.** `control.align` accepts exact coordinates or inclusive ranges along one axis/unit-diagonal leg, records actual samples and settling, and caps callback/owned-stop execution too. The adapter supplies source safety, domains and ordinary start/stop input. Overshoot or drift stops the attempt without automatic reversal, retry or restore. Use a coordinate watch only when the exact write matters. | Medium / medium / medium: ranges can avoid needless exact-stop work, while sampled movement can still coast past the goal. |
| 4 | **Explicit frame/state coherence — source implemented and bounded KQ1 pair verified.** `control.capture_frame_state` retains a stopped status/state/frame/state/status bracket and can poll cheap status for freshness at meaningful visual boundaries. Session/mode/frame/capture-revision checks and an optional state projection preserve unknowns; a stable bracket is not atomic. Render ticks and capture RPC revision remain separate. A stale timeout preserves the last status without automatically advancing or capturing again. | Medium / medium / high: reduces repeated image work while keeping freshness and readiness separate. |
| 5 | **Coordinate-domain adapters.** Offer narrowly scoped adapters that derive source-backed picture, viewport and collision extents for supported engines, then show what is known or unknown. A future NES adapter should qualify its own camera and pixel transforms from the target and observation; it must not infer them from the platform name or turn an edge candidate into a teleport route. | Medium / medium–high / medium: useful across games, but engine and camera conventions vary. |

For each proposal, success means an author can reuse a qualified binding and
produce the same bounded, source-linked scene with fewer repeated operations.
It does not mean automatic whole-game recovery, mandatory fresh native runs, or
replacement of a protocol's per-stop checks. A scene should exercise its actual
player actions and relevant stale/refusal behavior; full-suite or repeated
success runs need a project requirement, a new risk, or a changed conclusion.

Choose fresh visual captures where they can change the next decision, such as
after settled room entry or completed output. Routine progress can use bounded
state/status polls. Never resume a foreign stop or an unsafe state for a cleaner
picture. Supplied replay evidence can inform these choices, but does not replace
fresh qualification of a changed controller binding.
