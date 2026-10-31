# Shared interaction blocks

The 0.23 source adds a separate [original-backed DOS UDC](UDC_DOS.md) companion.
It retains this v1 schema and role behavior, while a bounded source-block
profile and Z3 checks qualify selection of original native backings. It does
not make the evaluator below execute native code or host events implicitly.

`fdisbull-il-1` is a small JSON representation for authored and recovered
interaction programs. The legacy v1 document roles `"udl"` and `"uil"` use the
same nodes and evaluator; the role records whether the document is being used
as an input or an output. `change_role` copies the document and changes only
that metadata. Separate compiler definitions, recognition rules and libraries
may be developed later; they are not implicit in the role. A completed target
need not depend on the original runtime, but this implementation does not yet
produce a complete game or a target compiler.

[Draft RFC 0001](uil-rfcs/0001-shared-intents-and-compiler-definitions.md)
uses **UDL** for mapping original code into **UIL**, and **UDC** (User-Defined
Compiler) for reading UIL and transferring it back into code. It proposes
original/source UDC definitions over this same representation, including
unchanged shared-IL pass-through, effect binding and qualified cross-language
reuse. UDC is not a new v1 role. Its catalog and new capabilities are proposals;
they do not change the v1 behavior or existing role strings documented here.

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
Conditions are `eq`, numeric `lt`, `bit_test`, `not`, and `and`. `lt` compares
mathematical values under their declared signedness; boolean operands are
invalid. It is an additive primitive used by the direct AGI scalar lifter.
A failed `require` refuses
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
It is not a general decompiler, complete UDL mapper or UDC.

The [direct AGI module](DECODER_MODULES.md) also lowers supported acyclic scalar
components into these nodes. Logic calls, source traces and component boundaries
are recorded in its projection wrapper rather than adding AGI-specific opcodes
to shared IL. A boundary inside a callee ends the component with the caller
suspended. Host plans, original-runtime execution and model checks retain their
separate qualification requirements.

## Compact shared continuations

The opt-in `fdisbull-il-2` document keeps the same roles, typed variables,
resources and evidence. It replaces top-level `body` with `entry` and a
`continuations` map. Each named continuation has one ordered `body` of existing
primitives and a `transfer`. Bodies and continuation IDs are globally distinct.

```json
{
  "format": "fdisbull-il-2", "role": "uil",
  "variables": {"$x": {"type": "u8", "initial": 0}}, "resources": {},
  "entry": "first",
  "continuations": {
    "first": {"body": [{"id": "inc", "op": "add", "var": "$x", "value": 1}],
              "transfer": {"op": "goto", "target": "done"}},
    "done": {"body": [], "transfer": {"op": "return"}}
  }
}
```

Transfers are `goto` with `target`, `if` with an existing `condition` and named
`then`/`else` targets, `call` with `target` and `resume`, `return`, and global
`stop`. A return pops the runtime continuation stack or completes at root.
A stop completes the selected component and retains the suspended stack; it
does not resume any caller. A null call `resume` admits no return continuation:
a stop still works, but an unexpected return refuses atomically. This permits
a proven nonreturning captured component without inventing its caller's body.

References and all bodies, including inactive/unreachable ones, are checked
once as a graph without expanding branch paths. The 64 KiB document, 1,024-node
and depth-32 limits remain. Nodes include continuations, body primitives and
conditions; graph edges do not increase structural nesting. `execute_il`
counts both entered continuations and executed body primitives against
`max_steps`, and has keyword `max_call_depth` (default 8, range 1..64) for v2.
Generic cycles are bounded by execution limits; the AGI semantic lifter still
refuses source cycles and recursive logic calls. No loop-termination claim is
made. Failure preserves the original state with no events or partial trace.

Successful `visited` includes continuation IDs and body IDs, with repeated IDs
when a shared continuation runs again. `control_trace` records each entered
continuation and suspended resume stack; final `control` records its location,
stack and `stop` kind. Host effects retain v1 pending-plan behavior, including
unchanged committed state until an external host resolves the plans.

V2 adds `opaque` body blocks with a nonempty `reason` (at most 256 characters)
and optional evidence. They preserve unsupported source effects for inspection.
An opaque block anywhere in the document makes execution refuse **before any
state change or event**, regardless of selected path or host capabilities.
Validation of such a document is structural, not semantic qualification.

`il-check`, `il-run`, `change_role` and immutable IL revision storage accept v2.
Existing scene execution and source-block/UDC equivalence consumers explicitly
require v1; they do not ignore continuation tables. Neither format adds an AGI
renderer, engine-effect implementation, compiler backend or complete game.

## Explicit object/resource effects

V2 also admits a top-level continuation-body `effect` primitive with a fixed
`contract`, named `action`, typed `args`/`outputs`, source `binding` digest and
optional evidence. The first built-in is the explicit
`fdisbull.agi.object-resource.2.917.v1` contract. No input file can import a
Python handler. Effect ports nested inside a body `if` are refused; source
branches use continuation transfers. V1 remains unchanged.

`execute_il(..., effect_context=CONTEXT)` uses private snapshots and captured
resource metadata. Immediate operations affect a model transaction. Draw,
erase and print can return `pending_host`, a `host_request` and a JSON
`checkpoint`; no host command is sent by the evaluator. Later model instructions
do not run until a matching explicit `host_result` is supplied with that
checkpoint. The checkpoint binds program bytes, state, resource context,
continuation, stack and cumulative budgets. Readback without a result is
idempotent. A fresh CLI process can resume it.

During suspension, `state` and `effect_context` are the model's uncommitted
baseline; `proposed_state` and `proposed_effect_context` show modeled progress.
This does not say that an external host rolled back an action. Supplied
completion claims remain in `host_completions`; a later model failure preserves
them, reports `recovery_required`, and exposes last modeled values. Reconcile
the host before retrying a route. These claims are caller-provided and are not
native execution evidence. Checkpoint checksums provide ordinary integrity
checks, not authentication or tamper-proof authorization.

`il-run` accepts `--effect-context`, `--checkpoint`, `--host-result`,
`--max-steps` and `--max-call-depth`. Pending/refused runs return exit code 1;
read the structured status. Save private checkpoints and artifact-backed
responses outside Git. A model `complete` result still has
`native_execution: false`. The [AGI effect contract](AGI_EFFECTS.md) describes
the bound operations and remaining renderer/scheduler gates.
