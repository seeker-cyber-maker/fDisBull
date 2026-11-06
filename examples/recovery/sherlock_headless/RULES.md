# Sherlock 7 relation model

Ruleset: `sherlock7-relations-v1`. This is an authored headless constraint
model grounded in the owner's Sherlock 7 English help. Source anchors below
refer to the private `HLP_English.txt` identified in [RESEARCH.md](RESEARCH.md).
They establish documented semantics, not live-original equivalence.

## Board and public representation

Width `W` and height `H` independently range from 3 through 8. Each row is a
category containing `W` distinct items. Every item appears once in its row,
and every cell contains one item. Thus each completed row is a permutation of
`0..W-1`. The help describes categories and dimensions at L424–432 and
L467–481; its same-row exclusion and known-image housekeeping support the
permutation model at L558–564 and L1287.

A submitted `board[row][column]` contains the row-local item number. A clue
uses global object IDs `row * W + item`. Let `p(o)` denote the column of object
`o`; this is the inverse lookup of the submitted board, not the board value.
A given `{object, column}` imposes `p(object) == column`. All row constraints,
givens and clues must hold together.

The Python types are `model.Puzzle`, `model.Clue` and `model.Given` in package
`sherlock_benchmark`. Public clue records use `{kind, objects: [...]}`. The
puzzle format is `sherlock-benchmark-puzzle-1`; submissions use
`sherlock-benchmark-submission-1` with `{format, challenge_id, board}`.
The challenge identity hashes the canonical public format, ruleset,
dimensions, clues and givens. Public puzzles contain neither generation seed
nor solution witness. See [README.md](README.md) for CLI and exact schemas.

## Clue predicates

In this table, `a`, `b`, `c` are the columns of `objects[0..2]`.
The eight kinds have nine admitted arity variants.

| JSON `kind` | Objects | Predicate | Help lines |
| --- | --- | --- | --- |
| `same_column` | 2 or 3 | All referenced columns equal | L550–564 |
| `not_same_column` | 2 | `a != b` | L566–570 |
| `same_column_excluding` | 3 | `a == b and a != c` | L566–570 |
| `xor_same_column` | 3 | `(a == b) != (a == c)` | L573–583 |
| `next_to` | 2 | `abs(a - b) == 1` | L594–604 |
| `left_of` | 2 | `a < b` | L606–611 |
| `between` | 3 | `abs(a - c) == 2 and 2*b == a + c` | L613–623 |
| `not_between` | 3 | `abs(a - c) == 2 and 2*b != a + c` | L625–629 |

For `same_column_excluding`, the first two objects are the original clue's
unmarked images; the third is its marked excluded image. For
`xor_same_column`, the first object is the original top/anchor image and
exactly one of the remaining objects shares its column. These are logical
positions within the clue, independent of the objects' category rows.

There is no wraparound adjacency. Left Of permits any positive distance.
Between occupies three consecutive columns with the second object centered;
the outer objects may reverse. Not Between retains the distance-two
requirement for the outer objects. Its second object may share an outer
column if the row constraints permit that. No `not_next_to` extension is
included in this profile.

### Examples that distinguish similar interpretations

Columns below are zero-based, and the referenced objects may be in different
rows. These are predicate examples, not copied original puzzles.

| Kind and `(a,b,c)` | Result | Distinction |
| --- | --- | --- |
| `between(0,2,4)` | false | Being somewhere between the outer items is insufficient. |
| `between(2,1,0)` | true | Reversing the outer items is allowed. |
| `not_between(0,0,2)` | true | The excluded item need only avoid column 1. |
| `not_between(0,0,3)` | false | Negating Between alone would incorrectly accept this. |
| `same_column_excluding(1,2,0)` | false | The unmarked pair must also coincide. |
| `xor_same_column(1,1,1)` | false | Inclusive OR would incorrectly accept this. |

## Original difficulty and interaction boundaries

Original Type A puzzles are described as solvable by repeated individual-clue
deductions; Type B is a separate pool that may require combined reasoning or
What-If (L474–481, L905–909). The help gives no Type A/B-specific clue
whitelist. A unique solution does not establish either original difficulty
classification, and this generator does not reproduce their numbered pools
or RNG. Givens are initial fixed positions; original Type A handicaps add
known positions, whereas Type B has no handicap (L441–459, L1322–1325).

The documented What-If tool saves a candidate state, makes an assumption and
supports restore, keep, restore-and-eliminate, or restore-and-try-next.
Original generation uses binary choices and does not nest assumptions
(L784–805, L836–863). A deduction dead end does not prove the assumption
correct; checking a What-If state reports current validity (L869–883).
These are requirements for any separately qualified assisted session track,
not implicit behavior of complete-board submission verification.

Full hints show a deduction; small hints identify useful cells or a clue
(L461–465, L930–933). Automatic housekeeping is an original option (L1287).
Clue layout, mnemonic reversals and XOR overlay movement do not change the
relations (L499–501, L585–604). Exact original hint selection, notification
behavior and deduction order remain unqualified. Benchmark assistance must
be declared separately from unassisted final-answer verification.
