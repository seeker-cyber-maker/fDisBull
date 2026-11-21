# Selected source-raster and stopped-state observation gate

## Current status

Native attempt 03 completed its full controller with **one passed test, zero
failures, errors or skips** on `c73a9bf73c3a01af140a4fd2e6fad70000f60f82`, tree
`2714d3bf61ea0a4af8ee3b76fce5e3427edf016e`. The original in-attempt postflight,
owner cleanup, process-absence and resource checks completed. This is one authored
mode-13 selected-state witness; both earlier failed native attempts remain failed.

The separately accepted host gate below establishes the selected host protocol
and public API contract. The earlier native07 paired raster gate stays pinned to
its own source and fixture; it is distinct from this observation-API witness.

The optional [native stopped-control extension](QEMU_STOPPED_CONTROL_GATE.md)
has its own arm, cached-raster and mutation-admission contract. Its new producer
and raw-peer witness require separate qualification; the results below do not
qualify that extension.

The separate [native input-schedule witness](QEMU_INPUT_SCHEDULE_OBSERVATION_GATE.md)
passed its complete controller on `c3bc62302340e879b21e9cd5862c82036045d5f5`.
It verifies both armed and cancelled `input-before` refusals with unchanged
genuine host bookkeeping and reusable original-owner health checks. Its
state-specific keyboard read boundary and earlier failed attempts remain explicit.

## Exact host qualification

The finite host gate passed **335 tests, zero failures, errors or skips** on
`c96a7fd20eb11633b006c88ebd6cc258ec57aa77`, tree
`3a3345ab79b37d5fd63b3fbc044a030fb7961217`. All 5,699 tracked file hashes were
unchanged and the checkout stayed clean. Pytest took 12.54 seconds; the owned
phase took 13.113819595993846 seconds. The worker exited zero, was reaped, and
its process group was gone with no adopted children or cleanup errors.

The admitted output cap was 512 MiB plus a 256 MiB free-space reserve and a
16 MiB log cap. The receipt recorded a **141,184,842-byte sample**; final retained
regular files totalled **141,932,037 bytes**. The 747,195-byte difference is exactly
the subsequently written `inputs-after.json` (741,080 bytes) and `receipt.json`
(6,115 bytes). Both measurements remain explicit and below the cap. The 60-second
worker and bounded cleanup limits were not exhausted. Tests used authored protocol
peers, real local socket/pipe boundaries and one bounded Python executable-identity
stand-in. No emulator, assembler, producer build or provider CI was started by
this host gate.

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

The first host attempt on `5b0638db4250d1ea0b61b98917e3a62066a90ef0` remains a
failed result: 187 passed and one failure before the rest of the selection ran.
The new transport guard incorrectly required a socket while parsing a complete
already-buffered unbound QMP reply. The production correction preserves that
parser behavior while leaving bound authority checks intact; the existing
regression test was not weakened. The corrected candidate ran in a fresh
execution directory, and both host attempts retain their inputs, logs and cleanup.

## Native source-state witness

The native case uses one original QEMU owner, one source stream and one completed
raster. Two complete observations select `0000` from two ordinary physical RAM
bytes. One actual bound GDB write changes the first byte to `5a`, with native
`OK` and readback; the third complete observation selects `5a00`. Native time,
instruction counter, selected registers and retained raster remain unchanged.
The immediately sampled Python control generation advances from 87 to 88. That
is cooperative control admission evidence, not a native mutation revision.

One actual native keyboard make then establishes an owner that is deliberately
not adopted into host bookkeeping. The fourth observer reaches the native input
schedule and keyboard queries and refuses with `native_keyboard_owner_active`.
It performs no export, GDB operation, input repair or continuation in that refused
interval. The original owner remains available for passive diagnostics and is
then closed and reaped. The backend's reserved DOS return breakpoint is preserved;
only the test's temporary ready-parking breakpoint is removed.

Expected RGB and row timing come from the unchanged authored VGA oracle and
guest-read timing registers, not candidate pixels. The expected 192,000-byte RGB
SHA-256 is `0023064781bf3284f863230adaf987cc366a426e5385d52865235ded35de32be`.
The retained 503-byte COM, prepared DOS baseline, firmware and native producer
were reused without assembly or a producer rebuild.

| Native03 evidence | Observed result |
| --- | --- |
| Test result | **1 passed; zero failures, errors or skips**; 2.13 seconds pytest (JUnit suite: 2.126 seconds) |
| Owned worker / complete controller | 3.29781263199402 / 41.797629174005124 seconds |
| Native journal | 300 calls: 114 bootstrap and 186 post-setup; 20 source-video calls |
| Post-setup behavior | One continuation, stream, accepted raster, fence arm/release, one RAM write packet, three exports, three complete observations and one native keyboard make/refusal |
| Lifecycle | Original QEMU PID 42 exited zero and was reaped; worker reaped and group gone; no adopted children, cleanup errors or remaining selected emulator images |
| Input integrity | 11,651 file pins and six counted trees matched preflight/postflight; retained QEMU source and prefix were also verified; exact tested source stayed unchanged |
| Output | 5,036,101 logical / 5,066,752 allocated bytes, plus the separate 4,194,304-byte open-log reservation, within the 64 MiB cap |
| Native observation receipt | 534,180 bytes, below its 2 MiB cap |
| Native producer SHA-256 | `b42b624f452e19c1560f1af45712fc93f6859ac753bab73a1495c49188cca0af` |
| Native test SHA-256 | `29fd1e7bcb3c96a236be7a69c159b2472caedb380ea13b1cf28949792e2811e0` |

