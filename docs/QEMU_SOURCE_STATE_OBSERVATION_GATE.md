# Selected source-raster and stopped-state observation gate

## Current status

The finite host gate passed **335 tests, zero failures, errors or skips** on
`c96a7fd20eb11633b006c88ebd6cc258ec57aa77`, tree
`3a3345ab79b37d5fd63b3fbc044a030fb7961217`. All 5,699 tracked file hashes were
unchanged and the checkout stayed clean. Pytest took 12.54 seconds; the owned
phase took 13.113819595993846 seconds. The worker exited zero, was reaped, and
its process group was gone with no adopted children or cleanup errors.

This establishes the selected host protocol and public API contract. **A native
observer witness remains unqualified.** The earlier native07 raster gate stays
pinned to its own source and authored fixture; it is not an observation-API pass.

The admitted output cap was 512 MiB plus a 256 MiB free-space reserve and a
16 MiB log cap; actual output was 141,184,842 bytes. The 60-second worker and
bounded cleanup limits were not exhausted. Tests used authored protocol peers,
real local socket/pipe boundaries and one bounded Python executable-identity
stand-in. No emulator, assembler, producer build or provider CI was started.

Exact host receipt: 6,115 bytes, SHA-256
`ae2a4a9d1475f397a639789044355aa70044e598dbb60e8a7ed94b7074942579`.
JUnit: 8,439,902 bytes, SHA-256
`b63ca0f5afc9b20cdaabf27b86887653e41d4b722b6e0a4fd315cfccf59e07b4`.

| Selected module or seam | Passed cases |
| --- | ---: |
| Cooperative authority and wire boundaries | 48 |
| Captured original-owner cleanup | 13 |
| Selected-state observer | 40 |
| New public JSON/script routes | 40 |
| Existing operation and I/O deadlines | 33 |
| Existing pipe transport | 16 |
| Existing source-raster behavior | 76 |
| Existing source consumers | 27 |
| Existing source public routes | 38 |
| Four explicit machine identity/GDB protocol nodes | 4 |

The first attempt on `5b0638db4250d1ea0b61b98917e3a62066a90ef0` remains a
failed result: 187 passed and one failure before the rest of the selection ran.
The new transport guard incorrectly required a socket while parsing a complete
already-buffered unbound QMP reply. The production correction preserves that
parser behavior while leaving bound authority checks intact; the existing
regression test was not weakened. The corrected candidate ran in a fresh
execution directory, and both attempts retain their inputs, logs and cleanup.

## Contract and qualification boundary

The [public operation](DOS_QEMU_SOURCE_FRAMES.md#selected-stopped-state-observation)
combines an exact retained source RGB export with explicitly selected physical
RAM, the selected-vCPU register/address bundle, stopped clocks and native
keyboard/input-schedule witnesses. Its VM-owned lease covers supported
cooperative host control paths. It does not establish native/external mutation
exclusivity, whole-machine equality, application drawing completion, mouse or
global input neutrality, or legacy completed guest frames.

The new receipt and capability are separate from legacy coherent-frame and
source-raster capture/control capabilities. Completion is scoped to the selected
observation contract; all 143 surface, 18 workgroup and seven campaign promotion
obligations remain open and DOSBox remains the default backend.

## Evidence covered by this host selection

The focused host gate exercises the real public operation and QMP/GDB
parsers with independently authored bytes: exact selected projection and RGB
verification; actual covered memory/register and direct transport mutation
attempts with unchanged clocks; a caught refusal that remains invalid;
changed RAM/register/input/source evidence; channel/owner replacement;
reentrancy, lock ordering and one inherited deadline; finite raw reply/resource
bounds; native keyboard idle throttle -1; script whole-route preflight and
resolved reference validation; and unchanged legacy capability meanings.

Host protocol evidence is not a native execution result. A later native gate
must independently admit a finite authored stopped-state witness using exact
retained producer/media identities, preserve all failed attempts, and verify
original-owner process cleanup. No new producer build or native run is admitted
solely by this source document.
