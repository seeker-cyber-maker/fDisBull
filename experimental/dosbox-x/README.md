# DOSBox-X headless debugger

The experimental backend now passes real headless DOS acceptance on macOS Apple Silicon. It runs an actual DOSBox-X emulator through inherited POSIX pipes. Screenshots come from completed guest frames; click acceptance comes from the guest's INT33 counters and callbacks.

A subsequent [actual DinoPark session](DINOPARK-VERIFICATION.md) also passed: title menu to bank to Dino City to Real Estate, with a game-code breakpoint and a 512-instruction trace showing the game consuming the New Game click. The backend source and executable were unchanged for that verification.

This backend is delivered as a separate source patch alongside the fDisBull 0.9.0 integration. It is excluded from the tool packages and must be built explicitly.

The local fDisBull 0.9.0 development integration now uses this backend through its public pipe RPC: [project debugger usage](../../docs/DOSBOX_DEBUGGER.md). The current patch also adds `execution.timing`, an emulation-thread getter/setter for guest milliseconds and the existing native fast-forward control. It does not change CPU instruction semantics. Earlier acceptance receipts below are historical; the project-integration evidence is under `evidence/integration-2026-10-23/`.

## Source and recovery

Upstream: https://github.com/joncampbell123/dosbox-x

Baseline: `029bd65c5dcc7cdc7f2e14e35278620d9707d969`.

- `recovered-work.patch`: original unfinished archive checkpoint, preserved unchanged.
- `headless-agent.patch`: complete current patch against the baseline, including recovered cloud changes and local fixes. Apply this patch alone to the clean baseline.
- `source-manifest.json`: hashes for all 27 resulting source files, complete patch, tested emulator, and evidence; also records cloud recovery provenance.
- `evidence/2026-10-23/`: real guest acceptance JSON and screenshots, client/transport test log, and a separate command-line launcher result.

The later cloud files were recovered by replaying nine complete saved `fileChange` diffs from interrupted chat `01a168ae-ed38-7565-b9db-557772f800d6` and pipe-client task `01a16916-46ba-76ab-a177-a234771da0e0`. These restore the pipe client/tests, package exports, SDL header placement, launcher diagnostics, and guest acceptance runner. Old passing-test statements were independently rechecked locally.

Local corrections select native-resolution rendering, refresh RGBA pixels on every completed frame so palette changes cannot stay stale, compare CPU values separately from input mutation revisions, and make the same-FIFO test portable to Darwin. The runner verifies actual traced EAX and stepped IP/SI against the authored assembly.

## Apply and build

In a clean upstream checkout at the baseline:

```bash
git apply --check /absolute/path/to/fDisBull/experimental/dosbox-x/headless-agent.patch
git apply /absolute/path/to/fDisBull/experimental/dosbox-x/headless-agent.patch
./autogen.sh
./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
  --disable-avcodec --disable-libslirp --disable-libfluidsynth
make -j6
```

The verified build used native macOS Clang, SDL2 2.32.74, and `C_DEBUG=1`, `C_HEAVY_DEBUG=1`, `C_DOSBOX_AGENT=1`, `C_SDL2=1`. SDL2, autoconf/automake, pkg-config, normal DOSBox-X build libraries, Python with Pillow, and NASM are required. NASM 2.16.03 was built locally; its source archive hash is in the manifest. The tested executable is `src/dosbox-x`.

## Run acceptance

From the patched DOSBox-X checkout:

```bash
python -m unittest discover -s client/python/tests -v
python tests/agent_headless/verify_headless.py \
  --executable src/dosbox-x \
  --nasm /absolute/path/to/nasm \
  --output /absolute/path/to/new-evidence-directory
```

Local checkout: `/Users/tiga/Documents/ChatGPT/fDisBull/.recovery/2026-10-23/dosbox-checkout`.

Project Python: `/Users/tiga/Documents/ChatGPT/fDisBull/.venv/bin/python`.

Local NASM: `/Users/tiga/Documents/ChatGPT/fDisBull/.recovery/2026-10-23/toolchain/nasm-2.16.03/nasm`.

