# Automatic frame timeline deltas: local verification, 2026-11-01

At measured source `762f6e72021f3f558844d332472c1f19280a0015`, opt-in delta storage retained **24.07–25.59% fewer logical cache bytes** and **26.32–27.97% fewer checkpoint payload bytes** than the paired full modes in this prepared KQ1 scene. Forward loop medians were **7.26–9.08% slower**. Full storage remains the default. These results support a storage tradeoff; they do not establish lower process RAM or RSS.

The delta is a lossless XOR of complete opaque native checkpoint bytes, compressed with zlib. Every recorded point still invokes the unchanged full native checkpoint capture, and every image remains a full PNG. This feature does not capture native dirty pages or replace native device/state serialization. Keyframes, descriptor/envelope hashes, bounded materialization, eviction rebasing and corruption refusal protect the retained representation. A pin exports ordinary full native Anchor Stone bytes.

All numeric values below derive from the sealed local receipts identified by SHA-256 in [metrics.json](metrics.json). Original game bytes, RAM reads, states, FDBs, images, host paths and raw logs are excluded from this directory. Exact private controllers are identified by hash below and available through the private attachment linked in the replay section.

## Protocol and timing scope

Three trials ran all six modes, rotating their order. Each arm restored the same private prepared Anchor, completed one alignment frame, then performed four warmups and 32 timed samples. The primary history had 37 points, with 37 full native captures in each automatic arm. Automatic full retained 37 full checkpoints; automatic delta retained five keyframes and 32 deltas with `keyframe_interval=8`. The configured limits were a 64 MiB logical cache, 2 MiB raw checkpoint, 1 MiB image and 512 captures. The host was macOS 27.2 / arm64 with Python 3.13.14 and the same separately provisioned DOSBox candidate-v3 for every fDisBull arm.

Each core sample dispatched two ordered paused keypad-5 edges (make, then break), advanced one completed DOSBox renderer frame to a stopped safe CPU fetch, and observed exposed CPU registers, one atomic 65,536-byte DS read and released keyboard ownership. Accepted edges do not prove game-level consumption. The core includes automatic capture inside `timeline_advance`. Dense manual Anchor/PNG capture is outside core and inside total-loop time. Per-point audit pin/image exports, status snapshots, report writing and bounds checks are outside both timers. Coarse Anchor modes add one setup pin, outside the timed loop.

Each forward entry is a within-trial median of 32 warm samples. The p95 values in the numeric companion use nearest rank. Counts are public Python/API operations or backend RPC dispatches; they are not model turns or end-to-end agent latency. The primary timed workload had 576 samples and 1,152 edges. Including setup, retries and RNG probes, the matrix completed 1,656 frames across three owned native processes, all reaped.

## Forward latency

Total-loop medians in milliseconds; trial labels correspond to the recorded trial order.

| Mode | Trial 0 | Trial 1 | Trial 2 |
|---|---:|---:|---:|
| Recording off | 22.263 | 21.414 | 21.631 |
| Manual dense Anchor Stones + PNG | 240.769 | 251.942 | 243.362 |
| Automatic full | 258.995 | 254.782 | 255.161 |
| Coarse Anchor + automatic full | 255.640 | 256.685 | 255.257 |
| Automatic delta | 279.677 | 277.018 | 277.289 |
| Coarse Anchor + automatic delta | 278.844 | 275.321 | 275.972 |

For manual dense capture, the corresponding core medians were 21.226, 21.308, 21.333 ms; its total includes the full Anchor and PNG save. Full and delta automatic modes did the same native capture work and had the same timed public-call/RPC counts. Delta adds codec and hash/materialization work to that path. Per-trial core medians, p95 values, exact call counts and return observations are retained in the numeric companion.

## Retained cache and forward cost

Savings use `(full − delta) / full`; forward increases use `(delta / full − 1)`. Each row compares the same trial, scene, logical points, inputs and capture count. Encoded payload counts retained checkpoint payload only. Complete logical cache also includes descriptors, native metadata, full PNGs/image metadata and input journal.

