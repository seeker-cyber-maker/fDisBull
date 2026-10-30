# Lost in Time UIL contract

## Definition

UIL is the executable interaction representation connecting a player's semantic action to a supported game behavior. This implementation uses **fDisBull's existing `fdisbull-il-1` format with `role: "uil"`**, together with its **`fdisbull-scene-1` native action format**. It does not define a competing general-purpose language or label the entire authored world as recovered original code.

The contract has three parts:

| Part | Authority | Current implementation |
|---|---|---|
| Text world | The adaptation's deterministic state runner | `text/reference-runtime/Lost_in_Time_World.json`, `state_engine.py`, `text/bridge.py` |
| Recovered behavior | A bounded translation of selected original script branches | Six files in `bilge_text/programs/`, the new poster model in `fast_pipeline/`, plus the retained bucket example |
| Native interaction | The running original DOS executable | Shared source target packet, live VM binding and fDisBull scene actions |

The narrator resolves intent and presents results. It does not create inventory, change flags or skip prerequisites. Native and adaptation state remain distinct; a model result is not evidence that a native click occurred.

## Required identity and evidence

A native object binding needs the **game release, resource/script, camera, subview or presentation, puzzle state, selected item and raw hotspot ID**. A raw number or coordinate pair alone is insufficient.

The canonical bilge packet, `bilge_source/bilge_interface_evidence.json`, contains **18 target records and 31 source action rules**. It records resource hashes, routine/opcode/operand offsets, VM byte offsets, geometry and source conditions. Runtime qualification remains a separate observation: static target status fields are deliberately unknown until a current frame and state have been checked.

The hold extension, `native_progress/fast_source/hold_interface_evidence.json`, adds five targets and twenty rules. The combined investigator outline contains **23 targets, 51 rules and 12 source views**. Target and script counts are coverage, not complete executable scenes. A separate archive inventory found 61 TOT scripts; it establishes candidate identities and references, not 61 rooms or reachable transitions.

Two concrete entry bindings demonstrate the rule:

| Action | Hold camera | Raw target | Selected item | Visit state | Native rectangle, XYWH |
|---|---:|---:|---:|---|---|
| First descent | 1 | 11 | Lamp, item 1 | Not yet visited | `[246,118,57,30]` |
| Revisit | 1 | 21 | Empty hands, −1 | Already visited | `[246,118,57,30]` |

The geometry is identical while the actionable identity differs. These branches were both exercised in the original game; visit count reached two while the drained water and corkscrew state persisted.

## Coordinate contract

Use original **320×200 guest-frame pixels**, with positive X to the right and positive Y downward. Source rectangles are `[x,y,width,height]`. fDisBull scene masks use half-open `[left,top,right,bottom]`, so convert to `[x,y,x+width,y+height]`. Avoid edge clicks and overlaps.

Popup objects store local rectangles. Read the current origin from VM i32 byte offsets **220 and 224**, add it to the local X/Y, and require equality with the live active rectangle at **17964 + 8 × raw target ID**. Also check positive dimensions, current presentation and the source conditions.

Examples from the qualified route:

| Object | Local XYWH | Observed origin | Live XYWH | Tested click |
|---|---|---|---|---|
| Lamp | `[48,29,19,32]` | `[8,52]` | `[56,81,19,32]` | `[65,96]` |
| Oil bottle | `[38,30,35,42]` | `[144,56]` | `[182,86,35,42]` | `[199,105]` |
| Pump handle | `[14,27,105,40]` | `[48,46]` | `[62,73,105,40]` | `[110,90]` |
| Corkscrew | `[79,41,14,11]` | `[112,36]` | `[191,77,14,11]` | `[197,82]` |

These are recovered observations. The resolver translates live geometry, while the complete route's visual recognizers and postconditions remain qualified for the recorded popup placements. Arbitrary placements have not been qualified.

Inventory selection is also dynamic: locate item 14 in the current inventory list and read its current 18×18 slot. Do not store its historical screen point as a universal oil-button coordinate.

## Separate presentation, effects and completion

Each native action follows this sequence:

1. Read current script, camera, subview, held item, relevant flags, registered geometry and frame identity.
2. Recognize the supported presentation. An old rectangle may remain under a popup or after a script-name transition.
3. Check a fresh context token and source conditions. Construct the click from the current target.
4. Deliver one bounded guest input, then evaluate its explicit postcondition. Stop on unknown delivery or incomplete execution; do not repeat automatically.
5. Observe again before another action. Save only at a qualified stable boundary.

Three source/native observations make these stages necessary:

- **First water inspection:** the rat-response message appears with `water_checked` byte 12661 still zero. Its acknowledgement precedes the write to one. The UIL projection models the retained effect after that boundary.
- **Pump work:** byte 12659 becomes one while the final message and popup remain visible. The later acknowledgement closes the inset and removes the water hotspot. A drain flag is not by itself proof of a quiet actionable scene.
- **Chain close-up:** animation/request fields were already −1 while target 3 was only `[191,36,0,0]`. Waiting produced `[191,77,14,11]`. Idle animation does not establish complete target registration.

