# Historical Linux core/player installation receipt

> **Review status, November 3:** source identities and earlier tests, MR states,
> uploads and installation statements below are November 1 intake records.
> Read the [current review](../REVIEW_2026-11-03.md) for superseding findings and checks.
> Historical upload receipts do not verify present remote availability or privacy.

The complete archive is retained privately; its identity and all member hashes
are in [manifest.json](manifest.json). Its 40 internal checksum entries pass.
[historical-report.md](historical-report.md) is a derived report copy whose old
cloud installation root has been replaced with `original-linux-run`.

The source report describes an isolated Linux x86-64 / Python 3.13.5 installation,
80 installed-module console tests and authored static/player smoke checks.
Those are reported historical results. This intake installs nothing and does
not repeat the reported Linux tests or qualify an installation on this Mac.

The two bundled wheels were rebuilt locally by that historical agent. Their
archive hashes differ from the published GitLab wheels. They remain separate
private artifacts and must not replace the canonical release files. Fresh
byte comparisons confirm all 191 core and nine player package source files
match the exact v0.29.0 tag; this is narrower than wheel archive identity or
runtime qualification. See [wheel-comparison.json](wheel-comparison.json).

`proposals/intake_smoke.py` is selected authored source, preserved inactive.
It creates authored fixtures and invokes an already installed tool/player;
it is not an installer. It expects a compatible Linux environment and declared
dependencies. It was parsed but not executed during this intake. The bundled
console test file already matches the main repository test and is not duplicated.
Wheels, installation logs and generated smoke outputs remain in the private ZIP.
