# Bounded native CALL step-over

Checkpoint: November 20, 2026, America/New_York.

The QEMU machine and DOS adapters now accept `step(mode='over', count=1)`.
The implementation and its focused host gate are complete. The authored native
comparison is source-only pending its separately reviewed owner controller.
DOSBox remains the default and fallback; this gate does not authorize retirement.

## Supported behavior

An unprefixed direct `E8 rel16` CALL is admitted only in one observed, unpaged,
real-mode 16-bit code and stack context. Caller, callee, fallthrough and return
slot must be nonwrapping ordinary conventional RAM. An active DOS process also
requires its current PSP, MCB allocation, capture epoch and mapped source bytes.
Ordinary `NEXT` instructions use one native step under the same explicit result
envelope. Other control transfers, REP/HLT, far/indirect/prefixed CALLs,
protected/V86/64-bit modes and active layers/task views refuse.

The CALL installs one private fallthrough alias without consuming the public
breakpoint ID counter. It uses the original VM, process, transports, source
epoch, operation lock and deadline through dispatch, observation, cleanup and
publication. Queued or scheduled input and conflicting execution controllers
refuse. A pending entry hook may displace the CALL once before continuation;
that displacement shares the original deadline and grants no repair grace.

Completion requires an exclusive private native breakpoint, the original
CS/SS/SP and address context, unchanged caller/fallthrough bytes and the expected
return word still in the original stack slot. A user breakpoint, hook,
watchpoint, tracker alias, timeout, exit, changed return identity or uncertain
observation remains the actual first outcome and prevents another continuation.
Cleanup preserves any existing user/hook/tracker aliases.

## Public receipt

The envelope is `fdisbull-machine-step-over-1`, model
`real16-direct-near-call-v1`. It contains `step_over_completed`, the complete
`native_result`, captured `owner`, `before`, `after`, `control`, `reason`, and
`instruction_completed=None`. A completed CALL retains `outcome='breakpoint'`;
this is fallthrough/stack evidence rather than an arbitrary instruction
retirement claim. Genuine native owner exit retains its actual packet and reaps
the owner without post-exit observations. Live DOS exit/TSR remains a distinct
incomplete outcome.

Python, JSON `debug-step` and saved-script `step` expose the same envelope.
Scripts continue only after explicit completion; an interrupted CALL retains
its actual native result and suppresses later script operations. The default
and explicit `mode='into'` routes retain their existing one-step/count behavior.

## Verified host gate

| Evidence | Observed result |
| --- | --- |
| Integrated tested commit | `353df71e2281a4078ac5c3ff87f89cd3ccdbb17e` |
| Author component | `7d7994e1de81854a6efbc06861f43835af300d96` |
| Selection | CALL, counted steps, hooks, late tracking stops, source-frame control, transport deadlines, CPU undo guard, checkpoint control failures and DOS process host modules |
| Result | **443 passed; zero failures, errors or skips** |
| Duration | 3.42 seconds pytest; 3.919845 seconds outer worker |
| Inputs | All 5,673 tracked file hashes unchanged; clean source before/after |
| Ownership | Worker/group reaped; no adopted child remained |
| Output | 60,127,765 bytes under a reviewed 256 MiB ceiling |
| Receipt SHA-256 | `d7268c58b3a12e8ccb8cdaf8c67dc8f2d176dfc1cf4659b4f3376dacbea16d28` |

The exact runner, JUnit, full log, pre/post inventory and receipt are retained
under `frame-parity-20261120/host-step-over-01`. The independent source review
is `reviews/call-step-over-source.md`, SHA-256
`f64a4384cd72dd4fce7329836a9cd9512a008b6f52810ab738d945b2a627a0e9`.
Its callback-owner, first-stop, script preflight, private-ID and child-deadline
findings were resolved before this gate. Root preserved both the existing
`video_frame_rgba` and new CALL outer-deadline guards during integration.

These are host protocol witnesses. Their supplied stop packets do not establish
native CALL execution, guest instruction retirement or DOSBox schema equivalence.

## Authored native gate, pending

`tests/test_qemu_step_over_native.py` uses the exact previously observed DOSBox
control bytes `31c0e8030090ebfe40c3`. The independent instruction oracle expects
XOR to reach IP0102, CALL/INC/RET to return at IP0105 with AX1 and restored
CS/SS/SP, return slot `0501`, then one step to IP0106.

Eight selected nodes propose nine strictly serial owners: one DOSBox and eight
QEMU. They cover the paired return, Python/JSON/script routes, user breakpoint,
coincident fallthrough alias, hook, stack-write watchpoint, interrupted-script
mutation suppression and an actual pending CALL-entry hook. Each real native
command/reply is retained. Hook no-ops preserve the observed full raw register;
the ten bytes establish only the low AX word.

The reviewed test SHA-256 is
`10952351e15bfebc6f693416f869d1a72b9ccc93707a547e5eeba2f54f13ea28`.
The pending repeat-hook witness was corrected before native execution: hook
displacement legitimately replaces its backing breakpoint and consumes exactly
one public identifier. The oracle predicts that replacement from the original
counter and requires the original breakpoint fields, logical hook and all
unrelated aliases to remain intact. The CALL's private return control still
consumes no public identifier. Register, stack and execution-order assertions
are unchanged.

The native-oracle source review is
`af178e5f96193bef1ebca3379f414a2c4386c781d1be56f8d86048d132e5b276`.
That earlier review refers to the preserved pre-correction test
`fd6e8b09a20b3d8def1db7972acdadec19fce3ce21388f7ef9a25213b9a70146`.
Exact producer, media, dependency, source and lifecycle closure still must be
frozen and reviewed before execution. No native result is claimed here.
