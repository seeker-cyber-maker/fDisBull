# Doom E1M1 cold restore, saves and timing evidence

Host receipt date: **2026-11-25 UTC**. The client-facing date in America/New_York is **2026-11-24**. This record summarizes three opt-in, bounded native gates using private original Doom inputs. No commercial media, saves, emulator states, captures or byte-containing databases are included.

## Matched-tic fresh-process QEMU checkpoint

The fresh-process checkpoint gate passed 1 test with no failures, errors or skips. It restored the full workspace snapshot into a child QEMU process, replayed the same Ctrl input in origin and child, and compared them at Doom's same `leveltime` pre-increment landmark, tic 352. At that point the source site and instruction bytes, exposed CPU/address fields, bounded 64-byte stack slice, normalized frame and decoded ammo matched. The previous 700 ms clock-stop comparison had CPU-frontier differences while frame and ammo matched; this later landmark result does not establish all-RAM equality, general deterministic replay or broad emulator parity.

Private result: `/Volumes/GitHub/GitHub/fDisBull-private/qemu-doom-e1m1-cold-20261125/matched-landmark-result.json`
SHA-256: `bd74f99ea0b7631f929fab5785eb36652169b02ce756ad90a7a13fb79712b55c`

JUnit: same private directory, `matched-landmark-junit.xml`
SHA-256: `f79b497e732fec13a09dcd468250b282df719d7568e1ba5a6c8530473361da86`

## Cross-engine game-save interchange

Each engine loaded the other's E1M1 save. In both directions the target restored ammo from 49 to 50. Saves were 24,702 bytes each; their SHA-256 identities are recorded below without publishing their contents. Four emulator owners exited with status 0. After one Enter, a bounded 2,000 guest-ms settle provided a stable post-load frame and status-bar crop for the WAD-based ammo decoder.

Private receipt: `/Volumes/GitHub/GitHub/fDisBull-private/qemu-doom-save-interchange-20261125/cross-engine-save-progress.json`
SHA-256: `4dc84412a95b1dbe8b02c4c9975ed8b6f69b3bc169cb52518d733ceb4e9cb8b8`

The receipt records the DOSBox-X-produced save hash `d9b131be1983109f85e6c81999377cb75df7916f579f5c4b8269bca5132a08f3` and the QEMU-produced save hash `22f864d4b4200c6f137af726f9263faa3976480bc2e21a09ad7200b5a6f87e0b`. The observed post-load frame changes were 20,472 pixels on QEMU and 20,546 on DOSBox-X. These checks cover the tested save pair and E1M1 state only.

## Paired BDA timing observation

Both runs began at the same source-bound Doom `leveltime` tic 70. DOSBox-X received a 1,800 ms PIC guest-time request, elapsed 1,890 ms, ended at tic 137 (delta 67), and advanced BDA by 38. QEMU received a 1,800 ms virtual-clock budget (1.8 billion ns), ended at tic 134 (delta 64), and advanced BDA by 36. Both emulator owners were reaped with return code 0. These values use backend-specific request and clock contracts; they do not establish equivalent timing or gameplay speed. The receipt's nominal 54,925,493 ns BDA-tick reference is not calibrated to these observed deltas. The BDA mapping and cross-engine timing relationship remain open.

Private receipt: `/Volumes/GitHub/GitHub/fDisBull-private/qemu-doom-timing-bda-20261125/paired-bda-timing.json`
SHA-256: `48a4326103f161b43e7beb1ee4001924c753316705aee5536c30c0ccde2f4ce9`

## Corrections and limits

The checkpoint harness uses distinct source-binding export filenames for the origin and cold child. Save observation waits for the single-Enter transition to settle before decoding. The timing harness removes a stale breakpoint before the accepted timing observation. The initial timer-stop CPU divergence is preserved as an open frontier-phase observation; it is not hidden by the matched-tic result.

These are opt-in private tests only. No CI ran, DOSBox-X remains the default, and no 143 surfaces or 7 campaigns are qualified. No release, merge, or shared installation/activation is claimed.
