# Verification receipt — fDisBull 0.8.1

Final integrated `python -m pytest -q -rs`: **716 passed**, exit 0, **51.67 seconds**.
`python -m compileall -q src/fdisbull` passed. Linux x86-64, Python 3.12;
iced-x86 1.21.0, Capstone 5.0.9, LIEF 1.0.0, Pillow 12.3.0.
The original DinoPark executable fixture was restored from the existing corpus;
there are no skipped tests in the final run. No imported program was executed.
Native macOS host execution remains unverified.

## Bidirectional labels

The 21 new shared-label integration and transaction tests pass independently.
They exercise explicit file→file→memory range correspondences on x86, ARM64
and DOS; interior fields; file and native rename directions; untyped files;
canonical names alongside structural paths; operand references, native xrefs,
CFG, memory-access queries, SVG and PNG; source deletion and separate-process
restart; schema 6→7 migration; DOS physical aliases; conflicting names and offset
cycles; stale instruction relationships; and parent/child version isolation.

Stored, current call-effect results resolve current target/call-site/callee
labels without another derived-analysis pass or a generation change. Verified
`memset` contracts retain their semantic summary identity while display names
change. Stale cached function-analysis documents remain historical raw results,
explicitly marked stale; the current envelope name remains query-time metadata.

A focused regression first demonstrated that a failed merge could survive when
caught inside an enclosing caller transaction. Shared-label writes now use a
savepoint; both ordinary and nested-transaction conflict/cycle failures roll
back without partially merging identities. Whole-block links check conflicting
names on interior fields as well as the starting field.

Existing unlinked native root renames retain their structural-root behavior.
For a linked first field, native rename changes the shared field name without
renaming the enclosing structure or neighboring fields. Decoded bytes, numeric
operands, original evidence and native control/data edges remain intact.

## Actual DinoPark example

`examples/shared-labels-v081.json` records a qualification on a fresh `/tmp`
copy of the historical bundled database. The original database hash remained
unchanged and SQLite `quick_check` passed. An explicitly authored eight-byte
correspondence connects save offset 3872 in two independently named attachments
to `4020:6fa6`. A file-side `food_count` rename and native-side
`restroom_count` rename resolve across the chain, typed native/file fields,
authored source relationships, and exported code images. Separate-process
restart retained both labels. `examples/dinopark-shared-labels.svg/.png` show the
real instruction supplying DS:6FA6 to the eight-byte reset call.

This qualification does not claim new loader recovery: the save/runtime
correspondence is user-reported evidence and DS=4020 is an explicit condition.
The historical corpus retains its obsolete native-facts warning; its raw code
and authored annotations are usable, while dependent native facts still need
`refresh-dos-state`. No gameplay meaning follows from sharing a label.

## Wheel and package

The built 0.8.1 wheel contains all **43 Python source modules**, byte-for-byte
identical to the final source. It was extracted into a separate directory and
imported there, outside the checkout. All **21 new tests passed in 4.04 seconds**
against that wheel, including a separate-process restart with the wheel import
path. The complete public generic CLI example in EXTERNAL_FILES.md produced
18 successful responses and demonstrated reverse rename propagation.

The package includes the current wheel, source, tests, docs, retained examples,
and the new label receipts and images. Build caches, generated egg metadata,
older wheels and earlier manifests are excluded; its manifest is regenerated
and every packaged hash and ZIP CRC is verified. Historical 0.8.0 verification
is preserved in `VERIFICATION-0.8.md`.

## Limits

Shared links are authored correspondences, not recovered I/O, pointer values,
runtime observations, value equality or new native xrefs. Names are resolved
from shared identity rather than replacing text in stored evidence. Explicit
renames override structural fallbacks for that instance, without changing type
definitions or unrelated instances. Child versions inherit these interpretations
and require evidence review after behavioral changes.

Links are bounded to 1 MiB each, 4096 per version and 256 corresponding byte
locations per component. Validation rejects contradictory offset cycles and
budget exhaustion rather than returning a partial name resolution. The existing
little-endian type interpretations and decoder/semantic limitations remain.
