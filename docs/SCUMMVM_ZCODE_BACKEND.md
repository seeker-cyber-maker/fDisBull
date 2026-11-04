# Native ScummVM GLK/Z-code integration

## Status

This change supplies the missing **native C++ command dispatcher, real ScummVM
hook installer, owned process launcher and Python control API**. It does not
implement a new Z-machine or execute the in-house word16 runtime. It extends the
ScummVM transport from !73; the independent word16 probe/comparison in !92 stays
separate.

**Not release-qualified:** the native bridge has been compiled and exercised
through the real inherited-socket transport with an authored event driver. The
complete ScummVM tree, injected translation units and a real game have not been
compiled/run together in the submitting environment. An unavailable upstream
source download prevented that gate. A compiled driver is not ScummVM evidence.
Do not describe this change as an installed or proven working game backend until
the opt-in real-engine test below passes.

## Architecture and existing machinery

`ScummVMZCodeSession` creates a private copy of the selected raw v3 story and
launches `ScummVMRPC(engine='glk')`. The existing transport owns socket framing,
one response reader, finite request deadlines, isolated configuration/saves,
process termination/reaping and cleanup. AGI and Gob routing remains unchanged.
The only shared additions are GLK admission, a strict Z-code hello and an explicit
engine-data path. There is no persistent listener, external service or agent.

The native code is an opt-in header linked into the existing interpreter. It
has **no instruction implementation or game-specific parser**. The source hook
installer targets these actual upstream seams:

| File | Instrumentation |
| --- | --- |
| `mem.cpp` | Capture original declared story immediately after `loadMemory()`, before interpreter header adaptation. |
| `processor.cpp` | Before `CODE_BYTE(opcode)` and operand loading; after dispatch; retain nested begin/end IDs. |
| `glk_interface.cpp` | Synchronous, explicit untimed line/character input requests and delivery into original input buffers. |
| `processor_screen.cpp` | Capture screen characters with window IDs in the declared text-only mode. |
| `zcode.cpp` | Final output flush and explicit exited lifecycle. |

This is **text-only host substitution**, not pixel or full GLK UI equivalence.
The screen-character hook deliberately bypasses the renderer while enabled.
Memory output streams remain in the original interpreter upstream of that hook.
No claim is made for every v3 title, timed input, graphic modes or later Z-machine
versions. Initial launch IDs are `glk:zork1`, `glk:zork2`, `glk:zork3` and
`glk:zcode`; only an actual detected v3 source can be admitted. Zork II/III have
not been qualified merely because their IDs are accepted.

## Source and build

The selected source is **ScummVM v2.8.1**, commit
`750f2373fb100efe08c6444e36b68c01387fc307`, matching !73's AGI source pin. It is
not a claim about the newest ScummVM release or !73's separate Gob pin.

Use a clean, isolated checkout at that exact commit. An existing AGI ScummVM
clone containing that commit can supply a new detached worktree without another
source download. Do not apply these hooks on top of its already-patched AGI tree
or alter the shared checkout. `apply.py` defaults to a
dry-run diff. It checks the HEAD, clean tracked/untracked state, exact committed
source bytes and single anchors before writing. Repeated application is refused.
The build helper does not download or install anything, requires a new build
folder, and defaults to a 40 GB storage reserve. A separately authorized reserve
can be supplied through `FDISBULL_DESTINATION_RESERVE_BYTES` (minimum 20 GB);
the script never lowers it automatically. On macOS, source and build paths must be
on the explicitly supported CODEX or CACHE external volumes.

```sh
python3 experimental/scummvm/zcode/apply.py /private/scummvm-2.8.1
bash experimental/scummvm/zcode/build.sh \
  /private/scummvm-2.8.1 /private/scummvm-zcode-build 2
```

The build selects GLK only, enables `FDISBULL_ZCODE_AGENT`, and uses the SDL
backend. The launcher selects SDL's dummy video/audio drivers. GLK's startup
still needs the normal SDL/freetype build dependencies and the pinned source's
`dists/engine-data` assets, including its fonts archive. The headers, complete
build, asset discovery and resulting binary remain part of the real-engine gate.
A build receipt records the source, injected header, tracked patch and executable
hashes; it explicitly leaves real-game acceptance `not_run`.

The sidecar code is GPL-3.0-or-later. Keep the pinned upstream source, license,
patch and build instructions with any distributed modified binary. No ScummVM
binary, upstream source archive or game asset is included in this submission.
This does not settle broader first-party license/provenance review.

## Launch and debug

Run from a source environment containing !73 and this change:

```sh
PYTHONPATH=src python -m fdisbull.scummvm_zcode \
  --executable /private/scummvm-zcode-build/scummvm \
  --extra-path /private/scummvm-2.8.1/dists/engine-data \
  --story /private/ZORK1.DAT --game-id zork1 \
  --runtime-parent /private/runtime \
  --commands /private/commands.json
```

