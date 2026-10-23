# Verification receipt — fDisBull 0.8.0

Final integrated `python -m pytest -q`: **695 passed**, exit 0, **50.64 seconds**.
`python -m compileall -q src/fdisbull` passed. Host: Linux x86-64, Python 3.12.14;
iced-x86 1.21.0, Capstone distribution 5.0.9, LIEF 1.0.0, Pillow 12.3.0.
No imported native/managed/game code was executed. Native macOS host execution
remains unverified.

## External snapshots and structured file views

New public workflows establish immutable file bytes, SHA-256/source metadata,
bounded raw reads, EOF behavior, version isolation and survival after input
changes/deletion/restart. Attachments never become native mappings or executable
seeds. Each identity is a version, file name and offset. Per-file and aggregate
attachment limits are checked atomically.

Nested structures, arrays, signed scalars and encoded pointers use the existing
type registry. Redefinition checks native and file bindings together, including
growth, overlap and file bounds. File views use compact layout descriptions and
bounded traversal. An independent nested-layout fixture exposed excessive
expanded output; the fixed one-item response is about 8.8 KB instead of 1.67 MB.

Authored source-to-file relationships retain exact instruction/CS identity,
fingerprints, evidence, access width and bounded strided spans. Tests cover x86,
ARM64 and DOS, separate same-offset files, exact interval overlap rather than
stride gaps, shared field renames in data/xrefs/disassembly/CFG/SVG, and unchanged
native facts/bytes. Inherited links become stale after source-byte changes and
await decoding after unchanged-byte reanalysis. A 128-reference single-row
fixture now renders with explicit preview/truncation instead of exceeding the
renderer text limit. CLI and JSON workflows exercise every new operation.

## Confirmed DOS pointer defect and repair

The prior LES/LDS transfer read immutable initial descriptor bytes as current
memory. On DinoPark, runtime allocation writes DS:BFC7/BFC9, but its initial
zeros had produced BX=0, ES=0 and false exact native references to 94h/98h.
The fix applies to both zero and nonzero descriptors: without reaching-value
proof the loaded offset and segment remain unknown. Raw instructions and the
descriptor-cell reference remain intact. Ordinary explicit constants, segments
and modeled stack propagation still work.

DOS pointer revision 2 marks fresh/rebuilt analysis. Legacy projects expose
stale status, hide obsolete native references/assumptions in raw disassembly and
reject dependent fact/graph/effect queries until explicit `refresh-dos-state`.
This bounded rebuild preserves bytes, versions, annotations, definitions, types,
external snapshots and authored file links; registered explicit roots are
re-admitted without their old register assumptions. Tests establish parent/child
isolation, restart and atomic rollback/retry after an injected analysis failure.
A plain `refresh-facts` cannot repair stale incoming register state and is
therefore guarded too. Native and derived queue status remain separate.

## Actual DinoPark qualification

An independent fresh copy of the retained original database was rebuilt in
`/tmp` in 40.37 seconds, including 67,046 native attempts. It retains **47,177
instructions and 652 candidate functions**, with **57,059 xrefs**, **12,232
operand references** and **32,729 memory facts**. Native pending work is zero;
all **652 derived jobs remain pending**. This is not whole-game semantic recovery.
SQLite `quick_check` passed after commit and after closing/reopening.

At `38ff:22DB` and `22E9`, stored state now retains DS=4020/SS=4D04 but does not
assert BX or ES. Their native operand-reference lists are empty; memory facts
have no concrete target and report unknown BX/ES. The LES instructions still
identify descriptor storage at physical 4C1C7. Native source/mapped fingerprints
are unchanged.

Actual `VARS.DAT` (364 bytes, SHA-256
`5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153`) and
`DINOSG.000` (4,153 bytes) were attached to that copy, typed and queried. All
91 parameter dwords are readable. Eight authored instruction/file relationships
survive a separate-process reopen after the import paths are deleted.
`examples/external-files-v08.json` records the values, native facts, fingerprints,
queue state and integrity result. PNG/SVG exports were generated; SVG parses
and the final PNG was visually inspected for correct labels and clipping.

The field audit corrected a report interpretation: file offsets 94h/98h contain
20/35, not the 1000 at 12Ch. The four additions at 10h/14h/18h/1Ch are
250/500/750/1250; the loop independently tests four flags, without proving gift
names or sequential tiers. The inspected use of 1250/1000/750/500 at 128h–134h
is not sufficient to label them four concession prices. See
`DINOPARK_RESOURCE_AUDIT.md` for exact sites, widths and qualified conclusions.

One earlier workspace working copy developed SQLite integrity errors between
qualification calls; the cause was not established. It is excluded from the
package. The fresh independent `/tmp` rebuild did not reproduce the failure,
passed integrity checks, and supplied the final receipts/exports. The canonical
bundled database was never modified: SHA-256
`2e8824f8d92df587f41104a63edf4992d656688119a39fa6816f00b2ef2358b9`.
It remains a historical legacy-pointer snapshot and requires the explicit repair
command before current DOS fact queries. No rebuilt duplicate large database is
bundled; the included data/layouts and commands reproduce attachment on it.

## Wheel and preserved platform behavior

`dist/fdisbull-0.8.0-py3-none-any.whl` SHA-256:
`e69969ebb68ccf4a3cbf0bad5bf91454b9fb8a0005706a411843be67f1778656`.
All **42** wheel Python modules exactly match source. Imported from the wheel
outside the source directory, new external snapshots, 91 typed VARS values,
authored xrefs, immutable patches, source-deletion restart and legacy DOS guard/
repair checks pass. The five ELF, Mach-O x86-64/ARM64 and PE/MZ selection workflows
also pass from the wheel. Receipts: `wheel-v08-external-check.json` and
`wheel-v08-platform-check.json`.

Schema 1–5 projects migrate to schema 6 without losing native versions or user
labels. Existing DOS computed facts need the separate pointer-policy repair.
No Swift game port, daily-tick reconstruction, runtime allocator/file-loader
model, debugger, decompiler or additional CPU mathematics is delivered. The
external links are authored evidence, not automatic runtime heap resolution.
Earlier platform/native evidence is retained in `VERIFICATION-0.7.md` and
`VERIFICATION-0.6.md`, with its original scope.
