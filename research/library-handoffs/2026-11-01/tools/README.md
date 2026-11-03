# Reviewed Library handoff utility

`handoff_bundle_checked.py` is the maintained derivative for new file-delivery
verification and packaging. The imported `../full-f001/tools/` files remain
unchanged historical source; do not use that older writer/verifier for new work.
[derivation.json](derivation.json) binds both versions and the reviewed tests.

The review fixes two defects: failed ZIP creation no longer deletes an uncertain
output pathname, and verification rejects a delta that reuses its parent ID even
when all checksums are internally consistent. Exclusive creation still refuses
an existing destination. A failed write may leave a partial file for explicit
review; use a fresh output path after failure. The utility never automatically
deletes an output, applies a delta, restores a tree or publishes an archive.

From the repository root, use an existing Python environment and an approved
private external scratch directory with sufficient admitted storage:

```sh
TMPDIR="$FD_RUN/tmp" PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q \
  research/library-handoffs/2026-11-01/tools/test_handoff_bundle_checked.py \
  research/library-handoffs/2026-11-01/full-f001/tools/test_handoff_bundle.py \
  -p no:cacheprovider --basetemp="$FD_RUN/tmp/library-utility"

python -B research/library-handoffs/2026-11-01/tools/handoff_bundle_checked.py \
  verify "$FD_PRIVATE_F001"
```

The CLI and manifest schemas match the imported utility. `delta` takes an exact
parent manifest and a current private directory, writes a new ZIP outside that
directory, and records additions/modifications/deletions. It does not perform
the deletions. `verify-delta` checks lineage, names, CRC, inventories and member
content identities; it is not an extractor or an archive sandbox. No target,
network, installation or game file is needed for the authored tests.

The two test modules exercise 36 tests and 16 subtests on macOS. The four new
regressions were first run against the imported implementation and demonstrated
competing-output deletion, replacement-output deletion, automatic partial-file
removal, and checksum-consistent parent-ID reuse. Both empty and changed forged
deltas are checked. The original 16-test suite remains an archive compatibility
check, not a recommendation to use the old implementation.