First-entry narration can also carry camera 0/subview 1, the same selector used by the cask close-up. Only the close-up has the qualified translated object geometry and matching presentation.

## Headless branch interface

`bilge_text/play.py` accepts JSON lines. `observe` returns the exact required typed inputs and the branch's scope. `execute` requires that complete explicit state and validates the catalog/program hashes before invoking fDisBull.

```json
{"op":"observe","branch_id":"bilge.water.first"}
{"op":"execute","branch_id":"bilge.water.first","state":{"$camera":1,"$selected_item":-1,"$water_checked":0}}
```

The successful request returns the retained effect `{"$water_checked":1}` and its source text reference. The interface does not silently persist a world or control the native game. A wrong guard produces no retained effects.

Four programs preserve selected response leaves: repeated water, small pipe on water, stuck pump and the pump's gentleness response. Two programs are explicitly partial semantic projections: first water and successful pump work. Their omitted animation, MENU helper and blocking-input operations remain listed as source evidence.

Only the declared retained puzzle effects are compared with native completion. Evaluator guard passthrough, including `$subview`, is not an established native output. Source text identity is retained; automated comparison does not establish OCR or equality of the complete native text-event stream.

## Minimum conditional code acceptance

Accept a claim about a specified action, state domain and result boundary. The minimum is source identity and entry binding; a complete relevant slice with numeric semantics and ordered effects; closed relevant dependencies or an explicitly narrowed claim; a satisfiable guard plus source/model effect agreement; and a receipt stating assumptions, unknowns and the claim ceiling. A decoded description alone is insufficient. An unimplemented helper cannot silently become a no-op.

Reuse accepted decoder primitives and helper summaries when their identities and assumptions match. A cache must also bind candidate UIL, typed interface/defaults, relevant bindings, outputs, semantic/checker policy and observation boundary. Current solver records are not independently checkable proof objects, and a reused receipt must say that it is reused. The public requirements in [PR #20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) propose this integration; the production service/cache is not implemented by this experiment.

Conditional behavior, ordinary-play reachability, current target readiness, committed native effects and save persistence are distinct claims. A helper-free code leaf can be accepted without replaying the native route when its source profile is already bound. A new native click still needs the current script/presentation, availability, registered geometry, transform and input readiness.

## New poster slice and Z projection

`fast_pipeline/` builds an investigator outline, 51 typed execution-blocked UDL descriptions, seven executable UDL/UIL branch models and two real candidate Z packages. Five executable models preserve selected response leaves; two are retained-effect projections. The six bilge models reuse the prior qualification; the poster branch is new. The actual candidate schema is `fdisbull-il-scene-1` from PR18 commit `c107d1576d46d7dc353c8043cb81be5005e8926b`, with common typed declarations/defaults and `partial: true`. UDL and UIL share `fdisbull-il-1`; changing role metadata is not semantic compilation.

The poster entry is camera 0, empty hands, handler 2758. Its byte counter selects text31 at zero, text32 at one and text33 otherwise, then increments modulo 256 with a signed read. The selected branch has no script-helper calls. The pinned ScummVM interpreter profile connects signed reads to unsigned-byte storage. All 256 counter values agree with the direct rule, and two wrong-guard inputs refuse without effects. This is conditional source-profile evidence, not a formal proof of original DOS interpreter equivalence.

The source poster rectangle is `[50,59,48,35]` in guest pixels, joined to raw target 13 and its handler. The target is unavailable at counter −1. Although the raw conditional handler model evaluates −1, the Z object hides that sentinel and rejects a direct action without state change. No new poster click has been qualified in the native harness.

The Z packages are investigator interfaces; some bilge context IDs expose model state. Player-knowledge parity remains unqualified. Private puzzle summaries must not become narrator observations. The complete authored adventure and actual ChatGPT Live integration retain their separate scope.

## Current qualification ceiling

The complete authored text adventure is playable. The source UIL subset is executable. The original-game hold/bilge route passed 35 stages, including 30 scene actions, one explicit neutral UI gesture and four waits, followed by a fresh-process save reopen. These results establish the documented slice. They do not establish a complete Gob interpreter, a whole-game source port or a ChatGPT Live/voice deployment.

Primary evidence: `bilge_source/SOURCE_REPORT.md`, `bilge_source/bilge_interface_evidence.json`, `bilge_text/catalog.json`, `bilge_text/native_comparison.json`, `native_progress/route.json`, `native_progress/replay01/qualification.json` and `native_progress/reopen01/verification.json`.

Fast-pass evidence: `native_progress/fast_source/FAST_SOURCE_REPORT.md`, `fast_pipeline/README.md`, `fast_pipeline/benchmark.json`, `fast_pipeline/poster_validation.json` and `native_progress/FAST_PROOF_REVIEW.md`. The final warm rebuild is 162.736 ms, including finite-domain and candidate-player checks; prior recovery and analyst time are excluded. No new native run was made for that pass.
