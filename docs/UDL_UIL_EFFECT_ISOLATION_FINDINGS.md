# Findings for the UDL/UIL/UDC compiler-definition RFC

Investigation: 29 October 2026 (America/New_York), Codex. Repository source
`75bbd7ee65118c0186844f73ef6c79245854eba0`; native probe pinned independently to
fDisBull 0.21.0 and its installed macOS ARM64 backend. Findings support
[RFC 0001](uil-rfcs/0001-shared-intents-and-compiler-definitions.md), not an
already implemented general compiler or scene-independent purchase API.

Terminology: **UDL** maps original code into **UIL**; **UDC** reads UIL and
transfers it back into code. Compiler definitions below are UDC definitions.
The observed v1 `udl`/`uil` role strings and sealed experimental receipts keep
their original identities; the clarification changes no experimental result.

## 1. Current representation already permits pass-through

Inspected implementation:

- [Shared blocks](INTERACTION_IL.md), `src/fdisbull/interaction_il.py`:
  `fdisbull-il-1` supports typed fixed-width state and ordered blocks. Its legacy
  `udl` and `uil` roles use the same validation/evaluation path; `change_role` copies
  the program and changes only role metadata.
- `src/fdisbull/il_recovery.py`: bounded v3 attribute recovery and immutable
  source-checked project revisions. Source evidence is not an execution binding.
- [Zork verification](VERIFICATION-ZORK-2026-10-29.md) and
  `src/fdisbull/zork_recovery.py`: a mailbox slice has a pinned story and native
  correspondence, including parser-object and action-entry witnesses. The
  existing recovery is narrower than a game parser, turn loop or general lift.
- [Text player](TEXT_PLAYER.md), [spatial policies](SPATIAL_MAPS.md) and
  [intent pipeline](INTENT_PIPELINE_RFC.md): state authority, public observations,
  context freshness and assistance are distinct from transport or prose.

A valid v1 program can already execute without being relabelled UIL. The new
need is a compiler-definition/binding contract, not a mandatory handoff copy.
Current v1 **does not** call an original native snippet for `role: udl`.
Input/media blocks return `pending_host`; their proposed state is not committed
by that evaluator. Required capabilities are checked even in unselected branches.

Ten existing interaction/recovery/Zork-example tests passed freshly. This checks
the implementation boundary, not all original Zork behavior.

## 2. Original DinoPark effect isolation experiment

### Question and exact cut

Can a purchase's reusable commit effect run without its current shop view,
without rewriting its internal instruction order?

The experiment uses the original food-order commit cut:

- entry before project `2d0a:2810`;
- original far-copy helper `1000:4fb8`;
- exit before project `2d0a:283d`.

The source bytes and their original helper remain in place in the complete DOS
image. This is an inline entry/exit slice, **not a recovered standalone function**.
The observed order is nine-bin stock copy, monthly expense posting, cash commit.
The instruction at the exit requests the next scene; it has not executed when
these comparisons stop.

Exact source executable SHA-256:
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Backend SHA-256:
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.
The existing private text adapter used for checkpoint acquisition was pinned
at `0fd84f33f655f3326e141c1ec939967057d9fc7cc1a9d055ef4fcbbf7fa3c91c`.

### Procedure

1. A real native saved park is loaded into a fresh private copy. Capture an
   office checkpoint after its actual office view is qualified.
2. Use original navigation and food controls to prepare a 20-feeder order.
   Stop at the byte-verified native entry before its stock/expense/cash commit;
   capture that prepared checkpoint. The first capture script subsequently
   stopped while trying to read the native stack through a module-only helper.
   Both immutable checkpoints survived. No missing continuation was relabelled
   a successful public purchase.
3. Restore the prepared checkpoint in a fresh original-runtime process and run
   to the exit: the native-context replay control.
4. Fork the office checkpoint, supply the naturally prepared order's differing
   inputs and caller frame, then enter the same original slice. This deliberately
   changes cloned data/register state for a research experiment; it is not
   ordinary gameplay, a live-world merge or a claim of equivalent mouse timing.
5. Run another office fork with the caller frame but **without** the prepared
   order data. This exposes the slice's dependency on prior preparation.
6. Compare ordered PC traces, all nine stock/pending bins, cash/working cash,
   cost, month and all twelve food-expense cells at the same entry/exit cuts.
   There are no new clicks in these replay executions.

The prepared bridge changes five data ranges (48 bytes), ten stack-argument
bytes, and ten differing registers. It leaves the office's other scene state
and pause state in place. It does not patch native instructions or game files.
The data values come from the observed order rather than invented funds.

### Native results

| Case | Context marker | Pause word | Stock before → after | Cash before → after | Expense before → after |
| --- | --- | --- | ---: | ---: | ---: |
| Prepared native replay | 4 → 4 | 0 → 0 | 18 → 38 | 4,507 → 4,007 | 500 → 1,000 |
| Prepared office fork | 6 → 6 | 1 → 1 | 18 → 38 | 4,507 → 4,007 | 500 → 1,000 |
| Unprepared office fork | 6 → 6 | 1 → 1 | 20 → 20 | 3,165 → 3,165 | 500 → 500 |