| Behavior | Fresh result |
| --- | --- |
| Python client and actual local pipe/socket transports | 31 tests passed |
| Startup | COM entry stopped at IP `0100h`, actual code bytes read |
| CPU trace | Two events at `0100h` and `0103h`; second snapshot EAX `1234h` |
| Breakpoint | Stops at `0106h`; EAX `1234h`, EBX `5678h` |
| Single-step | IP advances to `0109h`, SI to `0200h` |
| Memory writes | Wrong hash rejected without mutation; correct hash permits write/readback |
| Screenshots | Real PNGs at 320×200 and 640×480; expected authored color bands |
| Stopped screenshots | Repeated PNG/metadata and CPU/guest state remain unchanged |
| Mouse click | Pixel `(160,90)` maps to INT33 `(320,90)` in mode 13h; guest records one press, one release, held-button samples, and callbacks |
| Clipping | Guest subwindow clips to `(200,80)` without stretching over the screenshot |
| Validation | Stale mode and out-of-bounds coordinates rejected |
| Palette/mode changes | Red changes to magenta; mode 12h and restoration to mode 13h succeed |
| Lifecycle | Session reaches exited; launcher closes channels and reaps emulator |
| Complete patch | Clean replay reproduces all 27 source hashes |

Failed runs and logs remain under `.recovery/2026-10-23/acceptance-01` through `acceptance-03`. They exposed default double-scan dimensions, register equality incorrectly including the mutation revision, and stale palette capture. `acceptance-04` passed with the diagnostic fix; `acceptance-verified` passed on final source with stronger trace/step assertions.

## Use the launcher

Prepare a directory containing a DOS target and its files, then run from the patched checkout:

```bash
python tools/headless_agent.py \
  --executable src/dosbox-x \
  --workdir /absolute/path/to/dos-inputs \
  --target GAME.COM --run-ms 250 \
  --screenshot /absolute/path/to/frame.png
```

Import `HeadlessAgent` from `tools/headless_agent.py` for programmatic control. Its `.client` exposes the structured debugger API. `save_screenshot(client, session_id, path)` validates the PNG signature and hash before writing. RPC methods `input.mouse.move`, `input.mouse.click`, and `input.mouse.state` use the screenshot's upper-left pixel grid. Supply the returned `mode_id` when acting on a screenshot. Clicks queued while stopped are delivered when execution resumes; release timing uses guest emulated milliseconds.

The default launcher selects SDL dummy video/audio drivers, private explicit pipe configuration, readiness RPC, and native-resolution rendering (`render doublescan=false`). It reaps the process on exit. Optional `--window` mode was not covered by this headless acceptance.

## Limits and license

Acceptance covers authored DOS fixtures and the documented bounded DinoPark session on native macOS Apple Silicon. It does not establish every-game compatibility, Windows/Linux runtime behavior, PS/2/AUX, PC-98, external guest drivers, protected-mode input, or complete memory-access tracing. Absolute input is scoped to the built-in real/v8086 INT33 driver. CPU instruction tracing is distinct from tracing every memory access.

Headless emulation does not provide security sandbox isolation. Screenshot conversion refreshes a bounded RGBA buffer on every completed frame while capture is enabled; high-resolution throughput has not been benchmarked.

This is modified DOSBox-X source, separate from fDisBull. Upstream headers identify GPL-2.0-or-later. Upstream GPL v2 text is retained verbatim in `COPYING`; source notices remain intact. Upstream adoption or verification is not claimed.

## Editable native checkpoints and data watches

The current patch additionally exposes stopped `state.save`/`state.load` operations using DOSBox-X native serialization, structured `state.set_register` edits, and normal-core real-mode `r/w/rw` data-access breakpoints. Headless state calls reject mismatches without GUI confirmation, disable native flagged-file restore, and invalidate the completed-frame cache on restore. fDisBull checks native checkpoint identity and captures edited state forks in an isolated paused emulator. See [state/script API](../../docs/DEBUGGER_SCRIPTS.md) and [state verification](../../docs/VERIFICATION-STATES.md).

The original 0.9.0 patch and its 21-file replay are preserved in Git commit `a6cfea46fc255a347a397441137ae9e2d7116124`; earlier receipts refer to that exact patch/emulator. The current source manifest pins the expanded 27-file patch and new emulator.
