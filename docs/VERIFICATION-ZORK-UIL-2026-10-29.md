# Zork I executable IR verification (legacy UIL profile name)

**Terminology correction:** this historical receipt qualifies the low-level
word16 executable IR. It does not establish recovery of the intended game-intent
UIL. The original runtime, converter, outputs and tests remain unchanged. See
[partial intent recovery](ZORK_INTENTS.md) and its
[separate verification](VERIFICATION-ZORK-INTENTS-2026-10-29.md) for the new layer.

The exact Zork I release 88, serial `840726`, supplied for this investigation was
converted to `fdisbull-uil-word16-1` and completed as a standalone IR program.
The initial narrative and all 396 responses on the full-score route agree with
an independently built, unmodified reference interpreter. The game finishes
with **350/350 points in 394 counted moves**.

This is a complete low-level executable conversion, with behavioral evidence
for the route and additional cases below. It is not an all-path equivalence
proof or recovery of game-intent primitives.

## Source and implementation identities

| Item | Identity |
|---|---|
| Upstream baseline | `031b53eb953bfdc1d0e23c0ed49441031bad6e06` |
| Story | Z-machine v3; Zork I R88; serial `840726` |
| Story SHA-256 | `0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd` |
| File / declared bytes | 92,160 / 84,876; 7,284 trailing padding bytes recorded separately |
| Final consumer SHA-256 | `f5ca20999a1dea38b03df9386337a43600b54235fe4caffcbfb63a94dabc4168` |
| Compiled UIL gzip SHA-256 | `f29a6ed0ad1e4db1bcf01b5f5a39b80c8ecd6524f8cca17ee10c8bf5a07c4607` |
| Reference interpreter | Unmodified dfrotz 2.44, source `fe66e2ef738354f5e2fe37c7c01b1781ef659acd` |
| Runtime environment tested | Linux, Python 3.12.14; other host platforms unverified |

The [machine-readable receipt](evidence/zork-uil-2026-10-29/verification.json)
binds the remaining mapper, reference, route, checker and evidence hashes. The
private game payloads are deliberately not part of this repository or its
generic distributions. The supplied installer contains Zork I; these results
do not qualify Zork II, Zork III or a different edition of Zork I.

## Independent behavioral checks

| Check | Executed result | Claim boundary |
|---|---|---|
| Full winning route | Initial narrative plus 396/396 command narratives agree; 396/396 score/move pairs agree | One complete route at reference seed 12 |
| Final game state | 350/350 points, 394 moves, location object 178, halted | No death or assisted state edits on this route |
| Executed coverage | 2,498 distinct UIL blocks; 74 random calls | Measured execution, not total reachable code |
| Original DOS state | 34/34 prompt-boundary snapshots agree across every one of 11,795 nonheader dynamic bytes | Opening plus 33 commands through troll combat |
| Original DOS control and randomness | All input PCs agree; 7/7 observed random range/result pairs agree | Native generator was observed, not replaced |
| Parser alternatives | 25/25 narratives and score/move pairs agree | Valid-length empty, case, clarification, pronoun, abbreviation, punctuation and rejected inputs |
| Source-free execution and persistence | 14/14 checks pass in four fresh isolated processes | Only consumer and compiled UIL initially available |
| Fresh-process resume | First 100 commands, checkpoint, then 296 commands match uninterrupted play | Future responses, state and complete final snapshot agree |
| Real game SAVE/RESTORE | Restored continuation, future play and RNG agree; slot survives restart and a fresh-process checkpoint | Separate from original DOS save-file compatibility |

The reference runs the original story independently of the mapper and UIL
consumer. The route was taken from pinned Microsoft Jericho data and then
executed against the exact supplied story. The guide is a test input, not
evidence by itself. Reference source and route URLs are in the receipt.

Narrative comparison removes generated interpreter status decoration and the
terminal prompt, then collapses whitespace. Every other character is compared.
Score and moves are compared separately. This does not assert identical terminal
pagination, line wrapping, pixels or original interpreter UI. The comparison
found a real ZSCII indentation handling error during development; it was fixed
and the complete route was rerun against the final consumer.

Frotz's seeded random profile and the DOS interpreter's generator are different.
The native comparison therefore uses an observed range/result tape. Its 64-byte
interpreter header is excluded from byte comparison; every remaining dynamic
byte is compared. These exclusions are explicit rather than silently accepting
selected field matches.

The isolated-process checks run Python with `-I`. An audit hook refuses reads
from the analysis workspace, subprocess launches and network connections. The
consumer imports no `fdisbull`, source decoder, Jericho or Frotz module. The game
runs from expanded UIL operations; its initial memory remains available as data
to preserve code/data aliasing and packed text. There is no source-opcode
execution fallback.

