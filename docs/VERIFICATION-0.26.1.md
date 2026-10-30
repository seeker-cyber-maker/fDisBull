# 0.26.1 integration verification

This record accompanies the 0.26.1 source candidate. The intake baseline is
main `f159252761150ca2dd95eb12e16e515ce33f74fd`, which already contains PR #34
(`9e36da70ffd59dd3484a391b8132b809ef9bf87c`) and PR #35
(`ff4f08a6d4b337070b6e23ba403391366fb1e3e9`). PR #33 is integrated with its
reviewed head `8655d1c30a318323e5e1de8488bd92899e3ef96c`.

## Required acceptance

1. Preserve the main implementation of read-only reconciliation, unknown and
   partial original effects, selected DOS process termination and conservative
   access-stop interpretation.
2. Run focused combined source checks and both installed skill gates. Build
   and inspect core/player wheels, source archive and tool ZIP from the frozen
   candidate; check source/payload identity and private-input exclusions.
3. Qualify the current layers backend against its exact upstream baseline and
   applied source manifest, then verify the combined candidate on an owned
   private DinoPark copy. Keep original inputs unchanged, bind runtime/backend
   identities, and retain failed, unknown or budget-stopped results explicitly.
4. Require ordinary and all three native Linux jobs on the exact final source
   commit before creating the release tag. The layers offline-kit check must
   use genuine dependencies and Z3, and both bundled skill gates must pass.

## Source and evidence boundaries

Earlier PR reports remain attributed evidence at their recorded source/runtime
identities. They are not substituted for a fresh combined native check. Native
checkpoint restoration and journal reconciliation have separate obligations:
restore may change the game state, while the reconciliation interval must be
read-only. Matching observations do not recover a missing reply or certify a
partial original action.

Fresh combined results and their sanitized evidence will be recorded after
execution. Raw game copies, save inputs, native states, transcripts and project
databases stay private outside this checkout. Final GitHub CI and the annotated
tag provide the exact-commit acceptance readback once that commit exists.
