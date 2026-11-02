# Shipped v0.26 LE loader audit

## Verdict

The supported flat LE object/fixup mapping is instrumented, but its output is not a complete original-file accounting. Original source bytes are retained. Retention does not establish classification or validity of every referenced structure.

The authoritative source audited was the installed package under /workspace/scratch/ef022eef338f/fdisbull-runtime/env/lib/python3.13/site-packages/fdisbull. The fixture uses authored data only. No production source, tests, configuration, dependencies or game bytes were modified; no guest was launched.

## Material findings

1. **Physical storage and mapped source sizes differ.** le.py at lines 179 and 182 reads physical_size and maps min(object capacity, physical_size). Physical page suffixes outside capacity are retained only in source_bytes. Page records do not expose physical_size. file_backed_size is a sum of mapped object contributions, not necessarily a union of distinct file ranges.
2. **Optional table extents are not validated.** le.py line 80 unpacks header scalars; checks beginning at line 101 cover selected object/page/fixup tables. The fixture probe set each resident-name, entry-table, resource-table, module-directive, debug-data, nonresident-name, loader-size or page-checksum extent to 0xFFFFFFF0. Resource/directive count was 1 and debug/nonresident size was 16 where relevant. All eight variants of the 4,500-byte fixture were accepted by load_le and inspect_binary with empty warnings. This is a whole-container inspection blind spot, not evidence of a malformed game file.
3. **Twenty fixed-header bytes are unnamed.** HEADER_SIZE is 196 (0xC4), but 41 DWORDs are unpacked starting at 0x0C, ending at 0xB0. Bytes 0xB0 through 0xC3 are retained but not named or interpreted.
4. **Unparsed does not mean absent.** inspection.py line 304 initializes imports/exports to empty lists. Its LE branch never parses the entry/name tables, so exports=[] is not proof that the file has no exported entries. le.py line 330 provides one declared/overridden entry seed, not entry-table seeds.
5. **Fixup-section remainder is opaque.** The declared section extent and page-offset bounds are checked, but bytes between the page-offset table and record table, and after the final referenced record before section end, need an independent physical-range classification.
6. **Standalone relocation previews are capped.** inspection.py line 329 returns at most 10,000 fixups and warns when capped. The original main has 10,060 records. Full loader metadata and project pagination retain all supported records.

The iterated-data map, resource/name/entry/directive tables, unused import-name references, page checksums, nonresident names, debug data and checksum semantics are recorded as scalars rather than parsed. Preload/demand/automatic-data-object fields are not a recovered native loading policy.

## Existing strengths

The exact source container is distinct from the pre-fixup object image and relocated image. Fixup evidence preserves actual file fragments and virtual zero fill, including noncontiguous page-crossing words and BSS. Identical duplicate writes retain separate records while applying once; conflicting overlaps fail. Object bounds, selected structural overlaps, entry/file-backed requirements and unsupported fixup/page kinds are checked. Project status trimming does not discard stored metadata.

## Syndicate physical-accounting lead

Prior MAIN.EXE metadata yields 104*4096 + 3641 = 429625 physical page bytes, compared with 429101 mapped source bytes. The 524-byte difference equals object 1's 262144-byte page storage minus its 261620-byte virtual size. Complete arithmetic is 89088 prefix bytes + 429101 mapped source bytes + 524 page-capacity suffix bytes = 518713. This arithmetic alone does not classify the suffix contents as padding.

## Required ledger and invariants

Partition the physical file into MZ structures/load image, pre-LE gap, fixed LE header, all referenced tables, fixup streams/remainder, alignment gaps, unique physical page payloads, capacity suffixes, optional debug/nonresident extents and residual unexplained ranges. Keep virtual BSS separate. Every interval needs parsed, declared-but-opaque, padding-candidate or unexplained status. The union must equal [0,file_size), with overlaps explained. Reconstruct pre-fixup bytes independently, then apply unique writes and compare the mapped image. Complete structural scoping does not prove runtime reachability or recovered game meaning.

## Reproduction

fixture-probe.py contains the in-memory authored fixture and mutation probe. fixture-probe-results.json preserves the observed results from its original execution in this audit. Run the script with the selected installed fDisBull Python to reproduce. The script writes only JSON to stdout.
