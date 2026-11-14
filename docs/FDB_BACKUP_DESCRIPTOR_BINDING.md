# FDB backup descriptor binding (2026-11-14)

`capture_fdb` retains its four positional arguments and optional four-field
`expected_source_identity` admission. Snapshots remain disk-backed with a 2 GiB
bound; this change does not load whole databases into memory.

Two fresh, site-disabled Python children isolate SQLite's descriptor cache and
threads. The backup child proves the actual newly opened SQLite main descriptor
matches the inherited admitted source descriptor. Existing WAL/SHM files are
opened through the admitted parent directory descriptor without following
symlinks. A held source read transaction forces SQLite's sidecar opens; their
actual descriptors must match those admitted sidecars before copying. Missing,
new or unprovable sidecars fail closed. The same transaction and handles remain
held through the online backup, including committed WAL data.

Writable destination SQLite uses the inherited private snapshot's descriptor
alias, never its mutable staging pathname. A preliminary immutable read-only connection discovers unsupported alias
canonicalization before any writable SQLite connection. Both its actual main descriptor and
SQLite's retained alias filename must match before journal/page queries. Builds
that canonicalize that alias to an ordinary pathname are rejected. Exclusive
locking and journaling OFF apply only to this empty, disposable private snapshot.
After online backup, the writable connection closes without further queries.
A second fresh child uses an immutable read-only descriptor alias for integrity
and recursive reference extraction; held-file hashes bracket that scan. The live
source never uses immutable mode. No database header bytes are patched.

Publication creates exclusive hardlinks, retains each admitted write descriptor,
and verifies the published inode and bytes against that descriptor. Neither
success nor failure unlinks or removes pathname-selected staging/partial files.
Successful retained database names share one payload allocation through hardlinks.
Recovery may leave private stages/partials for explicit later inspection.

Focused authored regression coverage includes regular-file and parent-directory
A-to-B-to-A substitutions, WAL contamination, unrelated destination WAL deletion,
canonicalizing alias refusal, valid committed-WAL snapshots, source main/WAL
immutability, nested object closure, partial-manifest replacement and byte changes,
publication collisions, optional source identity binding, missing descriptor
proof, child deadlines, and the absence of pathname cleanup. All fixtures are
authored temporary data; no user database or live backup was exercised.

The preservation contract covers source/foreign main database and WAL content
and existing outputs. SQLite read transactions can update SHM reader marks; SHM
is a recomputable concurrency index, so byte-identical SHM is not claimed. The
implementation requires POSIX descriptor inheritance and a SQLite/VFS retaining
the descriptor alias; unsupported hosts fail closed rather than falling back to
writable staging paths. Native Windows support for this helper is not qualified.

Validation: `PYTHONPATH="$PWD/src" python3 -m pytest -q tests/test_fdb_backup.py
 tests/test_drive_library_sync.py tests/test_shutdown_receipts.py` (one command).
Local macOS authored fixtures: 65 passed, 1 expected unsupported-host-case skip. A separate measured Linux Python 3.12.3 /
SQLite 3.45.1 probe canonicalizes the alias; this private helper therefore refuses
there. Positive backup tests require measured alias support; admission/failure
tests and an explicit real-host unsupported refusal remain active. Hosted/native CI and release activation are
separate gates owned by their designated agents.
