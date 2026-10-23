# Verification receipt — fDisBull 0.2.0

Final integrated source tested on Linux, CPython 3.12. Native packages: iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0, Pillow 12.3.0.

| Requirement | Fresh evidence | Result |
|---|---|---|
| Final integrated suite | `python3 -m pytest -q --tb=short` | **80 passed**, exit 0, 9.06 s |
| Header/container inspection | Bytes-based PE32/PE32+, ELF, Mach-O, DOS MZ/NE/LE/LX tests; malformed/truncated cases | Passed |
| Original DinoPark recognition | Actual 268,480-byte DINOPARK.EXE passed through public `identify` command | Valid DOS MZ; no segmented analysis claim |
| PE metadata | Constructed named/ordinal import and export tables, disk offset vs preferred VA, overlay strings | Passed |
| Recursive analysis | EP-first traversal, data queue, later disconnected export, corroborated indirect call | Passed |
| Conservative code discovery | Arbitrary pointers and mapped immediates stay candidates; far calls remain unresolved | Passed |
| Fixed point | Budget-one resumption reaches empty queue; next analysis adds zero facts | Passed |
| Shared state | Target rename updates references, import list, queue, pointed value and SVG without rewriting instruction rows | Passed |
| Representation change | qword retracts pointer-derived call; pointer restores it after reanalysis | Passed |
| Byte/version isolation | Child pointer and header-string patches use child bytes; parent remains unchanged | Passed |
| Persistence/migration | Input deletion and separate-process reopen; schema-1 retains annotations and backfills new references | Passed |
| CHimpREC offline recovery | Named/ordinal exports, alias ambiguity, zero/unresolved cells, bounds, replacement map, recursive candidate selection | Passed |
| Output/protocol robustness | Protected DB/aliases/sidecars; malformed/nonfinite/deep JSON recovery; project-bound inspection | Passed |
| Unsigned addresses | x86 high-half addresses; ARM64 backward branch/ADR/literal targets | Passed |
| GUI-free exports | Annotated ELF and Windows PE listings exported as PNG/SVG; PNG visually inspected | Passed |

Independent review reran the integrated 79-test suite before the final mapped-immediate regression was added, reproduced all seven review findings against their fixes, and separately checked a fresh PE parsing/analysis/rename/SVG workflow and the actual DinoPark header. The final 80-test run includes the additional mapped-immediate test.

Examples: `demo.fdb` analyzes 84 ELF instructions plus four referenced-data tasks and reaches stability; `windows.fdb` analyzes three PE instructions and one IAT data task; `captured-iat.fdb` demonstrates offline alias-preserving recovery from a synthetic snapshot.

CHimpREC source methodology reviewed at `50495c0b9962130c17939bfbef806aecd41040ad`, with pinned provenance returned in recovery receipts. Automatic project recovery candidates come from recursive decoded references; the standalone recovery helper can also scan CHimpREC-style patterns.

## Limits

No macOS/Apple Silicon execution, live Windows attachment, runtime module discovery or import-table rebuilding was run or claimed. Constructed PE/Mach-O fixtures do not establish universal format compatibility. ELF/Mach-O import bindings are partial, PE delay imports are not enumerated, and string extraction is bounded ASCII/ASCII-range UTF-16LE. Stability describes implemented rules, not completeness of reverse engineering. Segmented DOS loading, general value propagation/jump tables, complete CFG/function boundaries, decompilation and runtime SMC remain outside this release.

The installable `dist/fdisbull-0.2.0-py3-none-any.whl` was built and imported directly from the wheel. Its info/analyze/imports/queue/render smoke workflow passed against the saved Windows example. Wheel SHA-256: `1324641219989ed5482e13ba798502a03544eaa4787b693351a3fd7078c7f10c`.

The original DinoPark binary is an external verification fixture and is not distributed in this package. Its one test skips when that fixture is absent; the remaining 79 tests are self-contained (the ELF compiler test can also skip if no C compiler is installed).
