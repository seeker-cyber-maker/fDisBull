# Experimental QEMU AGI pilot

Import caller-owned raw LOGIC code using `fdisbull import CODE PROJECT --arch agi`.
The entry and base are zero and static decoding is unavailable. Select
`backend="qemu-agi"` explicitly on that project and provide the separately prepared `qemu-system-agi` executable. An optional
`--agi-runtime-package` selects a private resource-backed package whose entry
LOGIC must match the imported bytes.

```python
with project.debugger(qemu_agi, backend="qemu-agi") as debug:
    registers = debug.registers()
    step = debug.step()
    observation = debug.scene_observe()
    # With a runtime package, observation["projection"] contains the native
    # 160 x 168 visual and priority planes as hexadecimal byte strings.
```

The native GDB PC is available as `registers["instruction_pointer"]`. With a
runtime package, it points into QEMU's execution trampoline and `linear_pc`
is null. Use `registers["logical_position"]` for the current LOGIC ID, byte
offset and source hash. These follow calls and returns across LOGIC resources.
For raw code, the LOGIC ID is zero.

A successful single step reports `outcome="step"` and `retired=1`. Other
outcomes include `stopped`, `timeout`, `exited`, `return`, `quit`, `fault`
and `pending`. Inspect `retired` to see how many instructions completed during
the call. Calling `step()` again at a terminal or pending stop returns the same
outcome with zero retirements. An execution error marked `do_not_replay` carries
the available evidence from the original attempt.

Use `debug.cpu_inventory()` to identify the CPU and inspect its stopped status.
`debug.diagnostics()` returns bounded log bytes in hex. Supply the returned
identity and next cursor to read a later chunk. The equivalent JSON methods
are `debug-cpu-inventory` and `debug-diagnostics`.

`debug-agi-scene-observe` takes a run ID and an optional integer `timeout_ms`.
It brackets the scene read with identical stopped state snapshots. The result
includes actor state and a bounded event journal. Check the mask, epoch and
dropped counts when interpreting the journal. A position event records a change
of coordinates. With a bound resource package, the response also includes the
visual and priority planes at the same revision and source identity.

Start a JSON-lines CLI session with a resource package using this command.

```sh
fdisbull debug /private/logic.fdb --backend qemu-agi \
  --executable /private/qemu-system-agi --agi-runtime-package /private/resources.json
```

Read the `run` value from the launch response's `result`, then send the
following line on its standard input with that ID in place of `<RUN>`.

```json
{"id":"scene","method":"debug-agi-scene-observe","params":{"run":"<RUN>","timeout_ms":10000}}
```

The server returns one JSON response per line. A runtime projection often exceeds
its inline limit and returns a `fdisbull-output-ref-1` descriptor instead. Use
its artifact ID to retrieve the retained response.

```sh
fdisbull output-export out-<sha256> /private/scene-response.json
```

The exported response holds the observation under `result`. Use the same
output artifact directory as the server. To retrieve selected fields or ranges
from the retained response, see [bounded replies](OUTPUT_LIMITS.md).

## Save a checkpoint and continue in another session

Use a checkpoint-capable `qemu-system-agi` for both sessions. The debugger
reports `save_states` in its per-run capabilities after it inspects the CPU.
The earlier AGI executable still supports ordinary inspection and stepping.
See the [native build instructions](../native/qemu-agi-checkpoint/README.md).

The checkpoint is an artifact in the private project. Keep its ID and reopen
the same project with the same native executable, original LOGIC and, for a
resource-backed session, the identical package. This example saves inside a
called LOGIC and restores in a new process.

```python
from fdisbull.project import Project

options = dict(backend="qemu-agi", agi_runtime_package=package_path)
with Project(project_path) as project, project.debugger(executable, **options) as first:
    first.step()  # The entry instruction in this example calls another LOGIC.
    saved = first.save_state("inside-room.agi")
    artifact = saved["artifact"]

with Project(project_path) as project, project.debugger(executable, **options) as second:
    restored = second.load_state(artifact)
    assert restored["verified"]
    position = second.registers()["logical_position"]
    scene = second.scene_observe()
    next_step = second.step()
```

For JSON, use `debug-save-state` with the original run ID, then
`debug-load-state` with the new run ID and the saved `artifact`. To inspect
the saved identity and component size offline, run
`fdisbull debug-state-info PROJECT ARTIFACT`.

A restore loads a fresh stopped owner and compares the native checkpoint bytes,
registers, guest state and scene projection before replacing the active owner.
This preserves the current LOGIC and offset, call stack and retained scene events.
Resource-backed checkpoints also retain the visual and priority planes.
Ordinary stopped instruction boundaries and root returns are supported.
Resource-backed pending host requests, faults and quit stops reject capture.
Checkpoints are limited to 16 MiB and are specific to the native executable.
