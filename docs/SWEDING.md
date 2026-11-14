# Sweding during UIL → UDC

Sweding reconstructs an operation's effect using available target capabilities,
borrowing the recreation concept from *Be Kind Rewind*. UIL preserves intent;
UDC orchestration may reuse a qualified module, use it as a reference, or create
a new backing. Formats, languages and machinery can change while the original
observable effects, action responses and timing remain indistinguishable.
The bundled [sweding reference](../src/fdisbull/skills/fdisbull-investigate/references/sweding.md)
is the durable decision procedure, with audio, alternative JavaScript blocks,
mixed-language hosting and acceptance/specification cases. Retrieve it from an
installed distribution with:

```text
fdisbull agent-skill --reference references/sweding.md
```

This extends the existing [executable Rosetta principles](uil-rfcs/0002-executable-rosetta-contracts.md),
especially contract/backing identity, semantic ports, explicit services and
polyglot composition. It preserves the [UIL consumer boundary](UIL_BOUNDARY.md)
and [current DOS compiler limits](UDC_DOS.md). It introduces no schema/API,
general target generator, audio backend or JavaScript/Win32 bridge. The examples
describe prospective qualification; bounded evidence and universal proof remain
different claims. Missing coverage stays unknown. Relaxed behavior requires an
explicitly accepted variation, rather than an equivalence label.

## Relationship to existing work

The inspected [Tic-Tac-Toe/Five-Dice PR #47](https://github.com/seeker-cyber-maker/fDisBull/pull/47)
at `2b8d4db9fda90edc11dfedf77b8acab1e4d1474c` provides three authored UIL
variants (`clean`, `compact`, `verbose`) and generated C. Its
[source](https://github.com/seeker-cyber-maker/fDisBull/blob/2b8d4db9fda90edc11dfedf77b8acab1e4d1474c/examples/udc/game_variants/tic_tac_toe.py)
implements a bounded terminal-notification decision, not a complete board game.
It is not an implemented JavaScript experiment. The three JavaScript functions
in the bundled guide are separately authored illustrations. Neither example
establishes original-game action/timing indistinguishability.

The guidance complements [source-reconstruction reuse #51](https://github.com/seeker-cyber-maker/fDisBull/pull/51),
[media adapters #53](https://github.com/seeker-cyber-maker/fDisBull/pull/53)
and [block orchestration #54](https://github.com/seeker-cyber-maker/fDisBull/pull/54).
Those PRs retain their own scope and qualification; this branch does not import
their runtime changes. Future integration must preserve all indexed references
and reconcile shared skill/index/distribution-test edits. This documentation
increment is separate from the frozen 0.27 release candidate #55.
