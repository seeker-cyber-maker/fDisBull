# SCUMM v2 room-transition phase contract

This host module is a reference-derived planning and receipt validator. It is not the native QEMU room loader and does not execute game scripts, load resources, mutate actors, or change the current room.

The phases are deliberately distinct:

1. Run the old room exit script when present.
2. Stop room-owned scripts, preserving global script ownership.
3. Release room-owned resources.
4. Admit the exact target room resource by SHA-256.
5. Parse the target room.
6. Reset/instantiate room objects.
7. Rebuild room-owned flags, palette, walkboxes and matrices.
8. Initialize camera and actor placement/visibility.
9. Publish the new current-room identity.
10. Run the target entry script when present.
11. Run global script 5 when available for this v1/v2 path.
12. Mark the transition complete.

A missing entry/exit script is an explicit optional phase, not an inferred successful execution. A phase receipt must be ordered, tied to the exact plan hash, and carry all expected evidence. The plan digest is recomputed during receipt validation to reject modified phase definitions. Missing phases never count as complete. The plan marks that movement is not implied and native execution has not occurred.

The source reference is ScummVM v2.9.0 commit 38af1883a2eb7a622c31bfc3708888bbcc47db48. The phase model must be rechecked against exact v2 behavior before being translated into native CPU state transitions. Do not reuse this old-bundle v2 contract for v3+ room formats.

Run:
```sh
python3 -m unittest test_room_transition.py -v
```
