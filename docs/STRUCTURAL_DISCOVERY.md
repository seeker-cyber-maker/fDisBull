# Cross-game structural discovery pilot

Date: 2026-11-07. Original-input static analysis and authored tests; no original-game execution.

## Executive result

One directory-scanning command produced useful investigation candidates from all
five supplied targets without a game name, known field offsets, record strides,
item IDs or per-title algorithm switches. Four connected graph patterns are
shared by format/processor fact producers. Two generic data heuristics add
record and pointer-table candidates. These are a read-only shortlist, not
complete schemas, recovered game mechanics or executable scenes.

The shared pass is integrated into a private source candidate and its CLI/JSON
method dispatch. It is not in a published release and has not been posted to
GitLab. The source-only patch includes maintained investigation guidance.

## Exact scope and provenance

Base: the supplied 0.32.0 candidate offline kit, whose source revision is
`c80bff03e4cd2b946a93e7aecab61e5ff9281f81`. This is different from historical
main `242e5343` and the !82 research branch `b57f51d5`. No claim of automatic
integration with either branch is made. Preserve their distinct implementation
and review ownership during integration. Existing !82 record/serializer work
was reviewed as related work; it was not copied into or merged with this pass.

Original game inputs came only from the user's five uploads. Existing
`gog_unpack.unpack_gog` used the supplied **innoextract 1.9** executable to
extract four GOG packages. The pending homemade Inno reader was not used.
The Hitchhiker ZIP was extracted with bounded safe paths. No installer was run.
Private extracted roots contain the original files and extraction receipts.
Input hashes and source-module identities are in the accompanying evidence.

## Same-default results

| Input | Admitted files | Detailed candidates | Compact lead families | Median of 3 scans |
| --- | ---: | ---: | ---: | ---: |
| Police Quest 1 package | 217 | 2267 | 5 | 1.290 s |
| Hitchhiker's Guide | 2 | 61 | 4 | 0.134 s |
| Ultima IV | 276 | 59 | 2 | 0.825 s |
| UFO Defense | 930 | 399 | 3 | 3.139 s |
| Terror from the Deep | 1284 | 282 | 3 | 2.979 s |

Every target's three reports are byte-identical. Timing is one host, three warm
in-process repetitions, not a cold-agent benchmark or broad performance study.
It excludes extraction, report serialization/write, tests, model inference and
manual interpretation. Known-size budgets intentionally skip large wrappers,
media and additional executables. File counts are admitted files, not a claim
that all are gameplay resources. Full coverage, skips and diagnostics remain in
the private JSON. No model or OCR calls occur in the scan.

Across the corpus there are **3,068 candidates**, grouped into two to five
avenues per input. Counts are pattern instances, not unique mechanics or
validated game objects. Native findings include runtime/interpreter/support
utilities; the source path remains attached so an agent can choose the correct
layer. Each compact installed CLI reply was 1.9-3.5 KB. Exact drilldown is paged;
the larger details remain in the private report rather than the default reply.

## Police Quest 1: vocabulary becomes a path into code

The supplied package contains both SCI resources and an EGA/AGI directory.
Discovery identified the AGI resource set rather than assuming the installer
version described a single engine. Existing readers decoded **118 logics,
26,105 instructions, 1,126 vocabulary entries in 358 groups, and 3,147 said
condition sites**. The scene census also retains 25 inventory objects and 42
scene candidates, with scene recovery explicitly incomplete.

The new matcher joins dictionary-backed conditions to short guarded effects:
**1,817 condition/effect pairs**, plus **377 same-entity test/mutation pairs**.
These are not 1,817 distinct accepted English commands. NOT/OR, additional
conditions, reachability, input claiming and room context remain attached.

A generic shape-based verification script selected three scalar source slices.
For each, all 256 values of its predicate byte were evaluated using the existing
bounded AGI source evaluator and separately executed through the existing UIL
scalar lifter. **768 comparisons, zero mismatches.** Each admitted slice includes
both branch outcomes. This is selected-source logic under authored states, not
native interpreter equivalence or whole-program lifting. The two paths share
underlying source/layout infrastructure, so this is not a wholly independent
parser oracle.