| Trial | Paired modes | Encoded payload saved | Complete cache saved | Delta forward increase |
|---:|---|---:|---:|---:|
| 0 | Automatic | 26.32% | 24.07% | 7.99% |
| 0 | Coarse Anchor + automatic | 26.33% | 24.08% | 9.08% |
| 1 | Automatic | 27.26% | 24.94% | 8.73% |
| 1 | Coarse Anchor + automatic | 27.36% | 25.03% | 7.26% |
| 2 | Automatic | 27.97% | 25.59% | 8.67% |
| 2 | Coarse Anchor + automatic | 27.83% | 25.47% | 8.12% |

The complete full caches occupied 6,754,450–6,755,040 logical bytes; delta caches occupied 5,026,141–5,128,849 bytes. Raw/native payload limits are separate from retained encoded sizes. The configured conservative codec workspace bound was **21,233,664 bytes** for these settings, outside the logical cache budget. That bound excludes native serialization/emulator memory and Python allocator overhead. Cumulative controller/child RSS observations do not isolate the storage representation. **No RAM/RSS saving or total-RSS bound is claimed.** All native save, ZIP compression and temporary-file work still occurs.

## Returning to prior frames and retrying

Each return depth was measured once per mode per trial. The table reports the median of those three return observations, in milliseconds, excluding subsequent verification and suffix replay. Automatic modes restore the selected complete native checkpoint after materialization; dense manual mode loads the corresponding saved Anchor. Recording-off reconstructs the target by loading the seed, aligning and replaying the known prefix, so its shorter prefix at depth 32 makes that return cheaper. This is a return-strategy comparison, not constant-work restore throughput.

| Mode | Return 1 frame | Return 8 frames | Return 32 frames |
|---|---:|---:|---:|
| Recording off | 598.588 | 485.897 | 93.366 |
| Manual dense Anchor Stones + PNG | 21.656 | 21.575 | 21.119 |
| Automatic full | 32.771 | 33.050 | 34.276 |
| Coarse Anchor + automatic full | 32.793 | 33.058 | 32.268 |
| Automatic delta | 37.465 | 37.889 | 37.490 |
| Coarse Anchor + automatic delta | 37.792 | 37.498 | 37.420 |

The numeric companion preserves all per-trial return times, suffix-retry times and return-plus-retry totals including verification. Every retry used the same known suffix and returned to the same logical endpoint through public APIs. A forward branch discarded the abandoned future rather than restoring private cache objects. The codec retains complete backend-provided serialized bytes; the observed CPU/DS/image projection does not by itself establish equivalence of every hidden machine component or game outcome.

## Exactness and image coverage

The matrix recorded 666 primary CPU/DS/PNG oracle points and 629 cross-arm point comparisons. Each automatic primary point was pinned and its materialized native SHA matched its own captured checkpoint SHA; stored-image SHA matched its point envelope. Independently saved native ZIP files were not required to have the same hash across arms because host timestamps can differ. The independent review rehashed 555 native checkpoint artifacts and 756 PNG artifacts, checked accounting/ratios and timing arithmetic, and recorded no validation failures.

One broad flag in the sealed main report needs a narrower interpretation: **36 automatic-mode immediate-return stored-PNG comparisons were performed; immediate-return images for the 18 recording-off/manual returns were unobserved. All 54 retry endpoint images matched.** The sealed receipt is preserved unchanged; this report corrects the claim scope.

The main controller asserted immediate post-restore, post-refusal and full-recovery DS equality but discarded those observation objects. Their raw DS bytes were not retained, so those specific assertions cannot be independently rehashed from the main timing receipt. Retained retry observations and checkpoint/CPU receipts remain separate evidence.

## RNG safeguard supplement and restart

