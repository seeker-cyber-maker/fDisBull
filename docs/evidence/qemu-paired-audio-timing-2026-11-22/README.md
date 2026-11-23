# Paired DOS audio clocks and recording windows

Three fresh macOS arm64 pairs passed on source `3005867eaae862a33cea084c86fa9b80517e4390`. The exact QEMU binary was `91321d463ad4b06e183f46cc1ab356dc4b2a23dd831531761b7f39845a835fe9`. The DOSBox-X reference was `df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e`. Each guest used the same authored COM, reached both guest report boundaries, exited with code 42 and had its emulator process reaped with code 0.

| Authored case | Shared guest observation | DOSBox-X PCM at 48 kHz | QEMU PCM at 32 kHz |
| --- | --- | ---: | ---: |
| OPL | 440 Hz, six BIOS ticks of key-on and two tail ticks | 19,824 frames / 413.000 ms | 14,350 frames / 448.438 ms |
| Asymmetric SB16, QEMU default U8 mono capture | One IRQ7, 4,096 bytes transferred, one BIOS tick through IRQ and two tail ticks | 6,614 frames / 137.792 ms | 2,048 frames / 64.000 ms |
| Asymmetric SB16, explicit S16 stereo output | Same DMA, IRQ and BIOS tick results, 500 Hz left and 800 Hz right | 6,758 frames / 140.792 ms | 2,048 frames / 64.000 ms |

The SB16 fixture independently programs 2,048 stereo frames at 32 kHz, or 64 ms of source. Both engines restore the original IRQ vector and mask and report the same final DMA address and residue. The QEMU stereo case retained all 2,048 frames with zero drops. Its entire observation window spans 159.534 ms of QEMU virtual time, including the guest tail, and its five audio callbacks are timestamped over 40.000 ms. A callback timestamp identifies when a chunk was delivered. It does not timestamp each sample or identify its hardware onset.

## Why the Doom WAVs differ in length

DOSBox-X configures its mixer at 48 kHz by default and writes its mixer stream via the native `DX-CAPTURE /A /-D` command. QEMU's [`sb16-opl` observer](../../../src/fdisbull/qemu_audio.py) requests 32 kHz and records output delivered by the QEMU mixer callback. Intervals where the callback delivers no frames have no synthetic silence in the WAV. Both settings describe the recorder, independent of Doom's guest DSP rate. The authored SB16 comparison demonstrates different PCM lengths even when both sides report the same guest tick, IRQ and DMA endpoints.

For the separately retained E1M5 original Doom demo prefix, DOSBox-X wrote 2,976,192 frames, or 62.004 s of PCM. The first nonzero frame followed 7.686979 s of exact leading zeros. QEMU wrote 788,225 frames, or 24.632031 s of PCM. On QEMU the first callback arrived 31.538899 virtual seconds after the capture start, and the entry-to-exit interval was 56.156559 virtual seconds. A zero-drop count establishes capture capacity and delivery, while the game and audio devices can still have inactive intervals.

Removing exact leading zeros would leave about 54.317 s of DOSBox-X PCM and 24.420 s of QEMU PCM. Startup silence alone cannot explain the difference. The workload lacked shared live Doom tic anchors and the DOSBox-X receipt did not record the terminal guest tick, so these WAV lengths do not determine a game speed ratio, output loss or matched gameplay duration. A timing comparison needs shared live game anchors and explicitly timed device or capture intervals.

The explicit S16 result concerns the output PCM container. The paired tone fixture's guest SB16 data is U8.

## Matched live Doom tics (2026-11-23)

Both native engines stopped at the same original Ultimate Doom code site,
LE object 1 offset `0x33120`, immediately before the relocated `INC` of
`leveltime`. The counter is in object 3 at offset `0x2d354`. Each engine
independently matched the loaded code and derived data placement from the
original executable and live relocation evidence. Initial single-instruction
witnesses observed DOSBox-X increment 0 to 1 and QEMU increment 38 to 39.
QEMU explicitly reacquired protected source at its endpoint. The DOSBox-X
witness used the native CPU/GDT diagnostic, stopped segmented/physical reads
and the owned breakpoint. The legacy native protocol leaves the hidden CS
cache unavailable for independent comparison.

