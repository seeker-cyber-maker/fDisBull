# Windows patch analysis path

The current Windows path has two distinct comparisons. A saved Wine/QEMU
experiment compares **two guarded code layer stacks of one PE version** from a
full native checkpoint. The offline trace helper compares **separately captured
PE versions** only when an investigator supplies evidenced site
correspondences. The debugger does not launch a patched project byte version or
restore one version's checkpoint into another executable. The latter would
require its own compatible-state and input contract.

## Evidence spine

| Stage | Existing component | Evidence and limit |
| --- | --- | --- |
| Identify inputs | Project byte identity, loader provenance, PE image base | Record each binary's hash, build identity and origin independently. Equal project-local version numbers do not establish a pair. |
| Locate candidate changes | Recursive analysis, xrefs, CFG and normalized instruction semantics | A code diff and static reachability are **candidate influence**, including unresolved calls, indirect transfers and memory aliases. They are not observed effects. |
| Map sites | `compare_trace_topology` with reviewed one-to-one correspondence for separate binaries | Record the source of each mapping. Keep unmatched blocks and repeated loop sites unresolved; do not infer a join from matching instruction text or runtime address. |
| Compare one PE under counterfactual layers | Wine/QEMU guarded RAM or execution layers and `compare_experiment` | Restore the same full native checkpoint before each script. Capture completed instruction traces, selected memory, final registers/FLAGS, stop observations and frames. Verify final baseline restoration. |
| Compare independent PE runs | Export each version's qualified trace, then use the offline topology helper | Site correspondence can align paths; input and checkpoint compatibility must be established separately. The helper does not certify both runs began in equivalent states. |
| Build an executable explanation | Authored UIL or a narrow C model with explicit typed ports and effects | Compare model outputs against original execution over chosen inputs and boundaries. Generated C is a realization of the model, not independent evidence that the binary was translated faithfully. |

At an aligned PE trace site, the runtime instruction pointer is treated as the
paired site identity **only when it equals the recorded runtime site**. This
prevents a load-base or code-placement difference from appearing as a
behavioral register change.
Other register values remain raw: a general register may hold an image pointer,
but automatically rebasing it could hide a real data difference. EFLAGS/RFLAGS
remain part of the observed state. A rejoin is a common control site, not a
state merge; compare the registers and selected memory at that point and at
later boundaries.

The measured effect envelope is only what the script captured. Selected-thread
traces are completed steps with pre-instruction registers; they are not a log
of all memory reads/writes or peer-thread scheduling. Selected memory ranges
show net bytes at their sampling points. Hidden CPU state, heap outside those
ranges, other threads, devices, files and timing stay unknown. A widened
static blast radius must retain those unknown effects, while a narrow observed
effect can be reported without assuming every reachable object changed.

## A bounded PE pilot

The homegrown PE64 GUI oracle in `tests/wine_gui_fixture.c` exposes an
`experiment_value` function and a `counter`. The native test in
`tests/test_wine_advanced.py` saves a checkpoint, runs the same click and trace
script under baseline and an execution layer, checks the counter byte change,
the topology report and final restoration. It requires `FDISBULL_PE_QEMU`,
`FDISBULL_PE_KERNEL`, `FDISBULL_PE_INITRAMFS` and `FDISBULL_PE_FIXTURE`; without
them pytest skips native acceptance. Synthetic PE32/PE64 trace tests cover
rebased instruction pointers, divergent paths and FLAGS at a rejoin. Those
tests check the report logic, not a native PE32 run.

For a real old/new Windows binary pair, a first qualified pilot should use a
redistributable homegrown PE pair with a stable callable boundary. Preserve
both original hashes, public symbols or reviewed block correspondences, the
input recipe and per-version runtime receipts. Compare the pair's outputs and
selected state before attaching a UIL/C explanation to either binary. A
successful finite differential run supports that input set and observation
boundary; it does not prove cross-language or whole-program equivalence.

This organization follows the useful *shape* of two public case studies:
[Anthropic's Windows binary-to-C account](https://www.anthropic.com/research/discovering-vulnerabilities-with-claude)
describes an annotated C program for relevant features checked against the
binary, while its [Windows N-day study](https://www.anthropic.com/research/n-days)
uses vulnerable/patched binaries, symbols, decompilation and a function-level
diff. Neither establishes lossless translation of arbitrary Windows binaries.
The current fDisBull UIL/C backends are bounded typed-model realizations, as
documented in [Common UIL](COMMON_UIL_CONTRACT.md),
[native realization](COMMON_UIL_NATIVE.md) and [UDC C](UDC_LINUX_AND_C.md).
