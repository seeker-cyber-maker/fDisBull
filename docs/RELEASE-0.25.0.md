# fDisBull 0.25.0

This source integration connects two useful ways to recover behavior: preserve
an interpreter's program as executable IR, then replace a qualified action with
a small semantic definition. Zork's opening interaction is the bounded example;
unrecovered behavior continues through the retained IR. The separate player can
checkpoint either representation without requiring the analysis debugger.

The original-backed DinoPark provider gains bounded continuation across park,
catalogue, notice and native-save boundaries. Native game input still performs
the transactions. An observed purchase remains committed even when a later
screen transition is incomplete; uncertainty does not authorize buying again.
See [DinoPark in Z](DINOPARK_Z.md).

## Included work

- **PR #24:** qualified Zork I release 88 conversion, a separate Word16
  consumer, source-linked game-intent UIL and its UDL adapter. The existing
  converter and consumer remain intact. The integration corrects the fault
  contract: completed effects remain visible, an interrupted effect has unknown
  completion, and the CLI reports failure without overwriting the last
  successful checkpoint or silently retrying. A failed transcript delivery is
  reported separately. See [the executable IR](ZORK_UIL.md) and
  [recovered intents](ZORK_INTENTS.md).
- **PR #26:** original-backed DinoPark continuation, scene recognition and
  provenance improvements, with bounded tests for notice return and draft
  reconciliation, plus journaled Z batches and shared original-action
  continuations. The integration blocks original actions even through aliases
  and requires provider authorization before continuing. Partial original
  effects remain paused because current providers do not certify their final
  completion. This is a qualified provider, not a recovered economic model.
- **PR #23:** native GOG Inno Setup extraction through an installed
  `innoextract`, with explicit destination checks and a file manifest. The
  operation extracts a supported installer; it does not execute it or supply
  game data. See [native unpacking](GOG_UNPACKING.md).
- **PR #25:** bounded static DOS/4GW LE loading and internal fixups for the
  existing 32-bit analyzer. Unsupported imports and fixups are refused. This
  does not add protected-mode native debugging. See [the LE profile](dos4gw-le.md).
- **PRs #20 and #27:** one investigation skill with research-led scene recovery,
  semantic contracts, format intake, minimum useful proofs and explicit cost,
  reward and confidence. The duplicate skill links from #20 are reconciled
  with #27's existing reference structure. Its authored ASM/C microbenchmark
  remains a bounded representation experiment, not a native recovery speedup.
- **PRs #21 and #22:** retained research and design documents for NoCD music
  boundaries and synthetic HUDs. These are documentation contributions;
  their proposed runtime features are not advertised as implemented.

## Scope and evidence

The source still distinguishes interpreter IR from recovered game intent.
Zork's parser, scheduler, autonomous actors and unhandled interactions remain
explicit retained IR. A successful short route does not qualify a complete
walkthrough or generalize the source adapter to another edition.

The [verification record](VERIFICATION-0.25.md) records fresh combined-source,
package and native checks, with their limits. The [PR backlog](PR_BACKLOG.md)
separates submitted documentation that was incorporated from capabilities that
remain partial or proposed. Closed PRs are not treated as proof that every
requirement in their discussions is implemented.

Game/story files, emulator states, saves, project databases and generated
byte-retaining packages remain private and outside Git and tool archives.
Ordinary and required-native Linux CI must pass on the exact integration SHA
before main is updated. Tagging, publication and changing the system
installation are separate actions.