The context marker is the observed word at project `4020:3c5a`. These values
correlate with the captured office/Diner parents; they are not a universal
scene ontology or readiness proof. The pending scene-request word at
`4020:3c5c` is `ffff` in **both** contexts, so it cannot distinguish them.

All prepared effect fields and the 35-entry instruction-address sequence match.
These are before-instruction fetch observations with unknown individual
retirement flags; the terminal entry is the exit instruction before execution.
They must not be reported as 35 confirmed retired instructions. The trace's instruction-count `complete` flag is false because the deliberate
exit breakpoint stops before its 256-entry budget; the named region exit was
reached. A drained instruction budget or a matching screenshot is not the
basis for claiming completion.

The unprepared slice does not itself prepare or validate a purchase. Its
recorded no-change result is **not a native guard refusal**. It is evidence
against publishing this address as an unconditional `buy` function.

### What was established and what was not

Established: a source-backed **commit-prepared-food-order** effect can be
re-entered under a different original presentation/context snapshot when its
specific data and control-frame dependencies are supplied. The original code
ordering and selected effects were retained in this finite experiment.

Not established:

- a complete purchase callable from arbitrary scenes or states;
- removal of world guards, prices, stock rules or preparation;
- return into the office's ordinary caller after this inline cut;
- relocation of the machine code or execution without the original DOS runtime;
- equivalence of animation, guest time, UI inputs, scene transitions or saves;
- an exhaustive read/write closure, all aliases, interrupts or rare paths.

The original binary/helper, mutable globals, native stack and bounded exit trap
are still dependencies. A production definition needs a reviewed entry adapter,
continuation/ABI, admission guard and complete-operation comparison. For a full
order, the scene request and relevant presentation must remain in the ordered
compound operation; the numeric commit cut alone is insufficient.

The public [sanitized observation](uil-rfcs/0001/native-observation.json) records
identities, operands, comparisons and limits without original bytes, images,
saves or host paths. The opt-in [replayer](uil-rfcs/0001/native_probe.py) accepts
operator-owned captured project and game inputs; it clones the database and
creates derived states. Private originals and failed probes remain preserved.

### Tool friction and requirements for definitions

The native SS:SP frame lay outside the original module mapping. The high-level
project-memory helper correctly refused to invent a mapped source location.
The research replayer uses the backend's explicit runtime-linear memory service
for the ten argument bytes, with expected-content hash and readback. Its initial
short-hex request was rejected until formatted as the backend's eight-digit
address. Both setup failures remain in the private record; neither is a
successful effect execution.

A binding therefore needs address-space identity, runtime lifetime, stack-frame
ownership, pointer width and guarded writes. A source span and a routine name
alone do not provide them. The observed context-word ambiguity also argues
against defining a semantic scene by one cached field.

A replayer attempt that copied the game working directory to a new path was
refused with `State compatibility mismatch: game_dir` before any slice ran.
The public replayer retains that exact captured disposable working directory,
clones the project database, and verifies game-file hashes before/after.
It does not rewrite snapshot compatibility metadata. Original-backed bindings
must declare current snapshot/file-handle path constraints; runtime relocation
is a separate feature requiring its own qualification.

## 3. Whole intents can cross multiple effects and processes

