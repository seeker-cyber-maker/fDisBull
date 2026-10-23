# Native state editing and data-watch verification — 2026-10-23

This receipt covers the local extension after the published `a6cfea4` 0.9.0 integration commit. No new commit, push, tagged release, or package publication is asserted by this receipt.

On native macOS Apple Silicon with the patched SDL2/heavy-debug backend:

- **10 real-emulator debugger tests pass**, including native state restoration after Project/emulator restart, RAM/register state forks, reinjection and resumed execution, immutable parent/static source, expected-byte rejection, same-value writes, multibyte access overlap, read/write modes, instruction-fetch/host-read exclusion, scripting, aliases, timeout, and cleanup.
- **31 backend Python client/transport tests pass.**
- The authored headless DOS fixture acceptance passes: real CPU execution/trace/breakpoints, memory guards, native PNGs, palette/mode changes, absolute mouse input and guest callbacks.
- The full suite reports **726 passed, 3 skipped, 2 failed, 23 errors**. The failures and errors remain in the documented Linux ELF fixtures under Apple's compiler/linker. Focused tests passed again after the final register aliases and script-validation guard.
- The complete backend patch applies against pristine upstream `029bd65c5dcc7cdc7f2e14e35278620d9707d969` and reproduces **27 source-file hashes**. The current emulator SHA-256 is `e749b6e50775de2807c2515f83e455dc705cdf6ddcdfb257e781f215d987865a`.

`examples/dinopark/verify_states.py` passes against the original executable hash pinned by the earlier DinoPark receipt. Through public fDisBull JSON methods it:

1. Executes a stored eight-step route that fast-forwards 35 guest seconds, clicks OLD GAME, captures its dialog, and saves a native checkpoint.
2. Restarts the emulator and restores that checkpoint. It separately loads the first available in-game save to prepare a test fixture and captures another native checkpoint.
3. Places an eight-byte `w` watch over project `0x471a6` without analyzing data as instructions, then removes it. This verifies placement, not an observed counter-writer hit.
4. Forks the native checkpoint in an isolated paused emulator. A checked two-byte edit changes `00 00` to `01 00` at `0x471a6`, with no guest instruction execution during editing; the derived artifact records the parent hash and edit readback.
5. Injects the derivative into a new debugger session. It verifies modified RAM, hits the relocated execution breakpoint at project `1000:75bc`, and captures a complete 64-event instruction trace.
6. Observes actual `w`, `r`, and `rw` stops on the game's mouse-button sample at project `0x4029a`. The originating project instruction addresses are `0x175c1`, `0x16c7e`, and `0x16cda`, respectively.
7. Restores the parent checkpoint and verifies its original RAM and unchanged artifact hash. All emulator children are reaped. Screenshots and trace evidence export after reopening the project.

The authored fixture additionally verifies an `EAX` edit (`1234h` to `BEEFh`) alongside a RAM edit. Resuming the reinjected snapshot makes the fixture write `EF BE`, demonstrating execution from modified register state, then parent restoration returns the original register/memory values.

The native archive contains 26 components, including CPU, memory, VGA, PIC, DOS, mouse, and mixer state. Compatibility is bounded to the exact tested binary/profile/game directory. Checkpoints are not disk snapshots; mounted files must match their capture manifest. Arbitrary device-component editing, protected-mode access tracing, device/DMA watchpoints, every-game compatibility, and security sandbox isolation are not established.

The purpose/meaning of `0x471a6`, the STF7 writer, OK-versus-next-tick commit timing, and the revenue formula remain unverified. The supplied thirteenth STF7 save is absent from this local eight-save collection. Native state artifacts and byte-retaining `.fdb` files remain local; only source, bounded traces, screenshots, manifests, and receipts are in `experimental/dosbox-x/evidence/states-2026-10-23/`.
