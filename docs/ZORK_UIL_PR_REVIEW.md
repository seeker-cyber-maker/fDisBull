# Zork conversion: upstream and PR review

Baseline review on 2026-10-29; inventory refreshed at 23:05 UTC, before this conversion PR.
Repository: https://github.com/seeker-cyber-maker/fDisBull
Current main: `031b53eb953bfdc1d0e23c0ed49441031bad6e06`.
Title/body/status and changed paths were retrieved for every PR. All discussion timelines were retrieved; all substantive nonbot comments were read. Key UIL/Zork source and relevant RFC documents were read. This is not a full line-by-line code review of every unrelated PR.

## Complete PR inventory

There are 23 existing PRs: 20 open and 3 merged; no additional closed-unmerged PRs.
The initial second 100-item API page was empty. The final refresh added PR #23; its complete diff, changed paths and review discussion were read as well.

| PR | State | Title | Relevance to Zork conversion |
|---|---|---|---|
| [#1](https://github.com/seeker-cyber-maker/fDisBull/pull/1) | Open draft | test: cover DOS keyboard input after mid-dialog restore | Native checkpoint keyboard coverage; not conversion. |
| [#2](https://github.com/seeker-cyber-maker/fDisBull/pull/2) | Open | Improve investigation methodology and ship all skill references | Evidence/authority, claim ceilings, packaged guidance. |
| [#3](https://github.com/seeker-cyber-maker/fDisBull/pull/3) | Open | Define the UIL export boundary and agent RFC process | Producer owns semantic recovery/export/receipt; downstream player/compiler remains separate. Core boundary doc already identical in main. |
| [#4](https://github.com/seeker-cyber-maker/fDisBull/pull/4) | Open | test/docs: distinguish keyboard delivery from delayed application polling | An accepted input is not a completed action; no automatic retry. |
| [#5](https://github.com/seeker-cyber-maker/fDisBull/pull/5) | Open | docs: separate state completion from UI-ready pre/post screenshot captures | Distinguish semantic, display and persistence boundaries. Doc already identical in main. |
| [#6](https://github.com/seeker-cyber-maker/fDisBull/pull/6) | Open | docs: record PQ1 runtime-resource layer gap | Version-bound runtime-resource authority; both changed docs already identical in main. |
| [#7](https://github.com/seeker-cyber-maker/fDisBull/pull/7) | Open draft | RFC: supplement UIL events with a linked interface description | Commands/interfaces must link to semantic events; unknown interface behavior stays explicit. Doc absent from main. |
| [#8](https://github.com/seeker-cyber-maker/fDisBull/pull/8) | Open | Document runtime navigation and observation capability ladder | Observation unknowns, bounded navigation, qualified resource/actor resolution. |
| [#9](https://github.com/seeker-cyber-maker/fDisBull/pull/9) | Open | docs: qualify content readiness separately from stable scene chrome | Source facts, requested/displayed state and current readiness remain different. Doc absent from main. |
| [#10](https://github.com/seeker-cyber-maker/fDisBull/pull/10) | Open | Design semantic input macros, navigation geometry, and UIL world IR | UIL is venue-neutral semantic model; Zork projection is bidirectional; loss has multiple dimensions. |
| [#11](https://github.com/seeker-cyber-maker/fDisBull/pull/11) | Open | RFC: define UIL invariants and bounded solver proof scope | Source/version-bound checks, unknown vs false, finite proof limits, R119/R88 distinction. Doc absent from main. |
| [#12](https://github.com/seeker-cyber-maker/fDisBull/pull/12) | Merged 2026-10-28 | 0.20: movement, readiness, bounded proofs, dot-mode and interpreter foundations | Runtime and proof foundations; no full UIL runtime/game conversion. |
| [#13](https://github.com/seeker-cyber-maker/fDisBull/pull/13) | Open draft | Define the intent recovery pipeline | Structural + behavioral recovery, source adapters, UDL/UIL blueprint; relevant content is in main with revisions. |
| [#14](https://github.com/seeker-cyber-maker/fDisBull/pull/14) | Open | Amend intent pipeline with recovery contracts and acceptance cases | Ordered effects, waits, partial actions, persistence, hidden-information policy, progressive scenes, Z text. Main contains revised documents. |
| [#15](https://github.com/seeker-cyber-maker/fDisBull/pull/15) | Open | Document DinoPark save, navigation and purchase feedback | Native gameplay lessons; not Zork semantics. Doc absent from main. |
| [#16](https://github.com/seeker-cyber-maker/fDisBull/pull/16) | Open draft | docs: record KQ1 assisted travel benchmark handoff | Native assisted travel evidence; not Zork semantics. Doc absent from main. |
| [#17](https://github.com/seeker-cyber-maker/fDisBull/pull/17) | Open | RFC: UDL mappings, UIL intents and reusable UDC definitions | Original code → UDL mapping → UIL → UDC → code; most docs/examples incorporated in main. No automatic compiler/discovery implementation. |
| [#18](https://github.com/seeker-cyber-maker/fDisBull/pull/18) | Merged 2026-10-29 22:03 UTC | Add Z scenes over shared IL with bounded content-service requests | Existing pure-IL scene provider and standalone player protocol. This lands after v0.23 tag. |
| [#19](https://github.com/seeker-cyber-maker/fDisBull/pull/19) | Merged 2026-10-29 22:03 UTC | Connect DinoPark scenes to Z with original-backed DOS UDC | Original-backed native provider/lifecycle. Explicitly zero recovered semantic blocks. Lands after v0.23 tag. |
| [#20](https://github.com/seeker-cyber-maker/fDisBull/pull/20) | Open | Define minimum scene-proof requirements and measure the fast recovery path | Minimum claim-scoped source acceptance, dependency closure/reuse, partial Z envelope, guide-derived hypotheses. New docs absent from main. |
| [#21](https://github.com/seeker-cyber-maker/fDisBull/pull/21) | Open | docs: document media-only no-CD rip scope and music-loop risk | Media-size work, unrelated to Zork conversion. Doc absent from main. |
| [#22](https://github.com/seeker-cyber-maker/fDisBull/pull/22) | Open | Propose synthetic HUD scenes and serializable agent context | Reusable typed observations below Z; snapshots not native saves. Documentation only, absent from main. |
| [#23](https://github.com/seeker-cyber-maker/fDisBull/pull/23) | Open | Add native GOG installer unpacking without Wine | Optional native extraction; no game semantic conversion. See the extraction boundary finding below. |

### PR #23 extraction boundary

At head `0778ea4b08cca69b5aa8c8f72b9fb9588c886024`, `unpack_gog` checks that
the destination is new but does not reject Git ancestry. This agrees with the
[existing P1 review](https://github.com/seeker-cyber-maker/fDisBull/pull/23#discussion_r4418788029).
Its documented private-output boundary therefore needs enforcement before
adoption. This conversion does not depend on that unmerged extractor and keeps
its licensed inputs and generated game payloads outside the checkout.

### Previous saved results

The retrieved previous experiment implemented two rooms, the mailbox and
advertisement, and seven command forms. Its explicit exclusions included the
general parser, conditional exits, turn processes, RNG, scoring and persistence.
That was a useful bounded prototype, not a full game conversion. A separate
browser bridge drove the original DOS program. A transcript titled
`Compile_Zorklike_Game_Script` described Lost in Time, not Zork, and was excluded
from Zork evidence. An older experiment ZIP could not be downloaded in this
session; its contents are not claimed to have been inspected.


## Existing Zork implementation

`src/fdisbull/zork.py` / `zork_worker.py` provide a live raw-v3 story harness through separately selected Jericho 3.3.1/Frotz.
This executes the original story; it is not recovered UIL. `observe` is passive, while `command("look")` is an actual guest command.
A command failure/timeout requires reset or restore; checkpoints bind story/interpreter/Jericho/native-library identities and seed.

`src/fdisbull/zmachine.py` is explicitly a bounded inspector and partial v3 instruction/Z-text decoder. It does not execute a VM.

`src/fdisbull/zork_recovery.py` recovers only the exact R88 story's first/repeated mailbox-open path:
- Story SHA-256: `0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.
- Direct object global 0x86 must resolve to object 160.
- Child must be object 161, with no sibling and selected property/attribute/name constraints.
- Instructions at 0x80a3 and 0x80a6 set attributes 11 and 3.
- Source spans, text abbreviations/object names/list formatting and action-entry witnesses are retained.
- Parser/object binding, turn loop, global processes and all other object/list states are explicitly unknown/out of scope.

The public verification receipt compares first/repeated mailbox text and selected mapped fields against DOS and Jericho, exercises checkpoint/reopen/isolated IL paths, and states that no full RAM/RNG/parser/world equivalence is established. This evidence is reusable for its stated slice; it cannot qualify a complete game.

Source:
- https://github.com/seeker-cyber-maker/fDisBull/blob/031b53eb953bfdc1d0e23c0ed49441031bad6e06/src/fdisbull/zork_recovery.py
- https://github.com/seeker-cyber-maker/fDisBull/blob/031b53eb953bfdc1d0e23c0ed49441031bad6e06/docs/ZORK_HARNESS.md
- https://github.com/seeker-cyber-maker/fDisBull/blob/031b53eb953bfdc1d0e23c0ed49441031bad6e06/docs/evidence/zork-2026-10-29/verification.json

## Existing UIL/UDC capacity

`fdisbull-il-1` has typed bool / signed and unsigned 8/16/32/64-bit scalars.
Supported blocks: set, add, subtract, if, require, text, load_graphic, play_sound, click.
Conditions: eq, bit_test, not, and.
Limits: 64 KiB, 1,024 nodes/conditions, depth 32.
There are no generic calls, loops, indexed state/object collections or autonomous processes. Switching legacy role `udl` to `uil` only changes metadata.

The pure scene envelope `fdisbull-il-scene-1` admits 32 programs, 64 contexts, 256 objects, 1 MiB.
One authoritative backend owns state; one context must match. Public metadata omits private state/program/evidence; partial coverage remains explicit.
The player adds no game semantics. Media/input remain pending host plans in v1.
The scene service supplies only in-memory checkpoints, not durable saves.

The original-backed DOS UDC rebuilds preserved original bytes/resources and may select original backings for a tiny proved register subset. A no-semantic-block build reports `original_bytes_only`. Emitted bytes running successfully are not a completed UIL conversion.

A complete Zork conversion therefore needs an explicit extension or independently executable target representation preserving all required control, object, memory, parser, scheduling, text, RNG and persistence behavior. An opaque original story attachment or new metadata label would not satisfy the semantic recovery request.

## Contracts to apply

1. **Single semantic authority.** UDL maps originals into UIL; UDC realizes shared semantics. Keep source names/addresses/private evidence separate from public observations.
2. **Preserve source identity.** Purchased R88 serial 840726 is distinct from public-source R119 serial 880429. A bounded matching trace does not erase this distinction.
3. **Complete claimed closure.** Every relevant operation is mapped, summarized by a qualified helper, or explicit unresolved obligation. Narrow unsupported branches honestly or reject/delegate them.
4. **Guard + effect agreement.** A satisfiable input witness plus appropriate finite branch/model comparisons must cover the stated domain. Do not call a sample trace or two models sharing a faulty decoder a proof of everything.
5. **Ordered side effects.** Preserve intermediate commits, events, random/time consumption, failure and cancellation effects. Equal final state alone may be insufficient.
6. **Input/interface fidelity.** Parser words, context, object binding, action availability and response are part of the interface. A semantic direct call is distinct from original parser execution.
7. **Persistence boundaries.** Evaluator snapshots, original saves and external persistence are separate. Restoring observations never grants fresh action tokens.
8. **Unknown remains unknown.** Missing room/exits/objects/readiness is not false or absent. Partial inventory cannot prove completeness.
9. **Qualification reuse.** Bind source/model/mapper/typed interface/defaults/assumptions/helpers/checker/runtime identities. Reuse validated receipts instead of repeating unrelated native verification.
10. **Private game payloads.** Main AGENTS.md requires story files, original bytes, native states, byte-retaining DBs and raw private deliveries to remain outside Git/tool packages. Generic code, synthetic tests and sanitized receipts can be committed.

## Gaps in upstream and the reviewed PRs before this conversion

- Full Zork source recovery, complete Z-machine semantics and complete original parser/turn-loop semantics.
- Generic UIL calls/processes/collections and the proposed UDC definition catalog.
- Automatic source-to-scene backward effect slicing/dependency closure and acceptance cache (#20).
- Automatic whole-game Z export/streaming beyond the current bounded envelope (#20).
- Persistent synthetic observation profiles/HUD snapshots/deltas (#22).
- Full game equivalence proof; solver results remain scoped.

## Review limits and next implementation advice

Use current main's #18/#19 protocol pieces rather than assuming the attached v0.23 tag contains them.
Retain existing v1 behavior; any larger executable semantic profile should be versioned, explicit, validated, and fail closed on missing operations.
Prove a real export can execute without the source story, original interpreter, Jericho or source database; otherwise it is a harness, preservation or reference path.
Separate structural/export completeness from behavioral qualification coverage.
A complete route proves that route, while tests for every implemented semantic primitive and negative/refusal cases support broader interpreter correctness.


## Resulting implementation

The new [word16 UIL conversion](ZORK_UIL.md) addresses whole-story low-level
semantic execution while retaining the evidence boundaries above. Its
[verification report](VERIFICATION-ZORK-UIL-2026-10-29.md) separates complete
export, a complete winning route, native-state agreement, persistence and
unverified game paths. No unrelated PR was merged as part of this work.
