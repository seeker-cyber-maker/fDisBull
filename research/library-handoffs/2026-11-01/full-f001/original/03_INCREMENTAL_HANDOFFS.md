# Full baseline now, partial packages afterward

Baseline ID: `SYNDICATE-F001-20261101`.

Keep the extracted F001 folder unchanged and work on a copy. A future delta
contains only added or changed payload files, a list of deleted paths for review,
and an exact resulting file manifest. It names its parent by both ID and manifest
SHA-256. Files omitted from a delta remain inherited, not missing.

## Verify this full handoff

```sh
python3 -B tools/handoff_bundle.py verify .
```

## Create a partial handoff from a working copy

Run from the preserved F001 directory; replace the example work/output paths:

```sh
python3 -B tools/handoff_bundle.py delta   --base-manifest MANIFEST.json   --current ../Syndicate-working   --output ../fDisBull_Syndicate_DELTA_D001.zip   --id SYNDICATE-D001-20261101
```

## Verify a received delta

```sh
python3 -B tools/handoff_bundle.py verify-delta   ../fDisBull_Syndicate_DELTA_D001.zip   --base-manifest MANIFEST.json
```

The ZIP includes `DELTA.json`, `RESULT_MANIFEST.json`, `SHA256SUMS`, and changed
files under `payload/`. The tool refuses a wrong parent, changed payload hashes,
unsafe paths, duplicate entries and destination overwrite. It neither applies
changes nor deletes files automatically. Review changes in a copy, preserve the
previous baseline, and use the resulting manifest as the next parent.

A subsequent partial delivery should state its parent and list added/changed/
deleted counts. It should not resend all historical ZIPs. An empty delta has no
payload and is not proof of additional investigation. No empty D001 is supplied
with F001: it would add confusion, not information.

This packaging convention is independent of GitLab status. Each later handoff
must also record whether its files are local, on a branch, in a review, or merged.
