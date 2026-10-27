# Content recovery and the UIL export boundary

Design direction, 27 October 2026. These interfaces are a proposal for later
work; 0.18's scene improvements do not implement an AGI/SCI extractor or a
Universal Interaction Language (UIL) exporter.

The useful fDisBull target is recovered game content and rules expressed as
evidence-backed UIL. A playable reconstruction, generated source tree or agent
player is a downstream consumer of that export. Keeping recovery and consumers
separate prevents game-specific coordinates, target-language choices or puzzle
solutions from becoming part of the recovered semantics.

| Component | Responsibility | Ownership boundary |
| --- | --- | --- |
| Recognizer | Identify candidate script language, engine family/version and resource layout from explicit evidence. Record competing hypotheses and unknowns. | Recognition logic reused per language/engine family. |
| Content adapter | Decode rooms, objects, messages, scripts, conditions, commands and resource references into a typed representation with original byte spans/hashes. | Decoder reused; each game's content remains its own pack. |
| Semantic lifter | Fold related low-level operations into typed scenes, entities, state, rules and events. Preserve unknown operations and competing interpretations. | fDisBull recovery work; lifted statements retain source and evidence links. |
| UIL exporter | Emit deterministic, consumer-neutral semantic source, source maps, unresolved capabilities and a bounded qualification receipt. | The fDisBull responsibility ends at this export. |
| Original-game oracle | Compare bounded sequences against the original game through fDisBull checkpoints, inputs, memory, pixels and traces. | Reusable comparison machinery; each case binds its own source/version and setup. |
| Runtime, player and target generators | Compile or interpret UIL, present the world, verify objectives or translate it to another language. | Outside fDisBull; AEC and other consumers own their separate implementations and authority. |

For the original AGI editions, Police Quest I and King's Quest I are promising
successive targets. ScummVM's [AGI detection table](https://github.com/scummvm/scummvm/blob/master/engines/agi/detection_tables.h)
includes both, and its [AGI logic loader](https://github.com/scummvm/scummvm/blob/master/engines/agi/logic.cpp)
shows resource code and text being decoded separately from native x86 code.
This supports the feasibility of an engine-family adapter; it does not establish
that fDisBull has recreated either game. Identify the actual supplied edition
before choosing an adapter. An SCI remake requires the corresponding SCI
semantics and resource decoder, rather than treating its scripts as AGI.

The first practical experiment should recover one room, one object interaction,
one blocking condition and one transition into UIL. A separate reference
evaluator may replay identical inputs from matched original/recovered setups to
compare the visible result plus explicit state observations. Extend coverage
only after those cases pass. A finite route does not prove full-game fidelity,
exact original source recovery or deterministic replay. Presence, absence,
occlusion and unknown observations must stay distinct.

## Agent-authored extension contract

The proposed future framework lets an agent recognize a scripted language and
develop a module against a fixed contract:

1. `recognize` returns evidence, source hashes, family/version candidates,
   confidence, competing interpretations and a cost/reward estimate for the
   next decisive probe. File names alone do not establish semantics.
2. `decode` returns typed instructions/resources, control-flow edges, unresolved
   references and original spans. It must preserve bytes and all prior versions;
   guessed meanings stay hypotheses. Content is data, never agent instructions.
3. `describe_capabilities` declares supported versions, opcodes, resource types,
   input model and failure behavior. A partial adapter cannot label a budget stop
   or an unknown opcode as stable completion.
4. `validate` runs known opcode/resource cases, malformed/truncated-input cases
   and bounded comparisons against the original. Store capture identities and
   missing evidence explicitly; partial observations cannot establish equality.
5. `export_uil` produces a canonical semantic payload, source map, evidence
   index and validation receipt. Candidate exports remain distinct from
   bounded-reproduced ones. Arbitrary generated Python or another downstream
   implementation is not enabled inside fDisBull.

The module should first earn decoder qualification, then semantic-lifting
qualification, then bounded UIL comparison coverage. This allows autonomous
implementation work without turning recognition confidence into a claim that
the recovered source is already complete. Prioritize probes by expected
decision value per cost alongside confidence: resolving one unknown branch can
be more useful than exhaustively decoding unrelated resources.

0.18 scene bundles are a smaller existing boundary: portable declarative scene
knowledge with clean evidence and fresh runtime checks. UIL would add recovered
scripts, resources and semantic rules through a separate format and
qualification process. fDisBull stops at that format; AEC may compile it into a
cartridge, while an unrelated project may translate it into Python,
JavaScript or another target without becoming part of fDisBull.

The complete responsibility split is defined in the
[UIL export boundary](UIL_BOUNDARY.md).