The interval below starts immediately before the increment at `leveltime=64`
and ends before the increment at `leveltime=128`. Each controlled run used the
same exact original EXE, WAD, configuration and 512-command E1M5 demo prefix.
For sparse runs the controller allowed 1.5 seconds of engine-reported guest
time after the first landmark before arming the next breakpoint. It verified
the relocated instruction and data address again at the exact final landmark.

| Native producer and procedure | Reported time from 64 to 128 | Audio recording frontier advanced |
| --- | ---: | ---: |
| DOSBox-X, fast-forward, each tic stopped | 5.421 s of PIC ticks | WAV file grew 1,048,576 bytes |
| DOSBox-X, fast-forward, sparse stops | 5.368 s of PIC ticks | WAV file grew 1,048,576 bytes |
| DOSBox-X, normal speed, sparse stops | 1.815 s of PIC ticks | WAV file grew 393,216 bytes |
| Earlier QEMU OPL producer, each tic stopped | 2.035180 s of virtual time | 55,890 mono PCM frames |
| Earlier QEMU OPL producer, sparse stops | 2.036338 s of virtual time | 62,690 mono PCM frames |
| Current QEMU producer, sparse stops | 1.902188 s of virtual time | 58,474 signed stereo PCM frames |

The normal-speed DOSBox-X result is the relevant reference for ordinary
timing. Fast-forward substantially changed the measured interval even in
the sparse run. The current QEMU stereo capture reported zero dropped
frames at both endpoints. Its retained samples span 1.827313 seconds at
32 kHz. DOSBox-X file growth is an observation of flushed bytes from the
48 kHz mixer writer. It leaves buffered samples at the exact endpoints
unknown. PIC ticks and QEMU virtual time are separate counters. The
remaining approximately 87 ms difference and sample-window alignment need
direct device timing measurements before accepting waveform or gameplay
speed parity.

The native producers were installed DOSBox-X `df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e`,
the earlier QEMU OPL producer `01773e0f8e4976db24449442e9e79f6f0042f9a1c21529a13b35dc8856991924`,
and the current QEMU producer `7e6640b8015a95f42233b9193785570a87882804729a9b3aebadf0a001343648`.
Every reported run reaped its emulator and verified the input hashes again.

| Private timing receipt | SHA-256 |
| --- | --- |
| DOSBox-X fast-forward, dense | `72d8e8205aa7d9248906da3a8a77726bd869fdb22ccaf136eb12981a2f9e744f` |
| DOSBox-X fast-forward, sparse | `a62d14f5697d979ab06b999fbd7723b49eb6a618d507294644cbeee6b380eeb5` |
| DOSBox-X normal speed | `326994b61fa3f95eae4daea030738ebee1d90e4bc16885b4e140d1f7f936b105` |
| Earlier QEMU, dense | `bc5b1eda73a479c7f22335518af2e0093d46189e82c8f7d7abe4df6b72542e0a` |
| Earlier QEMU, sparse | `0183d6e8df3f78868897858f7fab7ae292a1588dd9bd601e0be63cc15a4f98c6` |
| Current QEMU, stereo | `85bdc90b7334522a6e47403415666f25b8de22d1d72d4ba08dd71890a8c4d732` |

## Native protected Doom checkpoint at a live tic (2026-11-23)

A fresh QEMU guest running the same original E1M5 prefix and the current
stereo producer saved a public protected LE source checkpoint at the
`leveltime=64` landmark. The source and native machine artifacts charged
30,982,293 bytes. Both a hot restore and a restore from a separate Python
process established a fresh protected source binding, restored the pre-step
PC and live counter, and restored the audio frontier of 220,095 stereo
frames with zero reported drops. Each independent native step reached
`leveltime=65` at the same next PC and virtual time. The exact observed
audio frontier stayed equal after that instruction.

