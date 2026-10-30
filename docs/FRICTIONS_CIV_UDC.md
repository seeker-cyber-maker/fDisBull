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
