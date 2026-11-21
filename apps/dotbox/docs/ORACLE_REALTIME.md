# Live pseudo-oracle timing qualification

The pseudo-oracle is usable at approximately normal game speed for the tested
local Keen Dreams collection and enemy-encounter controls. These tests do not
qualify hard frame deadlines or uninterrupted execution. One encounter run fell
below the declared average-speed band, and long latency tails remain visible.

This is a test-only checkpoint. Production oracle, scene, adapter and controller
code were unchanged. The [authored receipt](evidence/pseudo-oracle-live-2026-11-20.json)
pins the tested source, private test drivers, all completed runs, the initial
failed attempt, measurements and evidence hashes. Raw original-game material
stays private; the Agent BBS completion handoff identifies its evidence archive.

## What ran

One foreground owner controlled isolated copies of the original game through
ordinary inputs. Workers analyzed frozen evidence and did not control guests.
Every observation came from the existing coherent `post_actor_pre_refresh` hook.
The loop reads a 30,710-byte hot RAM window, decodes it, checks source/owner/
revision bindings, constructs the scene, evaluates the oracle, projects its HUD,
selects an existing admitted choice and rechecks control admission before input.
The emulator then advances with its normal original timing.

The game is briefly stopped at each hook while the local callback runs. There
is no language-model call inside that callback. The state and algorithms use
original world coordinates, at 16 world units per game pixel; display size is
not an input to movement or oracle reasoning. The sampled actor updates contain
two game ticks, nominally about 35 updates per second. Native `guest_ticks` and
elapsed timing values in the transport are milliseconds, not game ticks or frames.

The primary sequence was baseline, oracle, oracle, baseline (ABBA), with 700
advanced updates and 701 observations per run. Both modes executed the same
existing qualified collection route: move, jump, collect a 100-point bonus,
land, then observe with neutral input through update 700. Baseline retained the
same wrapper, admission and diagnostics, but omitted adapter/oracle/selection.
Oracle mode selected the route at observation zero before its first input.

A fifth 700-update run included original-frame PNG capture, decoding and the
existing frame-store publication every two updates: 351 frames at 320 by 200.
This measured local presentation work, not browser/network delivery or a rendered
HUD overlay. The image is the last completed guest image, not a phase-synchronized
render of the current post-actor observation.

Three 82-update encounter runs measured actual direction release. After the
first oracle encounter was slow, one fixed baseline/oracle follow-up pair ran;
the earlier result was retained. One separate 700-update diagnostic added GC
timestamps without changing enabled state or thresholds. It is not part of ABBA.

In total, nine completed runs cover 4,446 advanced updates, 4,455 observations
and 126,972 feedback guest milliseconds. The initial failed baseline is retained
separately. Warm preparation took 450.314 seconds from its recorded start to
the first oracle-selected observed movement, including the failed preflight and
baseline setup. Read-only discovery preceded that clock; this is not a cold-start
or player-startup benchmark.

## Whole-controller speed and latency

Speed is elapsed guest milliseconds divided by complete controller wall time.
The declared diagnostic band was 0.95 to 1.05. Values slightly above one reflect
finite measurement boundaries, not an intentional speed-up. Cycle timing includes
the controller work and normal game pacing; it is distinct from evaluator cost.

| Run | Updates | Whole-controller speed | Cycle median | Cycle p95 | Longest cycle |
| --- | ---: | ---: | ---: | ---: | ---: |
| 11 baseline | 700 | 1.000330x | 28.549 ms | 30.372 ms | 44.425 ms |
| 12 oracle | 700 | 0.998814x | 28.550 ms | 30.634 ms | 53.690 ms |
| 13 oracle | 700 | 0.998906x | 28.531 ms | 30.235 ms | 52.667 ms |
| 14 baseline | 700 | 0.997976x | 28.552 ms | 30.501 ms | 68.585 ms |
| 15 oracle + frames | 700 | 0.995044x | 28.213 ms | 32.464 ms | 56.273 ms |
| 16 oracle encounter | 82 | **0.947063x, below band** | 28.578 ms | 30.787 ms | **115.788 ms** |
| 17 baseline encounter | 82 | 1.001440x | 28.627 ms | 30.719 ms | 33.819 ms |
| 18 oracle encounter | 82 | 1.001224x | 28.362 ms | 30.035 ms | 31.100 ms |
| 19 oracle, GC diagnostic | 700 | 0.998687x | 28.545 ms | 30.273 ms | 50.319 ms |

The pooled ABBA speed is 0.999151x baseline and 0.998860x oracle. Cycle p95 is
30.450 ms and 30.367 ms respectively. Normal game pacing can absorb extra local
work; similar throughput does not mean the oracle has zero cost. Whole callback
median/p95 rises from 0.312/0.451 ms to 1.879/2.964 ms. The oracle evaluator alone
has median 0.841-0.871 ms and p95 1.282-1.421 ms in the two primary oracle runs.

