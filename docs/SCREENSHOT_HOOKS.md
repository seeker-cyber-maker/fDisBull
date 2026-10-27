# Persistent screenshot pre/post hooks

Unreleased DOS feature after 0.18.0. These hooks are not installed in the fixed
0.18.0 system package. Python, live JSON and saved scripts share the same policy.
PE64 and raw-machine screenshot hooks are not implemented by this change.

## Configure once per project version

If an active code layer makes a sprite transparent by changing its render color
to the clear color, temporarily suspend that layer for screenshots. For example:

```python
debug.screenshot_hooks({
    "suspend_layers": [hide_sprite_layer_id],
    "pre": [{"op": "run", "guest_ms": 60, "timeout_ms": 3000,
             "fast_forward": True}],
    "post": [{"op": "registers"}],
    "timeout_ms": 5000,
})
visible = debug.screenshot("sprite-visible.png")
annotated = debug.screenshot("sprite-grid.png", grid=True, grid_step=8)
```

For the inverse behavior, start with that layer inactive and use a pre script
containing `{"op":"layer-enable","layer":"layer-id"}` followed by the bounded
repaint run/wait. The screenshot then sees the clear-color patch, and automatic
cleanup returns to the original visible baseline. No matching manual post-layer
command is required in either direction.

The preparation interval is an example, not a universal readiness delay. Use a
bounded `wait` with calibrated observations when the target needs a specific
render/ready boundary. A newly completed frame alone does not prove sprite
visibility, clickable-control readiness or a successful game action.

The policy is saved in the project database as an immutable, hash-checked
revision for the selected static version. It applies after closing/reopening
both project and emulator, and to `click-frame` and screenshot diagnostics.
Other static versions have their own policy. Read it with
`debug.screenshot_hooks()` or `project.debug_screenshot_hooks(version=...)`.
Store a new empty policy with `debug.screenshot_hooks({})` to disable it.

```json
{"op":"screenshot-hooks","configuration":{
  "suspend_layers":["layer-id"],
  "pre":[{"op":"run","guest_ms":60,"fast_forward":true}],
  "post":[{"op":"registers"}],
  "timeout_ms":5000
}}
```

That operation can appear in a normal saved `fdisbull-script-1` route. The live
JSON equivalent is `debug-screenshot-hooks` with `run` and `configuration`.
The offline Python setter is `project.debug_screenshot_hooks(configuration,
version=...)`.

## Capture lifecycle and evidence

1. Load and verify the saved policy, then record the original ordered layer stack.
2. Remove only the configured suspended layers, preserving the order of others.
3. Execute the bounded pre script. DOS runs stop on hooks; an unexpected
   breakpoint, watchpoint, hook, guest error, timeout or incomplete wait aborts
   capture. No implicit retry or run-through follows a stop.
4. Capture and verify the real framebuffer, then optionally derive the grid.
5. Execute the post script, including when preparation or capture failed.
6. Restore the original ordered layer stack in `finally`, including when the
   post script failed. An uncertain restoration closes the owned session.

Suspending render layers or changing layers in the pre script enables
`require_fresh_frame` by default. An empty native frame probe records the prior
frame ID without transferring a PNG. Each later pre-hook layer-stack change
resets that frame barrier. The capture must have a frame completed after the
last such change; an earlier repaint followed by a late layer toggle does not
qualify. Otherwise the workflow fails before storing it as a successful capture.
An explicit `require_fresh_frame: false` permits an already painted frame for
specialized uses, without asserting that layer toggling repainted it.

The immutable screenshot metadata binds the attempt ID, policy ID/hash and
original/capture layer stacks. A `screenshot-hooks` event records pre/post script
results, captured artifact, cleanup outcome and errors. A post failure can leave
a valid saved frame but returns a failed workflow with that artifact identified.
Python raises `ScreenshotHookError` with `.result`; saved scripts preserve that
result and stop before their next action.

Automatic layer restoration changes future execution. It does not repaint the
already completed capture. The next normal guest execution applies the restored
clear-color behavior. No native checkpoint, RAM rollback or guest-time rollback
is implied by the hooks.

## Script limits and bypass

Pre scripts may use `assert`, `memory`, `code`, `registers`, `status`,
`layer-stack`, `layer-enable`, bounded DOS `run`, and `wait`. Post scripts allow
the same reads/assertions/layer operations but cannot execute the guest; this
keeps `click-frame` tied to the captured frame. Each phase allows at most 100
expanded operations, with a shared script budget of 1–60,000 host milliseconds.
Cleanup is attempted even after that script budget expires.

Both phases receive `$capture.original_layers` and `$capture.suspended_layers`
bindings. Screenshot, click, keyboard, trace, checkpoint, hook-configuration and
arbitrary host-code operations are excluded to prevent recursive captures and
unexpected actions. Full configuration validation happens before persistence.

Use `debug.screenshot(..., hooks=False)` for an explicit unprepared frame. Its
metadata records the bypass. Diagnostic captures nested inside a failed hook
wait also bypass preparation and record `nested-diagnostic`, preventing recursion.
Native sparse pixel probes and stored-image exports never invoke these hooks.
Scene diagnostics may therefore differ from their earlier probe when the
preparation intentionally advances the guest; the existing snapshot/probe
identity comparison remains explicit.

See the [unreleased verification record](VERIFICATION-DOS-CAPTURE-UNRELEASED.md)
for exact source identities, native checks and independent-review corrections.

The pre/post terms here refer to preparation and cleanup around a framebuffer
capture. They do not automatically classify application events as post-state,
post-interface or post-persistence. Those broader distinctions are proposed in
[PR #5](https://github.com/seeker-cyber-maker/fDisBull/pull/5); a route must still
supply its own readiness and durable-outcome observations.