The main matrix had six RNG probes: every full/delta probe observed a natural nonzero transition at frame 6, restored/replayed it, preserved only the declared two RNG bytes, blocked eight ordinary mutation/execution/capture paths, and recovered through a full Anchor. The tested preserved overlay remained explicitly mixed and nonresumable until the declared full recovery; it did not claim whole-machine restoration.

The separate observation supplement repeats the unchanged RNG probe bodies once each for full and delta. It retains **50 observations and 50 exact private DS sidecars** (25 per mode), with full/masked DS hashes, CPU and released-key observations. It includes all 16 post-refusal observations and both full recoveries. Wrappers add no probe-body native reads or actions; setup adds one explicit Anchor load and two passive source-code witness reads. A fresh independent audit rehashed all 50 sidecars (3,276,800 bytes) and all 50 masked hashes. It confirmed both ordinary rewinds and natural replays against exact exposed CPU/raw DS, all 16 unchanged post-refusal observations, both full-Anchor seed recoveries and cleared guards, and pairwise full/delta observation equality. This closes the retained-observation gap for this targeted rerun, and **is not timing evidence or a retroactive replacement for the earlier 48-refusal matrix**. Raw DS stays private.

The restart check loaded the actual automatic-delta point-36 pin into a newly owned native process after the matrix processes had exited. It matched exposed CPU and full DS, confirmed no live timeline was inherited, exported stored images offline, and replayed point 35 → 36 with the same make/break pair and one completed frame to match CPU/DS/PNG. A one-byte static child patch affected only a derived analysis FDB; original parent bytes and the saved Anchor hash stayed unchanged, and child-version native launch was rejected before spawning. Offline original/replayed PNG exports also matched after the new process exited. Restore invalidates the live framebuffer until a completed frame; the offline image check does not claim immediate rendering. There is no golden point-37 result. All owned restart/supplement native processes reaped, and recorded input-preservation checks passed. The independent restart audit verified retained CPU/load receipts, five exported artifacts (three PNGs and two Anchor exports), the replayed native pin, empty inherited history and the new one-full/one-delta history. **Restart post-load/replay DS reads were asserted then discarded by that controller; they were not independently rehashed. The separate RNG supplement does not retain the restart reads.**

## Separate JPC-RR references

Six fresh JVM runs used stock JPC-RR 11.2: three baseline runs and three runs in which the external controller saved a full checkpoint and PNG every sample. Each used four warmups and 32 timed samples; the baseline/history order alternated between trials. These are external-controller history saves, not a built-in delta rewind feature. All six receipts completed, reaped their JVM and preserved their inputs. An independent audit reconstructed and rehashed 438 raw 64 KiB protocol reads (28,704,768 bytes), rehashed 330 PNG artifacts, and checked 54 anchor restores, 54 first/repeat comparisons and 54 endpoint restores against the sampled projection. It reported no failures; this remains bounded projection evidence.

| JPC-RR mode | Trial 0 median | Trial 1 median | Trial 2 median | Median of trial medians |
|---|---:|---:|---:|---:|
| Baseline, no per-sample history | 20.966 ms | 21.131 ms | 20.792 ms | 20.966 ms |
| External full checkpoint + PNG history | 111.567 ms | 112.223 ms | 112.116 ms | 112.116 ms |

The **20.966 ms** baseline and **112.116 ms** external-history medians describe those JPC-RR controllers only. JPC-RR used a prepared first-room movie prefix; fDisBull used the prepared rat-room Anchor. The machines/settings, scene, transport, observer postprocessing and frame boundaries differ. Their RAM-address selection differs too: JPC-RR observes the current DS base at each pause, while the fDisBull observer reads the preparation-bound fixed game DS region. JPC-RR stops at `TRACE_STOP_VRETRACE_START` after stock display update; DOSBox reports a completed renderer frame plus safe CPU fetch. JPC-RR spaces make/release by 1 ms of emulated time, while fDisBull queues both while paused. JPC-RR uses a Java headless front end over command/reply pipes; fDisBull uses its native RPC transport. JPC-RR command timing includes per-command log/size work that fDisBull places outside its loop timer. Therefore **no cross-engine speed ratio, normalized emulator throughput, fixed 60 Hz equivalence, game-consumption or TAS-parity claim follows**. JPC-RR per-run p95 and per-depth restore/repeat medians (three repeats per depth in each JVM) are supplied only as separate references. The retry input plans also differ: a JPC-RR depth-N retry sends **one** make/break pair and then advances N native frames; fDisBull repeats a make/break pair at **each** suffix frame. The JPC-RR hot loop uses a pair plus one frame per sample, but its retry timings remain controller-specific and do not measure the same suffix work as fDisBull.