The existing pytest `record_property`/xunit2 compatibility warning is retained.
The retained controller is `frame-parity-20261120/controller-source-state-03`;
raw evidence is under `/tmp/fdisbull-source-state-native-20261121-attempt-03`.
The unchanged 180-second aggregate includes setup and final verification. Its
outer worker allowance is 75 seconds and postflight 35 seconds; case work remains
60 seconds and original-owner cleanup 10 seconds. The receipt/private-output caps
are 2/64 MiB, with a separate 256 MiB free-space reserve. Native/video call caps
are 2,048/32. The retained inputs and source are unchanged from native02; only
the reviewed controller budget allocation and fresh attempt paths differ.

| Native03 artifact | SHA-256 |
| --- | --- |
| Complete phase receipt | `598b4410e3d251a4009654965e3a29232e295452c0170686e32a80424b73b2ab` |
| JUnit | `f669f44b2eddbd7834a5311b3f602d8ea21bd3dc58406c90ec999792fe100cd1` |
| Native observation JSON | `b276d92ba88519d80958c5250c82cfb8cf8cb119d59cc6ba6b2a512dcad4a1fc` |
| Raw native calls | `e1f52006d97c864d5a100ad999793e90b2c9604bfdd57b37238f1ad70d59369a` |
| Independent raw-evidence audit | `97cdbc54c6bd5e2538795ab327ffc7dd807ced67d270210e78a1ad9463c07b42` |

## Earlier native attempts remain failed

**Native01**, at `69d5290457e8226e261c2db222a7e5925681b6db`, failed immediately
after ready parking because the new test incorrectly required an empty shared
breakpoint registry. The remaining control was the backend's reserved DOS
parent-return breakpoint; the test's temporary breakpoint had been removed.
It recorded 114 native calls and no video/observer calls. The original QEMU owner
exited zero and was reaped, and input postflight matched. The narrow test correction
validates and preserves the exact lifecycle breakpoint; it adds no native
operation or deletion and does not weaken product behavior.

**Native02**, at `c73a9bf73c3a01af140a4fd2e6fad70000f60f82`, passed its case,
worker and native-evidence reconciliation, including the three observations,
actual byte write and typed input refusal. Its full controller nevertheless
failed when the original 20-second postflight budget expired before final input,
process-absence and resource records completed. A later separately admitted
read-only diagnostic verified all inputs and those later absence/resource facts
in 12.551476143999025 seconds. It did not retroactively complete or promote the
exhausted attempt. Native03 used a fresh, separately reviewed controller with
15 seconds reallocated from worker to postflight within the same 180-second
aggregate. Source, test behavior, verification checks and storage/call limits
stayed unchanged.

## Contract and qualification boundary

The [public operation](DOS_QEMU_SOURCE_FRAMES.md#selected-stopped-state-observation)
combines an exact retained source RGB export with explicitly selected physical
RAM, the selected-vCPU register/address bundle, stopped clocks and native
keyboard/input-schedule witnesses. Its VM-owned lease covers supported
cooperative host control paths. It does not establish native/external mutation
exclusivity, a native or whole-machine revision, application drawing completion,
mouse/global input neutrality or guest input consumption. Raw handles, independent
controllers and unobserved native/device effects remain outside that authority.

Receipts retain `atomic=false`, `application_frame_complete=null`,
`frame_state_equivalence=null` and `legacy_phase_equivalence=null`;
`completed_guest_frames` remains false. This one authored mode-13 result does not
qualify other modes, actual games, cold histories or broader legacy routes. The
new receipt and capability remain separate from legacy coherent-frame and
source-raster capture/control capabilities. All 143 surface, 18 workgroup and
seven campaign promotion obligations remain open, and DOSBox remains the default.

## Evidence covered by the host selection

The focused host gate exercises the real public operation and QMP/GDB parsers
with independently authored bytes: exact selected projection and RGB verification;
actual covered memory/register and direct transport mutation attempts with
unchanged clocks; a caught refusal that remains invalid; changed
RAM/register/input/source evidence; channel/owner replacement; reentrancy, lock
ordering and one inherited deadline; finite raw reply/resource bounds; native
keyboard idle throttle -1; script whole-route preflight and resolved reference
validation; and unchanged legacy capability meanings.

Host protocol evidence and this finite native result retain their separate
scopes. Neither admits another native attempt, producer build or broader parity
promotion. All failed attempts preserve their original evidence and disposition.
