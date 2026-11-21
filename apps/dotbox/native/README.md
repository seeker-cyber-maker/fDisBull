# DOSBox-X cooperative-input overlay

`input-control.patch` adds an opt-in input owner to DotBox's pinned DOSBox-X
agent. The default remains an agent-owned spectator window. Standard
DOSBox-X host keyboard/mouse processing is enabled only after an explicit
transfer to `host`.

The exact upstream commit, prepared fDisBull stable-patch identity, touched base
file hashes, overlay hash and expected result hashes are in `manifest.json`.
This overlay targets `experimental/dosbox-x`, not the separate layers profile.

The complete base patch, source manifest and license text are included under
`dosbox-x/`. Prepare both native patches without an fDisBull checkout:

```sh
python scripts/prepare_native.py /path/to/new/dosbox-x
python scripts/prepare_native.py /path/to/new/dosbox-x --check
```

See [standalone source and build instructions](../docs/STANDALONE_NATIVE.md)
for offline preparation, build prerequisites and qualification boundaries.
The lower-level `apply_overlay.py` remains available for an independently
prepared base: it verifies the seven touched base files, refuses incompatible
source or conflicting new files, and checks and verifies the ownership patch.

## Protocol

Capabilities include:

```json
{"input":{"cooperative_control":"dotbox-input-control-1","restore_control":"dotbox-restore-control-1"}}
```

`input.control` is session-scoped. Query with the normal `session_id` and no
other parameters; the response includes the normal session fields plus `owner`
(`agent` or `host`) and integer `generation`.

Transfer with:

```json
{"session_id":"SESSION","owner":"host","expected_generation":0}
```

A successful transfer returns the new owner, incremented generation and
`input_reset:true`; it increments the native state revision as well. Transfers
are accepted while the target is running or stopped, on the emulation thread.
The service may pause first and explicitly resume afterward. Host ownership
requires a visible agent window. The same-owner transfer deliberately performs
cleanup and increments the generation too. Query has no input side effects.

Every keyboard/mouse mutation rejects host ownership. While agent-owned,
mutations accept an optional integer `control_generation`; a mismatch rejects
the operation on the emulation thread before injection. The DotBox broker must
always supply this field. Legacy agent clients that omit it remain supported,
but do not acquire stale-generation protection.

At transfer, pending SDL keyboard/text/mouse events and relative mouse deltas
are drained while window-management events remain queued. Existing agent reset
helpers cancel delayed events and release RPC-owned input. Mapper focus cleanup
releases host-held keys; remaining pressed buttons in the supported built-in
DOS mouse driver are released. Existing debugger UI and stopped-IRQ behavior
is unchanged. This is not new support for arbitrary external guest mouse drivers.

Ownership starts at `agent`, generation zero for each new native target session.
Desktop takeover telemetry is not inferred or implemented by this native patch;
the broker must obtain that from a supported harness integration or use an
explicitly identified handoff source.

### Restore admission

The `dotbox-restore-control-1` capability adds an ownership-generation fence to
the existing raw `state.load` RPC. It is not a memory-only checkpoint capability
or a qualified interactive rewind API. DotBox's Python service does not expose
that raw operation.

`state.load` now requires an integer `expected_generation`, in addition to the
existing `session_id`, absolute `path` and optional explicit `frame_keys`.
Missing or malformed generations are refused. On the emulation thread, a stale
generation is refused before cleanup or loading. An admitted restore keeps the
current owner and consumes one generation before cleanup and serializer effects.
Successful responses add `owner`, `generation` and `input_reset:true`. Capture
through `state.save` does not consume an ownership generation.

Old generation-tagged input is refused even if the admitted restore later
fails. A caller must not retry or resume after an unknown/partial load merely
because `input.control` still answers. Failed admission and failed admitted
restoration are different outcomes; the future recovery controller must handle
the latter as incomplete and close the owned session when it cannot verify it.
Do not fetch a new generation automatically to replay a rejected old request.