## Tests and package boundary

| Check | Recorded result | Scope |
|---|---|---|
| Focused codec/timeline/interface/rewind suites | 319 passed | Includes corruption, eviction, branch, budget rollback and RNG guards |
| Unrestricted local macOS suite | 2,826 passed; 142 skipped; 3 failed; 23 errors | Kept as the original result |
| Clean-parent reproduction of all failed/error nodes | Same 3 failures + 23 errors | Exact node IDs and normalized exceptions; parent `865542a`; clean before/after |
| Scoped local macOS suite | 2,826 passed; 142 skipped; 26 deselected | Only those exact baseline failures/errors deselected |
| Authored native frame acceptance suite | 8 passed | Default full storage; restart, patch isolation, images, input ownership and cleanup |
| Real prepared KQ1 matrix/restart/RNG supplement | Passed within the scopes above | Does not qualify other games/backends/platforms |
| Local wheel validation | Passed | Codec included/imported, roundtrip, API parameters and bundled workflow checked |

The 26 baseline outcomes comprise 23 GNU/ELF compiler-fixture setup errors, two ELF-specific failures under the macOS toolchain, and one filename-case ambiguity fixture on a case-insensitive volume. They were not silently fixed or counted as passes. Linux CI and hosted CI were not run.

The locally validated wheel remains `fdisbull-0.27.0-py3-none-any.whl` (819,447 bytes; SHA-256 `973703624630ef51985a280d8a1b43bb698a74c70145ba30c70e8b6b6f17d4ef`). No version bump, release, system installation change or merge is established by this report. The pending feature and predecessor MRs remain subject to the user’s unmerged-work boundary. This macOS DOS-backend evidence does not qualify Windows/Wine, other hosts or generic whole-machine rewind.

## Bounded private replay recipe

