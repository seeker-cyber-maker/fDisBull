# Spectator window: Linux cloud verification

This unreleased source candidate was tested on the cloud Linux x86-64 X11
desktop on 2026-10-27, using a synthetic MZ program only. It is not a macOS
or other-platform qualification.

- Pinned DOSBox-X source: `029bd65c5dcc7cdc7f2e14e35278620d9707d969`.
  All 7,829 downloaded archive blobs matched the upstream Git tree. The
  complete layers patch applied and all 29 resulting source-manifest entries
  matched.
- The layers backend was built with SDL2, heavy debug and agent support, using
  official Debian dependencies extracted into a user-local prefix. Binary
  SHA-256: `482b2a1ecbfcb64e28852ea55b9fe47c4301e34185a83561e7c5fe31bdc8a0a8`.
  No system-wide dependencies or security/display settings were changed.
- The configured native headless suite passed **372 tests, zero skips** with
  that binary, including the native ZIP test. The ordinary Python suite passed
  1,144 tests and skipped 92 before the native build.
- A real 320×200 mode-13h synthetic frame appeared in a native DOSBox-X window.
  With the guest running, one host `a` key and one mouse click left the guest
  BIOS-key and mouse-change counters at zero. Agent RPC keyboard and mouse
  input then changed the counters from 0 to 1 and 0 to 2 respectively.
- Two paused frame captures a second apart matched; the synthetic input counter
  bytes remained unchanged, and the original synthetic executable hash was
  unchanged. These checks do not prove general stopped IRQ or register stability.
  The session closed, the window disappeared, and no DOSBox-X process remained.
- With an invalid X display, SDL failed to initialize X11; the target did not
  start and its emulator was reaped. The Python error reported a closed RPC
  channel rather than a detailed display diagnostic. This test did not exercise
  SDL's automatic offscreen fallback with this particular SDL build; the
  selected-driver/window guard also has isolated SDL-stub tests.

The earlier SDL-stub tests and fake transports are not GUI acceptance. No
production game or proprietary game data is part of the test source or patch.
The stable (non-layers) source patch was applied and hash-checked but was not
built or GUI-tested in this run.
