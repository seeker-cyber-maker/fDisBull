# Verification receipt — fDisBull 0.8.2

Final integrated `python -m pytest -q -rs`: **744 passed**, exit 0, **65.87 seconds**.
`python -m compileall -q src/fdisbull` passed. Linux x86-64, Python 3.12,
iced-x86 1.21.0, Capstone 5.0.9, LIEF 1.0.0, Pillow 12.3.0.
No imported program was executed. Native macOS host execution remains unverified.

## Correcting mistaken shared-label links

The 0.8.1 API allowed creating a link but exposed no inventory or removal
operation. The new `label-links` command lists stable IDs, endpoint ranges,
original evidence/authorship and optional removal history. `unlink-labels`
records a version-local removal containing reason, author and timestamp while
preserving the original edge. Removed edges are excluded from name resolution,
duplicate detection and prospective offset/conflict validation.

The 28 new public integration cases passed independently in 3.80 seconds.
They cover x86, ARM64 and MZ views; typed/native references, xrefs, CFG,
memory-access names, SVG and PNG; range/interior-field splitting; native
annotations and independent instruction-to-file relationships; alternate
paths; removal retries without rewriting the original audit; new IDs when
relinking; paginated inventories; invalid requests; schema 7→8 migration;
source deletion, separate-process restart and SQLite integrity; and isolated
parent/child retractions inherited by later versions.

Two failure injections establish atomic rollback inside a caller-owned outer
transaction: a rejected insert and an exception after the removal was inserted.
Both preserve the original graph and permit a subsequent successful retry.
Native facts, bytes, versions, attachments and instruction file references
remain unchanged by unlinking. The rendered regression shows a detached native
reference reverting to its local structural name while the independently
attached file-field annotation retains its own label.

## Actual DinoPark qualification

On a fresh copy of the previous label-qualified DinoPark database, a deliberate
wrong mapping joined save offset 3872 to physical `0x390f6`, while the existing
valid chain still reached `4020:6fa6` (`0x471a6`). Removing only the wrong edge
made that endpoint lose the propagated name, kept both existing valid links
unchanged, and retained food_stands/rest_rooms/gift_stands/parking_lots at all
four save fields. Restart and SQLite `quick_check` passed.
`examples/unlink-labels-v082.json` contains the before/after receipt, current
inventory and retained removal history. This exercises authored label repair,
not new runtime observations or loader inference. The original bundled corpus
was not modified; its historical DOS native facts still require the documented
state refresh before dependent analysis queries.

## Wheel and documented workflow

The built 0.8.2 wheel contains all **43 Python source modules**, byte-for-byte
identical to the final source. Outside the checkout, all **49 shared-label,
transaction and unlink tests passed in 8.45 seconds** against extracted wheel
modules. The separate-process restart tests also imported those wheel modules.
The generic documented CLI setup, link inventory, reviewed-ID removal and
active/historical inventory workflow completed successfully.

The release includes current source/tests/docs, the current wheel, prior
examples and new correction receipts. Its manifest is regenerated; ZIP CRC and
every packaged hash are verified. Earlier verification is retained in
`VERIFICATION-0.8.1.md` and the preceding historical receipts.

## Interpretation limits

Removal retracts one entire range edge. An alternate active path can still
connect the starting endpoints; `still_connected` explicitly has
`connectivity_scope: starting_endpoints`, not a whole-range reachability claim.
Interior fields can be checked independently with `label-info`.

Removal is not a rename undo. Existing shared names have a stored canonical
anchor, exposed by `label_info.label_anchor`, but their historical rename origin
was not retained. That marker remains at its anchor; detached endpoints resolve
remaining links, independently authored native annotations and structural
fallbacks. Names are never copied into every detached component, and authored
annotations are not silently deleted. Before/after receipts show the actual
outcome. Removed IDs remain historical, are never reused, and count toward the
existing 4096 retained-link limit. Links remain authored correspondences rather
than runtime I/O, byte equality, pointer facts or new native xrefs.
