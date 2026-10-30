# Z-machine processor verification — October 29, 2026

The new `ZMachineV3Processor` is a working implementation of fDisBull's
processor interface for checksum-qualified raw version-3 stories. The public
`zmachine-disasm` and `zmachine-analyze` commands use it to produce instruction
facts and bounded static control-flow analysis. The [module guide](ZMACHINE_PROCESSOR.md)
documents the Python, CLI and JSON contracts.

The preserved executable-IR conversion and the separate partial game-intent
UIL are unchanged. This addition supplies an instruction inspection layer; it
does not increase the game-intent recovery claim.

The [sanitized machine-readable receipt](evidence/zmachine-processor-2026-10-29/verification.json)
records implementation hashes, protected-file hashes, commands and evidence
hashes, independent review, actual-story checks and exact-wheel checks. Raw
story bytes, narrative transcripts and machine snapshots remain private.

## Outcome and acceptance evidence

| Requirement | Fresh evidence | Result |
|---|---|---|
| Implement the existing processor interface | Generic dispatcher tests and both public query paths | Confirmed |
| Preserve instruction encoding and distinguish control-flow cases | 89 new tests, including 49 independently authored specification-based cases | Confirmed |
| Retain unknown targets and incomplete work | Dynamic call/jump/restore examples, budget/frontier tests, source overlap tests, real entry graph | Confirmed |
| Preserve the working conversion and intent layer | All 154 existing conversion/intent tests; 15 protected files byte-identical | Confirmed |
| Keep path-based story recognition compatible | Original/new comparison on 12 valid and invalid inputs, including R88 | Confirmed |
| Match decoded facts to the existing source mapping | All 55,891 preserved candidates checked; accepted facts exact, stricter refusals classified | Confirmed within candidate scope |
| Exercise actual Zork code paths | 401 commands, 403 matching state boundaries; 2,511 observed instruction starts decode correctly | Confirmed for the two tested routes |
| Work from the built package | Six isolated fresh processes through the exact core wheel | Confirmed on Linux Python 3.12.14 |
| Recover every game intent or resolve all dynamic control flow | Neither supplied nor claimed by this module | Outside scope |

## Source identity and separation

The real input is Zork I release 88, serial `840726`, with full-file SHA-256
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.
It contains 92,160 file bytes, of which 84,876 belong to the declared story and
7,284 are trailing padding. The processor's address space includes the entire
source digest, while decoding is confined to the declared image after its
64-byte header. Initial PC is `0x4f05`.

The raw `decode_v3` and `decode_ztext` functions are unchanged. The only change
to `zmachine.py` extracts the existing path-based validator into
`inspect_story_bytes`, so the new adapter can qualify and decode one immutable
snapshot after a single bounded read. Existing callers retain their original
path interface and inspection results.

The processor, executable IR and game-intent UIL remain separate layers:

| Layer | This change |
|---|---|
| Source processor | Adds source-bound decoding, operand references, call-header metadata, successors and static queries. |
| Executable IR | Original converter, runtime, source mapping and executable package remain unchanged. |
| Game-intent UIL/UDL | Existing guarded mailbox and counter definitions, consumer and residual IR remain unchanged. |

This work starts from remote Zork commit
`14617b73c59b0000d6e92750e21b52762b4f3240`. It is a development addition,
not a release tag or system installation.

## Independent encoding and traversal checks

