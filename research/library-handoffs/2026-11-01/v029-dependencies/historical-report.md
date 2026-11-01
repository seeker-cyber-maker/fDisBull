# fDisBull v0.29 dependency-bundle intake

Verified and installed in an isolated sandbox environment on 2026-11-01.

## Outcome

The uploaded archive is the third-party dependency bundle, not the complete
fDisBull release. Its README explicitly excludes both application wheels.
It contains no native DOSBox backend. fDisBull v0.29 itself is NOT installed
in the new environment.

Archive: `fdisbull-0.29.0-linux-x86_64-dependencies.tar.gz`

- Size: 50,475,916 bytes.
- SHA-256: `e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`.
- Matches the publisher hash recorded in the earlier GitLab release intake.
  That comparison reused the earlier release metadata; GitLab was not queried
  again during this attachment intake.
- Nine internal SHA256SUMS entries match.
- Five wheel archives pass ZIP CRC/integrity inspection; all five match the
  manifest's exact size/hash/version.
- Archive members were checked for unsafe paths, duplicates and links before
  safe extraction. Only ordinary directories and files were admitted.

## Installation and checks

The bundled installer was read before use. It created a fresh isolated venv
under `original-linux-run`, using Linux x86-64 and
Python 3.13.5. Installation used only the supplied wheels, with `--no-index`
and `--require-hashes`. No dependencies were downloaded. The user machine and
the working Python environment were not upgraded or replaced.

| Package distribution | Version | Executed smoke check |
| --- | --- | --- |
| Capstone | 5.0.9 | Decode authored x86-16 MOV/ADD bytes |
| iced-x86 | 1.21.0 | Decode the same authored bytes |
| LIEF | 1.0.0 | Parse the host `/usr/bin/true` ELF, without execution |
| Pillow | 12.3.0 | Encode/decode an authored 2x2 PNG in memory |
| z3-solver | 5.3.2.0 | 8-bit commutative-add equivalence UNSAT query; deliberate difference SAT query |

All checks passed. `pip check` reported no broken requirements. The installer
also completed its own import and Z3 probes. These are dependency checks,
not original-CPU verification or full fDisBull release acceptance.

Version-reporting detail: Capstone distribution metadata says 5.0.9, while
its Python `__version__` string says 5.0.7. Both are recorded rather than
silently conflated. LIEF reports runtime build `1.0.0-d05b3499b` and Z3
reports 5.3.2; wheel distribution versions appear above.

## Remaining input

To install and qualify the full v0.29 tool and native debugger, the missing
file is `fdisbull-0.29.0-linux-x86_64-offline.tar.gz`. Its previously recorded
publisher SHA-256 is
`b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f`.

The dependency bundle does not need to be uploaded again. This delivery
contains only the new report, receipt, logs, probe and original bundle metadata;
it does not duplicate the 50 MB input, installed venv or third-party wheels.

## Reproduction of the functional probe

After installing the supplied dependencies into a compatible environment:

```sh
/path/to/dependency-venv/bin/python smoke_dependencies.py
```

The probe expects only dependencies in that fresh environment and checks that
fDisBull and its player are absent. No GitLab changes, new app installation,
native debugger run, game run or full repository test run was performed.
