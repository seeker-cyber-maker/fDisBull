# Zork I as a standalone UIL program

The `zork-uil` converter maps the complete, checksum-qualified v3 story into a
new executable profile, `fdisbull-uil-word16-1`. The independent Python consumer
executes that program with no DOSBox, Frotz, Jericho, original COM/DAT file,
project database, source decoder, or core `fdisbull` installation.

The original parser, command dispatch, puzzles, object mutations, turn loop and
autonomous processes are retained as lowered control and data operations. This
is a low-level semantic translation. It does not claim to infer a useful English
name for every rule or to prove all game paths equivalent. The existing
`fdisbull-il-1` interaction blocks and mailbox recovery remain unchanged.

## Convert and play

Use your own story file and new output paths outside a Git checkout:

```sh
fdisbull zork-uil /private/ZORK1.DAT \
  --output /private/zork1.uil.json.gz \
  --mapping /private/zork1.udl.json.gz \
  --world /private/zork1.z.json

fdisbull-player --uil /private/zork1.uil.json.gz --seed 12 \
  --checkpoint /private/zork-progress.json
```

The optional UDL document records every source mapping and the source identity.
The optional Z document inventories the initial object records and globals;
subsequent authoritative state belongs to the UIL runtime. All three outputs
contain game-derived content and remain private. They are not shipped in the
generic tool distributions or committed to this repository.

The direct module form is also available:
`python -m fdisbull_player.word16 /private/zork1.uil.json.gz --seed 12`.

Only the UIL file and the standalone consumer are required for play. The
consumer's `--commands` option accepts a JSON array of command strings for
reproducible runs; `--transcript` records their actual responses. A checkpoint
captures the execution continuation and random state, and can be reopened by a
fresh process. The story's own SAVE/RESTORE operations have a separate game-save
slot; these are not original DOS `.SAV` files.

The edition used for qualification is Zork I release 88, serial `840726`,
SHA-256 `0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.
Its supplied file contains 92,160 bytes; the declared story is 84,876 bytes.
The mapper records the identity of the trailing 7,284 padding bytes separately.
Different Zork releases must not borrow this edition's verification receipt.

## Where the semantics live

The UDL mapper expands instructions into ordered operand reads, arithmetic,
explicit wrapping and signed conversion, memory operations, control flow,
calls, returns, input boundaries and reusable layout-library calls. For example,
a signed decrement-and-branch is represented by a variable read, wrapped
subtraction, variable write, signed comparison and ordinary conditional transfer.
The player has no source-opcode dispatch and does not invoke the original engine.

The profile supplies these contracts:

| Surface | Contract |
|---|---|
| Numbers | 16-bit stored words; explicit signed interpretation and wrapping; division truncates toward zero. |
| Memory | Big-endian byte-addressed data; writes confined to dynamic memory. Raw-memory and structured object views alias the same bytes. |
| Variables | Global memory, routine locals and frame-local evaluation stacks; direct and indirect stack access differ. |
| Control | Full-width program coordinates, ordered operands, explicit conditional transfers, routine defaults and return destinations. |
| Objects | The declared record/tree, attribute and property layout; ordered mutation of shared memory. |
| Text | Packed data decoding, abbreviations, object names, ZSCII and dictionary encoding under the v3 codec. |
| Input | The text buffer and dictionary-token buffer are populated; the lowered original parser then processes them. |
| Randomness | An explicit reproducible Frotz-compatible generator or a declared range/result tape; different interpreter generators are not assumed identical. |
| Host effects | Explicit text, status/window, stream and sound events; unsupported host behavior raises an error. |
| Persistence | Full evaluator continuations bound to the UIL package; game SAVE/RESTORE distinct from external checkpoints. |

The memory image retains original data, including bytes that may also be code,
because a source program can read its own image as data. Execution comes from
the expanded UIL nodes. Each reached block and routine header has a byte guard;
modified executable bytes cause an explicit refusal. A missing target likewise
fails instead of falling back to interpretation.

## Indirect destinations and coverage

Restricting conversion to a walkthrough would discard unseen game behavior.
The mapper therefore attempts every byte offset in the declared image and
every structurally valid aligned routine header. It retains a finite superset
of supported original instruction starts and candidate headers. Indirect calls
and jumps can select those precompiled entries without decoding at runtime.

For this edition the export contains 55,891 candidate starts and 7,680 candidate
routine headers. These are deliberately conservative **candidate** counts:
many are alternate decodes inside data or other instructions. They are not
counts of real routines, reachable code, verified actions or game scenes.
Executed coverage is measured separately. The initial Z view has 250 actual
object records, with source offsets, names, links, attributes and properties;
it does not classify all of them as rooms.

## Verification boundary

Independent original-game execution and synthetic primitive tests are separate
evidence sources. The verification procedure compares the supplied edition
against unmodified Frotz, and also compares original DOS dynamic memory under
an explicitly captured native random tape. Narrative comparison normalizes
line wrapping and removes interpreter status decoration; it does not claim
identical pixels, terminal pagination or original interpreter UI.

The full-score route is a behavioral acceptance case, not an all-path proof.
Failure paths, parser alternatives, death states and timing combinations not
exercised by a receipt remain unverified. The same is true of other story
editions and platforms not actually run. See the accompanying verification
report for fresh commands, results, hashes and measured coverage:
[executed verification](VERIFICATION-ZORK-UIL-2026-10-29.md) and the
[upstream / all-PR review](ZORK_UIL_PR_REVIEW.md).

## Source contracts

- [Z-machine 1.1 storage and routine calls](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html)
- [Instruction encoding](https://inform-fiction.org/zmachine/standards/z1point1/sect04.html)
- [Object and property layout](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html)
- [Dictionary and lexical analysis](https://inform-fiction.org/zmachine/standards/z1point1/sect13.html)
- [Opcode definitions](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html)
- [Existing shared IL](INTERACTION_IL.md) and [recovery contracts](INTENT_PIPELINE_RECOVERY_CASES.md)

This implementation follows the source-bound UDL → UIL → consumer separation
in PRs #3, #10, #11, #13, #14, #17 and #20. The independent consumer realizes the
profile's operations in Python; it is not the existing byte-preserving DOS UDC.
