# Explicit scene inputs over native instruction facts

`processor_scene_binding.py` turns a selected path through the CPU's static
instruction records into a conditional scene-design recipe. It reuses the
[native discovery contract](SCENE_DISCOVERY.md), accepts explicit source-use
bindings and records ordered scene requests. It does not decode AGI opcodes,
evaluate predicates, propagate guest variables or execute a guest.

The result is a design input. A source command requesting a position or VIEW
does not establish an effective actor state. Animation resets, setter
normalization, motion, collision, callbacks, timing and screen presentation
remain outside this adapter. The existing observed scene planner and native
execution profiles retain their separate contracts.

## Public API

```python
from processor_scene_binding import derive_bound_scene_recipe

recipe = derive_bound_scene_recipe(
    code=exact_raw_code,
    pages=saved_native_pages,
    source_mappings=exact_source_mappings,
    resource_mapping=original_logic_mapping,  # or None for authored fragments
    entry_pc=declared_entry,
    endpoint={"pc": selected_pc, "phase": "after"},
    branch_choices={if_pc: "true"},
    operand_bindings=[{
        "pc": picture_use_pc, "operand_index": 0,
        "variable": 0, "value": selected_picture,
        "reason": "Explicit background choice for this design",
    }],
    actor_inputs=[{
        "actor": selected_actor,
        "fields": {"loop": 0, "cel": 0, "priority": 4},
        "reason": "Explicit endpoint design inputs; engine defaults unqualified",
    }],
    max_steps=4096,
)
```

The adapter validates native pages against the exact raw bytes and preserves
the decoder identity and original source mappings. Instructions, operands and
successors come from those pages. A full resource mapping retains the original
LOGIC number and complete payload SHA-256 separately from the native raw-code
identity. Neither number selects a picture implicitly.

### Selection and binding rules

| Input | Meaning and validation |
| --- | --- |
| `entry_pc` | An explicit caller-selected address. It need not be PC zero and does not prove an engine entry or the execution of any preceding source. |
| `endpoint` | Stop before or after one exact source instruction. A before endpoint retains the next native row but does not apply it or consume its operand bindings. |
| `branch_choices` | Integer IF PCs mapped to their native true/false edge. Conditions remain ordered source facts; their truth and the feasibility of the combined path are not evaluated. |
| `operand_bindings` | One value for one action operand use, identified by PC, operand index and matching variable index. Reads at different PCs need separate inputs. Predicate operands are not accepted here. |
| `actor_inputs` | Missing-only endpoint design fields. They cannot replace a source-explicit field, even an equal literal or an unresolved variable request. Resolve the latter through its exact operand binding. |
| `reason` | A nonblank caller explanation, at most 512 characters, retained with the binding. It is provenance for an assumption, not runtime evidence. |

Duplicate input records, invalid ranges, source/decoder conflicts, unsupported
field names and stale or unvisited choices/bindings fail with `HarnessError`.
Actor inputs must name an actor with a projected operation on the selected
path. Inputs for a barrier's own typed operands are consumed and preserved;
inputs beyond the barrier are unvisited and fail. A requested before endpoint
takes precedence over interpreting the instruction at that boundary.

Scalar and flag operations remain in the timeline without evaluation. For
example, an earlier `assignn` does not supply a later variable value, and a
reset after a variable position use does not rewrite that earlier use. This
also means explicit branch selections and operand bindings may describe an
infeasible execution. The recipe makes no feasibility claim.

## Scene requests and actor fields

The adapter projects this deliberately small scene-design subset:

- Actor position and reposition-to requests, VIEW/loop/cel/priority requests.
- Animate, draw, erase and start/stop-cycling requests.
- Picture draw and show requests.
- Resource load/discard references, with their original ordering retained.

Other actor or host-scene operations stop the selected path. Resource requests
do not establish that assets exist or that a load completed. Discarding a
picture resource does not erase a previously requested background. Asset
availability and rendering belong to the separate preview consumer.

Each actor field has `{value, provenance}`. Source fields use
`basis: native_requested` and retain the operation, PC, source mapping and
operand index where applicable. A resolved variable adds its exact caller
binding. An unresolved read has `value: null`,
`basis: unresolved_variable_request` and its variable index. There is no
fallback to an earlier field value when a later request is unresolved.

Endpoint design fills use `basis: caller_declared_design_input`, the caller's
reason and `scope: selected_endpoint`. They may represent an assumed inherited
appearance, but the adapter does not establish that an engine preserved those
values through animate or setter operations. Loop and cel are never silently
set to zero. The allowed fields are `view`, `loop`, `cel`, `x`, `y`, `priority`,
`animated`, `cycling` and `draw_requested`. The last three are strict booleans.
Caller numeric fields are unsigned bytes, except priority, which is 0–15.
Encoded source requests retain their native numeric domains without applying
engine clamping or normalization.

