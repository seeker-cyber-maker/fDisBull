# DinoPark caller and filename-producer follow-up

This follows the [172/201/13 residual review](VERIFICATION-DINOPARK-RESIDUAL-ANALYSIS-2026-10-31.md).
It investigates the 159 entries without qualified positive evidence and all 13
resource candidates. Original code, media, databases and raw runtime receipts
remain private. Source under investigation is
`51d0bef4b3954ce85a3acea283c7462c53ff0589`; the native backend is unchanged.

## Why the earlier static inventory missed used entries

The previous label described absence of a stored incoming reference, not
absence of execution. The earlier native probe established exact PC arrival
but retained neither stack bytes nor the transfer leading there. That was
enough to disprove an unused-code interpretation, but insufficient to name
the actual caller. The reference review should have followed mutable callback
slots and near dispatch tables before treating the incoming-reference inventory
as exhaustive.

The source explains a specific gap. `_dos_store_seed` in
[dos_analysis.py](../src/fdisbull/dos_analysis.py) collects literal stores by
destination and admits a paired pointer only when there is exactly one distinct
immediate offset and one relocated segment. It also requires an established
code-segment candidate. The relevant reused slots all fail the uniqueness
condition. For example, one scene slot has 22 distinct offsets and 10 segment
values across the stored analysis. These values cannot safely be combined as a
Cartesian product; the correlation between each setter's two stores matters.

The indirect-call rule can also read an initial file-backed pointer under a
known segment state. It does not supply a path-qualified reaching definition
for a mutable slot that the game fills later. None of the original 201
candidate address/CS pairs has a matching DOS seed record. Reopening the
database or completing all queued passes does not add these missing rules.

The 41 previously observed PCs divide into the following static mechanisms:

| Missing relationship | Entries |
|---|---:|
| Separate literal stores publish a far callback; a later instruction calls through the slot | 31 |
| Root descriptor table and active list lead to indexed near calls in the memory backend | 4 |
| Ordered initializer records supply near/far startup callbacks | 3 |
| DOS vector publication supplies asynchronous interrupt callback candidates | 2 |
| A code offset is loaded into a register and passed on the stack | 1 |

This classification identifies their static producer mechanisms. It does not
retroactively turn an old PC-only receipt into a recorded caller transfer.
The new native probe captures stack and pointer bytes for that purpose.

## The remaining 159 entries

The new pass recovers 89 consecutive two-store records for 77 targets in the
original 201-entry comparison set. Both stores have DS=4020 in the retained
segment-state model. Among these targets, **46 are from the remaining 159**.
Forty-five have matching indirect consumer sites; one currently has a publisher
but no recovered consumer. The records include reused scene slots and a
separate hardware/rendering interface. Their individual source instructions,
target bytes, slot identities and assumptions remain in the private ledger.

Twenty-five complete contiguous setter blocks populate the same six scene
slots. These provide a useful scene-lifecycle reconstruction boundary for UDL:
setter, pointer slot, indirect dispatch, target, then separately qualified
effects. The slots are not assigned user-facing semantic names merely from
their offsets.

A second chain starts at the memory backend's four descriptor roots. Each
descriptor contains five near offsets, interpreted in the caller's CS. The
original code selects descriptors, populates an active list and dispatches
through fields of those descriptors. This accounts for **16 additional entries
from the remaining 159**, plus four previously observed entries. The families
are consistent with EMS, disk-backed, XMS and INT15 extended-memory operations;
their conditional selection is separate from native invocation.

| Disposition of the requested 159 | Count |
|---|---:|
| Producer and matching static dispatch consumer recovered | 61 |
| Producer recovered; consumer still unresolved | 1 |
| Caller/producer still unresolved after the declared searches | 97 |

Together with the prior 42 positive entries, this gives 104 of the original
201 with PC-arrival or publication/reference evidence. It does not mean 104
runtime-qualified routines: none of the requested 159 was reached in the new
native routes.

The last 97 each retain an individual record. Sixty-one are in the early
runtime/audio segment, a coarse role inference rather than a recovered function
name. Twenty-five bodies contain conditional named DOS/BIOS/audio services.
For 46 entries, even the exact near-offset word is absent from the mapped image.
That is a useful negative search result, but computed addresses, aliases and
external/runtime input remain outside that exclusion.

