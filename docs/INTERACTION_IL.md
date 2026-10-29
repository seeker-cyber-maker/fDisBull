# Shared interaction blocks

`fdisbull-il-1` is a small JSON representation for authored and recovered
interaction programs. UDL (`role: "udl"`) and UIL (`role: "uil"`) use the
same nodes and evaluator; the role records whether the document is being used
as an input or an output. `change_role` copies the document and changes only
that metadata. Separate compiler definitions, recognition rules and libraries
may be developed later; they are not implicit in the role. A completed target
need not depend on the original runtime, but this implementation does not yet
produce a complete game or a target compiler.

```json
{
  "format": "fdisbull-il-1",
  "role": "udl",
  "variables": {"$money": {"type": "u16", "initial": 0}},
  "resources": {"message": {"kind": "text", "text": "Done."}},
  "body": [
    {"id": "add-money", "op": "add", "var": "$money", "value": 200},
    {"id": "show-message", "op": "text", "resource": "message"}
  ]
}
```

Each block has a unique stable `id`, an `op`, named sockets, and optional
`evidence` references. Bodies and branch children are ordered lists. This is
suitable for a future visual block editor; no drag-and-drop editor is included.
Values are integer or boolean literals, or a variable reference such as
`{"var":"$money"}`. Declared types are `bool` and signed or unsigned 8, 16,
32, or 64-bit integers. `add` and `subtract` wrap at the declared width;
boolean arithmetic is invalid.

Supported blocks are `set`, `add`, `subtract`, `if` with `then` and `else`
lists, `require`, `text`, `load_graphic`, `play_sound`, and `click`.
Conditions are `eq`, `bit_test`, `not`, and `and`. A failed `require` refuses
the evaluation. Text resources contain `kind: "text"` and `text`; graphic
and sound resources contain their `kind` and a `uri`.

`validate_il` checks the whole document, including unselected branches.
Documents are limited to 64 KiB, 1,024 blocks and conditions, and depth 32.
`execute_il` validates the entire typed initial state and preflights required
`graphics`, `audio`, and `input` capabilities before evaluating. Invalid input,
a missing capability, or a step-budget stop returns `refused` with no emitted
events or committed changes. Text events are declarative output. A graphic,
sound, or click produces `pending_host`: events and a proposed state are
returned, while committed state remains unchanged. No media or input side
effect is performed by the evaluator.

The optional top-level `evidence` map preserves JSON provenance and blocks
reference its IDs. Validation checks reference and basic digest/range shape;
it does not verify arbitrary provenance claims. Project storage additionally
checks file-bound evidence against immutable project bytes when saving and
loading. Revisions retain a parent and author; updates require the current
parent. Evidence identity alone does not prove behavioral equivalence.

The CLI offers `fdisbull il-check PROGRAM`, `fdisbull il-run PROGRAM [--state JSON]`,
`fdisbull il-store PROJECT NAME PROGRAM [--parent REVISION] [--version VERSION]`,
and `fdisbull il-info PROJECT REVISION`. `recover_v3_attributes` is a bounded
source-specific helper that lowers selected Z-machine v3 `set_attr` and
`clear_attr` instructions. Its caller supplies names and an object-variable
binding; those names and the runtime correspondence remain claims to verify.
It is not a general decompiler or full UDL compiler.
