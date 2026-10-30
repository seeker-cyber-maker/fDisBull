# Lost in Time: measured fast scene recovery

Status: bounded experiment and implementation requirements, 2026-10-29.
See [the proposed acceptance contract](SCENE_RECOVERY_FAST_PATH.md).
This report publishes counts, timing methodology and an authored microbenchmark;
the private game resources, decoded text, saves and native captures are omitted.

## Result

The experiment produced a broader investigator outline, typed source obligations
and seven executable branch models. One model is a newly lowered poster-inspection
branch; six reuse earlier bilge work. It also emitted two partial packages in the
existing Z candidate format and exercised the actual candidate player.

| Layer | Measured coverage | Claim ceiling |
|---|---|---|
| Container/script inventory | 7 validated containers, 634 members, 61 distinct TOT scripts | Candidates, not 61 rooms; two script code boundaries and six LTK sidecars remain unparsed |
| Investigator outline | 12 source views, 23 targets, 51 action descriptions | Private research outline; unresolved behavior is retained |
| Typed UDL descriptions | 51 descriptions | Each broad contract refuses execution while its obligations remain unresolved |
| Executable shared IL | 7 branch models linked to 11 source action IDs | Five selected response models and two retained-effect projections; not complete handlers or scenes |
| Bilge Z package | 7 contexts, 9 objects, `partial: true` | Disconnected investigator entry states; no complete movement/puzzle loop |
| New poster Z package | One separately bound partial scene package | One source-profile action with a target-availability guard |

The new hold packet contributes two scene descriptions, five targets and twenty
action rules to those totals. All five source geometry/raw-ID/dispatch joins were
reviewed. Three primary routines have complete bounded ASTs; two other routines
have official decoder output but unsupported nodes in the independent parser.
Their weaker status remains visible. A successfully decoded description is not
counted as an executable implementation.

The investigator interface is not yet qualified for player-knowledge parity:
some bilge public context identifiers disclose model state. Private summaries
also contain puzzle spoilers and must not become player narration by default.

## Smallest new code-accepted slice

The poster branch supplied a useful independent test of the reduced verification
budget. Its selected path has no script-helper calls. The lowering preserves its
camera and held-item guard, three response-selection cases, ordered response and
counter update, and signed-byte storage behavior. The action has a separate
source target-availability predicate; a removed-target sentinel is accepted by
the raw handler formula but excluded from the callable Z object.

Acceptance checked:

- Exact resource, AST and text-binding identities, plus the source dispatch and
  target-geometry join.
