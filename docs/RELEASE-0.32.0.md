# 0.32.0 feature scope

This line starts from 0.31.1 and carries its released capabilities, native CI
repairs and macOS Swift source-package repair forward. It adds the reviewed
features and complete fixes below. The version in source is not a claim that
the release is already tagged, published, installed or qualified on every
platform.

The [GitLab release inventory](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases)
and eventual [v0.32.0 record](https://gitlab.com/brewster-jennings-group/fdisbull/-/releases/v0.32.0)
are the authority for the exact release commit, final qualification receipts,
asset hashes and manual download verification. These notes define scope before
that source is frozen; publication evidence can be attached to the release
without changing the tested commit.

## New capabilities

- **Captured Windows import recovery:** [CHimpREC](CHIMPREC.md) consumes
  caller-owned PE32/PE32+ mapped-module captures and loaded-export maps. It
  recovers named and ordinal imports, requires explicit decisions for ambiguous
  or junk thunks, preserves original IAT addresses, and writes new lookup
  tables, a qualified entry point and a checked PE checksum. The bounded
  [Galaxy workflow](GOG_UNPACKING.md#galaxy-upx-wrappers) covers captured
  UPX0/UPX1 wrappers. Its fixed-base analysis reconstruction is structurally
  checked; successful Windows loader execution remains a separate gate. The
  tool does not download, attach to or launch Galaxy, defeat anti-debugging, or
  provide a universal unpacker.
- **Context-aware file and media intake:** the
  [format catalog](FILE_FORMAT_REGISTRY.md) connects bounded header facts to
  actual reader capabilities, and [collection intake](TARGET_COLLECTION_INTAKE.md)
  preserves target identity and resource context. Recognizing an SMK, FLIC,
  archive, image or audio header does not imply decoding every frame, pixel,
  member or sound. [Media coverage](INTAKE_MEDIA_COVERAGE.md) records the
  remaining consumer-specific recovery tasks.
- **Restricted SMK2 cinematic framing:** `smk-frame` builds a separate media
  variant with opening/ending images, native hold frames and complete embedded
  audio. Structural checks and independent decoding precede any claim about
  original-game playback or seeking. The audited native variant preserves the
  original executable; it is not a general SMK4 writer or a qualification of
  every cinematic consumer. See the
  [agent workflow](AGENT_QUICKSTART.md#reuse-media-readers).
- **Original Windows runtime controls:** the
  [Wine/QEMU bridge](WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md) adds the Win32 PE32
  route and an experimental Win16 route alongside PE64, with actual CPU
  context, bounded stops/traces, shared input, scenes and spectator frames.
  PE32 uses observed 32-bit registers rather than a PE64 projection. Win16
  requires live selector evidence and allows checked edits of six non-stack
  registers; instruction pointer, flags, selectors, stack registers, native
  checkpoints, layers and delta rewind are outside its supported edit/state
  path. The tested Wine 11 route does not establish general NE compatibility.
- **Protected-mode DOS investigations:**
  [runtime RAM bindings and whole-machine checkpoints](DOS_PROTECTED_RUNTIME.md)
  retain observed CPU mode, address context, backend and source identity.
  Guarded live edits require expected bytes and verified readback. Protected
  input uses the normal INT33 delivery path; queue admission alone does not
  prove application consumption. Paged linear allocation identity remains
  unqualified, and source-addressed code layers/register setters retain their
  real-mode limits. Mounted host files are checked, not rolled back.
- **Exact frame transport and direct pixels:** optional indexed PNG builds an
  exact per-frame palette, falling back to RGBA PNG when needed. Optional raw
  RGBA8 with Zstandard retains encoded and decoded hashes and requires the
  native codec plus Python `screenshot` extra. `frame_rgba()` returns a checked
  Python pixel buffer without PNG conversion or artifact persistence on the
  raw path; `screenshot()` retains persistent PNG evidence. The
  [codec](VERIFICATION-DINOPARK-SCREENSHOT-CODECS-2026-11-03.md) and
  [direct-consumer](VERIFICATION-DINOPARK-DIRECT-RGBA-2026-11-03.md) studies
  qualify specific paused DinoPark scenes. Faster encoding alone did not make
  every end-to-end path faster.
- **Experimental replacement-engine debugging:** the
  [ScummVM AGI](SCUMMVM_BACKEND.md) and [Gob](SCUMMVM_GOB_BACKEND.md) backends
  expose script state, bounded execution control, input and stored frames
  through separately prepared patched engines. Evidence identifies these
  engines separately from the original DOS interpreters. AGI native save slots
  are cycle-boundary game saves, not exact machine checkpoints. Gob native
  checkpoints and script patching are unsupported. The
  [AGI scene comparison](SCUMMVM_DOS_SCENE_COMPARISON.md) and
  [Lost in Time comparison](SCUMMVM_LOSTTIME_COMPARISON.md) bound the observed
  behavior; matching a scene, text or room number is not whole-engine parity.

## Correctness and delivery fixes

Headless DOSBox-X launches suppress the quit confirmation that repeatedly
captured desktop focus, and explicitly mute native audio. Visible launch
preferences remain separate. Applying a new installed controller does not
retroactively replace Python code already loaded by a running controller;
preserving active work and Anchor Stones remains a prerequisite for restarting
such sessions.

Signed 16-bit returns retain their signed meaning across the relevant UIL
execution paths. Ordered semantic-event comparisons ignore transport or
provenance decoration without discarding the original event lists. These are
bounded correctness fixes, not a new claim of whole-program equivalence.

Wine cold-prefix setup has a five-minute limit inside a seven-minute launch
request, allowing the native agent response and transport to finish within
the outer deadline. Startup errors still propagate and close the owned VM;
launch does not retry or continue after failed prefix setup. QEMU identity
probing remains bounded at 30 seconds, and installed runtime firmware is
verified at the executable-relative lookup location.

Package validation checks the complete intended inventory across core/player
packages and tool source delivery, including native support sources, Swift
capture resources, ScummVM resources and sanitized evidence. Original games,
captured modules, saves, emulator states, private FDB payloads and runtime
binaries remain outside distribution packages. The earlier 0.31.1 source-ZIP
repair stays included.

## Intake boundaries

The feature intake consists of reviewed GitLab
[!68](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/68),
[!77](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/77),
completed portions of
[!60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60),
[!72](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/72) and
[!73](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/73),
plus the complete CI/package, quit-popup and signed-return fixes. This is
selected source integration, not a claim that every development branch has
been merged.

[!42](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/42)
and [!74](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/74)
remain unmerged. The broken alternative
[!67](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/67),
raw Library handoffs and unfinished RFC/research work are excluded. Historical
examples already shipped in 0.31.x remain available within their documented
scope; this release does not promote them into general runtime capabilities.

## Qualification and publication

The release owner must freeze the exact source commit and run full local CI,
including ordinary Linux checks and required-native stable, layers and
installed-wheel PE/DOS/boot acceptance. Missing backends, skipped required
native cases, cancelled runs and earlier source-cut receipts do not satisfy
that gate. Local macOS checks, restart/state recovery, patch isolation, stored
image exports and the applicable real-target checks provide distinct evidence.

Build and inspect all intended packages from that same source. Check inventory,
private-input exclusions, isolated installs and both bundled skills, then
record hashes. Tag and upload to GitLab only after all required checks pass;
verify uploaded metadata and downloaded asset hashes. No CI result, publication
or system-installation success is asserted by this source document. See
[CI coordination](CI_COORDINATION.md), [release records](RELEASE_STATUS.md) and
the [0.31.1 notes](RELEASE-0.31.1.md) for the preceding release boundary.
