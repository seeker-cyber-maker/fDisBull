# Historical Linux dependency receipt

The 11 delivery checksum entries pass. The complete source ZIP and exact member
identities are recorded in [manifest.json](manifest.json); raw logs and receipts
remain private. [historical-report.md](historical-report.md) replaces the old
cloud workspace root with a provenance label.

The original dependency bundle is recorded as 50,475,916 bytes, SHA-256
`e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`.
The receipt describes an earlier Linux x86-64 / Python 3.13.5 no-index install
and dependency smoke checks. That bundle contains five third-party wheels,
no fDisBull/player application wheel and no native debugger backend. These
historical statements do not describe a new macOS installation.

`proposals/smoke_dependencies.py` is preserved inactive as an authored probe.
It specifically expects Linux ELF input and an environment without fDisBull
or its player. It was parsed but not executed in this intake. No dependency,
application, native backend or system installation was changed.