`missing_fields` lists absent or unresolved render inputs among VIEW, loop,
cel, x, y and priority. A selected endpoint may be reached with missing inputs;
that status describes the selected path only. It does not establish a complete
scene or make every actor renderable.

### Chronology is part of the result

The path and timeline include a described before-endpoint or barrier row even
though that row is not applied. `timeline.projection` distinguishes
`endpoint_before` and `barrier` from projected or retained instructions. A
missing native description or decode fault has no instruction to append; its
address remains in `endpoint.stopped_pc` and the frontier.

The timeline keeps every visited native instruction unchanged, with separately
resolved action operands. Draw requests capture a deep copy of the source-only
requested pose at their own PC. Later field changes and missing-only endpoint
fills do not rewrite that draw-site snapshot. Endpoint actor fields and
draw-site fields therefore remain distinguishable.

`draw_requested` describes source requests, not observed visibility. Erase
changes the endpoint request field to false while preserving earlier draw
history. A renderer must not infer a current draw from the existence of an old
draw request. An explicit designer-selected layer can still be useful without
any source draw; that selection needs its own provenance and must not become
an alleged source request.

## Boundaries and finite work

Unknown effects, external LOGIC calls, room transfers, assumed successors and
unsupported scene operations stop before effect application. Their native row, typed
operands and source mapping remain available. A call binding can identify its
declared target, but does not establish return or a preserved post-call pose.
A room transfer similarly does not establish dispatch, entry resets or a
preserved destination-room pose. Selecting an after endpoint at either boundary
does not bypass that stop; a before endpoint remains available.
No option silently ignores such a boundary.

Missing native records, reached decode faults, overlapping selected instruction
extents, out-of-range edges, missing branch choices and exhausted step budgets
also produce an explicit frontier. A repeated PC stops the path; this adapter
does not unroll loops. Prefetched instruction extents that the path never
selects do not invalidate it. Conflicting native descriptions of one PC remain
an input error.

The maximums are 65,536 code bytes, 128 pages, 4,096 native rows, 8 MiB JSON per
page, 32 MiB page JSON in total, 4,096 selected steps, 28,672 operand bindings
and 256 actors. Smaller step limits are retained in the output. No guest,
subprocess, build, filesystem write or network request is started by this API.

## Detached selected-layer preview

`processor_scene_preview.py` supplies the separate asset and composition
adapter. `prepare_preview_assets()` takes one explicit picture resource, an
explicit VIEW inventory and selected loop/cel requests. Each resource record
contains `kind`, `number`, `volume`, `offset`, `length`, `sha256` and immutable
`payload` bytes from a verified resource extraction. Its existing picture and
VIEW readers recover the indexed planes, cel dimensions, transparency and
mirroring. No LOGIC parser is involved.

`preview_bound_scene()` accepts an already prepared Sarien-compatible kernel
and composes caller-selected layers in their declared order. For example, after
binding the KQ1 actor-14 initialization recipe described below:

```python
from processor_scene_preview import prepare_preview_assets, preview_bound_scene

assets = prepare_preview_assets(
    source_scope={
        "basis": "caller_declared_resource_scope",
        "logic": recipe["resource_mapping"]["logic"],
        "logic_resource_sha256": recipe["resource_mapping"]["resource_sha256"],
        "reason": "Explicitly selected resources from this private target inventory",
    },
    picture_resource=verified_picture_resource,
    view_resources={53: verified_view_53_resource},
    cel_requests=[{"view": 53, "loop": 0, "cel": 0}],
)
preview = preview_bound_scene(
    existing_sarien_kernel, recipe, assets,
    layers=[{"actor": 14, "selection_basis": "selected_path_draw_request"}],
)
```

The preview requires a reached endpoint and an original full-resource mapping;
its caller-declared asset scope must match the mapped LOGIC identity. All input
payload identities and derived asset bytes are rechecked before composition.
The resource-scope declaration does not establish publisher authenticity or
observed use of those assets. Prepared bundles retain original bytes and belong
only in the private evidence workspace.

The selected background must match the last processed `scene.draw_picture`
request, if one exists. An unresolved source picture selection, a mismatched
background or contradictory source request is rejected. A fragment with no
picture draw may use an explicitly chosen background; the output preserves the
absence of a source picture witness.

Each selected actor needs resolved VIEW, loop, cel, x, y and priority. Selection
basis `selected_path_draw_request` additionally requires a draw on this path,
an endpoint draw request that has not been erased, and no changed render fields
since the last draw. Missing draw-site fields may only be supplied by explicit
endpoint design inputs. `explicit_design_layer` permits a deliberate layer
without a source draw and retains that weaker basis. Unselected actors appear
in `omitted_actors`, including an ego actor whose inherited appearance is still
unknown.

