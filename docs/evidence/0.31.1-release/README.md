# 0.31.1 release evidence

Status: **tagged and published** as `v0.31.1`; the tag commit is `e94bae0`.

- Source branch: `release/0.31.1`
- Source commit: `27b388d38cc14f04842a81b8ec1a113460900f53`
- Base: `v0.31.0` (`10d0106`) plus post-tag repair commits
- Version surfaces: core, player and package metadata all `0.31.1`
- Planned tag: `v0.31.1`

## Qualification

| Check | Result |
| --- | --- |
| Hosted `test-and-package` | **success**, pipeline `3023448913`; 8,961 passed, 402 skipped |
| Hosted native stable | **86 passed** |
| Hosted native layers | **148 passed** |
| Local full suite | 9,005 passed, 317 skipped, 2,316 subtests; 3 failures + 23 errors are the known macOS ELF/GCC/media baseline |
| Distribution checks | wheel 564, tool ZIP 1,822, sdist 1,843, player 19 entries |
| Swift helper | present in wheel, tool ZIP and sdist; `prepare_helper()` compiled it |
| Installed prefix | 97 tests passed, 0 failed/errors/skipped |
| Doctors | DOSBox, DOS-in-QEMU and Wine/QEMU `passed`, native state restored |
| Player | Two fresh processes restored `hall`/`key`; checkpoint mode `0600` |
| `check_local_install.py` | **PASSED** |

The three local full-suite failures are the known macOS baseline:
`tests/test_inspection.py::test_actual_elf_exports_and_unresolved_imports_are_honest`,
`tests/test_loading.py::test_real_elf_retains_entry_and_named_function`, and
`tests/test_media_modules.py::test_resource_ambiguity_and_directory_bounds`.
The 23 errors are the `test_elf_metadata.py`/`test_platform_calls.py` GCC
`-z ibtplt` fixtures, inherited from the same host environment.

## Artifacts

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `fdisbull-0.31.1-py3-none-any.whl` | 1,895,364 | `03bf5142aab0a9448c73b38c986ddeef92f68eab2630f6f1ef4842bb2364bf33` |
| `fdisbull_player-0.31.1-py3-none-any.whl` | 86,674 | `6b5098b8ad425579bb50bfd5d12fb4a6cfd362b45a863b3fd4937cbeedfa20a3` |
| `fdisbull-0.31.1-tool.zip` | 6,390,059 | `81db8e19349b6fb26ea2f91b7de79ed8ba1f3691c3d7f9eaec7ed04c7f5eb5c3` |
| `fdisbull-0.31.1.tar.gz` | 5,260,503 | `bd37507e6d91f0e3279f780b5238279a2b86fd02adc649ea1fe394cdde26b72c` |

## Local prefix

`/Users/Shared/fDisBull/releases/0.31.1-27b388d` is active and `active_verified`
with 4,379 payload entries. The previous `0.31.0-a12441b` prefix remains intact;
rollback preflight is ready and was not applied.