`commands.json` is a private bounded JSON array of strings. Without it, the module
runs to the first bounded stop, prints the observation and closes. For interactive
agent ownership and debugger operations, keep one Python session open:

```python
from fdisbull.scummvm_zcode import ScummVMZCodeSession

with ScummVMZCodeSession(binary, story, runtime_parent=private_runtime,
                        extra_path=engine_data) as session:
    entry = session.state()
    point = session.breakpoint(selected_story_byte_pc)
    stop = session.run(max_instructions=100000, timeout_ms=10000)
    one = session.step()
    paused = session.state()
    if paused['phase'] == 'input_pending':
        reply = session.command('inventory', expected_revision=paused['revision'])
    trace = session.trace()
```

`inventory` is an actual game command. Only `state()`, `memory()` and trace
retrieval are passive guest observations. `output()` drains the host capture
once without executing the guest. All resulting text, memory, traces and logs
are private game-derived evidence, not material for source commits.

The public entry point here is an experimental Python module/API, **not** a new
`fdisbull debug --backend` selector or FDB debug-session integration. It does not
silently activate a shared installation or change the internal player.

## Debugging and identity contract

- The host compares **every byte of the declared original story** with the
  native load snapshot. A hello echo is insufficient. The full supplied file
  hash also records trailing padding, which is not executed or included in that
  native extent. Hash identity is not publisher authenticity or attestation of
  an arbitrary executable's build lineage.
- Execution and memory coordinates are **story-byte offsets**, not DOS addresses
  or packed routine addresses. Original x86 is not executed.
- Breakpoints retain exact expected byte guards and stop before operand loading.
  Candidate addresses do not establish reachability. Resuming a stopped boundary
  passes that boundary once; subsequent visits can hit again.
- Step counts completed ScummVM dispatches, including nested interpreter calls.
  A completed nested call does not prove its outer call finished. Trace spans
  retain that distinction; `starting_dispatch_completed` remains unknown.
- Run/step/command use finite instruction and shared host-time budgets. The native
  guard is cooperative at instruction/input boundaries. The host transport kills
  and reaps a child that does not yield. Source-readback and normal requests are
  bounded. No uncertain operation is replayed.
- Input is accepted only for an actual current native request, with an exact
  paused revision and request ID. ASCII and the request's length are checked.
  Queue acknowledgement reports `consumed:false`; later execution is separate.
- Output separates main narrative (window 0) from other windows. Captures and
  traces are capped. Trace overflow reports an exact dropped-event count.
- Closing the owner socket exits the child. The launcher independently terminates
  and reaps it and deletes its private runtime.

Unsupported surfaces are not inherited from AGI: native SAVE/RESTORE opcodes are
explicitly refused in this first profile, not redirected into unowned dialogs.
There are no exact checkpoints, rewind, data watches, original CPU registers,
mutable memory patches, timed input, screenshot parity or asynchronous session
API. An injected non-yielding callback can only be stopped by host teardown.

## Verification commands and gate separation

```sh
PYTHONPATH=src python -m pytest -q tests/test_scummvm_zcode.py
```

Ordinary tests compile `tests/fixtures/zcode_agent_driver.cpp` with strict warnings,
no C++ exceptions/RTTI, and UBSan. The driver supplies **authored scripted hook
calls**, not an interpreter. It tests actual C++ parsing, stop ownership, native
sockets, source readback, breakpoints, nested counts, input revisions, text,
deadlines, EOF and process cleanup. Hook-transform tests use labeled synthetic
anchor fixtures, not a full upstream compile.

The separate real-engine test is skipped unless all three inputs are explicit:

```sh
FDISBULL_SCUMMVM_ZCODE_EXE=/private/scummvm-zcode-build/scummvm \
FDISBULL_ZORK_STORY=/private/ZORK1.DAT \
FDISBULL_SCUMMVM_ENGINE_DATA=/private/scummvm-2.8.1/dists/engine-data \
PYTHONPATH=src python -m pytest -q tests/test_scummvm_zcode.py \
  -k real_scummvm_owned_zork_acceptance
```

Passing that smoke would qualify only its bounded startup, stepping, input and
shutdown case. A subsequent independent comparison with the internal word16/
intent runtime and original DOS remains necessary. Equal seeds are not assumed
to produce equal random sequences across providers. No historical !73 or !92
receipt transfers automatically to this native implementation.

## Primary source references

- [Pinned interpreter dispatch](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/glk/zcode/processor.cpp)
- [Pinned source loading](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/glk/zcode/mem.cpp)
- [Pinned input boundary](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/glk/zcode/glk_interface.cpp)
- [Reused AGI/Gob transport, !73](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/73)
- [Internal Z-machine probe/comparison, !92](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/92)
