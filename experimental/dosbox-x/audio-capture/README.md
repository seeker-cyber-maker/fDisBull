# Bounded mixer capture overlay

This optional overlay adds an agent-owned PCM observation window to the original
DOSBox-X mixer. It does not replace a game decoder, patch a guest program, enable
host audio, change stock CaptureState, or open a capture file. The established
stable and layers patches/manifests remain separate inputs.

Apply the selected existing `headless-agent.patch` to the pinned upstream commit,
verify its source manifest, then apply `../audio-capture.patch`. The companion
`../audio-capture-manifest.json` pins both exact input variants and resulting
source hashes. The same overlay replays on stable and layers; **only stable has
been compiled and tested natively on macOS ARM64**. The installed backend remains
a separate artifact and may not advertise this capability.

## RPC contract

`agent.capabilities.audio` advertises capture, encoding `s16le`, two channels,
16 bits, a 4,194,304-byte maximum, source `mixer_recording_conversion`, and the
PIC tick/mixer-frame clocks.

- `audio.capture.start`: `{session_id, max_bytes}`; target must be stopped.
  `max_bytes` is 4..4,194,304 inclusive and divisible by four. The server also
  preflights base64 plus metadata against its configured RPC response budget.
- `audio.capture.status`: `{session_id, capture_id}`; metadata only. A budget
  stop retains the captured bytes for subsequent stop/readback.
- `audio.capture.stop`: `{session_id, capture_id}`; closes the window and returns
  `data_base64` and `sha256`. Repeated stop for the same retained ID is idempotent.

Responses include the normal session ID/revision plus `capture_id`, `active`,
`complete`, `truncated`, `stop_reason`, `max_bytes`, `byte_count`, `sample_rate`,
`channels`, `bits`, `encoding`, `captured_frames`, `first_mixer_frame`,
`next_mixer_frame`, `start_guest_ticks`, `end_guest_ticks`,
`last_data_guest_ticks`, and `source`.

`complete` means the capture window is closed and its data is retained. Explicit
stop gives `complete=true`, `truncated=false`, reason `requested`. Reaching the
byte limit gives `complete=true`, `truncated=true`, reason `byte_limit`; it stops
only the observer. State-load requests, selected guest exit and session stop
close the window with explicit truncation reasons. Changed sample rate or
noncontiguous clock/frame input also fails closed. A new successful start
explicitly replaces previously retained data. Session ownership and capture IDs
reject stale reads. Start/status/stop execute on the emulation thread through the
existing deferred-request/cache machinery; they do not increment guest state
revision. Reusing a request ID must follow the existing RPC retry contract.

The rate is the actual integer mixer rate, not an ABT header field. Frames are
stereo sample pairs, so `byte_count == 4*captured_frames` and
`next_mixer_frame-first_mixer_frame == captured_frames`. PIC ticks are millisecond
observations; the mixer counter gives the exact position within that stream.
The tap uses the same clipped, post-DC-adjustment, recording-volume conversion
as stock WAV capture. It is before the host output callback/master-volume path.
At the observed 48 kHz rate, the maximum window is about 21.85 seconds. A full
window is not proof of real-time output-device playback.

## Build and verification

Use an admitted private external output directory and an existing local Git
source containing the pinned upstream commit. This recipe clones into a new
workdir, verifies both source stages, runs the pure C++ buffer tests, and builds
without installing anything:

```sh
python3 experimental/dosbox-x/audio-capture/build_backend.py \
  --source /absolute/path/to/local/DOSBox-X \
  --work /absolute/private/external/new-build
```

The result records the binary path/hash and exact commands. It establishes a
build, not native qualification. Prerequisites match the existing SDL2/debug
backend build (autotools, a C++ compiler, SDL2 and its existing dependencies).
The layers option is available for future qualification, with its current
source-only ceiling retained.

The authored native tests require the tool's Python environment and an explicit
private output directory. They create only an authored PC-speaker COM program;
no game assets or native instruction/register edits are used:

```sh
PYTHONPATH=src python3 experimental/dosbox-x/audio-capture/tests/verify_native_capture.py \
  --backend /absolute/path/to/candidate/dosbox-x \
  --work /absolute/private/external/native-checks --tag smoke
PYTHONPATH=src python3 experimental/dosbox-x/audio-capture/tests/verify_capture_windows.py \
  --backend /absolute/path/to/candidate/dosbox-x \
  --work /absolute/private/external/window-checks
```

The smoke covers budget admission, one active owner, stale IDs, retained byte-limit
completion, exact transfer hash, contiguous frames, idempotent readback and an
empty requested window. The window checks cover a full known PIT tone, capture-off
control, state-load invalidation and natural DOS termination. Paused observer
operations compare registers, selected code/stack RAM hashes, guest ticks and
state revision before/after. Cross-process BIOS absolute-time seeds can differ;
these tests do not assert arbitrary whole-emulator state parity or general timing
neutrality. Native/game compatibility, waveform/device-rate interpretation and
build/install/release status remain separately evidenced gates.