- Signed reads and unsigned byte writes in a pinned interpreter profile, with
  modulo-256 wraparound. The profile is ScummVM commit
  [`984277131e510e554a669e865828efb953c03941`](https://github.com/scummvm/scummvm/tree/984277131e510e554a669e865828efb953c03941/engines/gob).
- All 256 typed counter inputs against independently calculated response-case
  and increment expectations, plus two wrong-context/held-item refusals.
- Candidate Z schema validation, one successful action through the real player,
  and exclusion of the removed target.

This establishes conditional agreement of the bounded headless model with the
reviewed source profile. It does not establish decoder correctness from first
principles, all-state reachability, original-DOS overflow behavior, native text
acknowledgement timing, or current mouse-input readiness. No formal Gob-to-UIL
solver proof or new native execution is claimed. The previously qualified
35-stage native route was not repeated for this helper-free lowering.

## Machine timings

These are separate local measurements, not one timed cold recovery run.
Acquisition, tool installation, previous decoding, analyst interpretation and
earlier implementation are outside the warm pipeline timing. Analyst wall time
was not instrumented; no throughput estimate is inferred from machine time.

| Operation | Measured wall time | Scope |
|---|---:|---|
| Archive read, six extractions and cached-byte comparison | 16.68 ms | One archive and six members |
| Six fresh official `degob` invocations | 18.57 ms total | 2.46–4.21 ms each; outputs may repeat helpers |
| Three bounded ASTs plus dispatch/hotspot checks | 2.50 ms | Primary routines and relevant interface records |
| Source packet build and checks | 47.47 ms | Includes Python subprocess startup |
| Supplied-container inventory | 172.47 ms | 61 script identities; no scene acceptance |
| Warm source evidence → UDL/UIL/Z and checks | 162.74 ms | Six reused models, one new poster model, artifact writes and candidate player subprocess |
| Within that run: prior bilge AST → UDL | 2.83 ms | Existing builders; prior model identity retained |
| Within that run: new poster AST → UDL | 0.81 ms | New bounded lowering after its code was authored |
| Within that run: UDL → UIL role copy | 1.43 ms | Metadata copy, not semantic compilation |
| Within that run: poster finite-domain checks | 44.45 ms | 256 counter cases and two guard refusals |
| Within that run: candidate validation/player subprocess | 71.74 ms | Both partial Z packages |

The pipeline runtime used the preserved 0.22.0 shared-IL evaluator. Z validation
used the clean, pinned [PR #18](https://github.com/seeker-cyber-maker/fDisBull/pull/18)
source at `c107d1576d46d7dc353c8043cb81be5005e8926b`; this is a pending integration,
not a claim that the installed release already exposes Z. The repository/API
review and the synthetic reader benchmark used current main
`ed89abca061964385b176537bc9fd275dd02afa5` (0.23.0).

The [sanitized measurement record](evidence/scene-recovery-2026-10-29/scene-pipeline-summary.json)
retains exact timings, coverage, hashes of our implementation files and scope
limits. Private source-backed outputs are not reproducible from this public PR
alone; the synthetic benchmark below needs no game assets.

## Does C beat ASM here?

For these scenes, the useful source is Gob resource bytecode. Official `degob`
renders its branches and operations directly. Its C-like output is not C
reconstructed from the x86 interpreter. Recovering that interpreter first would
answer a lower-level question than the scene conversion needs.

A fresh original-executable baseline took 267.62 ms to import and 6.81 ms for
entry-recursive static analysis. It decoded only 16 instructions covering
29 bytes, ending after a copy/far-return startup sequence with unresolved memory
and stack semantics. This is not a matched semantic sample for a C/ASM speedup.

The separate [authored reader benchmark](../examples/recovery/benchmark_lift_paths.py)
compares actual existing fDisBull paths on two straight-line uint16 register
examples. Results are medians of five batches of 100 calls, after unmeasured
warm-up, in milliseconds per call:

| Instructions | ASM bytes → IL | Already available C → IL | ASM bytes → C → IL |
|---:|---:|---:|---:|
| 2 | 0.1272 | 0.0215 | 0.4143 |
| 16 | 0.3451 | 0.0746 | 1.0699 |

Parsing supplied C was cheaper; deriving C through the current ASM path added
work. The paths share the restricted ASM decoder and are not independent source
oracles. Eight literal semantic cases passed, two bounded Z3 obligations returned
`equivalent_under_assumptions`, and two altered candidates produced
counterexamples. There is no memory, branching, ABI, flag, native-timing, general
decompiler or human-comprehension result in this measurement.

Reproduce with an installed project environment containing its normal dependencies
and the optional verifier dependency:

```bash
PYTHONPATH=src python examples/recovery/benchmark_lift_paths.py \
  --output /tmp/fdisbull-representation-paths.json
```

The script records `unavailable` when the optional
verifier is absent; it must not be read as proving equivalence in that case.
[Exact benchmark results](evidence/scene-recovery-2026-10-29/representation-paths.json).

## Engineering consequence

The bottleneck to remove is repeated manual source binding, dependency analysis,
adapter authoring and evidence handling. The first priorities are a Gob source
adapter, a claim-scoped effect slicer, explicit acceptance receipts and compatible
dependency-cache lookup. Next come generation of the existing Z envelope, bounded
scene streaming, separated presentation/effect boundaries and compact results.
The [requirements document](SCENE_RECOVERY_FAST_PATH.md) gives an acceptance check
for each requested seam.

This work extends the existing
[progressive scene proposal](https://github.com/seeker-cyber-maker/fDisBull/pull/14),
[source/UDL/UIL/UDC direction](https://github.com/seeker-cyber-maker/fDisBull/pull/17),
and [Z consumer](https://github.com/seeker-cyber-maker/fDisBull/pull/18).
It changes documentation and adds an opt-in synthetic benchmark. It does not
change production IL semantics, weaken native guards or merge pending features.
