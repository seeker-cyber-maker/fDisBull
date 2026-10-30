# DOS termination reporting candidate — 2026-10-30

The original cloud arithmetic task verified the authored COM program's result
but could not distinguish its DOS exit from a bounded pause. The candidate
backend now observes the selected process's `DOS_Terminate` cleanup and reports
`guest_exit`, independently of debugger shutdown. The Python normalizer retains
that process evidence without inventing final target registers from the restored
parent context. `guest_tsr` separately identifies a program remaining resident.

The fDisBull source base is `85503c0e895842424faa7db62f020b879d08568a`.
Both complete native patches target upstream DOSBox-X
`029bd65c5dcc7cdc7f2e14e35278620d9707d969`. Fresh pristine source replays
matched every manifest entry: 32 stable-profile files and 33 layers-profile
files. The native change affects seven source files; prior patch sections and
their original line endings are retained.

## Fresh runtime evidence

| Check | Observed result |
| --- | --- |
| Linux cloud, layers profile: termination, debugger, COM/launch, run boundaries, wait, code layers, experiments, runtime code, semantics, doctor, screenshot hooks | 140 passed, exit 0 |
| Linux cloud, stable profile: termination, semantics, run boundaries, debugger, COM | 53 passed, exit 0 |
| Independent macOS ARM64 layers build: termination, semantics, run boundaries | 26 passed, exit 0 |
| Source companion, extracted native window contract, installed-skill gate | 30 passed, exit 0 |

The native regressions exercise COM and MZ `INT 21h/AH=4Ch`, `INT 20h`, initial
COM `RET`, TSR, an interrupt remapped to return, explicit pause/session cleanup,
and a parent that resumes after its child exits. They check persisted exit
evidence after reopening the project and selected-process identity after an
exact same-session state restore. The additional macOS negative test confirms
that a foreign-session snapshot does not acquire a guessed target identity.
These focused runs do not claim a full repository suite or release CI result.

## Original cloud-task rerun

The existing [Verify authored DOS arithmetic cloud task](https://chatgpt.com/local/01a18c8b-c5ab-73bf-bfa0-913f4a0790ee)
ran the original 14-byte COM fixture with the isolated candidate backend.
Run `816f19a4cd8341b7a7a2c17c620c12f6` observed EAX `0x0000000C`
and memory bytes `0c00` before exit, then returned:

```json
{
  "outcome": "guest_exit",
  "timed_out": false,
  "session": {
    "state": "exited",
    "stop_reason": {
      "kind": "guest_exit",
      "guest_exit": {
        "psp": "0x0814",
        "parent_psp": "0x0701",
        "requested_exit_code": 0,
        "resident": false,
        "source": "DOS_Terminate",
        "stage": "after-process-cleanup"
      }
    }
  }
}
```

The same native event survived cleanup and repeated cleanup-operation waits.
The exact cloud receipt SHA-256 is
`86919edf2a01c5deca823d10dffd118f6f22be9e2953755fe45d604599a0af15`.

| Executable | SHA-256 |
| --- | --- |
| Tested Linux layers candidate | `91755d224f3f3951eb0912ead14c9e92a9c9bd032fa7321a35d81c8847c8609a` |
| Tested Linux stable candidate | `11a462e0ae4ef7fdc90a5bd6a9aae3133bcb0e19c35cd77054888ea7cd1beaa6` |
| Tested macOS ARM64 layers candidate | `28ace4af352d93db656d2a7b8366df77a94d8dc7c0c4609bf60d72017bfaf1fa` |
| Existing published Linux backend, preserved | `6dea7e6ac612adb31a213ee92b4871d6a28b18db51edc66fa47ac57383575c8f` |

## Scope and activation

The capability is `lifecycle.dos_guest_exit`. Reporting covers the built-in DOS
kernel and a known selected target PSP; it does not qualify a separately booted
operating system or arbitrary protected-mode lifecycle. `requested_exit_code`
is the kernel-call argument, not a claim about a later parent return status.
Unknown or foreign-session native snapshots disable tracking rather than
adopting the current restored child PSP. See the
[debugger contract](DOSBOX_DEBUGGER.md#dos-process-completion-and-debugger-cleanup).

These results qualify the isolated source and executable candidates. They do
not record a published release, default cloud-environment update, installed-system
activation, tag, or exact-commit release CI. Existing backend binaries need a
rebuild to gain the kernel notification; a Python-only update is insufficient.