This is a source-bound native checkpoint on a live protected demo route.
Game-authored save files, a paired DOSBox-X mid-demo checkpoint,
uninterrupted playback timing and waveform equality remain open.

| Private replay receipt | SHA-256 |
| --- | --- |
| Live capture and hot replay | `9f2b753e7128d25796ceece34a11e6e83923a890d389f5ee03789ed858773fe8` |
| Separate Python process replay | `85c82e3d97d8ee8da801949d1db768dda3dff7c3a3a380d3d415aefb973254bf` |

## Signed-S16 guest checkpoint recovery

The separate [native recovery matrix](../../../tests/test_qemu_sb16_s16_recovery_native.py) passed all 32 cases on macOS arm64 in a single finite local run. The exact harness was `9387667c6ea23dbd47baec971d05e7c87a5aca81`. It used the QEMU producer above and the retained pre-S16 transfer-count producer `d41bece601da8127ed049b76c2e09a43fd04aab85299632d48942e1dcc551268` as the legacy control.

- Eighteen cases reproduced the selected 600 ms future after hot restore and restore in a separate Python process. The oracle compares the complete exposed CPU register dictionary, authored report and 16 KiB DMA arena, SB16 device fields, retained PCM bytes and callback chunks, virtual time and instruction count. The cases include mono and stereo, single-cycle and auto-init, FIFO off and on, 5–45 kHz rate boundaries, pending IRQs, masked DMA requests, and absent or inactive voices.
- Five cases refused unsupported encodings or DMA geometry. The legacy producer refused four guest-S16 save attempts. Four corrupt-core imports failed at their native validation points, and one cross-producer checkpoint refused before destination construction.
- All 91 admitted QEMU owners exited with code 0 and had complete logs. All 18 cold Python groups were confirmed gone. The host fixture and process-supervision gate passed 149 cases. On Darwin, the supervisor accepts an `EPERM` final signal only when the still-unreaped leader has exited and is the sole member of the group. It verifies group disappearance after reaping.

The dedicated matrix verifies QEMU guest-S16 checkpoint and restore behavior. The paired tone and Doom results above compare bounded output observations across engines. They leave game timing and full audio parity open.

## Receipt hashes

| Artifact | SHA-256 |
| --- | --- |
| Paired native JUnit | `6a71b696833ba5405944738f3f37a07558219c630d036972fe643d6c8b9cfdfd` |
| OPL pair | `eda324161aaf1b0f0406f63646d879f2419dc8459b4552b77f4640d7a8491774` |
| SB16 default-output pair | `28e611b3482f22a0fd73d69337d0155b1f12ef5279c50ab4e93e16c698582ac3` |
| SB16 explicit stereo pair | `5f0dced10666ef0e94dce0f3443b1e6e16dd23b3bb55ea247d97d1a302229b0b` |
| Doom and DMA aggregate | `1e1fa5480b1582b5c05440c0954b546a5f504252d430de5f93e016dfb46148c9` |
| Reviewed S16 admission | `6ba71b3e3d45363f5edd1f40bdd60039e1e6fc7cfe1ac55519b019eed942d810` |
| S16 host JUnit | `f63a403088ef499f25fc00fe1dd6ef7c04e36b1a0c75b1fc2e5ed94e63c726e6` |
| S16 native JUnit | `7603bd6b21516d3b3e5e08e066694049e08131a1b6e80fbe53edcee033fe383c` |
| S16 native postflight | `7b0ba756d8cb3b684b4fc10a1937ca274c9fe3094b1aceba24400f1703bdbb37` |

The paired lane used [`tests/test_qemu_paired_tone_native.py`](../../../tests/test_qemu_paired_tone_native.py) with `-x`, the pinned native executables, FreeDOS and NASM. Raw receipts and media are private. Validation was local. DOSBox-X remains the default.
