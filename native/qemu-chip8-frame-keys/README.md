# CHIP-8 frame-owned keypad edges (native v6)

This package contains an incremental QEMU 10.0.13 patch that adds explicit,
stopped-state keypad ownership to the CHIP-8 analysis target. It builds on the
sealed v5 frame-sampling target and leaves the earlier v1-v5 packages and
runtime candidates intact.

The native owner represents a 16-key held set. A host submits an atomic batch
of unique press/release transitions using a token plus owner-generation and
CPU-state-generation compare-and-swap values. The CPU applies the whole batch
or none of it. A successful batch updates the architectural key mask and the
owner-held mask together. Repeated presses or releases of an already-matching
state are rejected. Each accepted key transition is counted; typematic repeat
is not modeled.

The owner cannot be claimed while manually supplied keys remain held. While an
owner is active, manual keypad updates are refused, including when the owned
set is empty. Detaching requires an empty set. This keeps legacy keypad input
from silently mixing with frame-owned edges.

A full checkpoint retains the logical active/held state and counters, but not
the process-local token. On restore, the new QEMU process rotates its epoch and
reports `needs-adoption`; the host must bind a fresh token with the adoption
command. Adoption never dispatches key events. Frame fences and key-owner
mutations are mutually exclusive. An FX0A wait remains architectural state
until the guest is explicitly resumed; accepted key input clears only the
native wait-stop attribution, not the wait itself.

## Wire surface

- `query-chip8-frame-keys`
- `x-chip8-apply-frame-key-edges(token, expected-generation, expected-state-generation, edges)`
- `x-chip8-adopt-frame-keys(token, expected-generation, expected-state-generation, held-mask)`
- `x-chip8-detach-frame-keys(token, expected-generation)`

Each successful mutator returns the complete `Chip8FrameKeysInfo` receipt.
The receipt identifies the CPU subset, device environment, process epoch,
owner token/validity/adoption state, owner and CPU generations, accepted edge
count, architectural and owner key masks, and sorted held keys. Key names are
single lowercase hexadecimal digits. A batch contains 1–16 unique keys.

VMState is version 6 with minimum version 6. Cross-version VMState restore is
not claimed. The older runtime packages remain separate so their saved states
continue to use their matching runtime identity.

## Build and qualification

The source patch applies to the sealed v5 source tree listed in
`source-manifest.json`. The v6 source configured and built locally for macOS
arm64. QAPI generation and linking succeeded. Fresh checks passed 18 native
cases, 72 retained cases on v6 (one obsolete v1-only CLS refusal deselected),
143 host/public cases and 323 retained DOSBox-X history/frame/undo/trial cases.
A v5 frame history created before this slice restored with the upgraded host
and original v5 binary, refused owned input without effects and advanced one
native tick; no v5 key-owner adoption is claimed.

Integrated coverage accounts for 3,277 distinct cases across 196 files under
1,215 frozen Python source/test hashes. The full attempt stopped after 2,819
passes on one retained DOSBox-X startup RPC EOF; the 462-case tail passed,
including that case. This is not a clean full-run result. A same-time macOS
report strongly correlates the failure with a stack-buffer abort in retained
`DEBUG_ShowMsg`; child-PID identity and triggering input remain unconfirmed.
The startup reliability issue remains unresolved, with its failure/diagnostic
receipts retained separately. Only the two original predeclared exclusions
were applied; the startup failure was not silently excluded.

No CI, release/tag, merge, shared installation or default-runtime switch was
performed. DOSBox-X remains the default and is retained.
