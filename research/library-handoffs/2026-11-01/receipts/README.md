# Standalone Library receipts and report alias

> **Review status, November 3:** source identities and earlier tests, MR states,
> uploads and installation statements below are November 1 intake records.
> Read the [current review](../REVIEW_2026-11-03.md) for superseding findings and checks.
> Historical upload receipts do not verify present remote availability or privacy.

The two exact F001 receipt files are preserved here, with their Library URLs,
original/new hashes and independent archive binding in [manifest.json](manifest.json).
Both identify the 2,656,225-byte F001 ZIP with SHA-256
`53c85cb2ac29f7986cbee35c83ed059d34bebc92c8258756fb50fe49df63b8c9`.
That agrees with the independently read archive and private upload receipt.
Neither receipt contains private host paths or credential tokens.

The JSON receipt reports an earlier 63-test direct player-source/authored-scene
check. That reported result was not rerun during this intake and is explicitly
source-only, without native execution or release-package installation. Fresh
intake checks are recorded separately in the parent verification receipt.

The standalone `REPORT(10).md` is byte-identical to `REPORT.md` inside the
privately retained core-installation archive. It contains historical cloud
paths and is represented as an archive-member alias rather than copied into Git.
The selected [sanitized report](../v029-core/historical-report.md) retains its
substance with the earlier workspace root replaced by a provenance label.
No additional private upload is needed for any of these three files.