The pass compared stored direct targets, raw far-pointer shapes, offset-bearing
MOV/PUSH instructions, both alignments of possible near tables and raw relative
branch candidates. A further scan correlated nearby register-valued absolute
stores under known segment/register facts and found no additional publication
for the 97. No new qualified direct caller emerged from the raw branch scan.
A repeated small integer in a possible table remains a hypothesis without
a consuming code path. These searches do not certify the 97 entries dead.

Publications and potential consumers are not inserted as unconditional direct
call edges. A setter may be conditional, a later setter may overwrite the slot,
and a backend may never be selected in the tested environment. The per-entry
records preserve those distinctions.

## Filename producers for the 13 resource candidates

The follow-up goes beyond searching for candidate names. Luna traced the
arguments at all 17 stored callers of the shared file-opening wrapper and
followed the relevant helper callers into literal strings, tables, formatters
and forwarded arguments.

The generic binary opener has 36 direct caller sites: 35 push fixed ABT
filename pointers, and one iterates an eight-record filename table. The latter
loop's immediate comparison against eight qualifies the row count. An earlier
draft mistakenly borrowed the preceding employee-loop count; the private audit
retains the correction. A separate music route supplies six XMI filenames.
These are producer domains, not claims that every caller ran.

The actor parser has 28 direct caller sites: 24 use fixed filename literals,
one formats `plants%d.act`, one indexes a six-row employee table, one consumes
a structured far pointer with unresolved origin, and one forwards filename
arguments recursively. The plants formatter's literal family cannot produce
the three candidate ACT names, but the unresolved structured-pointer and
forwarding paths prevent a global exclusion.

| Candidate group | Recovered chain and limit |
|---|---|
| BUS.ACT, OFFICE.ACT, PEOPLE.ACT | No producer for these names in the recovered fixed ACT arguments, employee rows or plants format family. Structured-pointer and forwarding origins remain open. OFFICE.PIC is a different asset. |
| Eight ABT candidates | No matching candidate name in the recovered fixed ABT arguments or eight-row table. Successful use is not inferred from valid decoded audio, and other entry paths remain possible. |
| MECC.PIC | Thirty display-helper callers resolve through 27 literal PIC arguments, two local pens.pic pointers and one global pointer. Four recovered global-pointer writers name sizes.pic, recons.pic, ages.pic and types.pic. None names MECC.PIC; other loader paths remain outside this exclusion. |
| SBP1FM.ADV | Byte-identical to MIDPAK.ADV. The configuration route's observed SBPFM.ADV is a different filename. Neither proves this alias was selected. |

The eight sounds are CLICK11.ABT, DINO1.ABT, EARSQK.ABT, NEONA1.ABT,
NEONB1.ABT, RICOCHE2.ABT, SQUEAK.ABT and TING1.ABT. Case-normalized
comparison is used without conflating similarly named files.

One useful neighboring relationship is narrower than a loader alias:
RICOCHE2.ABT and RICOCHE3.ABT have the same decoded PCM hash, but declare
11 kHz and 16 kHz respectively. A recovered caller names RICOCHE3.ABT. That
does not establish a call to RICOCHE2.ABT or identical playback behavior.

## Native verification and limitations

Luna independently checked all 201 entry prefixes, the 178 instructions in
the 89 split-store pairs and the 20 near descriptor words against the original
MZ file, relocation records and retained native facts. The source and mapped
image identities remain separate.

The first accepted fresh context reached office, bank and street. It recorded
24 exact candidate PCs, all previously observed; 23 have stored CALL/stack-return
matches, 15 also correlate with live far slots and four with live near-table
cells. Parent readback required the slot's segment and offset to match the
actual runtime CS:IP, rather than accepting a static segment alias. The clock
callback has no normal CALL match in this capture; its invocation origin stays
unknown. These are bounded transfer correlations under the normal ABI, not
function-effect or universal call-graph proofs.

That route omitted the land prerequisite. Four business routes correctly
rejected entry with confirmed no effects. The native run therefore does not
qualify seven-location access. It captured 37 shared-open-wrapper entries,
28 distinct successful DOS opens and the DINO.CFG constructor buffer. Provider
readiness took 102.624 seconds; the context closed with native return code zero
and unchanged original files.

