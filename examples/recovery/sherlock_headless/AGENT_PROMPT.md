# Agent task: solve a relational logic puzzle

You receive one JSON puzzle with ruleset `sherlock7-relations-v1`. Find a complete
board that satisfies all givens and clues. Return exactly one JSON object, with
no Markdown fences or commentary:

```json
{"format":"sherlock-benchmark-submission-1","challenge_id":"<supplied challenge_id>","board":[[0,1,2],[2,0,1],[1,2,0]]}
```

The board above illustrates syntax only. Use the supplied dimensions and clues.

Each board row is a category with `columns` distinct items numbered from zero.
Every item in that row appears exactly once. `board[row][column]` is that row's
item number. Numbers in different categories may repeat in the same column.

Clue operands are global object IDs: `object = row * columns + item`.
For the following definitions, `a`, `b`, `c` mean the board columns occupied
by the listed objects, in order. A given fixes one object's column.

| Kind | Constraint |
| --- | --- |
| `same_column` | All two or three listed objects have equal columns. |
| `not_same_column` | `a != b`. |
| `same_column_excluding` | `a == b` and `c != a`. |
| `xor_same_column` | Exactly one of `a == b` and `a == c` holds. |
| `next_to` | `abs(a-b) == 1`; edges do not wrap. |
| `left_of` | `a < b`; distance can exceed one. |
| `between` | `abs(a-c) == 2` and `2*b == a+c`; three consecutive columns. |
| `not_between` | `abs(a-c) == 2` and `2*b != a+c`; outer spacing is still required. |

Return the supplied challenge ID unchanged. Do not return altered puzzle
constraints, claimed acceptance, or a partial board. The evaluator accepts any
complete board satisfying the public constraints.

Organizer: state the track's permitted tools, deadline, and token budget
alongside this prompt. For a reasoning-only track, isolate the agent from the
reference solver and private generation manifest. For a tool-using track,
record available tools in the evaluation metadata. This prompt alone does not
enforce isolation.
