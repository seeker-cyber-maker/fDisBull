# Content, engine adapters and reusable players

Design direction, 27 October 2026. These interfaces are a proposal for later
work; 0.18's scene improvements do not implement an AGI/SCI extractor or VM.

The useful target is two independently testable results: recovered game content
and rules, and a player that can use them. A playable reconstruction also needs
the engine semantics between those two. Keeping all three separate prevents
game-specific coordinates or puzzle solutions from becoming engine behavior.

| Component | Responsibility | Reuse boundary |
| --- | --- | --- |
| Recognizer | Identify candidate script language, engine family/version and resource layout from explicit evidence. Record competing hypotheses and unknowns. | Recognition logic reused per language/engine family. |
| Content adapter | Decode rooms, objects, messages, scripts, conditions, commands and resource references into a typed representation with original byte spans/hashes. | Decoder reused; each game's content remains its own pack. |
| Engine runtime | Implement instruction, variable, event, rendering and input semantics. Unknown opcodes remain explicit unsupported operations. | Reusable for compatible engine versions, with declared differences. |
| Player | Observe, choose goals/actions, plan and execute using the same public input/actions. Store learned policies separately from recovered rules. | General navigation/planning transfers; game facts and puzzle solutions do not silently transfer. |
| Original-game oracle | Compare bounded sequences against the original game through fDisBull checkpoints, inputs, memory, pixels and traces. | Reusable comparison machinery; each case binds its own source/version and setup. |

For the original AGI editions, Police Quest I and King's Quest I are promising
successive targets. ScummVM's [AGI detection table](https://github.com/scummvm/scummvm/blob/master/engines/agi/detection_tables.h)
includes both, and its [AGI logic loader](https://github.com/scummvm/scummvm/blob/master/engines/agi/logic.cpp)
shows resource code and text being decoded separately from native x86 code.
This supports the feasibility of an engine-family adapter; it does not establish
that fDisBull has recreated either game. Identify the actual supplied edition
before choosing an adapter. An SCI remake requires the corresponding SCI
semantics and resource decoder, rather than treating its scripts as AGI.

The first practical experiment should recover one room, one object interaction,
one blocking condition and one transition. Replay identical inputs from matched
original/reconstruction setups and compare the visible result plus explicit
state observations. Extend coverage only after those cases pass. A finite route
does not prove full-game fidelity, exact original source recovery or deterministic
replay. Presence, absence, occlusion and unknown observations must stay distinct.

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
5. `enable` selects a versioned, qualified adapter for that project. Candidate
   modules remain separate from accepted ones and have a reversible selection.
   Enabling arbitrary generated Python directly from a content bundle is outside
   this design. Publication and broader activation remain separate decisions.

The module should first earn decoder qualification, then bounded runtime
qualification, then game-route coverage. This allows autonomous implementation
work without turning recognition confidence into a claim that the engine is
already correct. Prioritize probes by expected decision value per cost alongside
confidence: resolving one unknown branch can be more useful than exhaustively
decoding unrelated resources.

0.18 scene bundles are a smaller existing boundary: portable declarative scene
knowledge with clean evidence and fresh runtime checks. A later content pack
would add scripts/resources and VM semantics through a separate format and
qualification process.