The tests use authored checksum-valid stories rather than copied game data.
Expected destinations come from independently placed bytes and the
[instruction encoding](https://inform-fiction.org/zmachine/standards/z1point1/sect04.html),
[routine layout](https://inform-fiction.org/zmachine/standards/z1point1/sect05.html),
[storage and calls](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html),
and [opcode definitions](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html).

Coverage includes branch polarity, signed offsets, branch-return shortcuts,
packed calls and default locals, null versus dynamic calls, malformed arities,
inline text, return/quit/restart boundaries, successful restore's unknown saved
continuation, and failure branches for both encoded restore polarities. Tests
also exercise indirect stack references, unknown current local frames,
foreign source identities, padding, truncated instructions, immutable returned
facts, and routines below the high-memory mark.

Analysis tests demonstrate that self-loops are deduplicated, explicit roots
remain separate from routine headers, unresolved transfers prevent a complete
graph result, conflicting spans are reported, and both instruction and byte
budgets retain a truthful frontier. A loop that closes exactly at the instruction
limit is distinguished from unfinished work at that limit.

The final integrated command was:

```sh
PYTHONPATH=src:player python -m pytest -q \
  tests/test_zmachine_processor.py \
  tests/test_zmachine_processor_acceptance.py \
  tests/test_zmachine_analysis.py \
  tests/test_zmachine.py tests/test_processor.py \
  tests/test_uil_word16_runtime.py tests/test_zork_uil.py \
  tests/test_zork_uil_cli.py tests/test_game_intents.py \
  tests/test_zork_intents_mapper.py tests/test_zork_intent_runtime.py \
  tests/test_zork_intents_cli.py
```

Result: **261 passed, 5 skipped**, with no failures. The five skips require
optional managed-CIL dependencies unavailable in this environment. This total
includes 89 new tests, 69 preserved IR tests, 85 preserved intent tests,
14 existing raw decoder tests and four existing processor tests.

A broader affected selection also covered the existing harness, language CLI,
output protocol, distribution and offline kit: **251 passed, 16 failed,
5 skipped**. All 16 failures match failure IDs already reproduced on unchanged
upstream. They are existing artifact-directory `inside_git` refusals and their
downstream assertions. There are zero introduced failure IDs. This selection
is recorded separately, rather than represented as an entirely green full suite.

## Complete preserved-candidate comparison

The existing converter's exhaustive offset map contains 55,891 candidate
instruction starts; that inventory includes overlapping interpretations and
data, and does not establish executed code.

| Candidate comparison | Count |
|---|---:|
| Candidates examined | 55,891 |
| Accepted with every original raw decoder field identical | 55,132 |
| Stricter rejections for constant indirect variable numbers above 255 | 759 |
| Accepted raw-fact mismatches | 0 |

The stricter refusals are 479 `dec`, 131 `inc`, two `inc_chk` and 147 `load`
candidates. The adapter rejects those invalid direct variable numbers while
retaining the old converter and all original map entries untouched. None of
the observed instruction starts in the tested routes is rejected. The source
mapping gzip retains SHA-256
`b933d8fb4cf7f739f4c0fe9c0c1c61b306ea0dd64224fd408b41d5f6d4e3bd05`.

## Actual execution and reference agreement

The new processor was used as an observer of source instruction boundaries
while the unchanged executable-IR runtime executed the game. Each newly
encountered source start was decoded through the generic processor dispatcher
and compared against every raw fact in the preserved source mapping. Observed
transitions were checked against known successors; caller-dependent returns
and dynamic calls remained explicitly unresolved in the static facts.

The original IR runtime and the existing mixed UIL/IR runtime also ran side by
side. Their complete machine snapshots and game-result fields matched after
each input boundary. Implementation step counts and recovery audit fields are
excluded from the game-result comparison. Snapshot comparison includes memory,
PC, stack, frames, input, RNG, host state and save state, normalizing only the
package identity as in the existing checker.

Fresh unmodified dfrotz 2.44 executions supplied the independent narrative,
score and move checks. The executable digest is
`350a783fc5468e2239a27fa61a5d4cca26353c209980631baf43b285fdd524f2`,
built from source commit `fe66e2ef738354f5e2fe37c7c01b1781ef659acd`.
Narrative comparison removes interpreter status/prompt decoration and normalizes
whitespace; score and moves are compared separately.

| Case | Commands | Matching boundaries, including startup | Observed distinct instruction starts | Final state |
|---|---:|---:|---:|---|
| Existing winning route | 396 | 397 | 2,498 | Halted, score 350, 394 moves, location 178 |
| Open/repeat/take/close/reopen mailbox | 5 | 6 | 756 | Awaiting input, score 0, five moves, location 180 |
| Combined | **401** | **403** | **2,511 distinct across both** | All checks agree |

Together the runs observed 390,701 instruction executions. All 362,701
transitions checked against a known static successor matched. The remaining
observed transitions comprised 2,142 dynamic calls and 25,856 caller-dependent
returns; their unknown static destinations were retained. Counts exclude the
first instruction of each run, which has no preceding transition.

The full winning route still has zero mailbox-opening lifts and 392 counter
lifts. The focused mailbox case has three opening-binding hits and five counter
hits. These retain the earlier recovery scope; processor decoding is not counted
as additional recovered game intent.

## What the real static analysis discovers

| Query | Instructions | Routine candidates | Unresolved transfers | Status |
|---|---:|---:|---:|---|
| Original initial PC, budget 10,000 | 1,788 | 60 | 13 | `partial`; static queue drained |
| Explicit mailbox instruction entry `0x8089`, budget 1,000 | 64 | 2 | 0 | `static_worklist_drained` within the stated scope |
| Original initial PC, budget 1 | 1 | 1 | 0 | `instruction_budget`, two frontier entries retained |

The initial-entry graph includes only 972 of the 2,511 instruction starts
observed across the two executed routes. The other 1,539 were not discovered by
the static traversal. Runtime dispatch is a concrete remaining gap; a drained
queue must not be called whole-game code coverage.

The mailbox dispatcher at `0x586d` takes its packed callee address from the
evaluation stack and resumes at `0x5871`. There is no literal call to packed
address `0x4042` in the preserved map. The processor correctly leaves the callee
unknown. The earlier recovery's separately qualified routine header `0x8084`
has two zero defaults and entry `0x8089`; supplying that entry explicitly does
not resolve the original dynamic call statically.

The direct contents-listing call at `0x80ee` is different: its packed operand
`0x472c` identifies header `0x8e58`, six default locals, entry `0x8e65`, and
continuation `0x80f4`. Those source facts agree with the preserved mapping.

Recursive `complete` applies only to the requested static worklist and
explicitly excludes caller-dependent return destinations. Even the mailbox
query does not prove path feasibility, routine ownership, mutable-memory
behavior or completion of a semantic interaction.

## Built-package verification

The candidate core wheel was built with the installed `setuptools.build_meta`
backend, without downloading dependencies or changing a system installation.
The tool-only archive gate passed all **151 entries**. Wheel SHA-256:

```text
a09cae3cd86c4d4627014088a1f9365a2e0381b78040b8b4e1c8356bd3a85a7e
```

Six fresh Python `-I` processes loaded the exact wheel. They exercised the
actual metadata-declared `fdisbull.cli:main` entry point for authored disassembly,
recursive analysis and budget exhaustion, plus bounded real-R88 disassembly
and analysis. A separate process imported the processor directly and verified
the packed-call/header/entry distinction.

All imported fDisBull modules came from that wheel. Repository and build-source
reads were actively denied, with a deliberate guard probe confirming the
restriction. No actual operation attempted a forbidden read, network access or
subprocess. Original story and tested source hashes remained unchanged.

## Remaining qualification limits

Only the supplied R88 edition was executed; other v3 stories have encoding
support but no equivalent edition-specific gameplay qualification here. Other
Z-machine versions, early v3 headers outside the existing inspection profile,
container extraction, live mutable VM memory and native `.fdb` import remain
unsupported by this module.

Original DOS captures, fresh-process checkpoint resume and native-backend
verification were not repeated for this static processor addition. Their earlier
receipts remain scoped to the preserved conversion. No macOS execution was
performed for this module. No all-path equivalence or complete game-intent
recovery is claimed.
