# Matched research-method pilot: prepared, not dispatched

This imports the authored protocol, dispatch packets and measurement tools from
the [2026-11-02 Colonization methodology delivery](https://chatgpt.com/library?file_id=libfile_4db229554abc81918ebbbcf658951771&account_id=personal).
It is a reusable experiment design. No independent worker ran in that delivery,
and this import does not launch the experiment. The original host-availability
statement in `protocol.json` is a historical observation, not a claim about every
agent host. Worker times, token costs and agent speedup remain unmeasured.

## Dispatch boundaries

A coordinator must create genuinely separate conversational contexts and private
workspaces through the host. Copy only the allowed packet and exact user-owned
inputs into each worker workspace. Instructions alone do not enforce blinding.
Do not give a blind worker this whole repository or example directory.

| Assignment | Initial packet |
| --- | --- |
| Binary-only worker A | `COMMON_TASK.md`, `WORKER_A_BINARY_ONLY.md`, `claims.template.json`, logger, exact original target/resources and generic tool/processor references |
| Self-research worker B | Common packet plus `WORKER_B_REFERENCES.md` and `REFERENCE_LEADS.md`; withhold the optional prebuilt hypotheses |
| Optional prebuilt-assisted replicate | A separately recorded future run receiving `PREBUILT_HYPOTHESES.json`; charge packet preparation separately |
| Reviewer/coordinator | `reviewer/answer_key.json`, calibration helper and retained evidence; these expose target-specific answers and offsets |

The two worker roles have the same question and acceptance scope. Context mode,
source assistance and execution isolation are independent choices. Worker B must
freeze guide-derived hypotheses before candidate-code verification. Source-lead
metadata is preserved from the delivery; this import does not claim a fresh read
or independent confirmation of those guide pages.

## Tools and evidence

`tools/log_worker_event.py` appends observable milestones for one run in a private
worker directory. It rejects reuse of another run's log and terminal-run writes.
Its monotonic elapsed time is local to one running host/boot; do not merge clocks
across hosts or treat resumed records after reboot as one timing interval. Token
and tool-call counts are explicit reports, not automatically measured telemetry.

`tools/check_production_dependencies.py` is the coordinator's assisted calibration
helper. It requires exact owned inputs, Capstone, binutils and a separately
prepared DOSBox backend. Generated source-retaining files must remain in a new
private directory outside Git. Its historical calibration covered 420 unique
input cases; a fresh-process repeat was a replay of those same cases. Recovering
the shortage-accounting graph does not establish full warehouse mutation, exact
production ratios, a whole colony turn, or another edition.

The original [report](https://chatgpt.com/library?file_id=libfile_cf79394fa878819193915c9988f6f4fd&account_id=personal)
and [benchmark status](https://chatgpt.com/library?file_id=libfile_8d7e0fc431e08191b5303cd5381f9b54&account_id=personal)
remain separate evidence. This is not the earlier Gemini three-arm experiment.
No original executables, text resources, saves, emulator states, or generated
byte-retaining harnesses are included here.

For the general context/delegation policy see
[Draft MR !47](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/47).
The pilot's settings are experimental parameters, not universal worker quotas.
