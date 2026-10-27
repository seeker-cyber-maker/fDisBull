# Keyboard delivery is not application-level consumption

Scope: next-version feedback from DinoPark E40, followed by an authored DOS
regression test. This is not a demonstrated native-backend defect, a change to
keyboard defaults, or work on the UIL/decompiler design.

## Observed friction

The external E40 investigation used Python source `416b64d` (0.18.0) with the
previously qualified scene/keyboard-capable Linux DOSBox ELF. An 80-guest-ms
Ctrl+S worked in one original-game session but did not reach the selected
audio-toggle completion boundary in a fresh reproduction. A 500-ms chord did
reach that boundary. Input queue completion alone could not distinguish a
missed application poll from successful action handling.

That observation concerns a particular target and starting phase. It does not
establish a universal minimum hold, prove that every short input is lost, or
justify silently replacing the existing 40-ms API default with 500 ms. Longer
holds can also change the target's behavior, including repeat actions.

The E40 Ctrl+1 finding is separate: two retained original-game traces show the
actual handler receiving that chord and taking its unrecognized-key return.
The unrelated Ctrl+S calibration must not be used to invalidate or substitute
for those direct consumption observations.

## Small redistributable regression

`tests/test_keyboard.py::test_real_keyboard_delivery_and_late_modifier_poll`
uses a newly authored MZ program, not proprietary game instructions or assets.
It waits four emulated BIOS clock ticks before sampling the BIOS Control flag
once through INT 16h/AH=02. It stores the observed bit and a completion byte.
The delay is based on guest time, not host sleep or a calibrated loop count.

Two parametrized cases start at the same instruction boundary:

| Controller request | State at the delayed application poll |
| --- | --- |
| Control held for 80 ms | Queue drained; sampled Control bit is zero |
| Control held for 500 ms | Control still held; sampled bit is four |

Both requests are accepted and both queues eventually drain. Neither test
patches target memory or skips through a debugger stop. The test deletes its
completion breakpoint explicitly before allowing the long press to release.
The completion byte proves the application executed its poll even in the
short-press case; an all-zero buffer alone would be insufficient.

This demonstrates a mechanism compatible with the friction report. It does
not prove the exact cause of the earlier game's timing variation. The fixture
samples a held modifier, not buffered ASCII, a complete chord-dispatch engine,
or every keyboard path supported by DOS programs.

## Route-authoring guidance

1. Establish a calibrated scene, focus and readiness condition before input.
2. Use an explicit, bounded hold for the particular target route when necessary.
3. Verify a target-level result: its dispatch branch, changed field, scene
   transition, text value or persistent output, as appropriate to the claim.
4. Preserve separate delivery and outcome observations. Empty queue means no
   adapter-owned input remains; it does not certify application consumption.
5. On timeout or a debugger stop, inspect effects before deciding whether to
   resume, change the experiment, or retry. Do not automatically resend a
   purchase, submission, toggle or other state-changing action.
6. A longer hold is a new declared trial, not a silent repair to the first trial.
   Record guest-time budgets and prevent accidental duplicate actions.

Existing scene actions and bounded waits can supply the outcome check. No new
API is required to use this method. If a convenience operation is added later,
it should retain distinct queued/delivered/outcome-observed states, explicit
budgets, stop preservation and opt-in retry policy; it must not claim a generic
application-consumption signal that the backend does not have.

## Local verification

Linux x86-64, CPython 3.13.5, installed 0.18.0 wheel, no source-path injection:

```sh
FDISBULL_DOSBOX=/path/to/compatible/dosbox-x-offline \
PYTHONDONTWRITEBYTECODE=1 python -m pytest -o pythonpath= -q \
  --require-native tests/test_keyboard.py
```

Result: **16 passed, no failures or skips**, including both new polling cases.
Native ELF SHA-256:
`c04b1c189530af93cf054505ee92f2336c83b86e819bae8d8370350d23259fc6`.
The environment reuses genuine private libraries from the supplied 0.15 offline
kit; this is a local composite-runtime result, not sealed-delivery acceptance.
No new Mac, stable-profile, QEMU or hosted-CI result is claimed here. Existing
native workflows select `tests/test_keyboard.py`, so the added cases remain in
that required native test surface.

Only tests and this note change. No production keyboard, scene, decompiler or
UIL implementation is modified. See [the keyboard API](GUEST_KEYBOARD.md) for
supported keys, queue semantics and existing duration bounds.
