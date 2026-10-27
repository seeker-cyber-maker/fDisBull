# Unreleased 0.20 candidate

This is development work, not a version bump, release, or complete game recovery.

- DOS COM loading and debugging support complements existing MZ handling.
- The DOSBox-X dot-mode option provides a controlled visible window; agent input remains separate from host input.
- An explicit processor decoder seam adapts the existing native and CIL decoders and supports a synthetic processor. It is not generic persisted VM analysis or execution.
- DOS data-watch stops report a post-stop CS:IP when available, or null; the watched data address is not treated as the resume PC.
- A read-only AGI 2.917 logic inspector traverses a documented partial decoder subset. Unknown instructions stop their paths; it is not an AGI runtime or full implementation. See [AGI logic](AGI_LOGIC.md).

## Verification and limits

The integrated local Python suite passed 1,169 tests with 94 skipped. Focused tests with the configured Linux layers DOSBox-X binary passed 49 tests for COM, window, native contract and processor seams, and 24 debugger/semantics tests including a real watch-stop check. These are scoped checks, not a blanket platform qualification. See [spectator verification](VERIFICATION-SPECTATOR-CLOUD.md) for the synthetic GUI test and its limits. The stable non-layers patch was not built in that run; macOS remains unverified.


UIL and target-language generators remain future work. A playable harness is a separate, weaker gate than full implementation recovery; neither is claimed here.

## Recovered development work

This candidate also adds typed input macros and owned held-key leases, bounded
movement with explicit stop and progress contracts, game-coordinate navigation
geometry and readiness checks, run-scoped runtime observations, and persisted
bounded bitvector proofs. A proof describes the supplied model under its stated
assumptions; it does not establish that the model matches the game. Bindings must
be re-established after state restoration. Movement rejects unqualified geometry
and reports arrival separately from a qualified stop.

The combined layers backend passed 414 configured native tests, including
synthetic held-key ownership and movement checks. The exact optional Z3 dependency
was used in proof tests. Both combined backend patches replayed against the pinned
source and matched their 28 stable and 29 layers manifest hashes; only the layers
backend was built locally. These checks do not establish general game or macOS
compatibility.
