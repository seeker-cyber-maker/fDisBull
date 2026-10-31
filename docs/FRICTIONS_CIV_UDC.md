# Friction Notes: Civ UIL/UDC Work

## Fixed in this branch

1. Native shell build `output.path` was relative to `directory`.
   - Affected: `build_linux_shell` (`output.path='program'`) and `build_windows_shell` (`output.path='program.exe'`).
   - Evidence: callers treating `output.path` as a filesystem path hit `FileNotFoundError`; the emitted file was at `directory/program` or `directory/program.exe`.
   - Fix: added `output.absolute_path` as a directory-qualified filesystem path while preserving `output.path`, `directory`, `capsule`, and all existing fields.
   - Regression: `tests/test_udc_linux.py::test_build_output_absolute_path_is_filesystem_path`.

## Follow-up (not fixed in this branch)

2. DOS packed-root coverage.
   - DOS EXEPACK import/analyze reports a bounded packed root as `stable` without making packed-root/overlay coverage limitation obvious in the compact receipt.
   - This slice does not implement a full unpacker; only the receipt/coverage UX needs clarification.

3. Interpreter identity.
   - System Python vs pinned venv resolved different `fdisbull` versions, so commands should report/verify interpreter identity.
   - No code change made here; document/reporting follow-up.
4. Native shell domain admission is not represented in the generic profile.
   - `build_selection_shell` refuses a nonempty contract/layer domain because
     the emitted shell has no generic compiled admission adapter.
   - The corrected Civ module therefore keeps signed limits in typed IL
     `require` guards and its module-level release gate instead of silently
     dropping them. A future profile should carry and qualify concrete native
     input-domain guards explicitly.
5. macOS full-suite Linux fixture portability.
   - The complete suite on Darwin reached 2,183 passed and 149 skipped, but
     23 Linux-ELF fixture setup errors and 2 ELF assertions remained because
     `/usr/bin/gcc` emitted Mach-O or rejected Linux-only linker flags.
   - No unrelated test or toolchain workaround was added; the follow-up is an
     explicit Linux-container/runner or cross-compiler fixture policy.

6. Active-version selector versus convenience-path drift.
   - The active installation record and `RUNTIME.json` resolve to fDisBull
     `0.26.1` at `/Users/Shared/fDisBull/releases/0.26.1-f783f2a/venv`.
   - `/Users/Shared/fDisBull/current/venv` imported `0.26.0` during this
     investigation even though the active selector reported `0.26.1`.
   - The workflow now treats `RUNTIME.json` and its versioned interpreter as
     authoritative, asserts the imported version before analysis, and records
     the source commit. This avoids silently attributing stale-agent results to
     the current fDisBull release.

7. NE seed spelling differs between documentation and CLI.
   - The NE guide uses logical addresses such as `ne:20:0x547c`, while
     `fdisbull analyze --start ne:20:0x0` rejected with
     `invalid literal for int() with base 0`.
   - The equivalent packed numeric identity `--start 0x140000` was accepted
     and produced a bounded traversal.
   - The workflow records the numeric fallback for now. The CLI should either
     accept the documented logical form or state the numeric-only boundary
     explicitly, with a regression test before changing parsing.