The source change leaves the serializer and explicit saved-key policy intact.
Pre-load cleanup does not prove that deserialized keyboard/device state is
neutral. The serializer's existing historical disk backup/restore exclusion
also does not establish all handle, pending-I/O and device behavior. Qualify
those boundaries and fresh post-restore observations before exposing player
recovery. See [memory-only recovery](../docs/RECOVERY_AND_SAVES.md).

## Bounded execution

The `execution.bounded_frame_step` capability advertises
`schema: "dotbox-bounded-frame-step-1"`, `max_frames: 10000` and
`max_guest_ms: 30000`. A caller must check this capability before sending the
new fields to `frame.step`; an older backend may silently ignore unknown fields.

```json
{"session_id":"SESSION","max_frames":120,"max_guest_ms":2000}
```

Both limits are required together and must be positive integers within the
advertised maxima. The operation starts only from a stopped target and runs on
the emulation thread until a breakpoint or other debugger stop, the requested
number of completed renderer frames, or the guest PIC-tick allowance is reached.
The frame/guest-limit checks stop at a safe fetch or after an event callback has
unwound. They do not stop in the middle of a guest instruction or renderer
callback. The bounded path checks a pending execution or data-access breakpoint
before attributing a coincident limit to the budget, so resuming cannot skip an
unreported breakpoint. The legacy call with neither limit still steps one frame.

A successful response retains the normal `session_id`, `state_revision`,
`stop_reason`, stopped register snapshot and frame fields. It adds
`boundary: "bounded_execution_then_safe_fetch"`, `frame_available`, and:

```json
{"bounded":{"max_frames":120,"max_guest_ms":2000,"frames_completed":1,
 "guest_tick_bits":64,"guest_ticks_before":100,"guest_ticks_after":125,
 "guest_elapsed_ms":25,"stop_cause":"breakpoint"}}
```

`stop_cause` is `frame_limit`, `guest_time_limit`, `breakpoint` or `other`.
`completed` is true only for the requested frame count; a breakpoint or guest
limit is a valid stopped return with `completed: false`. A guest limit can occur
before any new frame. `frame_available` reports whether a retained screenshot
exists, not whether the operation produced a new frame. Use `frames_completed`
and frame identity to establish freshness. Tick subtraction uses the native
unsigned clock width, reported as `guest_tick_bits`; guest milliseconds are
execution evidence, not elapsed host time or game-calendar time.

These are native guest/frame bounds, not a host wall-clock deadline or a
production action transaction. A lost response, transport timeout or server
`OPERATION_TIMEOUT` does not certify a stopped guest and never authorizes input
replay or automatic resume. The caller must retain uncertainty and use its
existing recovery/termination policy. No ownership transfer, game-state meaning,
complete rewind qualification or platform takeover is implied by this capability.
The raw protocol supports older clients; a controller still owns stop attribution,
input neutrality, binding checks and final readiness admission.

`tests/test_native_bounded_wait.py` runs authored DOS programs against an explicit
`DOTBOX_DOSBOX_EXECUTABLE`. It checks the legacy and multi-frame paths, zero-frame
guest expiry, foreign-stop attribution, exact breakpoint/guest-limit collision, a pending execution breakpoint at a
halted CPU frame boundary, and invalid-parameter admission. Pending data-access
collision follows the reviewed source path but has no separate fixture here. Its checkpoint fixture contains only authored
program bytes. Missing executable configuration skips these native tests; a
qualification receipt must therefore require their actual execution with no skips.

## Build and checks

Use the existing DOSBox-X build prerequisites and configure path:

```sh
./autogen.sh
./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
  --enable-agent-zstd --disable-avcodec --disable-libslirp --disable-libfluidsynth
make -j2
```

The repository tests compile the shared ownership policy, verify all DotBox-owned
recipe inputs and exercise immutable source export and both patch stages with
authored fixtures. Pinned overlay application can also be checked when
`DOTBOX_DOSBOX_BASE_SOURCE` points to prepared base files. Neither source tests
nor a successful build establish human takeover
on Dot's actual cloud computer. Native protocol tests and visible keyboard/mouse
acceptance are separate checks.

The native overlay is modified DOSBox-X code under GPL-2.0-or-later. Preserve
the upstream notices and corresponding source when distributing its binary.
No emulator binary or original game data is included here.
