# Shadowrun bounded targeting

The reviewed US Genesis source at `$ACAE..$AD1A` calls `$1DC4C` when the B
pressed bit is set, subject to caller state. For the prepared player record at `$FF0100`, the bounded ordinary NPC branch cycles
records `$FF0400..$FF0A00` in source order. A candidate needs bit 0 set and
bits 4 and 6 clear in byte `+$10`, bit 7 clear in byte `+$B0`, and a nonzero
word at `+$0C`. It updates the selected pointer, target flag and reciprocal
link. It does not choose the nearest target or itself establish weapon range,
line of sight or a hit.

The ordinary `$5A56..$5AC6` projection computes the word at `+$0C` from the
actor, camera and actor-height fields; it is cleared outside a source-defined
screen rectangle. This is an engine admission condition, not an assertion that
a player can see an actor or shoot it. The special callback `$15390`, party
targeting, alternate backlink and special D1 paths are outside this slice.
Captured records supply starting positions; NPC AI is not reproduced.

`scripts/check_shadowrun_targeting.py` compares finite prepared cases against
an original 68000 core. These injected leaf calls do not establish B-input
consumption, natural gameplay reachability, or entire combat behavior. Private
ROMs, captured records and emulator receipts remain outside the checkout.

A separate [sanitized assisted B-input receipt](evidence/shadowrun-assisted-original-b-target.json)
records the original game selecting `$FF0500` after only player/camera state was
injected. It binds the source, frame and capture receipts by hash. The selected
slot, flag, backlink and player field agree with the bounded selector; the
post-frame contact also agrees with the source projection at that frame's actual
camera and actor coordinates. The selector's immediate marker and the original
post-frame marker are recorded separately because they are observed at different
phases. This remains an assisted prepared-state observation, not a natural
encounter or a whole-game parity result.
