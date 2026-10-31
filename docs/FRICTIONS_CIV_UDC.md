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

7. NE seed spelling differed between the active release and the source under test.
   - The NE guide uses logical addresses such as `ne:20:0x547c`, while the
     installed `0.26.1` command rejected `fdisbull analyze --start ne:20:0x0`
     with `invalid literal for int() with base 0`.
   - The equivalent packed numeric identity `--start 0x140000` was accepted
     by the installed release and produced a bounded traversal.
   - The source checkout already routes NE projects through `ne.parse_address`;
     `tests/test_ne_cli_seed.py` now exercises the documented logical form
     through a fresh CLI process using the pinned `0.26.1` interpreter, with
     the source checkout explicitly under test (`1 passed`).
   - Until that source change is promoted into the installed release, baseline
     runs use the numeric fallback and report the release/source distinction
     instead of claiming that the installed `0.26.1` command is fixed.

8. Artifact-broker failure was independent of shell execution.
   - During archive inspection, `proc://omp.blob.broker` reported
     `blob broker exposure failed to start`; ordinary bash, pytest, and Git
     operations continued to work.
   - A source-companion archive also exceeded the reader's 64 MiB in-memory
     limit for one nested member. This is an inspection transport/size
     boundary, not evidence that fDisBull could not analyze the target.
   - The workflow now uses bounded reads, explicit repository paths, and
     fail-fast shell commands; the broker failure remains a harness follow-up.

9. The unpacked DOS root was not present locally, and a size-only decoder was
   insufficient.
   - `CIV_UNP.EXE` is the decoded MZ root used for analysis; it is not a
     media/resource unpacker. The missing artifact initially blocked the
     `R:0D12:0045` city route.
   - A bounded clean-room decoder was added in the Civ worktree. Its first
     output had the correct 340,791-byte size but the wrong SHA because MZ
     `e_cp`/`e_cblp` must describe the root load module rather than the
     physical file including overlays, and `e_minalloc` must be compensated for
     decoded paragraph growth.
   - An independent UNP 4.12 run isolated the six-byte header difference. The
     decoder now produces the published
     `aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57`
     identity, with a synthetic regression fixture plus a real-target check.
   - The utility and the exact-target output remain in the feature PR; this
     friction PR records the repeatability boundary and the reason not to call
     any size-only output equivalent.