For one actual said-only guard, the matching group sets its selected flag and
claims the pending input. A wrong group, input-not-ready and already-consumed
input do not set that flag. The scalar lifter refuses the parser predicate with
`unsupported condition; runtime/parser predicates are not scalar facts`.
That is a useful, correct capability boundary, not full parser-lifter success.
Three other source slice candidates were refused because their boundaries were
not established by the stricter lifter path; these refusals are preserved.

Next avenue: qualify parser-aware lowering and composed preconditions, rather
than importing the dictionary as a list of always-available verbs. The SCI
portion was not semantically decoded; its large resource file exceeds the
initial scan budget. AGI 2.917 is an analysis profile, not a newly proven exact
version of the bundled interpreter.

## Hitchhiker's: an engine-family difference caught at intake

The uploaded story is **Z-machine version 5**, not version 3. The new bounded
format producer validates the header/checksum and reads **1,019 dictionary
entries**. Its candidate contiguous object directory contains **236 records**,
with property bounds, ordering and link/parent checks passing for this input.
The count is inferred from directory closure at the earliest property table;
it is not stored as an explicit header count, nor are all objects rooms/items.
The declared story extent is 158,412 bytes with one trailing source byte.

A bounded core-layout walk reached **2,358 instruction candidates** and retained
**8 indirect calls unresolved**. It produced **49 attribute-test/branch
matches** using the same read -> mask -> branch rule as native code. The bundled
DOS interpreter contributes another 9 native mask candidates and one pointer
label table; those are separate from the story's own semantics.

Next avenue: follow dictionary metadata/parse-buffer consumers, then selected
object attributes and property handlers. Vocabulary metadata remains opaque.
No new registered Z5 processor, VM execution engine or Z5 semantic lifter is
claimed. Extended opcodes, custom alphabets and other unsupported forms retain
explicit limits rather than silent v3 fallback.

## Ultima IV: pointer tables and bit use, not invented item stats

The scan found and validated a bounded embedded EXEPACK reverse-RLE stream,
producing a read-only derived view of AVATAR.EXE. This is not a rebuilt executable
or a claim that wrapper execution and relocations are understood. The decoder
supports the admitted 18-byte header / skip=1 profile only.

The generic pointer-table pass found **19 same-base label-table candidates**
across AVATAR and TITLE. The native pass found **40 loaded-bit-test/branch
patterns**, of which **17 are in AVATAR and 23 in TITLE**. These are linked
instruction facts, not all equipment checks.

One maximal 71-entry pointer run includes creature, weapon and armor labels;
another 73-entry run includes class labels among other categories. The shared
candidate base in AVATAR is 61,648 (0xf0d0). Its consistency is a static clue,
not a qualified runtime DS binding. Adjacent semantic arrays must not become
one invented 71-item schema merely because their pointers form one run.

Next avenue: locate the indexed consumers of the relevant label subrange,
recover the index domain, join numeric/bitfield arrays through that same index,
and test permitted/refused uses. **Damage, prices, range and allowed-class
bitmask meanings have not been established.** The labels and code masks are
leads, not yet a proven connection between an item and its use permission.

## UFO/TFTD: one rule finds compatible record populations

Without supplying stride or count, padded-name spacing inferred the same
candidate **54-byte layout / 80 record positions** in each OBDATA file. UFO has
66 qualifying padded labels; TFTD has 62. These are qualifying witnesses, not
occupied-item counts. Coarser multiples are retained as competing alternatives.

In UFO's supplied MISSDAT data, the same rule also found **68-byte records,
250 positions and eight name witnesses** in SOLDIER.DAT, plus a **124-byte,
18-position candidate** in UNIREF.DAT. The pass does not decode all fields or
establish cross-context identity from matching display names. It does not claim
a corresponding populated TFTD soldier save was present/recovered.

The native pass found **383 mask/branch and 13 indexed-decision candidates**
in the UFO root, and **269 / 12** in TFTD, including non-gameplay utilities.
Both games' large LE executables reached the 30,000-instruction-per-view bound;
the unvisited work and indirect/far edges are retained. A budget stop is not
whole-program coverage.

The production LE loader refuses the observed selector fixup encoding. The
new analysis path reads validated object-relative source pages **without
applying fixups**, resolving absolute references, executing code or weakening
the loader's refusal. Authored tests independently preserve the distinction
between unrelocated bytes and the production loader's relocated image.

