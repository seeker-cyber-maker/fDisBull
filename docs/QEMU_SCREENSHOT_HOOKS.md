# Stopped-surface screenshot hooks

Native `qemu-dos` sessions can prepare a **stopped QEMU display surface** using
the shared version-bound screenshot-hook policy. Each policy must explicitly
set `require_fresh_frame: false`. The adapter accepts `assert`, `memory`, `code`,
`registers`, `status`, `layer-stack`, and `layer-enable` in the pre/post phases.
It refuses `run`, `wait`, input, frame advancement, and a freshness requirement
before effects. This does not qualify completed guest frames or arbitrary
DOSBox screenshot-preparation workflows.

```python
debug.screenshot_hooks({
    "require_fresh_frame": False,
    "suspend_layers": [layer_id],
    "pre": [
        {"op": "memory", "address": runtime_address, "length": 2, "as": "value"},
        {"op": "assert", "value": "$value.hex", "equals": "3412"},
    ],
    "post": [{"op": "registers"}],
    "timeout_ms": 10000,
})
image = debug.screenshot("stopped-surface.png")
```

The persisted policy uses the common DOS grammar. QEMU validates it again
against its native method signatures and semantics. Memory addresses are
literal machine addresses with the native default physical address space;
legacy `cs` memory parameters are refused. Primitive parameters and all layer
destinations must be literal; assertions can reference earlier phase results.
The plan is limited to 256 referenced layer patches and 64 KiB of total layer
bytes and 256 distinct possible cleanup stacks, in addition to the existing
64-layer stack and 100-step phase limits.

Capture validates policies written directly through `Project` as well as
policies written by the native session. Whole-script admission follows known
literal `screenshot-hooks` setters in order, so a later screenshot uses the
prospective policy. Runtime admission rechecks the actual stored policy.

The adapter holds one unchanged machine owner/lock and one inherited host
deadline through admission, pre, capture, post, and restoration. It pins the
project/run, immutable version, process/checkpoint epochs, task binding, and
the exact original layer order and definitions. Every layer control uses the
existing native expected-byte and receipt guards; existing source, history,
selected CPU undo, and voluntary fair-play policy retain their usual meaning.
Post destinations are checked for every possible failed pre-prefix before the
first transition. A changed owner, layer hash, deadline, or uncertain restore
cannot trigger a replay or a cleanup continue. Unresolved modified controls
quarantine/close the owned machine. A refused preflight preserves entry input
ownership. Failed reports preserve the executed prefix, first error, any
published capture, and separate post/restore/close errors.

The saved surface adds only a nested `metadata.screenshot_hooks` object. Its
original capture ID, CPU and clock bracket remain authoritative, and both
`completed_guest_frame` and `guest_frame_id` remain `null`. Layer suspension
does not imply the guest has redrawn VRAM. Grid output derives from the saved
surface and carries that same bounded provenance. `capture_surface()` remains
a direct passive observation; `screenshot(hooks=False)` explicitly bypasses
the configured workflow.

## Verification

`tests/test_qemu_screenshot_hooks.py` exercises real project, policy, script,
and artifact persistence over an explicit stopped boundary peer, including
preflight, prospective setters, failures, deadlines, replacement owners,
immutable definitions, caller input preservation, and provenance isolation.
`tests/test_qemu_screenshot_hooks_native.py` is an optional authored COM
witness using the explicit `FDISBULL_QEMU_CLOCK` runtime lane. It checks actual
native layer suspension/restoration, unchanged CPU/virtual time, no GDB
execution during hooks, first assertion stop, and preserved pending input.
Its collection without a selected runtime is not native qualification.
