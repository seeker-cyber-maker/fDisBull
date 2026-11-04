# Zork / Z-machine providers and debugger probes

## Decision and scope

Keep the existing in-house Zork execution path. Add ScummVM GLK/ZCode as a
separate, optional comparison provider, not as a replacement for that path and
not as part of Kyra. The Z-machine guest processor, fDisBull's agent-facing Z
interface, game-intent UIL and presentation shells are distinct layers.

This contribution provides an executable Python debugger probe over the
unchanged word16 consumer, a strict client contract for a future native
ScummVM ZCode peer, and an internal comparison runner. **It does not contain a
ScummVM C++ bridge, launch a GLK interpreter, or register a production backend.**
The client tests use explicitly labeled peers; they do not qualify ScummVM.

Reviewed fDisBull main: `242e5343f5aa55dec95af3a49668a71ae14982c6` (0.31.1).
This is an additive branch on main, not a modification to the AGI/Gob or Kyra MRs.

## What already exists

| Component | Code / documentation | Existing responsibility |
| --- | --- | --- |
| Static Z-machine v3 support | `zmachine.py`, `zmachine_processor.py`, `ZMACHINE_PROCESSOR.md` | Inspect headers, decode source instructions and traverse candidate control flow; no running VM. |
| Jericho/Frotz reference harness | `zork.py`, `zork_worker.py`, `ZORK_HARNESS.md` | Explicit external Python/native runtime, bounded command operations, passive observations and private checkpoints; current identity requires Jericho 3.3.1. |
| In-house executable IR | `zork_uil.py`, `player/fdisbull_player/word16.py`, `ZORK_UIL.md` | Lower the story ahead of time, then execute the resulting word16 graph without DOSBox, Frotz/Jericho, original DAT or a runtime opcode decoder. Original-derived game data still remains in the private package. |
| Recovered game intents | `intent_runtime.py`, `ZORK_INTENTS.md` | Qualified mailbox/discourse/turn primitives, joined to explicit residual IR. Not whole-game high-level intent recovery. |
| Recovered scene/interaction layer | `scene_runtime.py`, `ZORK_SCENES.md` | Named scenes, directional selection, live exit conditions, kitchen-window open/close behavior and explicit remaining handlers. |
| Agent-facing Z / text interface | Existing text host and player | Observation/action surface, not another Z-machine implementation. |
| Text asset and shell pilot | Draft MR !90, `examples/text_asset_pilot/` | Separate portable text assets, die/socket/provider contracts and terminal/JSON shells; reuses the word16 die. Not part of this implementation or a new interpreter. |

`zork-uil` retains a legacy command name. Its `fdisbull-uil-word16-1` output is
low-level executable IR, not a claim that every puzzle has become address-free
UIL. The higher-level intent and scene packages keep unrecovered behavior as
explicit residual IR rather than silently dropping it.

The existing `ZORK_UIL.md` reports historical full-score, Frotz and DOS checks
for release 88. Those dated results are not fresh tests of this contribution.
ScummVM observations likewise must retain their own provider identity instead
of being relabeled as original DOS execution.

## Working internal debugger probe

`make_word16_probe(program, story, seed=12, random_tape=None)` lazily imports the
optional standalone player and delegates every executed block to its unchanged
`Word16Runtime.run(max_steps=1)`. It is instrumentation of the existing runtime,
not a second interpreter. Source identity includes trailing bytes, while the
execution image retains the declared story extent. Entry, writable boundary,
layout and initial memory must match the bound story. Package identity also
remains part of observations and checkpoint validation; a matching source hash
alone is not proof that arbitrary altered IR implements that source correctly.

The probe offers passive `observe()`, `peek_variable()`, guarded source-byte
breakpoints, removal, single/multiple block stepping, finite runs, capped trace
records, explicit input revisions and the baseline consumer's checkpoints.
Variable zero is a non-destructive peek into the *current routine's* evaluation
stack, never a call to the interpreter's destructive operand-read function.

```python
from pathlib import Path
from fdisbull.zmachine_probe import make_word16_probe
from fdisbull_player.word16 import load_program

story = Path('/private/ZORK1.DAT').read_bytes()
program = load_program('/private/zork1.ir.json.gz')
probe = make_word16_probe(program, story)
probe.breakpoint(program['entry'])
assert probe.run(max_steps=10000)['stop_reason'] == 'breakpoint'
probe.step()  # one lowered source block, not one native CPU instruction
result = probe.run(max_steps=1000000)
if result['status'] == 'input':
    observation = probe.observe()
    result = probe.command('inventory', expected_revision=observation['revision'])
```

The probe is single-controller/synchronous. Its host deadline is cooperative at
block boundaries, not a process-killing deadline. Per-run text/event aggregation
and trace storage are bounded. An output-budget fault latches until a qualified
checkpoint is restored. Breakpoints at a candidate offset do not by themselves
establish that offset is reachable. No save format portability to ScummVM or
original DOS is asserted. No FDB debug-run persistence or new CLI registration
is introduced here.

## Future ScummVM peer contract

`ScummVMZCodePeer` consumes an explicitly owned `call(op, params,
timeout_ms=...)` / `close()` transport. The caller must independently pin its
runtime executable; the hello repeats that expected SHA-256 and exact story
SHA-256. The client requires protocol `fdisbull-scummvm-zcode-probe-1`, engine
`glk`, subengine `zcode`, version 3 and `original_x86_executed: false`.

