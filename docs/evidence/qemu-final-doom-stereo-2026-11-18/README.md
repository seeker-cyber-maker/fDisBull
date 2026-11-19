# Original Final Doom: bounded stereo capture and persistence

The supplied TNT and Plutonia originals now pass fresh QEMU directory launch,
physical keyboard firing, and exact hot/separate-Python cold machine and audio
continuation on the declared Linux tuple. The installed DOSBox-X baseline also
passes visible firing, same-owner save/load and normal guest exit for both
variants. These results do not establish full DOSBox-X replacement parity.

The measurements completed on 2026-11-19 UTC. [Verification](verification.json)
records the immutable identities, retained private-receipt hashes, counts and
claim limits. Game files, databases, states, screenshots and audio remain
private; none are included here. No hosted CI was dispatched.

## Tuple and the admission defect

The accepted host source is commit
`f35d387f8f0aec330b886e6897d40813c8126f39`. The unchanged Linux QEMU 10.0.13
executable has SHA-256
`71bef609647922544bfca23811caa0c08843a09d6b48c70293ab5ebd6cdb1a40`.
The DOSBox reference is the isolated installed fDisBull 0.34.1 release,
DOSBox-X 2026.10.01 commit `f1c4414`, native executable SHA-256
`d9236f1178855524a74516eb37cbb636431f9bdec599d9d675e6d69ea6309251`.

The original 16 MiB aggregate file cap refused both directories before any VM
spawned: TNT contains 19,378,242 bytes and Plutonia 18,963,571 bytes. Both exact
refusals are retained. The fix applies one 24 MiB cap consistently to capture,
generation sealing/loading, refresh and mutations. The 32 MiB FAT workspace,
64 MiB native disk cap and checkpoint bounds remain unchanged. No WAD was
split, omitted or modified, and no manifest was edited to evade admission.

Four new regressions first reproduced the old refusal. After the change,
68 focused host tests passed with zero failures or skips, and independent root
review reran the four new tests successfully. They cover large capture and
immutable mutation, reopening and cold generation launch, exact 24 MiB FAT
acceptance, aggregate-plus-one refusal before VM/artifact publication, and
large persisted workspace-record/FAT recovery. The host checkpoint test uses
an authored conversion seam; the game campaigns below supply native evidence.
See the [workspace contract](../../DOS_FILE_LAYERS.md).

Each game retains its original EXE and WAD. A private shipped-config derivative
changes only music device 3 to AdLib device 2; both volume settings remain 8,
SB16 effects remain enabled, and `BLASTER=A220 I7 D1 H5 T6` matches the machine.
Both use Map01, skill 2 and `-nomonsters`. The QEMU profile is `sb16-opl` with
virtual-clock execution and explicit `s16-stereo` observation at 32,000 Hz.
The observed guest SB16 voice is unsigned 8-bit stereo at 11,025 Hz. S16 output
capture does not imply qualification of 16-bit guest SB16 voice checkpoints.

## Observed application and recovery results

Each QEMU case starts in visible Map01 with 50 bullets. A physical Ctrl press
held for 300 ms, followed by a 700 ms execution budget, produces a visible
gunshot and 49 bullets. No game memory, register or IRQ-mask edit supplies the
input effect.

| Variant | Saved A frames / chunks | B after 600 ms frames / chunks | Differing L/R frames at A | Accepted QEMU owners |
| --- | ---: | ---: | ---: | ---: |
| TNT | 34,845 / 112 | 53,763 / 173 | 0 | 4, all reaped with code 0 |
| Plutonia | 34,683 / 112 | 53,300 / 173 | 2,924 | 4, all reaped with code 0 |

Hot and separate-Python cold restoration each reproduce A exactly and then
reproduce its next 600 ms exactly: full exposed CPU, PNG bytes, retained PCM
bytes and callback chunks, OPL/SB16 queries, mixer state, virtual time and
instruction count. The saved PCM prefix extends without replacement. Raw DC,
RMS, extrema and rail counts are retained without centering or normalization.
TNT's selected left and right lanes are identical; no asymmetric application
signal is invented. The separate authored paired-tone test supplies explicit
lane-separation evidence.

These are owned-machine checkpoints. `source_binding_restored` and
`protected_source_rebound` are false; no LE admission or restored original MZ
source authority is claimed. All eight accepted native owners were closed and
reaped. These Final Doom QEMU campaigns did not attempt normal DOS guest exit.

Both DOSBox baselines visually establish 50→49 firing and 50 after same-owner
load, with exact exposed CPU fields at load. Each observes the physical F10
confirmation, then Y and a normal `DOS_Terminate` guest exit code 0 before
emulator cleanup. Its retained audio is nonconstant S16 stereo at 48,000 Hz.
The clips include startup, input, load and exit; no audio-writer continuation,
cold DOSBox recovery or cross-engine sample alignment is claimed. Earlier TNT
startup and short observation windows remain retained and are not counted as
visible input consumption.

## Known sound-device counterexample and claim ceiling

A later independent authored count oracle tested U8/S16, mono/stereo and FIFO
on/off on this same frozen native executable. DOSBox consumes the documented
extent in all eight cases. QEMU's four mono cases pass; all four stereo cases
consume twice the programmed byte extent: 2,048 instead of 1,024 bytes for U8,
and 4,096 instead of 2,048 for S16. The test does not wrap DMA. Its eight paired
cases account for sixteen separately reaped owners; the smoke pair is not
double-counted. The immutable result hash is recorded in `verification.json`.

Exact recovery preserves the tested emulator behavior, including a behavior
that can still differ from the device contract. Audio fidelity, stereo DSP
count semantics and full parity therefore remain unqualified on this tuple.
A corrected native candidate needs fresh qualification and new states under
its own identity. Menu navigation, map transitions, mouse consumption, ordinary
save-game behavior, broader compatibility and a full playthrough also remain
outside this bounded campaign.
