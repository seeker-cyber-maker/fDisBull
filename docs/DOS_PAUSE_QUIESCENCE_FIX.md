# Ordinary debugger pause: native loop handoff

The candidate stable and layers patches return a stopped agent session from
`Normal_Loop` immediately after the agent command pump, before `PIC_RunQueue`
or `TIMER_AddTick`. This corrects a native control-flow path that permitted
guest-clock movement after an ordinary pause had already been published.
The timing API, stop replies and strict observation comparisons are unchanged.

**Status:** the source correction, exact source replay and focused host
regressions are verified. A rebuilt native producer and its runtime regression
remain required. The retained stock failures are not closed by source tests.

## Observed failure

On clean host `40342352985b73323eed141c93d6e7173dd0d40c`, stock Linux DOSBox
SHA-256 `d9236f1178855524a74516eb37cbb636431f9bdec599d9d675e6d69ea6309251`
reproduced the problem with an authored ten-byte `PVERIFY.COM` CPU-busy loop.
The requested profile was normal core, fixed 157600 cycles and
`fast_forward=false`. Effective native profile instrumentation was not added.

After the first ordinary pause, four fixed timing/status/registers/timing
blocks recorded PIC tick samples **9, 11, 12, 14, 15, 17, 19, 20**. The four
status objects were identical and stopped; the four register objects were
identical. The timing replies differed only in `guest_ticks`, a net increase
of 11. There was no intervening continuation, step, input, restore or screenshot.
The controller retained the full admitted observation set and stopped future
guest continuation at the mismatch. Native and worker owners were reaped with
complete logs and no cleanup errors.

The prior Doom observation separately retained a six-tick change after its
neutral pause. Both counterexamples remain preserved. Register equality at
sampled points does not establish continuous CPU immobility or identify the
exact runtime stack that advanced the clock.

Sanitized identity references for the authored fixture observation:

| Record | SHA-256 |
| --- | --- |
| Final result | `d7894d96b9e019b14fd5fe6ac11f04135da8eb8e96f7956064825e177bbd18e2` |
| Raw decoded RPC journal | `080cb8a5e602b3476ade26ee390f046b79c5ced1f4eb92c6825417ad9ec4bfbb` |
| Completed first episode | `903851d5f59650627d85dd10eb6ed78a913a8e049d2a9d11d673ce80efba146a` |
| Authored COM fixture | `fc98fc96de8fa01651cd36f3877242a0cc35cf306621d2236db205e9b3718d91` |

The fixture bytes are `b8 34 12 bb 78 56 40 43 eb fc`: initialize AX/BX,
then increment them in an unconditional loop. No commercial payload or saved
machine state is part of this regression source.

## Mechanism and correction

The emulation-thread pause adapter calls `DEBUG_EnableDebugger`. The debugger
becomes active, selects the future `DEBUG_Loop`, and synchronously publishes
the stopped state/revision. Publishing the stop does not unwind the current
`Normal_Loop` stack frame. `PIC_RunQueue` already refuses execution while the
debugger is active and runwatch is inactive; its false result nevertheless
selected `Normal_Loop`'s timer branch. `DOSBox_Paused` represents a separate
host-pause flag and did not prevent that branch from draining `ticksRemain`.

The new guard uses the same existing persistent debugger-state predicates,
scoped to an agent session:

```cpp
if (dosbox_agent::AGENT_IsSession() &&
    IsDebuggerActive() && !IsDebuggerRunwatch()) {
    (void)DEBUG_ExitLoop();
    return 0;
}
```

Its placement immediately after `AGENT_BridgePump` prevents further PIC,
interrupt, decoder or timer work by that normal-loop invocation after the
stop. It consumes the pending exit flag while stopped. The guard does not
depend on that one-shot flag being set: direct stepping can clear it, and
nested work may already have consumed it. Calling `DEBUG_ExitLoop` only in the
stopped path also avoids adding its heavy-debug variable inspection to every
running iteration.

The compatibility boundaries are explicit:

