# PE64 development acceptance: watches, layers and native states

This record preserves the **0.13.0.dev0 pre-release experiments**, including their then-uncommitted status. The versioned 0.13.0 candidate and its required CI gates are described in [release verification](VERIFICATION-0.13.md); the development receipts below remain byte-for-byte unchanged. Published 0.12.0 packages, their tag/CI receipts and the existing DeepSeek delivery remain fixed. See [usage and limits](WINE_DEBUGGER.md#pe64-watches-layers-and-native-states-013-development).

## Scope and acceptance

The authored `tests/wine_gui_fixture.c` is compiled as a real PE64 executable. Its GUI accepts mouse input, exposes a volatile counter, computes a software CRC over its own experiment function, and has an independently toggleable conditional branch. There are no game files in this experiment. QEMU emulates x86-64 Linux on the Mac ARM64 host; Wine runs the original executable inside the offline guest. Screenshots come from the guest client window; no host GUI is operated.

The required native command is:

```bash
FDISBULL_PE_QEMU=/path/to/qemu-system-x86_64 \
FDISBULL_PE_KERNEL=/path/to/linux-amd64 \
FDISBULL_PE_INITRAMFS=/path/to/matching-runtime.cpio.gz \
FDISBULL_PE_FIXTURE=/path/to/oracle.exe \
FDISBULL_PE_EVIDENCE=/path/to/reports \
FDISBULL_REQUIRE_PE=1 \
python -m pytest -q -s tests/test_wine_debugger.py tests/test_wine_advanced.py \
  -o pythonpath=/path/to/installed-wheel --junitxml=/path/to/reports/tests.xml
```

The gate requires native inputs, rather than succeeding through missing-backend skips. The wheel's production Python and packaged guest resources are compared byte-for-byte with working source before execution. The matching runtime is prepared from the retained pristine Wine base, without changing the published delivery. A source fingerprint mismatch on boot or restore fails the run.

The development gate covers:

- Existing disassembly breakpoints, guarded memory edits, real screenshots/clicks, bounded traces and offline exports after project restart.
- A byte write watch inside a larger store, before-access old memory, real read watches, pure-store exclusion for read-only watches, and read-modify-write access facts.
- RAM layer on/off and a self-CRC failure while the RAM patch is active; execution layer on/off with unchanged RAM and a passing software self-CRC.
- An inverted conditional branch and traces retaining original RAM, alternate bytes, scratch execution and pre-instruction registers.
- A data watch triggered by the relocated alternate instruction reading original source RAM, and refusal to save an unfinished alternate instruction.
- Whole-QEMU native state capture/load with saved registers, active layer and `rw` watch restored in a fresh process.
- All-edit preflight rejection without applying an earlier valid memory edit, followed by an immutable derived state with memory 17 → 51 and RAX `0x123456789abcdef0`.
- Closing/reopening the database, launching a fresh VM directly from that derived native state, clicking with an 8px grid, continuing with and without its saved execution layer, and restoring the unchanged parent again.
- Static original/child byte versions remain separate, and the original EXE's SHA-256 is unchanged. A native export contains exactly `state.json` and `machine.mig.gz`.

## Current results

The first complete installed-wheel acceptance passed **12 tests, no skips**, in **797.16 seconds** on 2026-10-24. The advanced state/layer scenario itself took 358.52 seconds. [Selected evidence](../experimental/wine/evidence/2026-10-24/pe-advanced/) includes [native JUnit](../experimental/wine/evidence/2026-10-24/pe-advanced/native-tests.xml), [watch stops](../experimental/wine/evidence/2026-10-24/pe-advanced/watch-events.json), [alternate-instruction trace](../experimental/wine/evidence/2026-10-24/pe-advanced/layer-execution.json), [restored 8px click frame](../experimental/wine/evidence/2026-10-24/pe-advanced/restored-click-grid8.png), [resumed counter screenshot](../experimental/wine/evidence/2026-10-24/pe-advanced/restored-after.png), and the [advanced result](../experimental/wine/evidence/2026-10-24/pe-advanced/advanced-verification.json).

Review then found that a native fork needed to reuse the parent's complete explicit upload allowlist. That fix was tested against another installed wheel with an authored text asset beside the EXE: **6 advanced tests passed, no skips, in 506.20 seconds**. The [separate follow-up evidence](../experimental/wine/evidence/2026-10-24/pe-advanced/asset-followup/) preserves those inputs/results without overwriting the initial gate. Parent and child retain both file identities, and the same native state/layer/restart/export assertions pass.

The final source also corrects RIP preflight to validate runtime addresses through the observed relocation delta. **10 installed-wheel unit tests passed**, with the three native tests deliberately deselected because their separate real gates are recorded above. The rebased RIP check exercises the real static address mapper without launching or claiming a rebased native RIP redirect. The only production difference from the asset-aware native wheel is this RIP-validation helper/branch; the real state test edits memory and RAX. Shared DOS native regression passed **45 tests** with the real 0.11 layers backend.

| Runtime experiment | Observed result |
| --- | --- |
| RAM layer changes increment 1 → 2 | Counter 7 → 9; software self-CRC fails |
| Execution layer changes increment 1 → 3 | Counter 9 → 12; original RAM and software self-CRC preserved |
| Branch inversion, then disable | Increment 2, then original increment 1 |
| Alternate instruction reads source RAM | Reads original byte `01`; read watch triggers inside relocated execution |
| Parent native state | Counter 17 and original GPRs restored after a live edit to 41; layer and `rw` watch restored |
| Immutable child native state | Counter 51; RAX `0x123456789abcdef0`; restored after database and VM restart |
| Continue restored child | Counter 54 with execution layer, then 55 with layer disabled |
| Restore parent again | Counter 17 and original registers; parent identity unchanged |
| Static/version/export checks | Original instructions and EXE hash unchanged; static child remains separate; complete native ZIP validated |

An earlier full run reached all runtime assertions above but failed the final static-child query because the test had not analyzed that child before asking for disassembly. That run is retained as a failed gate. The test now explicitly analyzes the child version before the query. Earlier separate watchpoint and fresh-QEMU migration probes passed, but do not replace the final installed-wheel acceptance.

The final-source full ordinary Linux suite passed **769 tests, 31 skipped, no failures or errors**, in **614.11 seconds**, inside the offline QEMU guest. The skips are ordinary-suite optional/native cases; required Wine/QEMU and DOS native results are recorded separately above. The source and test files in that Linux image were checked byte-for-byte against the frozen final tree. One nonfatal pytest cache warning records that the source directory is read-only to the test user. [Linux JUnit](../experimental/wine/evidence/2026-10-24/pe-advanced/linux-tests.xml) and [log](../experimental/wine/evidence/2026-10-24/pe-advanced/linux-tests.log) retain the complete result.

The initial full macOS ordinary run reported **741 passed, 33 skipped, 2 failed and 23 errors**. The failures/errors are the existing Linux ELF compiler/linker fixture incompatibilities on Apple's toolchain, in `test_inspection`, `test_loading`, `test_elf_metadata` and `test_platform_calls`. This is not an all-green macOS suite. The final installed-wheel unit and native checks above are fresh Mac-host results; the ordinary Linux run additionally exercises its compiler/linker fixtures.

A full Linux attempt reached 100% progress but failed pytest session finish because the harness left the report directory owned by root and the test user could not write JUnit. This is preserved as a [failed reporting gate](../experimental/wine/evidence/2026-10-24/pe-advanced/linux-reporting-failed.json), with its log. The corrected harness assigned that directory to the unprivileged test user and reran the unchanged source, producing the successful result above. The earlier interrupted and failed reporting runs are not counted as green gates.

The [final checksum receipt](../experimental/wine/evidence/2026-10-24/pe-advanced/verification.json) binds the review packages, production source, test definitions, installed test wheels, emulator/kernel/runtime/fixture identities, separate gate results and selected evidence. All owned VMs were reaped. At the time of these development receipts, no new GitHub CI, tag, release or DeepSeek delivery was claimed and the source was uncommitted. Subsequent release preparation is recorded separately.

## Evidence and limits

Native machine images, fixture executables, databases and runtime images stay in ignored private storage. Only authored fixture source and selected report/log/PNG/trace evidence may enter Git. State exports are deliberately outside the evidence upload directory. The native CI workflow now includes the advanced gate, but a local run does not establish new GitHub/Linux CI status.

This fixture qualifies a finite set of scalar instructions and GUI operations. It does not establish arbitrary game compatibility, complete memory tracing, scheduler fidelity, invisible instrumentation or cross-version native-state portability. PE layers use a private 4 KiB target allocation, guard protections and host stepping. Exact backend/input identities and the native-state sidecar are required for restore. See the mechanism-specific exclusions in [the debugger guide](WINE_DEBUGGER.md).