The earlier original Vegasaurus investigation in
[PR #15](https://github.com/seeker-cyber-maker/fDisBull/pull/15), frozen feedback
commit `5d9118ae6c967439c935471c1ca4e992ce2fcdfb`, records reservation, animation,
release and an expense that remains posted. Native boundaries are
`334b:205e`, `334b:208b`, `334b:18b6` and `334b:18be`.

A fresh player bought without reading the entry first; the calendar changed
during the animation. Cash/loan/working cash went from
27,029/4,411/27,029 to 27,029/4,411/2,029, then
27,098/4,290/2,098 and 27,098/4,290/27,098. The original $25,000 reservation and
release were correct while simulation intervened. Tight boundary pairs, not a
frozen whole-action balance, qualified the final adapter. Later navigation can
fail while the order stays confirmed.

This motivates ordered multi-phase intents, separate effects/follow-up receipts
and explicit time semantics. It also demonstrates an observation requirement:
private research must not tell a fresh player a hidden purchase outcome.
The optional native encyclopedia is normal player-discoverable evidence.

## 4. Rust, JavaScript and Python UDC/compiler-definition seeds

The redistributable [source fixture](uil-rfcs/0001/README.md) independently authors
one tiny backing in each language for an explicit synthetic commit contract.
The same v1 block program also runs by unchanged pass-through. All four backings
agree on five literal cases: **20 backing/case comparisons**, including u32
expense wrap and admission refusal. Five malformed requests are refused before
backing dispatch. Unknown native opcodes remain refused and graphics remain
pending host work rather than fabricated successful effects.

The fixture preserves stock → expense → cash order and intermediate checkpoints,
not only final state. A synthetic lower-cost wrong-order candidate is excluded;
a lower-cost equivalent candidate wins under invented fixture cost units.
Actual performance is not measured, and the Rust/JS/Python definitions were
not generated from one another. The runnable checker and
[source-definition observation](uil-rfcs/0001/source-definition-observation.json)
separate this narrow implementation from proposed compiler propagation/learning.

The language boundary is real: Rust has an explicit wrapping operation,
Python integers need a recovered width policy, and JS BigInt avoids a Number
precision assumption. [LLVM data-layout documentation](https://llvm.org/docs/LangRef.html#data-layout)
also illustrates why binary-target layout remains explicit even with a
language-independent intermediate representation.

## 5. Workload evidence versus hypotheses

| Workload | Inspected evidence | Proposed use; not claimed as executed here |
| --- | --- | --- |
| DinoPark | Fresh original-code experiment and prior native purchase receipts | One complete out-of-view order, including its guards and transitions |
| Zork | Current source, packaged recovery and verification records | More actions and parser/turn-loop recovery beyond the mailbox slice |
| PQ1 / SQ1 | Current AGI/source-policy code and repository verification | Edition-qualified actor, inventory, modal and timed action slices; SQ1 not newly run |
| Lost in Time | ScummVM's own compatibility entry identifies `gob:lit` | Investigate supplied edition and richer scene/media dependencies; no original runtime inspected |
| Dune II | OpenDUNE's own documented recreation and structure source | Factory/production, autonomous ticks and cancellation as an RTS extension; no original Dune II binary comparison |
| Warcraft II | Blizzard's own worker guide documents construction, gathering and repair roles | One object with several affordances and asynchronous orders; no rates/costs inferred |
| Word | Microsoft documents `Range.InsertAfter` and range/paragraph behavior | Text-driven range editing with identity, formatting and undo contracts; no Word execution |
| Excel | Microsoft documents `Range.Value2` and distinct Change/Calculate behavior | Cell intents with value types, recalculation, events and persistence; no Excel execution |

OpenDUNE is a re-creation, not original Westwood source or automatic proof of
original parity. Its `GameLoop_Structure` and `Structure_BuildObject` give a
concrete source example of simulation and production separated from an input
widget, with rendering calls still present. No uninspected commercial-game
cost, timer or refund formula is proposed as fact.

Word's range insertion can change a range and depends on paragraph/bookmark
boundaries. Excel's cell-value API and worksheet change/recalculation distinction
show that a text interface is feasible, but a correct effect is richer than
replacing one displayed string. Compiler definitions can bind documented APIs
before full binary recovery; that backing must be identified as an API provider,
not mislabelled a recovered native snippet.

## External primary sources

These sources were inspected for the named interface/implementation claims;
external game scenarios remain hypotheses until an original is compared.

- [OpenDUNE README](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/README.txt) and [structure code](https://github.com/OpenDUNE/OpenDUNE/blob/ebea79aeba025be2fe9004570e9255044aacc0be/src/structure.c): pinned project source; a recreation.
- [Blizzard Warcraft II worker guide](https://classic.battle.net/war2/units/peasant.shtml): worker roles, not native implementation evidence.
- [ScummVM compatibility](https://www.scummvm.org/compatibility): its `gob:lit` entry; not identification of an uninspected private edition.
- [Z-machine state and routine-call standard](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html): guest state/call-frame distinction.
- [Microsoft Word Range.InsertAfter](https://learn.microsoft.com/en-us/office/vba/api/word.range.insertafter).
- [Microsoft Excel Range.Value2](https://learn.microsoft.com/en-us/office/vba/api/excel.range.value2) and [Worksheet.Change](https://learn.microsoft.com/en-us/office/vba/api/excel.worksheet.change).
- [Rust u32 wrapping_add](https://doc.rust-lang.org/std/primitive.u32.html#method.wrapping_add), [ECMAScript BigInt type](https://tc39.es/ecma262/multipage/ecmascript-data-types-and-values.html#sec-ecmascript-language-types-bigint-type), [Python numeric types](https://docs.python.org/3/library/stdtypes.html#numeric-types-int-float-complex).
- [LLVM language reference: data layout](https://llvm.org/docs/LangRef.html#data-layout).

## Verification and claim ceiling

The required repository command was run before edits: 13 failed, 1,407 passed,
116 skipped and 23 errors. These failures belong to the inspected baseline;
this investigation does not relabel the whole suite green. Ten affected existing
IL/recovery tests and the separate source-definition fixture passed. After edits,
the required suite repeated the same counts with the same 36
failure/error test identities. The ten focused tests passed again, the source
fixture receipt reproduced identically, and the published native replayer
reproduced all three cases in fresh processes with both parents and captured
game files unchanged. PR checks are recorded separately in the PR description.

The RFC is draft and the source fixture is synthetic. Neither the native office
experiment nor successful cross-language vectors implement a generic compiler,
prove all inputs, recover arbitrary applications or authorize execution of
untrusted compiler definitions. Continuous improvement is a proposed, versioned
candidate/qualification/selection protocol, not a service activated by this PR.
