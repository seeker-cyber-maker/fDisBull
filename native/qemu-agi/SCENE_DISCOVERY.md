# Static scene discovery from the AGI processor

The AGI CPU supplies instruction facts; the host analyzer chooses which source
addresses to visit. `processor_discovery.py` follows the native successors from
declared LOGIC entries and collects source-linked scene candidates. It uses no
Python AGI opcode table, instruction parser or guest interpreter. This is a
separate contract from the [observed scene planner](PROCESSOR_RECORDS.md), which
still requires a complete, coherent native history for its supported fragment.

The result is useful before a whole LOGIC can execute under the native pilot:
it identifies scene setup sites, their branch structure, direct resource
references and the specific unknown inputs needed to select a scene. It does
not resolve branch outcomes, assemble competing setup paths into one pose, or
assert that a referenced resource was loaded or displayed.

## Native facts and executable support

Current [processor pages](PROCESSOR_RECORDS.md) identify the fixed
`agi-2.917` encoding and `structural-1` policy. Structural descriptions cover
more commands and larger IF blocks than the native execution pilot. They keep
exact code bytes, typed operands, ordered condition tokens and local successor
facts together. Catalog-only commands explicitly retain unmodeled effects.

The structural catalog reuses the project's existing AGI layout/name facts;
the native parser remains the authority for this output. The legacy Python
scene decoder and its value propagation are not used by this path. In
particular, native IF displacements remain unsigned and GOTO displacements
remain signed. The context-dependent `trace.on` layout remains a decode
boundary under this fixed profile.

Execution continues to use the existing scalar/position, VIEW-binding and
deferred-draw profiles. More complete static descriptions do not add execution
semantics, native drawing, screen presentation or a complete AGI interpreter.

## Reachability contract

The default seed is raw-code PC zero. Explicit seeds are caller declarations,
not evidence that an engine entered them. The analyzer follows only edges
returned by the native decoder and deduplicates work by exact source identity
and PC. It preserves both IF branches and their ordered conditions without
evaluating either outcome.

Linear page reads may prefetch instructions past a return or onto an
unreachable path. Those rows remain page evidence; they do not become reached
nodes or scene references unless native edges or an explicit seed reach them.
A prefetched decode fault likewise affects local closure only if traversal
reaches its PC. A page obtained at an explicit target is not invalidated merely
because a different speculative listing crosses that target.

| Native edge or boundary | Discovery meaning |
| --- | --- |
| `fallthrough` | Possible next local instruction described by a modeled operation. |
| `true`, `false` | Both structural IF outcomes are retained; feasibility is unknown. |
| `branch` | Encoded GOTO target, with range information preserved. |
| `assumed_return` | Possible local continuation if an external LOGIC call returns. Its target is a separate typed LOGIC reference. |
| `assumed_fallthrough` | Next encoded instruction after an unmodeled operation, with continuation explicitly assumed. |
| Return or room transfer | No local continuation is invented. |
| Out-of-range target, reached decode error or missing description | Explicit unresolved frontier; local decoding is incomplete. |
| Reached overlapping instruction extents | Both source descriptions and the conflict remain visible; local decoding is incomplete. |
| Budget exhausted | Remaining demanded work stays in the frontier. A bounded stop is not stability. |

Exhausting the worklist establishes only the reported local structural closure.
It does not prove branch feasibility, that a callee returns, that engine cycle
entry remains PC zero, or that a game scene is complete. Scan-entry operations
and unknown effects remain visible dependencies.

## Scene candidates

The artifact uses `fdisbull-agi-native-scene-candidates-1`. It carries native
source/decoder identity, declared roots, reached instruction nodes, edges,
ordered conditions, resource references, scene-operation sites, budgets,
coverage and unresolved frontier entries. Original source mappings identify
the corresponding LOGIC resource and payload addresses separately from the
raw CPU input's `logic_id: 0`.

| Candidate input | What the output establishes | What it does not establish |
| --- | --- | --- |
| Literal VIEW, picture, sound, LOGIC or room operand | This exact source site encodes that resource/domain reference. | Resource availability or use during an actual run. |
| Variable resource operand | The semantic role and variable index are known. | Its historical value or selected resource. |
| Animated actor operand | A scene operation reads or affects that actor ID. | A committed actor state, visibility or draw completion. |
| Inventory object operand | The source references an inventory object. | An animated actor with the same numeric ID. |
| Position, loop, cel or priority input | Encoded inputs for that source operation. | That the branch ran, or that later operations preserve the value. |
| Ordered IF predicates, including `said` words | Condition structure and exact encoded inputs. | Parser matches, predicate truth, or stateful side effects. |
| Call or unmodeled command | A boundary requiring external semantics or state. | Preserved incoming variables or actor values after the operation. |
| Draw/show site | A possible presentation request in source. | Pixels or screen presentation. |

