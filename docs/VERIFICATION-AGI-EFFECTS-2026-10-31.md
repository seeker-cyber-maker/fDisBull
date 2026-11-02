# KQ1 logic-103 object/resource model: verification

2026-10-31. Follow-up to PR #72, based on exact head
`bd8cded9113cd4cae554b56982d4a668c3eda09a`. Engine development only: no release,
tag, merge or system installation change.

## Implemented seam

`module-lift --control-flow compact --effect-profile agi-2.917` lowers the
selected 22 source action encodings to 21 typed object/resource ports. Position
and position.v share a port. The projection is `object_resource_projection`;
the module descriptor is revision 4, with the existing revision-3 instruction
processor. The default scalar/tree projection is unchanged.

The [effect contract](AGI_EFFECTS.md) describes explicit snapshots, VIEW
geometry, message bindings and host requests. Supported immediate operations
model resource loading, view/loop/cel binding, clipping, positions, queries,
flags and motion-controller configuration. The evaluator does not advance an
independent tick or infer arrival. It refuses missing snapshots/resources,
unloaded view use, unbound draw geometry and unsupported motion/cycler overlap.
Invalid message IDs and unsupported narrowing are outside the admitted profile.

Draw/erase/print can suspend with a bound JSON checkpoint. No later instruction
runs until a matching caller-supplied host result is provided. Checks cover the
program, request, context, stack, body position and cumulative budgets; readback
does not replay the request. Those unkeyed checksums are not authentication,
and supplied results are not native completion evidence. A failed model stage
preserves earlier completion claims with recovery information instead of
implying an external action rolled back.

## Original-resource inputs and model corpus

The real private KQ1 logic 103 and VIEW 14 resources were captured read-only.
The explicitly assumed profile is DOS AGI 2.917; the successful parse does not
fingerprint the original interpreter. The resource loader captured view 14's
four loops and 20 cels and decoded the logic's two hash-bound messages. Original
pixels/message text, source-retaining projections, contexts and checkpoints are
not distributed. VIEW parsing checks headers, offsets, dimensions and RLE bounds;
it is not a pixel renderer or proof of original runtime correspondence.

The graph retains 111 continuations and 12 shared joins. All 56 former opaque
sites become typed effects, covering 22 source opcodes; zero opaque actions
remain. The IL is 63,778 bytes under the unchanged 65,536-byte bound. Repeated
optional instruction-kind labels are omitted, while source bytes, digests,
coordinates and source-entry mappings remain intact.

The corpus contains 384 seeded synthetic frames and 88 guided synthetic
supplements. They vary declared flags, scalar values, initialized object
snapshots and distances. The supplement includes completed-controller frames
and a counter value before its source decrement. No code branches were forced,
production handlers patched, or initial values inferred from original gameplay.

A separate coordinating-agent replay used those saved inputs, genuine Python,
the public evaluator, JSON checkpoint round trips and explicit synthetic host
results. It reproduced the coverage and completion counts:

| Observation | Result |
| --- | --- |
| Model cases | 472 complete; zero refusals or unresolved requests |
| Effect sites visited | 56 / 56 |
| Branch outcomes observed | 44 / 44 across 22 source conditions |
| Supplied draw results | 183 |
| Supplied print results | 26 |
| Supplied erase results | 1 |
| Stable request/checkpoint readbacks | 210 |
| Recorded completion claims | 210 |
| Native execution claimed | None |
| Original inputs | LOGDIR, VIEWDIR and all three VOL hashes unchanged |

Draw responses used geometrically bounded fixture positions. Collision safety,
rendered pixels, dialogue completion and timing were supplied assumptions, not
observations of the original engine. These are **model self-consistency and
coverage checks**, not an independent state/effect oracle. All-site/all-branch
coverage under interventions does not prove those inputs are reachable in the
original game or establish state, visual, scheduler or whole-game parity.

The [sanitized receipt](evidence/agi-effects-2026-10-31/receipt.json) contains
counts, input/output/implementation digests, scope and integrity results. The
private case inputs and detailed outputs remain outside Git.

## Authored regression checks

Fresh CPython 3.13.13/macOS ARM64 focused suite: **397 passed, 1 skipped**. The
skip requires a case-sensitive filesystem. The suite covers new effects,
resources, suspension and existing AGI/IL/decoder/processor/scene/UDC/proof,
CLI, revision storage, distribution and bundled-skill checks.

Controls include:

- All 22 source-opcode lowerings, with typed arguments and query outputs.
- Position without guessed clipping, set.view clipping and valid loop/cel
  retention, odd-width distances, drawn/unavailable objects and saturation.
- Flag resets/idempotence, ego control, controller initialization and refusal
  of unknown overlap or geometry.
- Draw/erase/print suspension, both print modes and timer handling, aliased
  get.posn writes, and no later instruction before a host result.
- Wrong requests, invalid acknowledgements, changed programs/checkpoints,
  missing inactive bindings and cumulative budget exhaustion.
- Preservation of caller completion claims after a later model failure.
- Saved JSON checkpoints resumed in a fresh real Python `-S` CLI process,
  including source-call stacks and stopped-callee continuation behavior.
- Authored VIEW/RLE and encrypted-message fixtures, bad bounds/offsets and
  unchanged source-file hashes. No replacement decoder libraries were used.

## CI and remaining qualification

PR #72's canonical exact-head workflows passed:
[ordinary](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41195286745),
[native](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41195286747).
The complete native gate includes stable/layers and installed-wheel PE64 plus
DOS/QEMU/boot acceptance. No failure required a patch. This follow-up needs its
own exact-head CI before integration.

A real host adapter, renderer/collision execution, independent movement/time
cycles, original-interpreter differential runs and target UDC generation remain
separate gates. The evaluator sends no native/GUI commands. No game files,
saved states, project databases or raw private deliveries entered this PR.
