# Bounded patch behavior diff prototype

This prototype builds on saved debugger experiments and temporal code layers.
One experiment checkpoint supplies the same starting machine state and script to
two trials. Save layer stack A as the baseline, then call
`compare_experiment(..., layers=B)` with the complete ordered stack B. The
comparison restores the experiment before each trial and attempts to restore A
again afterward. This is a **full native checkpoint restore**, not CPU/RAM delta
rewind. It is also not deterministic replay: input timing, devices, external
files and hidden state may still matter.

The result keeps three questions separate:

| Field | Meaning |
| --- | --- |
| `observed_difference` | Existing representation-sensitive comparison of captured observations, including trace bytes and instruction text. |
| `code_difference` | Captured instruction bytes differ at an aligned site. Text-only rendering changes are reported separately. This alone is not a measured behavior change. |
| `control_flow_difference` | Observed path sites differ. An open tail or unmapped span yields `null` when it leaves the path relation unresolved. |
| `observed_effect_difference` | Paired register/flag snapshots, selected RAM, route observations or frames differ. A changed path alone does not set this field. `false` means no difference **within comparable samples**; unpaired trace state remains unknown. |
| `semantic_equivalence` | Always `null`: bounded agreement does not prove that two programs mean the same thing for all inputs. |

Each trace comparison now includes `topology`. The saved-experiment path asserts
that both trials share one project version, then pairs sites by project address
and context. The original trace artifacts remain available,
and reports common spans, divergent spans, unmapped unresolved spans, open tails and rejoin
sites with half-open event index ranges. An extra tail on one side can reflect
the observation boundary, so it is not automatically a path difference. A
rejoin says the observed control path reached the same site; it
does not say the state merged. `rejoin.registers` and common-span entry/exit
relations show whether sampled register fields, including FLAGS when supplied,
agree at those points. `observed_path_overlap` is a trace coverage ratio, not a
semantic distance score. Repeated loop sites are not used as guessed rejoin
anchors; unique monotone sites and exact intervening sequences provide the
bounded alignment. A negative trace code/register verdict requires every event
on both sides to be paired; otherwise it is unknown. A positive difference at
one paired site remains a valid bounded observation.

For explicitly selected RAM ranges, each changed observation also reports
contiguous byte-run offsets, lengths and a total count. These are **net sampled
differences**, not a log of every write. An instruction can write the same value
or write and later restore a value without appearing in that list. Use watches
and narrower checkpoints to investigate such paths. The existing final register
comparison and route-step observations remain available alongside the map.

## Comparing independently built binaries

The pure offline helper `fdisbull.behavior_diff.compare_trace_topology` accepts
two trace records and an optional `correspondence` list. Separate binaries need
one-to-one, evidenced site pairs **even if both projects call their local
version `1`**. For example, a synthetic pair of sites may be declared as:

```python
correspondence = [{
    "baseline": {"source_version": 1, "context": "flat", "project_address": "0x100"},
    "layer": {"source_version": 2, "context": "flat", "project_address": "0x900"},
    "evidence": "reviewed source-to-source block correspondence",
}]
map_result = compare_trace_topology(old_trace, new_trace,
                                    correspondence=correspondence)
```

The mapping is an investigator claim with provenance, not proof of semantic
equivalence. Unmapped sites remain distinct. The live saved-experiment API
currently compares layers of one project version; it does not automatically
boot two independently built binaries from one compatible checkpoint. Exported
traces can use the offline helper when each binary has its own qualified run.

## Influence and uncertainty

The prototype's measured influence envelope consists of captured path,
registers, flags when exposed, selected RAM, route observations and frames. It
can show a changed instruction whose selected state and later path agree, or a
branch that rejoins with different flags and later converges. It does **not**
infer that all reachable code or memory changed because a patch was installed.

An authored detour test models the case raised by [BLA's public anti-REA
project](https://github.com/qybaihe/bla): two paths can have low site overlap,
then rejoin with equal sampled state and output. The map reports a path change
and no sampled effect change, while leaving semantic equivalence unknown. This
fixture is not a test of a BLA release or of any private crackme challenge.

Potential influence beyond the samples remains a separate static question.
The existing CFG and normalized instruction semantics can supply a conservative
candidate reachability and may-write analysis, but that would include unknown
calls, aliases, unmapped transfers and paths never taken in a trial. This
prototype does not turn that candidate cone into observed effects. In
particular, unselected RAM, hidden CPU/FPU state, devices, interrupts, external
files, and timing are outside the verdict. DOS trace records are before-fetch
observations; the final budget record can be pending. A common PC or same final
bytes therefore does not establish whole-program equivalence.

The helper admits at most 10,000 events per side. It limits stored example
changes to 64 and topology segments to 256, reporting truncation. The original
trace artifacts remain the evidence for detailed inspection. Native DOSBox and
Wine/QEMU acceptance of this new report shape has not yet been run.

For the PE route and its source/model validation gates, see
[Windows patch analysis](WINDOWS_PATCH_ANALYSIS.md).
