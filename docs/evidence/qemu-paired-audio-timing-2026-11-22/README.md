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
