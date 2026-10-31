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

10. The emitted Linux x86-64 city shell is not host-runnable on Darwin.
    - The bounded builder emits a mode-0700, 32,768-byte static ELF64
      artifact, but macOS returns `Exec format error`; no local `qemu-x86_64`
      or `wine64` runtime was available for this check.
    - The build receipt correctly keeps `native_execution: false`. A Linux
      runner, QEMU profile, or another explicit target runtime is required
      before claiming native execution.
    - The required full Darwin suite remains portable only in part:
      `2189 passed, 149 skipped, 23 errors, 2 failed`. The errors and failures
      are the existing Linux-ELF/Mach-O fixture boundary (`/usr/bin/gcc`
      produces Mach-O or rejects Linux-only linker flags), not the Civ slice.

11. Darwin had no native output target, so executable evidence stopped at a
    cross-built ELF.
    - Static `arm64` Mach-O is not a usable route on current macOS: `clang
      -static -nostdlib -Wl,-e,_entry` links, and even ad-hoc signing succeeds,
      but the process is killed before `main` (exit 137). Static user binaries
      need dyld.
    - Resolution: added the `macos-arm64` target in `src/fdisbull/udc_macos.py`
      (profile `macos-arm64-c-plan-libsystem-1`). It compiles generator-owned C
      for `arm64-apple-macos11`, links libSystem for `write` plus CRT startup,
      and writes one JSON observation frame to stdout. `tests/test_udc_macos.py`
      runs the artifact natively, and the Civ city slice reports
      `$shield_box: 3` from a real arm64 process.
    - Declared differences: dyld/libSystem dependency, stdout-only observation,
      no `capture_state`. The builder still records `native_execution: false`;
      running the artifact is separate evidence.

12. The installed investigation skill was stale against the source tree.
    - `~/.omp/agent/managed-skills/fdisbull-investigate` held 5 files (SKILL.md
      plus four references) while the source tree ships 12, including
      `sweding.md`, `source-and-concepts.md`, `formats-and-media.md`,
      `recovery-research.md` and `workflows.md`.
    - Open PRs #59 (sweding), #51 (reconstruction reuse) and #52 (source and
      concepts) each extend different parts of the same skill, so no single
      branch was the latest complete version.
    - Installed the union of `main` plus those three branches (one clean
      three-way merge on `references/udl-uil-udc.md`, no conflict markers) with
      a timestamped backup beside the live directory. Skills are used from the
      installed copy, so the cached release is not a reason to run an older
      guide.

13. `execute_il` reports refusal in its result, not as an exception.
    - A differential harness that wraps the call in `try/except ValueError`
      records the refused branch as "committed" and compares two unchanged
      states. The refusal is `{"status": "refused", "error": ..., "state":
      original}` with no raise; harnesses must branch on `status`.

14. The IL cannot express an AND-mask or a multiply.
    - The recovered buy commit clears a status bit (`and byte [...], 0xef`) and
      doubles a cost (`shl ax,1`). Doubling is reachable as two `add`s in a
      signed 16-bit scratch cell, because `set` rejects a negative value for a
      `u16` cell; the mask is not expressible and was excluded from the model
      rather than approximated. Any further city routine that masks flags or
      multiplies by a table value needs an IL primitive first.

15. String-patch scripts silently no-op after `ruff format` rewrites a file.
    - Patching `examples/civ/civ_city_udc_diff.py` in place with exact-substring
      `str.replace` matched before formatting and stopped matching after, so
      `main()` kept its old body while the module gained new functions. Assert
      the anchor before replacing (`assert old in text`) or the failure is a
      later `KeyError` in the receipt, not an error at patch time.

16. A commit modelled from store shape was the wrong routine.
    - `R:0D12:4C00..0x4E03` ends with `add [bx+0x70fa], ax`,
      `shl ax,1 / sub [bx-0x4e2a], ax` and `and [bx+0x70f2], 0xef`. That reads
      as a purchase, so it was modelled and committed as the buy commit.
    - The `b` key branch is at `0x737D`; the real price is computed at
      `0x7387` (`2b + b*b/20`, doubled twice), the guard is `0x75D2`, and the
      commit is `0x75E5` (`box := 10*cost`, `gold -= price`) - about 0x2A00
      bytes away. The earlier window is still unattributed.
    - Lesson applied: trace the key branch to its commit before modelling.
      Store shape alone does not identify an action.