The broader fresh route purchased the desert plot through the ordinary Z action:
cash changed from $5,000 to $4,500 and the canonical receipt records
`applied-confirmed`. The subsequent DinoMart transition returned `incomplete`
with unknown effects after a `Scene operation timeout`. It was not replayed.
DinoMart ACT/PIC opens and reads are positive resource-use evidence, but do not
certify scene readiness. Later locations and the encyclopedia action were not
executed. The timeout occurred with observation hooks active; their causal role
has not been isolated.

That broader route captured 29 candidate PCs, all in the prior observed 41:
28 have a matching stored CALL return, 20 correlate with live far slots, and
four with live near-table cells. Parent independently reconciled the raw
segment/offset bytes. Its union with the first accepted route is still 29,
with zero new PC witnesses among the requested 159. The 62 new static records
were independently checked against original code and data, not promoted to
runtime invocation.

The broader run reached eight producer sites and 63 shared-open-wrapper entries,
with 44 distinct successful DOS-open/read names and 1,251,866 bytes read.
RICOCHE3.ABT, DINOMART.ACT and DINOMART.PIC are among the positive inputs.
None of the 13 candidate filenames was observed opened or read in either new
route. Provider readiness took 101.488 seconds and total elapsed time was
181.940 seconds. Native cleanup returned zero and all 192 original-folder
files remained unchanged. Driver exit zero is not action completion: the final
service receipt correctly remains recovery-required for the held transition.

Two earlier launches stopped during private probe setup, before any public
player request: a missing import, then a byte guard ending halfway through a
relocation word. Their native cleanup receipts report zero exit codes. These
are probe failures, not demonstrated emulator crashes. Three guard windows
were expanded to retain the whole relocation field. Parent independently
compared all 221 candidate/producer/return windows against full original MZ
relocation at three load segments: 663 matches, no partial spans or mismatches.
The accepted run also checked 221/221 actual runtime windows before installing
observer breakpoints. Synthetic preflight is kept separate from native evidence.

## Implementation follow-ups

1. Retain typed code-pointer publication records for locally correlated stores,
   including each half's source, DS assumption and byte version. Preserve
   distinct setter alternatives; do not form arbitrary cross-path pairs.
2. Connect publications to indirect consumers as conditional relationships.
   Keep snapshot pointers, reaching definitions and runtime-observed transfers
   distinct. Expose the actual scope of a stable analysis in coverage reports.
3. Represent near-pointer descriptor fields with explicit implied CS, data DS,
   field width/stride, root selection and active-list mutation.
4. At native entry observations, retain bounded stack bytes, matching original
   CALL facts and live slot/table contents. Separate interrupt frames and tail
   transfers from normal call-return matches.
5. Propagate filename arguments across helper calls into literal/table/format
   producers. Keep unresolved structured input explicit instead of reporting
   a zero resolved-argument count as a completed producer trace.
6. Share a canonical expected-runtime-byte-window helper that owns whole
   relocation fields, including overlap at a requested window boundary. UDL/UDC
   snippet identity must retain that ownership. The private guard failure did
   not demonstrate a defect in the existing full-image MZ loader.
7. Retain the provider and its observation/reconciliation options when an
   instrumented batch holds a transition. This private driver closed the
   context on hold; a completed file read is not an authorization to retry the
   navigation or assume its destination. Diagnose the scene timeout separately
   from transport startup and observer setup failures.
8. Preserve exact-name, basename-substring and file-inventory provenance as
   distinct evidence types. A draft MECC.PIC literal claim conflated a basename
   hit with a full filename; the independent original-byte audit corrected it.
   The matching EXE bytes are MECC.ACT, and all 13 exact candidate filenames
   are absent from that executable. Computed-name paths still require tracing.

The new private database retains 62 scoped publication/reference comments and
preserves all 101 earlier comments. Its 75,950 native instruction facts and
original byte version are unchanged; reopening and database integrity were
checked. No unconditional direct call edge was injected. Parent also checked
the filename ledgers' source instruction bytes and DS strings. This follow-up
changes documentation and private evidence, with production code unchanged
from the previously tested implementation pin; it does not claim a new full
test-suite run.

These are qualification requirements and implementation recommendations. This
follow-up does not claim they are a newly shipped analyzer feature. Existing
analysis/convergence fixes remain in PR #41. No packaging, installation,
backend build, release or activation is part of this work; sound stays off.
