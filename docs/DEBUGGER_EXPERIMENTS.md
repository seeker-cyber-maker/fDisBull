# Saved debugger experiments (0.15.0)

An experiment preserves a private native checkpoint, its active layer stack,
owned breakpoints/watchpoints, hook definitions and hit counts, an immutable
bounded script, and explicit memory observations. A comparison restores that
setup before a baseline trial and before a trial with a supplied layer stack.
It restores the baseline setup again afterward, including consumed once-hooks.

The experiment, trial scripts, results, screenshots and traces remain in the
project. Reports and frames can be exported after closing every emulator and
reopening the project. Neither trial edits the original static byte version.
An experiment is a repeatable scripted procedure; it is not deterministic
record/replay, an instruction rewind log, or a complete snapshot of host files.

See the [TAS analysis harness guide](TAS_ANALYSIS_HARNESS.md) for checkpoint
branches, evidence collection, failure minimization and UIL/UDL differential
tests built around these experiments, including their timing and claim limits.

## Interfaces

Use Python on a live session or JSON requests through `fdisbull serve` / `debug`:

| Python | JSON method | Parameters |
| --- | --- | --- |
| `debug.controls()` | `debug-controls` | `run` |
| `debug.save_experiment(...)` | `debug-save-experiment` | `run`, `name`, exactly one of `script` / `script_id`, optional `observations` |
| `project.debug_experiments(...)` | `debug-experiments` | optional `version` |
| `project.debug_experiment_info(...)` | `debug-experiment-info` | `artifact` |
| `debug.restore_experiment(...)` | `debug-restore-experiment` | `run`, `experiment` |
| `debug.compare_experiment(...)` | `debug-compare-experiment` | `run`, `experiment`, `layers`, optional `timeout_ms` |

`layers` is the complete ordered stack for the alternate trial. Use `[]` to
test no layers. The baseline always uses the stack captured in the experiment.
Existing layer guards and native-state input/backend identity checks still
apply. `debug-experiments PROJECT` and `debug-experiment-info PROJECT ARTIFACT`
also work as offline CLI commands.

Native DOSBox and DOSBox/QEMU require the layers-capable backend. Custom PE64
Wine/QEMU supports experiments with execution/data breakpoints and its existing
RAM/execution layers. PE hook actions remain unsupported. The optional IDA
backend and outer/raw machine context do not support saved experiments. The
separate CHIP-8 v6 profile also supports the bounded trial contract below.

## Capture and restore controls

Place controls through the project debugger API before saving the experiment.
Execution breakpoints retain their project address, DOS CS interpretation and
static/execute view. DOS watches are recorded per live native byte, so deleting
part of an ordinary watch group preserves only its remaining bytes. Hook
definitions include actions, access mode, once/max-hit policy and the exact
current hit count. A partially deleted multi-byte hook is refused rather than
silently reconstructed with a different meaning. Untracked DOS native controls
are refused. Direct low-level RPC mutations are outside the owned API contract.

Restoring an experiment **replaces all current owned controls**. Native IDs may
change. DOS recreates session controls; PE verifies and reuses the native
registry restored with the whole VM, preserving pending instruction displacement
and page guards. Reinstalling a PE breakpoint at the saved PC would introduce an
extra stop. The result maps captured IDs to their current descriptors and hooks.
A route can use stable
captured keys through its reserved `$controls` binding:

```python
bp = debug.breakpoint(address)  # address must have the selected analysis/view
route = {"format": "fdisbull-script-1", "steps": [
    {"op": "run", "timeout_ms": 5000},
    {"op": "registers"},
    {"op": "delete-breakpoint",
     "breakpoint_id": f"$controls.breakpoints.{bp['breakpoint_id']}.breakpoint_id"},
    {"op": "trace", "count": 32, "timeout_ms": 5000}
]}
saved = debug.save_experiment("branch hypothesis", script=route,
                              observations=[{"address": data_address, "length": 2}])
result = debug.compare_experiment(saved["artifact"], layers=[theory_layer],
                                  timeout_ms=60000)
```

Addresses and the layer above are caller-selected, verified project inputs.
For DOS watch groups, use each returned byte's `breakpoint_id` as its captured
key. PE watches have one key for the whole range. Aliasing a route result as
`controls` is rejected. Ordinary scripts retain their existing reference rules.
PE routes can request `expect:"watchpoint"`; DOS access stops use `breakpoint`.

Plain `load_state` keeps its existing backend-specific control semantics. The
additional replacement/rearming behavior belongs to `restore_experiment`.
Experiments survive a project restart and can be restored in a fresh compatible
session. They cannot migrate incompatible native states between backend builds,
launch inputs, project versions or emulator configurations.

## Trial evidence and differences

A comparison stores its checkpoint/script identities, layer hashes, both script
reports, final register snapshots, requested memory ranges, and references to
screenshots and traces. It also compares memory/register reads made inside the
route and normalized stopping reasons, so an intermediate value need not survive
to the final CPU snapshot. `ok` means the procedure completed and the baseline
was restored; `observed_difference` separately reports whether the captured
observations differed.

Differences include register fields, memory hex, image hashes and the first
observed difference in each pair of traces, paired by route step and event index.
This is positional comparison of bounded evidence, not trace alignment after a
divergent loop. DOS's 15-byte fetch lookahead is truncated to the decoded current
instruction for comparison; a patch to a later instruction is not reported as
having executed early. Raw trace artifacts retain their original evidence.
DOS records pre-execution fetches, with the final record pending; PE records
confirmed completed steps. Those semantics are retained in the report.

