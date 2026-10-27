# Unreleased 0.20 candidate

This is development work, not a version bump, release, or complete game recovery.

- DOS COM loading and debugging support complements existing MZ handling.
- The DOSBox-X spectator option provides a controlled visible window; agent input remains separate from host input.
- An explicit processor decoder seam adapts the existing native and CIL decoders and supports a synthetic processor. It is not generic persisted VM analysis or execution.
- DOS data-watch stops report a post-stop CS:IP when available, or null; the watched data address is not treated as the resume PC.
- A read-only AGI 2.917 logic inspector traverses a documented partial decoder subset. Unknown instructions stop their paths; it is not an AGI runtime or full implementation. See [AGI logic](AGI_LOGIC.md).

## Verification and limits

The integrated local Python suite passed 1,169 tests with 94 skipped. Focused tests with the configured Linux layers DOSBox-X binary passed 49 tests for COM, window, native contract and processor seams, and 24 debugger/semantics tests including a real watch-stop check. These are scoped checks, not a blanket platform qualification. See [spectator verification](VERIFICATION-SPECTATOR-CLOUD.md) for the synthetic GUI test and its limits. The stable non-layers patch was not built in that run; macOS remains unverified.


UIL and target-language generators remain future work. A playable harness is a separate, weaker gate than full implementation recovery; neither is claimed here.
