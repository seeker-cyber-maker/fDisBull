# Explicit variable-position overrides

The bounded AGI scene prototype can replace one witnessed `position.v` instruction
with a literal `position` instruction of the same length. This is an explicit
change from variable-driven coordinates to fixed coordinates at that source PC.
The original variable assignments and every other instruction remain untouched.
Fresh replay establishes the actual outcome, including downstream effects.

## Shared planning API

```python
from fdisbull_core.agi_scene import plan_variable_position_override

plan = plan_variable_position_override(
    original_code, captured_result["view"], actor=0, x=30, y=40,
)
```

The pure function consumes exact immutable raw code and a coherent stopped view
already obtained through the [scene consumer](SCENE_CONSUMER.md). It performs no
I/O, changes no controls, and mutates neither argument. Malformed or unsupported
inputs raise `SceneInputError`. The existing
[`plan_literal_position_edit`](SCENE_EDITING.md) remains literal-only; neither API
silently chooses the other operation.

Admission shares the source/session identity, complete-history, actor, checkpoint,
instruction-window and lifecycle checks of the literal planner. The new API
requires opcode 38 and preserves the original four-byte witness:

```text
expected_bytes:     [38, actor, x_variable, y_variable]
replacement_bytes:  [37, actor, requested_x, requested_y]
```

The actor operand and instruction length stay fixed. Coordinate requests are byte
values 0–255 and actor IDs are 0–15; booleans are refused. The selected profile is
`agi-2917-scalar-position-pilot-1` with logic ID 0. A candidate plan is bound to the
exact source hash, and its new source hash covers the entire resulting program.

## Historical read values and changed binding

Opcode 38 reads the two named variables, stores those values in the actor's
coordinates, and then emits its position-change observation. Under this profile,
the witness's `after.x/y` therefore supplies the historical values used at that
instruction. The source bytes retain the variable IDs. These are distinct facts.

A variable may have changed after the position instruction. The planner does not
substitute its later stopped value, infer the assignment that supplied it, or
claim that the captured view is current in another live process. Consistency
checks do not authenticate caller-supplied observation JSON.

The plan schema is `fdisbull-agi-variable-position-override-1`. It retains the
standard source/session/checkpoint, witness, offset, expected/replacement bytes,
requested coordinates and candidate identity fields. Additional fields are:

| Field | Meaning |
| --- | --- |
| `binding_change` | `{"from": "variable", "to": "literal"}` |
| `variable_reads` | Separate x/y records, each containing the original variable `index` and historical `value` |
| `read_value_basis` | `position_witness` |
| `requested_position_matches_observed` | Whether requested coordinates equal the selected witness's resulting coordinates |
| `changed` | Always true: opcode 38 becomes opcode 37 |
| `write_performed` | Always false |
| `scope` | `static_instruction`: the changed binding applies at every execution of this PC |

Even a same-coordinate override is a program change because later executions
stop reading those variables. It is deliberately different from the literal
planner's same-coordinate no-op.

When x and y name the same variable, the historical values must be equal. A
contradictory witness is refused. An explicit override may nevertheless request
different literal x/y values, because removing the variable binding is its stated
operation. The actor's position before the witnessed assignment need not have
equal coordinates.

## Native experiment and observed consequences

The CLI runs four homegrown raw-code originals and their separate candidates:

```sh
python native/qemu-agi/variable_scene_edit_harness.py \
  --binary /absolute/path/to/qemu-system-agi \
  --output /private/new-variable-scene-receipt.json
```

The output must be new. Optional `--evidence-dir` selects an existing private
directory for failed native-run evidence, and `--timeout` is bounded to 0.1–30
seconds per harness operation. The CLI reserves its report before launch, keeps
partial successful stages on failure, and performs no retries. Each original
child closes before its separate candidate starts.

All cases request actor 0 at `(30, 40)`, use SCENE mask 2 with capacity 8, and keep
DISASM disabled. Eight owned children receive one resume each with an
eight-instruction budget: a maximum of 64 retired instructions. The exact successful
authored programs retire 44 instructions in total.

| Case | What the original demonstrates | Candidate outcome to verify |
| --- | --- | --- |
| Historical reads | Actor 0 uses `v7/v8 = 10/20`; those variables later become `70/80` and position actor 1 | Actor 0 becomes `(30,40)`; actor 1 stays `(70,80)`; final variables stay `70/80`; the plan retains historical `10/20` |
| Aliased variables | Both actor coordinates read `v9 = 25`; another actor also uses it | Actor 0 becomes `(30,40)`; actor 1 and v9 remain unchanged |
| Later assignment | Two identical `position.v` instructions originally emit only one effective-change record | The later unchanged instruction restores `(10,20)`; placement mismatch is explicit |
| Downstream `get.posn` | Actor 0's position is copied back into v7/v8, then used by actor 1 | The override propagates: both actors and final v7/v8 become `30/40` |

Before replay, the harness independently checks the original source and expected
instruction bytes, permitted opcode/actor binding, unchanged program length and
candidate hash. After replay, it checks the captured candidate source identity,
distinct attachment and identical native binary identity.

The receipt contains the exact raw programs, plan, original/candidate captures
and complete final guest states. `placement_matched` compares requested and
observed coordinates. `final_variables_changes`, `final_flags_changes` and
`final_other_actor_changes` compare all corresponding arrays in the final
snapshots. Their `difference_scope` is `final_guest_snapshots`; equal endpoint
values do not establish identical intermediate behavior.

An experiment can be `completed` while a placement did not match or effects
propagated elsewhere. These outcomes remain separate. The CLI does not silently
rewrite another instruction or retry until the requested result appears.

Run its independent contract and native checks with:

```sh
PYTHONPATH=packages/fdisbull-core/src \
FDISBULL_QEMU_AGI=/absolute/path/to/qemu-system-agi \
python -m pytest -q packages/fdisbull-core/tests/test_agi_scene_variable_edit.py \
  tests/test_qemu_agi_variable_scene_edit.py
```

## Scope and integration

This action leaves source assignments unchanged; it does not promise that final
variables, other actors or control flow remain unchanged. `get.posn` is a concrete
path by which a new position can propagate. Loops revisit the changed binding,
and later assignments can override it. A last effective-change witness is not a
proof of the last assignment.

Editing the assignments that supplied the variables while preserving their
dynamic binding needs a separate reaching-definition/data-flow contract. Current
SCENE records identify a witnessed effect and source instruction. DISASM records
alone do not establish that assignment provenance either.

Both products pin shared core `0.1.0.dev5`. DotBox can use the explicit override
as a small scene-design action; fDisBull can retain its exact source proposal and
observed outcome for recovery work. Application policies, board projects and
backend defaults remain separate. This adds no native CPU change or rebuild,
full game/resource engine, renderer, visual editor, UDC export qualification or
original-DOS QEMU parity claim. The existing legacy Python guest resource
regeneration requirement still applies to its changed shared-package version.