Required operations are `state.get`, `memory.read`, `run` and `step`. State reads
need a confirmed stop, explicit phase and monotonic revision. Memory replies
must echo the requested range/revision and exact bytes. A bounded execution
reply reports completed dispatches and a structured stop; the client never
infers completion of an outer callback from a nested dispatch count. An
ambiguous response/timeout closes the peer and is never automatically replayed.

This is a client-side contract only. Stock ScummVM and the AGI/Gob sidecars do
not implement it. Native breakpoints/watches, input/output events, native saves,
exact checkpoints and async pause are not implemented by this client. Do not
advertise `--backend scummvm-zcode` before a real launch/ownership path exists.

### Native integration seams to implement next

The reviewed upstream reference is ScummVM v2.8.1 at
`750f2373fb100efe08c6444e36b68c01387fc307`, matching the AGI/Kyra source reference,
not a claim about the newest ScummVM release. A different pin needs fresh review.

1. Reuse the owned inherited-socket transport pattern from MR !73. Add an
   explicit GLK/ZCode selection path; do not masquerade as `agi` or `kyra`.
2. In `engines/glk/zcode/processor.cpp`, instrument `Processor::interpret()`
   **before `CODE_BYTE(opcode)` and operand loading**. `load_operand()` can pop
   variable zero, so a hook after it is not an instruction-entry observation.
   Retain begin/end IDs and nesting for recursive `interpret()` calls.
3. Capture source-byte PC, current frame locals, live evaluation-stack bounds,
   globals and dynamic memory. Keep VM values distinct from host/native CPU
   registers and packed routine addresses. Do not invoke mutating accessors
   while collecting observations.
4. Instrument GLK line-input request/completion and text/window events. A printed
   `>` or an empty event queue does not prove readiness. Preserve memory output
   streams as guest memory effects, not only terminal text. Record window IDs
   and keep status-line presentation separate from game transcript comparison.
5. Use instruction, host-time, input and trace bounds. Service cancellation/EOF
   during input waits as well as instruction dispatch; prove child reaping.
6. Qualify the actual pinned binary with the owned story, then compare explicit
   boundaries with the internal consumer and original DOS. Do not assume equal
   seeds imply equal RNG sequences across providers. Use declared input tapes
   or compare a separately qualified RNG contract.

The C++ files were inspected, but **no native GLK build or patched game run was
performed**. ScummVM's source licensing remains distinct from first-party code;
keep any future derivative patch, notices and source-distribution obligations
explicit. This document does not supply licensing clearance.

## Comparison boundary

`StoryBinding.projection()` and `compare_prompt_states()` compare same-story,
same-command-index input boundaries. The scoped projection includes all dynamic
bytes after the 64-byte header and all 240 global words, whose values must agree
with those bytes, plus whitespace-normalized output. Missing/unknown fields,
wrong identities, incomplete memory and non-input boundaries are refused.

The header exclusion is explicit and excludes it from the claim, not an assertion
that every header difference is irrelevant. Stack, locals, RNG, host continuation
and output-stream state are absent from this portable projection. Consequently,
a match is not a full VM checkpoint or whole-engine equivalence. The internal
runner additionally compares *full baseline-compatible snapshots*, including
those fields, because those three implementations share a known state model.

`examples/zmachine_probe/compare_internal.py` compares unchanged word16, the
existing semantic scene runtime and the new probe at every boundary of the
repository's bounded house/window cases. Selected recovered bodies are trapped
if they fall back to retained IR. This verifies actual semantic substitution
for those cases; deliberate residual paths remain allowed and counted.

```sh
PYTHONPATH=src:player python examples/zmachine_probe/compare_internal.py \
  --story /private/ZORK1.DAT --ir /private/zork1.ir.json.gz \
  --scenes /private/zork1.scenes.json.gz --output /private/comparison.json
```

Use `--case house` or `--case window` for a smaller run. The output contains
aggregate evidence and hashes, not original game bytes or transcript text.
Private story, IR/scene packages, projections, snapshots and raw traces must stay
outside Git and public attachments. The final report is delivered separately.

## Verification and remaining gates

Run `python -m pytest -q tests/test_zmachine_probe.py` with the source and optional
player available. Tests use invented v3 programs and explicitly named protocol
peers. Real private acceptance is separate and does not make the ScummVM tests
native. The intended integration gate is a real pinned GLK binary exercising
entry stop, passive reads, bounded stepping, input completion, text events,
checkpoint policy and owner-EOF cleanup. Until then only the internal probe is
an executable engine-backed debugger path.

## References

- [Internal executable IR](ZORK_UIL.md), [reference harness](ZORK_HARNESS.md),
  [game intents](ZORK_INTENTS.md), [scene layer](ZORK_SCENES.md).
- [ScummVM processor source at the reviewed pin](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/glk/zcode/processor.cpp).
- [ScummVM GLK interface at the reviewed pin](https://github.com/scummvm/scummvm/blob/750f2373fb100efe08c6444e36b68c01387fc307/engines/glk/zcode/glk_interface.cpp).
- [Z-machine state, globals, stack and calls](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html).
- [Existing AGI/Gob sidecars, MR !73](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/73),
  [Kyra control scaffold, MR !88](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/88),
  [text asset/shell pilot, MR !90](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/90).
