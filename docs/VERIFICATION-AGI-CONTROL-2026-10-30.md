# Direct AGI scalar control and calls: verification

2026-10-30. Follow-up to PR #67, based on
`7bf8c1abe7376853925ac7aba29fef11d04dc813`. This is engine-development work;
no tag, release or system update is part of it.

## Source and behavior contract

The AGI module/processor contract revision is `2`. Direct source lifting now
supports scalar comparisons 1–7, pure AND/OR/NOT, acyclic if/goto graphs,
explicitly captured direct logic calls and the scalar arithmetic/flag operations
needed by that profile. Shared IL adds numeric `lt`; variables remain u8 and
flags bool. Increment/decrement saturate; byte add/sub wrap. Both conditional
paths are checked, including paths inactive for the supplied initial witness.

Cached callee scan entries are explicit caller assumptions, not guessed zeroes.
Nonzero entries and stop points must also be candidate boundaries established
by known encoded paths from code zero. Operand bytes cannot be relabeled as
entries. Boundary metadata records the resource digest, processor revision,
work and unresolved paths with `runtime_observed: false`. Unknown lengths and
exhausted proof budgets refuse entry qualification.

Calls use an explicit source return stack. Each returning callee path resumes
the correct caller instruction. A declared stop inside a callee ends the entire
component, preserving its reached scalar effects and the suspended caller stack;
it does not invent a return or run that caller's continuation. Source-model
traces retain instruction-entry markers. Root/callee resource captures must
share consistent LOGDIR and VOL snapshots.

This change also fixes an inherited decoder issue: IF false skips were sign
extended. They are unsigned 16-bit offsets, while GOTO displacements are signed.
The regression uses a `0x8000` IF skip and an acyclic backward GOTO. The nominal
rules were checked against pinned ScummVM
[predicate/control handling](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_test.cpp#L362-L441)
and [command handling](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_cmd.cpp).

## Original-resource component checks

The private PQ1 and KQ1 LOGDIR/VOL copies were read without opening a native
project, game executable or original interpreter. An independently authored
raw-byte AGI scalar interpreter compared generated IL under declared test
states. It does not call the production decoder/lifter/evaluator to execute
the source semantics. Candidate selection and container capture remain separate
from that reference execution.

| Check | Evidence |
| --- | --- |
| Real branch components | 13 sites: 8 PQ1, 5 KQ1 |
| State/source-trace/stop-stack comparisons | 4,352; all byte values for the first variable and 0/127/255 for a second variable where present |
| Boolean forms in these sites | NOT is present; OR is covered by separate authored controls |
| Mutation controls | 13 inverted-condition IL mutants detected |
| PQ1 call component | Logic 82 at code offset 23 calls logic 81, stopping at callee code offset 0 |
| KQ1 call component | Logic 27 at code offset 92 calls logic 103, stopping at callee code offset 0 |
| Full game callee admission | Removing those explicit stops refuses both unsupported callee bodies |
| Input integrity | Every inspected LOGDIR/VOL hash unchanged; source implementation hashes stable during the comparison |

The bounded call components verify source transfer and suspended caller
continuations, not full callee execution. No complete original-game direct-call
graph qualified under this scalar subset. Full call/return, multiple callee
returns and branch-specific callee stops are verified with authored resources.
The declared cached entry of zero in the real-resource probes is an assumption;
it was not read from a running interpreter.

The public [sanitized receipt](evidence/agi-control-2026-10-30/receipt.json) retains
component coordinates, counts, controls, oracle digest and source-code digests.
The independently authored reference is inspectable in
`tests/agi_scalar_reference.py`, with authored controls in the test suite. Its
private-input driver, original-resource digests, raw model traces and test
states remain private. These results establish nominal source-model-to-IL
agreement, not original-interpreter execution, game progress or whole-game
parity. Parser/I/O predicates, dynamic calls, recursion, loops and unsupported
engine effects remain unqualified.

## Automated checks

Fresh CPython 3.13.13/macOS ARM64 in a separate private development environment
(also checked earlier with CPython 3.13.17):

```text
python -m pytest -q -p no:cacheprovider \
  tests/test_agi_control.py tests/test_agi_control_proof.py tests/test_agi_reference.py \
  tests/test_decoder_modules.py tests/test_agi.py tests/test_agi_lift.py \
  tests/test_agi_layout.py tests/test_agi_picture.py tests/test_processor.py \
  tests/test_zmachine_processor.py tests/test_zmachine_processor_acceptance.py \
  tests/test_zmachine_analysis.py tests/test_interaction_il.py \
  tests/test_agent_skill_gate.py tests/test_agent_discovery.py \
  tests/test_distribution.py tests/test_language_cli.py \
  tests/test_udc.py tests/test_udl_blocks.py tests/test_il_scenes.py

317 passed, 1 skipped
```

The skip needs a case-sensitive filesystem. Checks include all comparison forms,
both branches and joins, unsigned IF/signed GOTO, scan-entry offsets, copied
state, arithmetic boundaries, multiple callee returns, source snapshot integrity,
unselected unsupported paths, recursion/cycle and expansion budgets, and a stop
that suspends one callee arm while another returns to its caller.

The optional genuine Z3 check models emitted shared IL for an authored
callee-return/caller-copy contract over all declared u8/bool inputs. It returned
UNSAT for a differing output, and SAT after deleting the caller copy. This is
an explicit bounded model result, not a proof of an original runtime. The skill
frontmatter validator and selective-reference gate also passed.

## Base PR CI snapshot

PR #67's exact head `7bf8c1abe7376853925ac7aba29fef11d04dc813` has successful
[ordinary CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41159090986),
plus successful stable/layers native matrix jobs in
[native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41159090990).
At this snapshot the dependent installed-wheel unified DOS/boot/PE64 job was
queued; the complete native workflow was therefore still pending. Follow-up PR
CI is separate evidence and must be read on its own head before integration.

No original resources, saved states, databases or raw private outputs are
included in this PR or copied into tool packages.
