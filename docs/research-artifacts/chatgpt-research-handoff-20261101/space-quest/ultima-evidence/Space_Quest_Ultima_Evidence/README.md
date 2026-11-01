# Reproducing the bounded static intake

The evidence contains authored scripts, operation metadata, hashes and aggregate
analysis results. It excludes original games, fonts, emulator state and project
databases. The summary is not proof of whole-game equivalence.

Python 3.11 or later with standard-library lzma and zlib is sufficient for the
static installer comparison. No Windows execution or external dependency is used.
The decoder is restricted to the three input hashes in summary.json. It is not
a general Inno parser and is not a hardened untrusted-archive service.

Place the three original installers in one directory and run from this folder:

    python tools/bootstrap_intake.py --input-dir /path/to/installers --output-dir /path/to/new-private-output

Use a new output directory and do not use Python -O. The output contains privately
extracted game assets; do not publish that tree. About 1 GB of temporary working
memory is a reasonable allowance because the full installer is read into memory.
The selected payload checksum checks and the 36-target comparison are reproduced.
Native fDisBull analysis counts in this delivery are retained measurements, not
reproduced by the extraction-only script; that requires the separate 0.22 offline
environment and the extracted files. No game execution occurred.

Parser-layout provenance: dscharrer/innoextract, files cited in REPORT.md. This
script is a separately authored narrow reader, not an upstream innoextract build.

SHA256SUMS binds the included evidence files. It establishes identity, not semantic
correctness, source authenticity or a digital signature.