The preview retains the binding contract's inventory of at most 256 actor IDs
0–255, while each composition selects at most 16 ordered layers. This layer
count does not narrow the CPU record's actor domain or require every known
actor to be rendered. Assets are bounded to 16 VIEW resources, 128 cels and
4 MiB of cel pixels. Composition uses a 160×168 indexed canvas and a lower-left
baseline. The complete cel must fit in bounds; there is no clipping or position
repair. Priority composition can hide a selected layer, but that compositor
result is not proof of original-game visibility. Missing assets or fields,
changed/erased draw poses, mismatched backgrounds and out-of-bounds placements
are rejected before any blit.

The returned visual and priority planes are a conditional selected-layer
preview. They do not establish native draw completion, engine position repair,
an observed room, screen presentation or a complete scene.

## PQ1 and KQ1 development cases

The following addresses describe the qualified development inputs, not other
editions or the held-out games. Exact source identity remains a required input.

| Case | Useful finite selection | Explicit limits |
| --- | --- | --- |
| PQ1 LOGIC 5, original entry | Select the PC-0 initialization branch and the required conditions through picture setup. The strict path stops at the unmodeled `set.string` at PC 64. | PC 67 is another unknown boundary. Later actor setup cannot be called a continuation of this prefix without more semantics or new explicit inputs. |
| PQ1 LOGIC 5, actor design segment | Declare a fresh entry at PC 143. Select the inventory-dependent cel edge at PC 161 and the helper-test edge at PC 190, bind the LOGIC use at PC 197, and stop before the call at PC 199. | Actor 8 requests VIEW 65, loop 1, position (94,84), priority 4 and needs a selected cel. Actor 5 requests VIEW 65, loop 2, cel 0 or 1, position (99,86), priority 9. Neither actor is drawn in this segment. Preview layers require `explicit_design_layer`, and the background is independently declared. |
| PQ1 LOGIC 5, call diagnostic | Request an endpoint beyond PC 199 and separately bind the variable LOGIC use at PC 199. | The bound callee target is retained, but the path stops at the call. No post-call actor state or return is inferred; blocked recipes cannot be previewed. |
| KQ1 LOGIC 53, initialization | Select PC 0 true and either PC-18 placement edge; bind each picture use at PCs 6, 8 and 10; stop after the show-picture request at PC 58. | Actor 14 requests VIEW 53 and position (30,90), draws at 52 and stops cycling at 54. Its loop/cel/priority still need explicit design inputs. Actor 0 lacks a local VIEW/loop/cel/priority request and, on the PC-18 false branch, a local position. It can remain omitted from a selected actor-14 preview. |

An example choice of picture 5 for PQ1 or picture 53 for KQ1 is a declared
resource input, not a deduction from the LOGIC number. Likewise, loop/cel zero
and a chosen rendering priority are visible designer assumptions. Differences
between branch variants remain separate recipes; they are not combined into a
single alleged observed pose.

## Output contract

The schema is `fdisbull-agi-bound-scene-recipe-1`. Its top-level fields are:

| Fields | Content |
| --- | --- |
| `source`, `decoder`, `resource_mapping`, `source_mappings` | Exact native and original source identities. |
| `entry`, `endpoint`, `status` | Caller entry; requested before/after endpoint; actual stopping address, reason and optional native boundary row. Status is `selected_endpoint_reached` or `blocked`. |
| `path`, `timeline`, `branches` | Ordered selected addresses and native facts, resolved action operands, selected edges and untouched condition tokens. |
| `operand_bindings`, `actor_inputs` | Consumed source-use bindings and explicit endpoint design inputs. |
| `actors`, `draw_requests` | Endpoint requested/design fields and separate source-only draw-site snapshots. |
| `scene_requests`, `resource_requests` | Projected picture requests and typed resource uses, with boundary uses marked `at_barrier`. |
| `required_inputs`, `frontier` | Unbound scene operands/actor fields, missing branch selections and the actual stopping boundary. |
| `budgets`, `usage`, `coverage` | Finite limits, consumed counts and the deliberately limited qualification. |

Every result has `qualification: conditional_designer_recipe` and false values
for `runtime_observed`, `native_draw_completed`, `presentation_established`
and `effective_actor_state_established`. Coverage explicitly retains unknown
interprocedural effects, absent state propagation, unevaluated branch
feasibility and unmodeled implicit setter effects.

The native decoder remains the owner of instruction facts and the intended
future UIL seam. This adapter does not create a competing instruction language
or infer executable UIL from a composed image. Its projection policy can be
used by both fDisBull and DotBox while their acceptance criteria and separate
boards remain unchanged.