No variable propagation is performed. Even an earlier literal assignment does
not cause the consumer to substitute a value into a later symbolic resource
operand. This keeps the first discovery pass small and avoids a second AGI
interpreter. A later qualified analysis can reason over the native operations
and explicit unknown effects.

Source-linked alternatives are intentionally retained as separate sites. A
consumer can inspect the graph and choose a branch with explicit assumptions,
or collect runtime evidence for the missing condition. It must not take the
union of alternative resource/actor setup sites as one observed scene.

## Full-resource capture

`processor_discovery.logic_input(payload, logic)` reads the two-byte
LOGIC code-length header, verifies the extent, and binds the exact code to the
complete original payload identity. It does not parse instructions or infer a
game version from a filename.

`capture_logic()` owns one stopped scalar-profile CPU. It requests native
metadata and checks the complete state and retained events before and after.
It never calls the guest run operation. For example, from a source environment
with `native/qemu-agi` and the application packages on the import path:

```python
from pathlib import Path
from processor_discovery_trial import capture_logic

capture_logic(
    "/private/qemu-system-agi",
    Path("/private/logic-5.payload").read_bytes(),
    5,
    "/private/new-logic-5-discovery",
    expected_binary_sha256="<exact qualified binary SHA-256>",
)
```

Outputs include the native instruction pages, scene candidates, before/after
metadata evidence, a capture report, exact raw-code input and original source
mapping. A source identity mismatch or changed guest state fails the capture.
Failures retain their output; the capture has no automatic retry.

The native input keeps its raw-code identity and selected execution profile.
The original LOGIC number, complete resource SHA-256 and code payload span
belong to the resource mapping. A LOGIC number is not evidence that a
particular picture was selected. In the PQ1 LOGIC 5 and KQ1 LOGIC 53 development
cases, the picture operations read `v0`; that input remains unresolved.

### Finite work

| Limit | Maximum |
| --- | ---: |
| Raw source bytes | 65,536 |
| Declared roots | 16 |
| Rows per native page | 64 |
| Native pages | 128 |
| JSON per native page | 8 MiB |
| Admitted JSON across native pages | 32 MiB |
| Decoded rows, including prefetch | 4,096 |
| Reached nodes | 4,096 |
| Local edges | 8,192 |
| Resource/input references | 32,768 |
| QMP timeout per operation | 5 seconds |
| Resource capture traversal deadline | 30 seconds |
| Guest runs | 0 |

Smaller caller budgets remain explicit in the result. A page that exceeds the
remaining aggregate JSON allowance is recorded as a budget frontier and
contributes no admitted rows. Received bytes can therefore exceed the admitted
budget by that one rejected response; both totals are reported. Reached
overlaps retain one conflict witness per node rather than enumerating every
pair of overlapping descriptions.

The acquisition deadline covers recursive reads. Launch, final state/event
neutrality reads and teardown remain finite phases owned by the surrounding
process gate, which also retains child identities and reaps its children.

## Scene reconstruction and later UIL

The full-LOGIC graph makes setup discoverable without manually selecting a
straight-line fragment. PQ1's initialization has alternative VIEW loads and
actor cel choices, followed by an indirect helper call. KQ1's setup includes
an entry-dependent ego position and actor 14's binding, draw and cycling sites.
The graph preserves these distinctions; saved fragment observations remain
evidence about their own recorded setup, not execution of the containing
LOGIC or its surrounding branches.

The [conditional scene-binding adapter](SCENE_BINDINGS.md) consumes these
records with explicit path choices, variable values at individual use sites,
and declared values for missing actor fields. It stops at unknown effects or
calls and keeps the requested pose separate from effective guest state.
Fully bound selected layers can use exact picture/VIEW assets and the existing
Sarien compositor. Position repair additionally needs actor flags, peers and
other scene policy; the conditional adapter does not infer those inputs.

The native semantic operation names, typed inputs, source addresses and effect
boundaries provide the intended seam for later direct UIL emission. This
increment does not introduce another intermediate instruction language or
attempt to recover UIL from generated TCG. Unknown operations will need
semantics before stronger recompilation or equivalence claims are possible.

fDisBull and DotBox can consume the same optional evidence. fDisBull applies its
recovery/recompilation acceptance criteria; DotBox uses enough information for
the next useful harness step. Their boards, live-session ownership, normal
backend choices and independent QEMU parity qualification remain separate.
