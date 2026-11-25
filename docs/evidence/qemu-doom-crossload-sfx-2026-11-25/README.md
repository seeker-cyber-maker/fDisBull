# Original Doom cross-load and pistol sound gate

On 2026-11-25, one guarded native test passed (`1 passed in 66.72s`) for a
single one-way route: DOSBox-X wrote a private original Doom 1.9 E1M1 save,
QEMU admitted and loaded the exact save bytes, then one Ctrl keyboard input
fired a pistol shot in the loaded game.

QEMU's workspace readback matched the DOSBox-X save SHA-256
`d5a3983da612d9d959801188a9823b104c600bb3bcd868a13aa399c349bca475` (24,702
bytes). The visible load-menu frame changed 20,158 pixels; the WAD-derived
ammo observation returned to 50 after loading. A no-shot audio control kept
ammo at 50 and scored 0.18962 against `DSPISTOL`. The subsequent Ctrl action
was dispatched as two input edges; the WAD-derived ammo changed 50 to 49 and
the shot capture scored 0.97032 against the pinned WAD sample. QEMU retained
38,071 frames with zero dropped frames. Both emulator owners were reaped with
return code 0.

The correlation establishes a bounded sample match in this capture. It does
not establish sound-call instruction attribution, calibrated onset latency,
PCM identity, mixer/music fidelity, reverse-direction combined audio, general
save compatibility, or broad QEMU/DOSBox-X parity. DOSBox-X created the save;
the combined load-and-shot/audio observation ran only on QEMU. No campaign or
inventory qualification is added.

The private progress receipts, pytest/guard log, WAV captures, and save are
retained outside Git. Their hashes and the exact test/input identities are in
[`verification.json`](verification.json). No commercial media, save, WAV,
screenshot, emulator state, or byte-retaining database is included here.
