# Genesis Miniplanets performance

The final cartridge is SHA-256
`09d3c5b5e8e908c296072d1ef2850dee08228b07f77342b0cfc711afe6a8c534`.
It passed the unchanged **4,822 original-backed controlled cases**, including
all 79 game-state fields, return values, hardware-counter consumption and sound
event observations. Source inputs and complete original contracts were checked
again before and after the run.

The procedural Miniplanets build uses a native 68000 renderer for an adapted globe display. Terrain projection and frame addresses are reused, staging buffers are cleared in aligned units, and presentation shares palette work across each tile pair. Generated C uses `-O2`, and an authored 68000 helper copies the larger diagnostic fields using separate source and destination registers. The complete 79-field diagnostic publication remains enabled.

On the pinned Genesis Plus GX core, with the same 1,200 host-frame input schedule and frames 260–1199 measured, the baseline completed 470 presentation batches and 469 logical updates over 939 sampled intervals. The new cartridge completed 940 batches and 939 updates. At the core's reported 59.9227 frames per second, these are 29.96 and 59.92 completed batches per second respectively. All observed complete terrain, HUD and sprite batches matched the staging captured at their first data write; no diagnostic fault was observed. The 600-frame prefix had 340 of 340 complete batches in its measured window. These are bounded emulator results, not a claim of 60 fps in all gameplay.

The following later-stage runs selected a stage in GameIL and skipped its intro. The native loop was paused at frame 220; all 79 fields were initialized using the build's own manifest and the publication ring and epoch were cleared at frame 240. The paused state was read back before release at frame 260. Original world and actor data were loaded through the typed game procedures. The assistance did not reinitialize the audio hardware to the selected stage's music state. The runs used 600 host frames, with frames 280–599 measured; the moving scenario held Right during frames 320–519. Both builds had the same host input schedule, but their game states progressed at their own update cadences.

| Stage index | Original actors | Baseline neutral / moving | New neutral / moving |
| --- | ---: | ---: | ---: |
| 40 | 10 | 29.96 / 29.96 | 59.92 / 59.74 |
| 43 | 11 | 29.96 / 29.96 | 59.92 / 59.74 |
| 44 | 28 | 29.96 / 29.96 | 59.74 / 59.55 |

A separate synthetic test inserted 48 visible type-1 actors. Both cartridges completed 150 batches in 300 host frames, or 29.96 per second, with no observed VRAM differences. It is a constructed load test, not an original stage. All real-stage and synthetic batches counted above matched staged terrain, HUD and sprites at the sampled frame boundary.

An earlier candidate's generated `-O2` copy loop failed the 79-field ordinary-play oracle: at epoch 102, a publication contained a shifted `next_life` while the live native field held the expected value. The final build emits explicit stores for small fields and uses the separate-register helper for larger fields. A native diagnostic checked all 1,044 combinations of lengths 0–260 and source/destination parity, including unchanged source bytes and destination canaries. The helper's contract is a non-overlapping copy. In a fresh 1,800-frame ordinary-input run, 1,749 completed native publications matched all 79 GameIL fields and all 1,749 independently mapped controller inputs. The controlled procedure checks are a separate qualification.

These display writes start at emulated scanline 226 and finish at scanlines 14–16 after rollover in the ordinary new-build run; the synthetic stress test finished at scanline 38. The HUD begins at screen Y=64, the globe at Y=96, and the minimum staged sprite Y observed in the assisted new-build cases was 90. Those coordinates do not prove when the VDP fetches tile or sprite data, when its FIFO completes, or whether a physical console displays tearing. The observer's control and forwarded-write runs matched RAM, audio, trace and final image; serialized state differed by 110 bytes, while independent controls in an earlier run also differed, so full observer neutrality remains unknown. This display is adapted and does not establish original Genesis pixel or waveform parity.

The machine-readable, sanitized [performance receipt](evidence/miniplanets-full-game-2026-10-31/genesis-performance.json) records source, cartridge, core and checker hashes, counts, protocols and limits. Reproduction uses `scripts/check_genesis_performance.py` with a privately built cartridge, its manifest and symbols, a pinned compatible core, and a private input schedule. `scripts/check_genesis_stage_performance.py` additionally takes the privately supplied source ROM, GameIL program and both build directories; it writes the assisted state patches and measurements only to a new private output directory. `scripts/check_genesis_copy.py` builds the separate native copy diagnostic. None of these checkers distributes original ROM or asset bytes.

A separate `scripts/check_genesis_seeded_states.py` run used the same atomic
pause/seed/release procedure for the three original stages and both input
scenarios. Across six 600-frame runs, **2,035 completed full-state snapshots**
and their independent controller mappings matched the UIL reference, including
**92 observed hardware-counter words** replayed with matching consumption.
These checks reuse the existing publication oracle; its ordinary boot mode
retains the same defaults. The stage selection and intro skip are assisted,
while subsequent inputs and rule execution are observed normally.

The NES target's sources and output bytes are unchanged. The first Genesis
cartridge and all superseded experiments remain preserved separately. In
particular, the all-`-O2` publication-loop candidate failed its ordinary-state
gate and is excluded from the reported qualified result.
