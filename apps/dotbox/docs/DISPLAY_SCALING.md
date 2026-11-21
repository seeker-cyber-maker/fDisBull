# Display scaling without changing game coordinates

Verified 20 November 2026 with the existing Linux DOSBox-X core. The default
and maximized trials used installed DotBox `0.1.0.dev8`; the explicit 3x and 4x
trials used installed `0.1.0.dev9`. Larger presentation reuses the same game
state, physics, native framebuffer and controller.

## Finding and change

The original visible launch displayed Keen Dreams at 640 by 400. Maximizing
the window to 1364 by 1000 left the game image at 640 by 400, centered in black
margins. The larger container did not enlarge the game content.

The installed native core already contains the `normal3x` and `normal4x`
software scalers. DotBox now accepts an optional `--window-scale` argument on
`serve`, a `window_scale` backend configuration value, and the equivalent
`NativeSession(..., window=True, window_scale=4)` keyword. They request the
existing normal scaler through one native configuration argument. No movement,
physics, map, camera, decoder, saved-control or native-renderer algorithm changed.

For example, add this option to the usual launch command:

```sh
dotbox serve ... --window-scale 3
```

Use `4` when the desktop has room for the larger image. Accepted values are
integers 2 through 5; omitting the option preserves the previous native launch
arguments. An explicit scale is rejected for a headless session. This is fixed
integer scaling, not automatic fitting to every viewport. Actual display size
also depends on the original DOS mode and aspect settings.

The upstream configuration reference likewise distinguishes output scaling from
window dimensions and explains that `windowresolution` does not scale surface
output. The installed build's source and symbols were checked separately before
selecting its existing software scalers:
[DOSBox-X configuration reference](https://github.com/joncampbell123/dosbox-x/blob/master/dosbox-x.reference.conf).

## Live measurements

Each run started from an isolated, byte-identical game copy and the same
qualified first-level state. The root controller alone owned guest execution.
The guest paused for presentation measurements before the unchanged policy ran,
and after its final renderer capture. Those pauses verified unchanged guest
ticks, native state revision and hot memory and were excluded from loop timing.

| Case | Measured client size | Measured game image | Native frame | Settled world x |
| --- | --- | --- | --- | --- |
| Original default | 640 by 400 | 640 by 400 | 320 by 200 | 32800 |
| Maximized default | 1364 by 1000 | 640 by 400 | 320 by 200 | 32800 |
| Explicit 3x | 960 by 600 | 960 by 600 | 320 by 200 | 32800 |
| Explicit 4x | 1280 by 800 | 1280 by 800 | 320 by 200 | 32800 |

Client dimensions came from the attached desktop's window inventory; native
screenshots and the displayed content were inspected separately. The desktop
measured 1364 by 1024. The 3x and 4x game images filled their client rectangles.
These measurements concern the native game window in this development thread,
not the separate Context Kitty Lemmings session shown in the user's screenshot.

The controller requested a 32-game-pixel movement to the left. Every run began
at world x 33280 and settled at 32800: 30 game pixels traveled, 2 short of the
requested target, within the existing policy's admitted tolerance. The final
native PNG was byte-identical across all four runs:

```text
5d6cd50a895de8cf5750cb0e1d47106c4eaf4757200c594d6bd3d6e6bc094686
```

An independent comparison checked all 56 complete observations (the initial
state plus 13 updates per run), 104 raw memory reads, 52 stopped register
records, nine policy decisions and two keyboard edges per run. Corresponding
game states, hot-memory bytes, registers, policy choices and guest-relative
input timing were identical across all four runs. Host scheduling varied.

The same frozen loop, decoder and waypoint policy were used. All trials
completed their objective, released input, closed and reaped the emulator with
return code 0. All seven original game files remained unchanged.

## Coordinate contract

Keep three spaces separate:

| Space | Used for | Effect of presentation scaling |
| --- | --- | --- |
| Game/world coordinates | Physics, map tiles, actor positions, planning and camera state | None |
| Native guest framebuffer pixels | Screenshot inspection and saved native mouse controls | None |
| Display or streamed-desktop pixels | Human-visible image and outer pointer events | Size and position change |

Native frame capture reads the completed renderer source before host scaling,
menu bars and aspect correction. The screenshot decoder preserves its dimensions
and pixels. Native mouse input accepts `guest_frame_pixels`, then maps them into
the DOS mouse driver's coordinate range. Window size does not enter that native
mapping.

For desktop or browser pointer input, use the current rendered **game content**
rectangle, excluding title bars and letterboxing. The presentation adapter maps
the pointer back into the native grid. For example, native point (100, 50) appears
at (300, 150) relative to a 3x game image and (400, 200) relative to a 4x image;
both map back to the same native point. This conversion belongs at the display
boundary, not in a game-specific movement algorithm. A streamed video may contain
an entire desktop, so its video coordinates are not automatically game pixels.

A renderer reset can invalidate frame identity even when the coordinate system
is unchanged. The maximized run changed `mode_id` from 5 to 6 and ended one
renderer-frame counter behind the other runs while retaining the same native
image and gameplay result. Obtain a fresh frame/mode binding after reset;
do not reinterpret that token change as a new world scale.

## Verification and limits

The affected native runtime, wrapped-entry, backend and CLI suites passed
**142 tests**. Authored pipe peers verify the actual launch arguments, including
unchanged default visible/headless arguments and the sole explicit scaler pair.
The `NativeSession` and `DOSBoxRPC` constructors refuse booleans, strings,
floats, unsupported integer scales and headless scaling before source/process
access. Earlier focused checks also
covered unchanged screenshot bytes, fresh-frame mouse binding and the existing
waypoint policy.

The ordinary dev9 wheel was installed without an editable installation or
source-tree `PYTHONPATH`. Its 126 hashed wheel payloads matched the installed
bytes; all 39 Python modules matched the source; the installed offline doctor
passed. The native emulator binary was unchanged.

The short movement trials cover a qualified flat-floor route and keyboard
controller, not complete gameplay or live pointer targeting in Lemmings. The
2x, 3x and 4x presentations were observed; the accepted 5x setting was not
visually qualified. No arbitrary-resize fitting, browser device-pixel-ratio
sweep or original Dot takeover integration is claimed.

Rendering cost remains separate from coordinate correctness. The 3x and 4x
trials each advanced 371 guest milliseconds in about 382 host milliseconds.
The 4x trial recorded two missed paced deadlines and a 31.15 ms maximum cycle;
these small runs are not a sustained real-time performance guarantee.

Native PNGs, raw RPC receipts, guarded observations and trial identities are
retained privately. The desktop screenshots were inspected through CUA; its
temporary JPEG paths could not be copied into the evidence archive. The archive
therefore retains their measured geometry and observation receipts, not those
JPEG files. Commercial game files and raw memory are excluded from Git.

See the [machine-readable result receipt](evidence/display-scaling-2026-11-20.json)
and [installed launch guidance](STANDALONE.md#display-size-and-coordinates).
