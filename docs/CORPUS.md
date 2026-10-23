# Bounded static corpus qualification

Checked **2026-10-22** against the working source exposing the inspection, byte-location, function-pattern and decoder-comparison APIs. This is corpus qualification, not a final-release receipt or a claim of complete code coverage. The application reported version `0.3.0` at the time of this run.

Nine already downloaded PE samples were parsed as data. Every source SHA-256 was recomputed and matched the supplied manifest. Each received exactly one recursive analysis call with a **5,000-attempt maximum**. No sample ran, no DLL was loaded into an OS process, and this qualification did not unpack or automatically unpack anything. The original executables, DLL, archives and temporary `.fdb` databases remain outside the code archive.

The machine-readable receipt is [corpus-analysis.json](../examples/corpus-analysis.json). It records source SHA-256, Drive URL, size, per-sample API results, entry bytes, metadata counts, analysis receipt, candidate evidence, truncation flags, native parser diagnostics and unresolved/pending work.

## Header and metadata results

All nine byte-based identifications, inspections and native-loader project imports succeeded. Headers classify four samples as PE32+ and five as PE32. All supplied CLR-directory entries are zero; this set therefore does not qualify managed/.NET parsing. Metadata totals are static, not recovered runtime imports.

| Source | Bits | Sections | Imports | Exports | Strings |
| --- | ---: | ---: | ---: | ---: | ---: |
| Test64.exe | 64 | 3 | 4 | 0 | 14 |
| Test32.exe | 32 | 3 | 4 | 0 | 18 |
| deroko-64.exe | 64 | 2 | 0 | 0 | 383 |
| PESpin-64.exe | 64 | 6 | 6 | 0 | 359 |
| SEH.exe | 32 | 3 | 3 | 0 | 13 |
| HideDebugger.dll | 32 | 5 | 120 | 1 | 3077 |
| deroko-64-_.exe | 64 | 3 | 61 | 0 | 934 |
| seh_asm2.exe | 32 | 3 | 52 | 0 | 211 |
| CryptoKeygenMe1.exe | 32 | 4 | 151 | 0 | 488 |

Import/export examples in the JSON are capped at five records and marked when truncated. Function-pattern examples are capped at 20, issue examples at 10; full counts and pagination flags remain recorded. String truncation and parser warning fields remain explicit. These samples do not test every loader format or every PE directory.

## Recursive analysis results

| Sample | Instructions | Function candidates | Xrefs | Pending | Issue records | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Test64.exe | 57 | 5 | 14 | 0 | 4 | Implemented queues drained |
| Test32.exe | 27 | 5 | 14 | 0 | 4 | Implemented queues drained |
| deroko-64.exe | 164 | 5 | 29 | 0 | 8 | Implemented queues drained |
| PESpin-64.exe | 367 | 2 | 103 | 0 | 6 | Implemented queues drained |
| SEH.exe | 30 | 4 | 12 | 0 | 3 | Implemented queues drained |
| HideDebugger.dll | 5000 | 236 | 1902 | 411 | 269 | Budget-limited, partial |
| deroko-64-_.exe | 5000 | 104 | 2181 | 200 | 141 | Budget-limited, partial |
| seh_asm2.exe | 4568 | 72 | 1831 | 0 | 120 | Implemented queues drained |
| CryptoKeygenMe1.exe | 128 | 8 | 57 | 0 | 12 | Implemented queues drained |

In total, the run stored **15,341 instruction interpretations**. Seven samples drained the implemented queues; `HideDebugger.dll` and `deroko-64-_.exe` stopped at the 5,000-attempt budget and deliberately remain partial. No second analysis call was used to make those results look complete. Issue records include pending code work and unresolved/invalid decode details; their counts are not a count of application defects and do not include every pending data task.

A drained static queue can still contain unresolved indirect flow, exception-directed control flow, packed/runtime-generated code and unvisited data. In particular, a small recovered stub or zero static imports does not establish that a protected executable has been unpacked. Function entries and pattern evidence remain candidates rather than proven boundaries.

## Additional public API checks

For each imported file, `locate` described the exact entry byte as stored code, and `function-patterns` returned bounded candidate evidence from stored instructions without a raw unexplored-byte scan. Every entry was also compared once through `decoder-check` using iced-x86 and Capstone. Both decoders accepted the entry bytes and agreed on instruction length in all nine cases; four texts matched and five differed in formatting/mnemonic spelling. No physical CPU was involved, and agreement does not establish execution or semantic equivalence.

`deroko-64.exe` produced native LIEF diagnostics about missing resource/exception sections, a failed resource tree and a debug payload at `0x000f000f`. Static import still succeeded. A separate-process inspection reproduced and captured those diagnostics in the JSON without repeating analysis. They are retained as qualifications, not silently discarded or repaired.

`CryptoKeygenMe1.exe` was already materialized from `CryptoKeygenMe#1.by.TiGa.zip`. The receipt retains both the archive URL/member identity and the extracted executable SHA-256. No archive extraction occurred during these checks. The downloaded `10nop.asm` is source text, not a substitute executable test.

## Provider-blocked fixtures

These three requested fixtures remain blocked exactly as recorded by the original Drive retrieval. They were not downloaded, parsed, executed or bypassed. Their binary hashes remain unknown.

| Fixture | Retrieval result |
| --- | --- |
| 10nop.exe | `Google Drive 403 cannotDownloadAbusiveFile` |
| HyperUnpackMe1/Notepad.exe | `Google Drive 403 cannotDownloadAbusiveFile` |
| IMA Files.zip | `Google Drive 403 cannotDownloadAbusiveFile` |

The inventory is a bounded selection from the user-requested `VM/Dropbox/AMA/Files` and `VM/Dropbox/IMA/Updated/Files` hierarchy, not a complete recursive Drive inventory. Download links and provenance are preserved in the receipt; no claim is made that every exercise or blocker has been recovered.

## Reproduce without execution

Use an original sample path outside the source directory and a scratch database. The following invokes static APIs only:

```bash
fdisbull identify /path/to/Test64.exe
fdisbull inspect /path/to/Test64.exe
fdisbull import /path/to/Test64.exe /scratch/Test64.fdb
fdisbull analyze /scratch/Test64.fdb --max-instructions 5000
fdisbull status /scratch/Test64.fdb
fdisbull issues /scratch/Test64.fdb --limit 10
```

Use the entry address returned by `status` for `locate`, and consult `fdisbull methods` for the available pattern/comparison request fields. Final integrated verification may rerun selected fixtures; it should be reported separately from this bounded working-source receipt.
