# From game investigation to reusable semantics: design notes and proposed backlog

This document records the conceptual direction alongside the 0.20 work, not a claim that the proposed pipeline has shipped. The processor seam in this candidate is minimal native/CIL/toy decoding—not an AGI or Z-machine module, generic persistence, or a complete VM. The COM and spectator changes are also candidate work; see their verification notes for the scope actually tested.

## Direction captured

- Text commands and graphical clicks are different input routes to underlying behavior. Investigate each route and the code it reaches; do not assume that identical-looking actions have the same implementation or effects.
- First map dispatch and guest control flow; use a probabilistic state-transition model only where the target or question warrants it. Text input does not by itself imply a stochastic model, and an interpreter need not have a text interface.
- The interpreter execution cycle can carry the guest game's logic. Input, rendering, and timing can also be outer scheduling or host services; investigate their actual boundaries rather than assuming that an outer loop alone is the game logic or that all logic lives outside the interpreter.
- A game-backed Zork-like interface can be an intermediate way to express recovered actions. UIL could then become an **independent representation** with a fixed input contract and variable outputs. Original code links remain provenance, not a runtime dependency of the independent representation.
- Views from assembly through C-like and Z-like forms to UIL may help focus analysis and limit abstraction. These are useful staged views, not mandatory or automatically lossless translation passes. UIL should map its pseudocode back to the relevant original code and evidence.
- Once semantics are sufficiently understood and supported by verified target-specific libraries, UIL and reusable macros may support generation for multiple languages or products. That is an architectural goal, not an established ability to trivially or automatically transcode arbitrary games today. Godot and iOS are prospective outputs, not delivered products.
- An agent playing as it investigates can collect context, exercise routes and help QA. It cannot alone establish that all code and possible behavior were recovered.

## Two distinct completion gates

1. **Playable harness gate:** enough qualified interfaces, readiness conditions and action/result checks exist for the declared scenario to play without further reversing. This makes no whole-game or complete-implementation claim.
2. **Full implementation-recovery gate:** code, data, guest and native behavior, side effects, and unresolved paths have been accounted for to an explicitly stated completeness standard, with independent verification. A harness can be an artifact of this work, but a working harness is not evidence that this stronger gate has passed.

## Proposed minimal model and backlog

These are design proposals beyond the implemented candidate seams, not features claimed by the skill. Approach, methodology, decision rules and verification belong in the skill; tools belong in the **0.20 PR**. Full generators and broader portability remain later work. Priorities should be revisited when actual target/tool constraints are known.

1. **Prove one scene end to end.** Choose one bounded scene and at least one natural action. Link input and readiness to the guest/native handlers and observable result; retain a contrasting control and unresolved paths. **Acceptance:** another investigator can reproduce the declared action and control on the stated versions, and distinguish observed from inferred claims.
2. **Make action semantics explicit.** Model an action, its arguments, preconditions, handler, effects and result, with references to evidence and separate verified versus hypothetical fields. Text and click adapters may map to the same action only when evidence supports it. **Acceptance:** one scene's authentic routes and outcome are captured without turning a diagnostic shortcut into ordinary reachability.
3. **Preserve layered provenance.** Record source file identity/offset, load/read/copy evidence, loaded/runtime generation, native coordinates and guest stream/PC where applicable; mark inferred or cross-session edges. **Acceptance:** a reviewer can follow at least one action from interface to behavior and locate missing links without treating a byte match as a traced load.
4. **Introduce a small UIL vertical slice.** Express only the established action semantics and source mapping, with explicit unknowns. State contracts for overflow, aliasing, timing, randomness and I/O where relevant; do not invent missing semantics. **Acceptance:** independent checks compare the original and representation on matched preparations and negative cases, while preserving differences and uncertainty.
5. **Add target macro contracts and one generated output.** Propose reusable, versioned mappings for operations such as displaying an image, specifying inputs, effects, constraints and platform assumptions. Allow user-authored libraries without assuming they are correct. **Acceptance:** one generated scene builds and matches the declared original behavior under differential replay, including a negative case; independent review checks semantics and provenance. One successful scene does not establish a universal compiler.
6. **Expand coverage and automation deliberately.** Use play-assisted exploration and static/runtime evidence to select missing paths; expose coverage and uncertainties rather than equating playthrough success with full recovery. **Acceptance:** harness and full-recovery gates are reported separately, with explicit evidence for each claimed scope.

## Evidence boundaries and immediate next questions

The implemented AGI decoder is a conservative static subset. Next practical validation is one reproducible authored scene with an action and contrasting control. Define output contracts and failure cases before claiming portability or broader automation.