The primary oracle runs produce HUD data 4.923-5.038 ms after the qualified hook
receipt returns, with p95 6.393-6.427 ms. Including local frame publication gives
6.890 ms median and 8.826 ms p95. This host boundary is not the exact instruction
at which an in-game event occurred, and HUD-ready data is not visible UI latency.

All nine runs completed their functional checks. Eight met the average-speed
band. Run 16's feedback-only ratio is 0.950313x, but the complete-controller
ratio is 0.947063x; the former must not replace the latter to obtain a pass.
No hard deadline pass is inferred from an average-speed band or a percentile.

## Did decisions arrive in time to do something useful?

Yes, for the tested bounded routes. Every collection run gained 100 points at
observation 39. Every oracle-enabled collection run removed the consumed bonus
from the HUD in that same observation. The already admitted jump continued
through landing at 67 and settling confirmation at 70; removing a consumed
target does not abort a safe route midway through a jump.
Lives stayed at three and inventory stayed unchanged. Zero flower power kept
the attack resource condition false, and no throw route became ready.

In both oracle encounters, `carrot_encounter` first held at observation 63 and
the oracle-selected existing `release_direction` choice ran in that callback.
The guarded original encounter policy independently required neutral desired
keys. No attack, retreat route or collision-avoidance prediction was invented.

| Boundary from returned hook receipt at observation 63 | First encounter | Follow-up |
| --- | ---: | ---: |
| HUD ready | 6.857 ms | 5.017 ms |
| Selection complete | 7.134 ms | 5.206 ms |
| Release edge acknowledged | 9.474 ms | 8.455 ms |
| First next observation with neutral input | 64, after 28 guest ms | 64, after 28 guest ms |
| First subsequent observation with zero horizontal movement | 65, after 57 guest ms | 65, after 56 guest ms |

Input acknowledgement, sampled input consumption and physical stopping are
different events. At observation 64 the player still moved 24 world units (1.5
game pixels) while entering the standing state. Position was stable at 65.
The sample bounds input consumption; it does not locate the exact input-read
instruction. The largest encounter stall occurred at update 10, before this event.

All six completed collection runs, including the diagnostic, have identical
701 compact states, key decisions and 700 hot-memory hashes. Absolute native
guest timestamps are not identical across all runs. The follow-up encounter
pair also matches compact states, keys and hot-memory hashes. The original slow
encounter matches compact states and keys but has different hot-memory hashes.
The optional frame workload did not change this collection trajectory; that is
evidence for this route, not a new browser-resolution qualification.

## Failures and latency tails retained

The first baseline attempt stopped at observation 168 after successful collection
and landing. The newly added sustained-neutral test had incorrectly required the
standing animation state to remain fixed. The original source's idle look changed
animation, collider top and idle counters while position, feet, floor contact,
controls, score, lives and inventory stayed unchanged. The test-only correction
allows and records animation transitions while preserving physical/gameplay
guards and neutral input. The failed attempt and both driver versions remain
in private evidence. It is not counted as a completed performance run.

The primary oracle runs contain 34.006 ms and 33.258 ms evaluator calls, both at
callback 673. A separate instrumented run reproduced a 30.785 ms oracle interval
at that callback, containing a 29.862 ms generation-2 GC interval. GC remained
enabled with thresholds `[700, 10, 10]`; that collection reclaimed zero objects.
This is a measured wall-time overlap and a concrete allocation/retention
optimization lead. It neither proves the cause of earlier uninstrumented pauses
nor separates GC CPU work from host preemption.

Run 16's 115.788 ms cycle instead included 53.408 ms in `frame.step`, 38.774 ms
in memory read and 12.247 ms in decoding. The preceding oracle callback was
2.132 ms. A second 68.619 ms cycle also occurred. These receipts localize elapsed
time but do not establish its CPU/scheduling cause. The follow-up pair did not
reproduce the large stalls; it does not erase them.

## Verification and practical conclusion

The frozen analyzer passed all nine runs. Root and independent analysis produced
byte-identical final JSON, SHA-256
`c0ff9c4527832a56aac495e3d4cb174538511e7819d313bb0f0e7226596dbdbc`.
Fresh targeted controller/oracle/adapter tests passed 140 cases. Every native
owner closed and reaped its guest with return code zero, released held keys and
left original game files unchanged. No production code changed in this test.

The useful operating model is a small local state/choice loop with delegated
bounded controls, while Dot handles longer-lived intent and conversation outside
the time-critical callback. Practical normal-speed use is demonstrated for this
profile. Continuous execution, browser delivery, model-response latency, general
hazard forecasts, attack/retreat play and strict frame deadlines remain unqualified.

The next optimization target is allocation and retained-history pressure in the
local callback and its surrounding test/observation path, followed by the RPC and
decode tails. No production performance fix or hard-deadline claim is part of
this checkpoint.