An assertion failure, unexpected stop, incomplete trace or unexpected timeout makes the
trial incomplete. The alternate trial is not started after baseline failure.
An explicitly expected `timeout` remains a valid bounded script outcome.
Incomplete trials cannot establish equality: `observed_difference` is null when
both trial records exist but either is incomplete. A missing trial leaves the
comparison null. Script failures and attempted restoration remain recorded.
A partial native/control restore closes the session; it must not be resumed.

`timeout_ms` is a shared comparison dispatch budget of 1..600,000 host ms.
Existing native serialization and RPC deadlines still govern calls already
dispatched. For the DOS/PE behavior described above, final baseline restoration is attempted
even after budget expiry; the timeout is not a hard wall-clock limit on
serialization and cleanup. The CHIP-8 v6 rule below uses its remaining budget
and closes the owner if the final restore cannot be completed.
There are at most 64 memory observations, totaling 64 KiB per trial. Existing
script, layer, artifact and native-state size budgets remain in force.

After native restore, DOS framebuffer evidence is invalid until another frame
completes. A route needing `click-frame` should first run enough bounded guest
time to refresh the frame. Check that no earlier watched event interrupts that
warm-up. Host/game files are checked by the native-state manifest and are not
rolled back. Scripts that write an in-game save can invalidate the baseline;
use an isolated input copy and preserve the matching files separately.

## CHIP-8 v6 comparative trials

The explicit `qemu-chip8` v6 frame-key runtime, launched with its matching
checkpoint tool, supports `controls`, `save_experiment`, `restore_experiment`
and `compare_experiment`. The existing JSON `debug-*` methods and offline
`debug-experiments` / `debug-experiment-info` routes use the same names. The
experiment, trial and comparison documents use the separate formats
`fdisbull-chip8-experiment-1`, `fdisbull-chip8-trial-observations-1` and
`fdisbull-chip8-experiment-comparison-1`. An experiment and its checkpoint are
bound to the original ROM and version, exact v6 QEMU and checkpoint tool, and
full checkpoint bytes and metadata. Original ROM bytes are unchanged.

Each arm starts by restoring the same verified full checkpoint. The baseline
uses its saved layer stack; `layers=[...]` supplies the complete ordered
candidate RAM/fetch stack. Layer guards are checked against the saved 4 KiB
RAM and saved active-layer base before either arm. An unchanged stack can be
used even when its saved RAM layer has guest-modified bytes. Hook definitions,
logical IDs and hit counts are restored, and a fresh key owner adopts held
keys without injecting new edges. A final verified full restore reinstates the
saved setup. A stored full or delta frame-history DAG remains retained; trial
execution invalidates its former live edge. Host files are not restored.

A CHIP-8 trial script may use only `step`, `run`, `registers`, `memory`,
`screenshot`, `assert`, and deletion of a captured hook through
`$controls.hooks.<id>.hook`. If any hooks were captured, every `run` must
specify `stop_on_hook=True`, limiting a run to one dispatched hook. Ordinary
user breakpoints must be removed before capture. Input, writes, tracing,
timelines, selected undo, nested experiments and other operations are not
trial-script operations. The whole script and candidate are checked before
execution; failed baseline assertions or other incomplete baseline evidence
skip the candidate. A timeout makes a CHIP-8 arm incomplete even when the
script expects that stop. At most 128 expanded steps and a 1 MiB script are admitted,
subject to the more conservative 4 MiB per-arm report-plan limit. Up to four
PNG screenshots per arm are accepted, each at most 1 MiB. There are at most 64
nonoverlapping declared flat RAM ranges totalling 4 KiB; each scripted memory
read is at most 4 KiB, and declared plus scripted reads are bounded to 64 KiB.
The project artifact budget and native checkpoint limits can bind earlier.

The comparison covers exposed CPU registers, declared and intermediate RAM
reads, normalized stops and hook actions, decoded screenshot pixels, and the
reported RNG, timer, framebuffer, key and fault fields. Administrative owner
IDs and virtual-time bookkeeping are retained as provenance but do not alone
establish a program difference. PNG file hashes remain available alongside the
pixel comparison. `observed_difference` describes only this captured evidence;
it is `null` for an incomplete paired comparison, and no comparison is produced
if an arm is missing. This is not deterministic replay or proof of complete
execution coverage.

An uncertain dispatched arm, failed final restore or uncertain result
publication closes the owner and retains the available receipt; do not replay
it automatically. If the comparison deadline leaves no time for final restore,
the owner closes and `baseline_restored` remains false. A selected CPU/RAM
partial undo blocks saving or comparing an experiment; an explicitly requested,
verified `restore_experiment` can load the full anchor and clear that freeze.
Eleven bounded authored native CHIP-8 trial witnesses passed locally on macOS
arm64 as part of a 65-case trial and preservation run. This does not establish
game or conversion compatibility, historical timing, hosted CI qualification,
or a change to the DOSBox-X default.

## Real DinoPark verification

The parameterized `examples/dinopark/verify_experiments.py` navigates the actual
game to its concession catalogue, captures an experiment with a disassembly
breakpoint, eight read-watch bytes and a once-hook, deletes those controls,
closes the emulator/project, then compares baseline and execution-layer trials
from a new session. Both trials use the saved script with marked 8px frames.

```bash
PYTHONPATH=src python examples/dinopark/verify_experiments.py \
  --executable /absolute/path/to/layers/dosbox-x \
  --game-dir /absolute/path/to/user-owned/dinopark \
  --output /absolute/path/outside/git/new-experiment
```

Its `private/` directory contains the game copy, database and native states and
must stay local. Only selected files from `evidence/` may be shared. The saved
script's native control keys belong to that experiment; rerun the driver to
create a new experiment for another project. This proves a selected price
lookup, not a full purchase or a universal revenue formula. See the
[0.15.0 verification record](VERIFICATION-0.15.md).