Next avenue: inspect the record reader/indexed consumer, bind candidate strides
and identities, and qualify selected fields before generating entity schemas.
The shared method transfers; addresses and field meanings do not transfer by
family resemblance.

## Generic implementation and agent interface

`structure_patterns.py` contains game-free connected rules. `structure_tables.py`
contains title-independent data heuristics. `structure_native.py` produces
bounded x86 facts; `structure_vm.py` produces facts from existing AGI IR and
bounded Z3/Z5 source layout. `structure_discovery.py` handles intake selection,
budgets, evidence, grouping and private reports. `cli.py` exposes projectless
CLI and JSON methods. No new graph database or model service is required.

```
fdisbull structure-scan /private/extracted-game --output /private/new-leads
fdisbull structure-info /private/new-leads/report.json --pattern labelled-record-array --limit 5
fdisbull structure-info /private/new-leads/report.json --lead-id LEAD_ID
```

The output states what was found, why it matters, exact bindings, limitations,
and the cheapest next discriminator. Heuristic rank orders work; it is not a
probability of correctness. Reading a report never authorizes execution.
The maintained scene-recovery skill now tells agents to reuse this shortlist,
qualify a small consumer, propagate compatible rules, and retain unknowns.

## Negative results and methodological corrections

- Repeated image bytes initially passed weak printable-name filters. Padded
  row-local fits and label diversity remove retained SHAPES/BACK06/MEDIBITS
  cases. Some terrain records spelled short sequential alphabet fragments;
  these no longer masquerade as named entity populations. They could still be
  real records under a different detector. The name heuristic intentionally
  misses short/numeric/non-ASCII populations; no global recall claim is made.
- Native `TEST r,r`, all-bit tests and zero masks are not selective permissions
  masks. They are excluded from this rule. Overwritten values/flags, missing
  edges, mixed source spaces, joins and unknown identities have negative tests.
- Grouping record multiples removes redundant discoveries but does not prove
  the smallest retained stride is the true row width. Alternatives remain.
- A full scan can decode support utilities as well as game code. Per-file
  provenance is required. No attempt is made to rename every mask a game rule.
- Static pattern counts, three repeated scans and generic authored fixtures do
  not measure cold-agent comprehension or end-to-end investigation speed.
  The same investigator tuned the heuristics on this roster. This is a
  cross-target development test, not a held-out generalization benchmark.

## Verification and delivery status

- **68 new authored cases; 368 focused and existing checks passed** in the final
  source suite, including relevant AGI, Z-machine, LE and skill checks.
- **15 source scans**: three per target, all byte-identical within each target.
- Fresh wheel privately built and installed; **5 real scan + 5 drilldown CLI
  commands** run from outside the checkout under isolated Python. Every scan
  matched the source report exactly. Seven installed implementation/skill files
  matched tested source. The wheel is a private test artifact, not a release.
- **768 scalar comparisons plus four parser-state cases** passed on selected
  original PQ1 resources; unsupported candidates and lifter refusal retained.
- Original inputs remain read-only. Every admitted source snapshot was checked
  again before a scan completed. These file-set checks are not atomic live
  memory observations. Four installer hashes match their intake records; all
  five upload identities are retained.
- No original game execution, live-state mutation, full project suite, hosted
  CI, remote commit/MR, release, model trial or shared installation occurred.
  GitLab discovery in this session exposed reads, not commit/note writes.

The source bundle contains only authored code/tests/guidance and sanitized
receipts. Detailed candidate reports are a separate **private** bundle because
they contain decoded source-derived words, object properties and names.
No original installer, game executable, save payload, media, disassembly dump
or full dictionary is in the public source contribution.

## Primary format references (not title-specific answer keys)

- Z-machine standard, dictionary: https://inform-fiction.org/zmachine/standards/z1point1/sect13.html
- Z-machine standard, objects: https://inform-fiction.org/zmachine/standards/z1point1/sect12.html
- Z-machine instruction layouts and opcodes: https://inform-fiction.org/zmachine/standards/z1point1/sect14.html and sect15.html
- EXEPACK reverse-RLE format: https://www.bamsoftware.com/software/exepack/

These references support format/ISA producers. Original target bytes and
existing fDisBull readers supplied the private observations. External game
reimplementations or published target offsets were not used as discovery keys.