This is a source-bound, prepared-state recipe. It requires the operator’s matching private game edition, prepared FDB/Anchor, game-file manifest, backend and JPC runtime/media/movie. No game, firmware, saved state, raw observation or portable standalone kit is supplied here. The [private authored-controller archive](https://gitlab.com/-/project/88349936/uploads/fb66891c6a75840a0527c8e32f7d63bd/fdisbull-frame-delta-authored-controls-20261101.zip) is 43,695 bytes, SHA-256 `6c0a8ab5d90ef42e5db617148b84300b38fb386f9d0ec3466ba2e25364003019`; the publication owner verified a byte-identical download. It preserves the authored scripts and their private path bindings. **The game, prepared Anchor/FDB, imported helper, predecessor controller and runtime are not included.** Obtain those separate hash-matched inputs and verify all identities in `metrics.json` before use. The original fDisBull controllers retain explicit private-root bindings; preserve the provisioned layout or document/hash a separate path-only derivative rather than silently treating it as the measured controller.

1. Select exact measured source `762f6e72021f3f558844d332472c1f19280a0015` with a suitable existing Python environment. Verify the source-module hashes, native candidate SHA, source-bound observer/helper and preparation/project receipt hashes. Keep runtime outputs outside Git and use fresh output directories. Accept only an absent/empty sealed WAL and stable database/copy hashes; SHM metadata is not committed content.
2. Recheck the current storage policy and proposed maximum before every growth phase. The measured matrix admitted at most 512 MiB of new output, used 64 MiB primary live caches and a 600-second host deadline, and reaped each owned child. A historical admission is not a new storage authorization. Keep one native owner and run phases serially.
3. Bind the private roots, then run the following measured matrix controller with three trials, 32 samples, four warmups and interval eight. Its default invocation without `--execute` validates a plan first. All receipt/controller hashes must match this report.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$FD_REPO/src" TMPDIR="$FD_RUN/tmp" \
  "$FD_PY" -B "$FD_RUN/control/fdisbull-delta-benchmark.py" \
  --repo "$FD_REPO" --start "$FD_PREPARED_RECEIPT" \
  --expected-head 762f6e72021f3f558844d332472c1f19280a0015 \
  --output "$FD_RUN/evidence/$FD_FRESH_MATRIX_NAME" \
  --trials 3 --samples 32 --warmups 4 --keyframe-interval 8 \
  --wall-seconds 600 --max-new-bytes 536870912 \
  --destination-reserve-bytes "$FD_APPROVED_RESERVE_BYTES" --execute
```

4. Reproduce the six separate JPC references with the hash-matched Java 21/JPC-RR 11.2/headless-author inputs: three fresh JVMs per mode, `--start-ns 4009098300 --scan-code 76 --warmup 4 --samples 32 --observation-bytes 65536 --depths 1,8,32 --trials 3`, 64 MiB output per JVM and a 300-second controller deadline. History adds `--checkpoint-every-sample --capture-every-sample`. Preserve the different native boundaries and settings; do not form a cross-engine ratio.
5. The restart checker is bound to the original sealed matrix/trial-0 identities, and the RNG supplement is bound to the sealed matrix/preparation. Run their exact hash-matched private recipes against copies, after prior native children reap: one-frame restart with a 64 MiB/120-second bound; two-mode RNG observation supplement with a 32 MiB/120-second bound. A new measurement produces new identities and needs an explicitly documented derivative; do not rewrite sealed receipts.
6. Verify source/backend/input preservation, reaping, count/timing arithmetic, checkpoint and image identities, the narrower PNG coverage, and all raw-sidecar hashes in private storage. Publish only sanitized summaries. Keep merges, hosted checks, release and installation as separate gates.

Exact controller SHA-256 values:

| Controller/helper | SHA-256 |
|---|---|
| `fdisbull-delta-benchmark.py` | `795c0cb4fc18fdaa6e588aa8b13bf45e35609a74a858ee9624ae7bf77558585d` |
| `jpcrr-reference-benchmark.py` | `02f81e2c2134244f5fa9bb2c5076b68bdbd4a2771be6e2e6d88b227f115ba26b` |
| `run-jpcrr-three-trials.py` | `2e79146f33a17a166e65cf597059b3522762039d63a20828cf16d307ca7d4c66` |
| `restart-delta-check.py` | `8f9bc31276a7626cb1a12220f50c6057b36ab8086d094d5144cf058d6897cad2` |
| `rng-observation-proof.py` | `adb094b392939579e9b7abee00ddb82aaf202f7b803a6af8fdd1b01b7a368eb8` |
| `fdisbull-loop-benchmark.py` | `13b00f0890546f4d1937f4ee482635f3b19d778ca10575d32162664bd7bbc4d8` |
| `kq1-review.py` | `f4c56cd166dfb4c4ec6afc5f41ef795d49ac87e7bdfa806017e56ea1282f9c29` |

Source, receipt, JPC JAR/front-end and wheel digests, all three per-trial measurements and complete comparison denominators are in [metrics.json](metrics.json). The attachment preserves the measured controllers rather than packaging a standalone replay kit.

## Companion work

[Draft Library intake MR !42](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/42) at source `2323b2b4715a98b4bad44b576685f0a9330d6eb0` tracks separate Library intake work. It is a companion to this feature; it is not part of measured runtime source `762f6e72021f3f558844d332472c1f19280a0015`. The publication owner confirmed it open, draft and unmerged.