## Export completeness and execution coverage

The mapper tries every offset in the declared image, retaining every supported
valid instruction start and every structurally valid aligned routine header.
For this edition it exports **55,891 candidate starts** and **7,680 candidate
routine headers**. Many overlap other instructions or lie in data. These counts
must not be presented as actual routines, verified actions, rooms or reachable
instructions. The separate initial Z view contains **250 object records** and
**240 globals**, without pretending to classify every object as a room.

Indirect control flow selects already expanded entries. Missing targets,
unsupported effects and modified executable bytes fail explicitly. This
supports whole-image export without making the winning walkthrough decide
which code survives conversion. See [the profile and converter](ZORK_UIL.md)
for arithmetic, memory, object, text, input and persistence contracts.

## Repository tests and packaging

The focused compiler, consumer and CLI suite passes **69 tests**, including
operand ordering, signed arithmetic, stack behavior, object/data aliasing,
calls, input, persistence and refusal cases. The final review added direct-path,
symlink and hardlink input/output alias checks. CLI checkpoint or transcript
arguments can no longer overwrite the UIL package or command file; a complete
batch is validated before any output is written.

The final full repository run collected 1,762 tests:

| Result | Count |
|---|---:|
| Passed | 1,605 |
| Failed | 48 |
| Skipped | 109 |
| Warnings | 3 |

All 48 failing test IDs also fail on the exact unchanged upstream source in the
same environment. They comprise 28 existing private-output/Git-ancestry checks,
10 tests requiring absent optional `dnfile`/`dncil` dependencies, and 10 tests
affected by sandbox socket restrictions. One initially introduced distribution
allowlist failure was fixed and passes in the final run. The suite is therefore
**not globally green**, and these baseline limitations are not waived. Exact
failure IDs and hashes of the complete test logs are retained in the receipt.

Core and standalone-player wheels were built without downloading dependencies.
Reconversion through the built core wheel produced byte-identical UIL, UDL and
Z outputs. The player distribution includes the new consumer. The source manifest includes
this report and sanitized evidence, while the archive gate excludes licensed
game payloads. The archive gate passed for 147 core-wheel entries, 11 player-wheel
entries and 482 source-archive entries. These are development builds of the 0.24.0 source line, not a new
tagged release. A release still needs the repository's required CI on its exact
commit.

## Reproduction

Use an owned copy of the exact story and new output paths outside a checkout:

```sh
fdisbull zork-uil /private/ZORK1.DAT \
  --output /private/zork1.uil.json.gz \
  --mapping /private/zork1.udl.json.gz \
  --world /private/zork1.z.json

fdisbull-player --uil /private/zork1.uil.json.gz --seed 12 \
  --commands /private/commands.json \
  --transcript /private/transcript.json \
  --checkpoint /private/progress.json

fdisbull-player --uil /private/zork1.uil.json.gz \
  --resume /private/progress.json --checkpoint /private/progress.json

PYTHONPATH=src:player python -m pytest -q \
  tests/test_zork_uil.py tests/test_uil_word16_runtime.py \
  tests/test_zork_uil_cli.py
```

The independent comparison script is included without licensed fixtures. Build
the pinned unmodified dfrotz reference and supply the pinned route as a JSON
array of strings, then run:

```sh
python scripts/verify_zork_uil.py \
  --uil /private/zork1.uil.json.gz --story /private/ZORK1.DAT \
  --commands /private/commands.json --frotz /private/dfrotz \
  --output /private/new-comparison
```

The optional `--native-receipt` adds captured original-DOS memory/PC/random-tape
comparisons. Its RAM paths may be relative to the receipt. Raw checker outputs
contain game text and must remain private. The packaged checker was rerun on
the complete route and 34 native snapshots with the same passing result.

The consumer's internal game-save slot and full evaluator checkpoints have
different purposes. Neither is claimed to import or export original DOS `.SAV`
files. A checkpoint contains licensed game-derived state and belongs outside
the repository.

## Remaining limits

Unexercised failure paths, death states, alternative puzzle orders and timing
combinations remain unverified. The reference frontend ignores its input-length
argument, so intentionally overlong commands are outside its comparison domain;
the 396-command route has a maximum length of 29 characters. Runtime limits and
unsupported host effects remain explicit errors. High-level rule names, a
general UDC definition catalog, other story releases, and cross-platform
qualification are not established by this work.

The [review of all 23 pre-existing PRs](ZORK_UIL_PR_REVIEW.md) records which
upstream contracts and previous bounded experiments informed the conversion.
