# Shared machine debugger acceptance — 2026-10-25

This is a local, uncommitted development milestone after published 0.13.0.
It establishes one owned offline QEMU lifecycle for DOSBox and Wine plus an
explicit outer-machine CPU context. It is not a release or hosted CI receipt.

- Full ordinary Linux snapshot: **812 passed, 45 skipped**.
- Final Linux focused checks: **44 passed, 15 skipped**; cover the three final
  runtime changes and the added remote-launch timeout validation cases.
- Boot/GDB native gate: **7 passed**, no skips (two wire contracts and five real
  machine cases, including `r`, `w`, `rw`).
- DOSBox/Linux/QEMU gate: **3 passed**, no skips (one preflight, the full real DOS
  state/layer/watch/grid/input/restart workflow, and disconnect-during-boot).
- IDA/Wine/QEMU gate: **4 passed**, no skips (three contracts and one real session).
- Custom Wine/QEMU regression gate: **13 passed**, no skips (ten contracts and
  three real native workflows, including editable machine checkpoints).
- Direct DOS and local integration checks: **103 passed, 5 optional skips**.
- Installed final wheel: **43 passed, 7 optional runtime skips**, with an explicit
  installed-package import assertion and pytest's source-path insertion disabled.

Native numbers include their accompanying contracts; they are not counts of
independent game runs. The full Linux snapshot predates the final launch-budget
changes; `verification.json` records exact snapshot deltas and focused coverage.
Only a documentation filename correction follows that focused snapshot.

The real **DinoPark** replay uses `dosbox-qemu` through the interface-31 binary
endpoint, uploads the explicit private asset list, skips the intro, clicks New
Game with an 8px frame, hits the relocated patchless breakpoint at project
`0x175bc`, captures **512 fetch records**, and opens the bank dialog. The last
fetch record is pending execution. Original game inputs are verified unchanged;
the owned VM is reaped. `dinopark/` contains screenshots, the bounded trace and
JSON receipts, not a copy of the game. The replay source is
`examples/dinopark/verify_remote_endpoint.py`.

`boot/` contains a real QEMU display capture and completed-step trace from an
authored BIOS boot sector. `dos/` contains authored DOS fixture captures and
fetch trace; `ida-pe/` contains authored PE fixture captures and completed-step
trace. The tests reopen the project, export stored images/traces without a GUI,
and verify original/child patch isolation. Private databases and native states
are excluded.

Tool packages passed `scripts/check_dist.py`: **84 wheel entries, 205 tool ZIP
entries and 213 sdist entries**. Each packaged source/resource was compared with
the current source. These local audit builds retain 0.13.0 package metadata;
they are not replacements for the published release. No packages or runtime
images are included in this evidence folder.

Runtime resource hashes, Linux binary origin, tests and exact claim limits are
recorded in `verification.json`. The recovered Linux DOSBox executable passed
real feature acceptance; this run did not independently rebuild it to prove
source-to-binary parity. DTrace, OS task discovery, typed Windows kernel objects,
register-read filters and universal execution overlays are not implemented.

The earlier `2026-10-25/` and `2026-10-25-speed/` evidence remains unchanged.