- Agent Continue and step-over clear `debugging`; they still reach the normal
  decoder/callback path. The existing post-decoder exit check remains.
- Runwatch keeps `debug_running=true` and is deliberately excluded.
- Direct single-step runs its explicitly requested instruction through
  `DEBUG_Run`; the returned stopped state permits no extra timer work.
- Both existing frame-step completion checks remain byte-for-byte unchanged,
  including the check after a renderer callback returns from `PIC_RunQueue`.
- Non-agent interactive behavior is outside the new guard.

There is no host sleep, clock rebase, settling read, allowed tick tolerance,
timer-budget reset or changed screenshot comparison.

## Source identity and verification

Only `src/dosbox.cpp` changes in the reconstructed native sources. The same
ten-line addition is present in both complete patches. Each still applies
directly to upstream `029bd65c5dcc7cdc7f2e14e35278620d9707d969`; the layers
patch is not applied over the stable patch.

| Candidate | Identity |
| --- | --- |
| Stable complete patch SHA-256 | `20fd864b63057f486ddb4a6eee78e24b7b548b312029a37280684ffd69b2d9d2` |
| Layers complete patch SHA-256 | `351b97c1aa5924f140e38c5b14a2209c77ef1222022a3b5569955ac8cc6518b0` |
| Reconstructed `src/dosbox.cpp` SHA-256, both variants | `e3704ede473a6710e2ca935256ab070cd48dfab469300b2909e77bc9ad7163d9` |
| Reconstructed file length |343,776 bytes |
| Verified source replay entries |37 stable; 38 layers |

Exact-context replay read only the patch-listed source members in memory from
the retained upstream archive, SHA-256
`bc442b7ade6ce3f05e280dacd7984a770d6ee576b0d8f29cf94e66f917819f4a`.
Original Git blob prefixes, every hunk's old context/counts, and all resulting
manifest size/SHA records were checked. Every native source member other than
`src/dosbox.cpp` remained identical to the previous variant. No full native
source extraction, native build or emulator execution was performed for these
source checks. Current replay counts were corrected in the manifests; earlier
receipts and native producer identities remain unchanged.

`tests/test_dosbox_pause_source.py` compiles the actual patch fragments before
the PIC boundary and before the decoder, with small state/side-effect stubs.
The ordinary-pause case failed on the unchanged stable patch because it reached
the forbidden PIC/timer path. After correction, all 18 stable/layers source
cases passed: ordinary pause, consumed exit flag, step-cleared exit flag,
continue/step-over, runwatch, non-agent behavior, both frame boundaries and
ordinary running after PIC. Moving the guard below `PIC_RunQueue` excludes it
from the extracted prefix and makes the stopped cases fail.

The focused host command completed with **29 passed, no failures or skips**:

```sh
python -B -m pytest -q tests/test_dosbox_pause_source.py tests/test_run_boundaries.py
```

That total comprises 18 source/control-stub checks and 11 host run-boundary
checks. It establishes neither actual native pause immobility nor full native
single-step/runwatch/frame behavior.

## Native qualification remains required

`tests/test_dosbox_pause_native.py` provides the corresponding opt-in public-RPC
regression. It uses a fresh authored COM, one selected native lifetime, the same
normal/fixed profile and false fast-forward policy, eight fixed running waits,
and four complete stopped-state blocks per episode. A mismatch fails before
another continuation. It retains raw decoded replies, first stops, sampled
registers and clocks; on Linux it also retains the original native log fd
through cleanup. It is not executed by the source/control-stub checks.

```sh
FDISBULL_DOSBOX=/absolute/path/to/rebuilt/dosbox-x \
python -B -m pytest -q --require-native tests/test_dosbox_pause_native.py
```

The external qualification owner must admit the exact rebuilt binary,
dependencies, source/configuration and output limits and preserve its process
cleanup evidence. The retained standalone pause gate additionally enforces
the 120-second whole-owner/storage bounds and remains the direct comparison
route for the stock counterexample. A clean candidate run on the tiny fixture
does not close the separate Doom failure, qualify a different native tuple,
or establish that DOSBox can be retired.
