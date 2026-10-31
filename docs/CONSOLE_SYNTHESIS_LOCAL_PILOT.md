# First-party console synthesis: local implementation pilot

**Revision in progress. Implemented and tested locally on 31 October 2026.**

This implements the first bounded mechanisms from PR #79's specification-first
plan. GitHub was unavailable and was not accessed. No branch, pull request,
release, or shared installation was changed. This is an additive candidate for
review, validated against the supplied **fDisBull 0.26.0** wheel, not an integration
claim against the unavailable current console branch.

## What is implemented

The new `fdisbull.console_synthesis` package contains:

| Component | Actual capability |
| --- | --- |
| Immutable source backings | Retain exact executable fragment bytes, image/bank identity, entry context and a whole-fragment digest |
| Logical bindings | Named scalar state and registers/flags; source addresses remain separate; canonical mirrored RAM aliases refer to one cell |
| Strict 6502 recovery | 56 accepted opcode/addressing combinations, bounded forward control flow, explicit carries and signed overflow, balanced saved values |
| Shared representation | Generate the existing `fdisbull-il-1` syntax, with UDL/UIL role views and separate original backing/observation assumptions |
| Retained UDC | Return exact source-fragment bytes only for an unchanged shared description; semantic edits cannot silently reuse an obsolete backing |
| C realization | Generate new C from shared IL and compile/run it as host-native code through a caller-selected compiler |
| JavaScript realization | Generate standalone JavaScript implementing the same admitted shared operations; no foreign runtime or native backing is called |
| Mapped-code selection | Immutable backing identity, per-slot generations, restore epochs, explicit dependency vectors and selective lease invalidation |
| Target selection guard | Reject an implementation whose semantic-document identity differs from the selected source contract |
| Comparison | Report the first differing field/event, missing observations and type differences; budget exhaustion is not equality |

No code from a surveyed external recompiler is incorporated. The implementation
was written from the authored mechanism requirements. Earlier research had
already inspected some upstream source; this is not described as clean-room or
blind development. Existing approved general tools are reused: the fDisBull
shared evaluator, C compilers, Node, Z3 and a packaged Capstone decoder check.

## Small vertical slice

The authored eight-byte source fragment is:

```asm
lda #1
pha
lda #2
pla
sta $10
```

The physical address `$10` is separately bound to a logical label. The saved
value becomes an explicit temporary in shared IL. The original stack machinery
is not emulated in either generated target. Both targets retain the saved value,
so the result is **1**, not 2. A target compiler is still free to use its own stack
or registers internally; this is not a claim of universally stackless code.

The document is editable. Changing the first value to 3 changes the compiled
result to 3. That edited document is rejected by the original-backed UDC and by
an execution selection still bound to the previous source meaning.

There is no new mandatory IR between UDL and UIL. The document does contain
private temporary labels and low-level flag meanings where needed. Generating
these operations does not infer game-level intent or historical variable names.

## Source profile and observation boundary

The implemented source profile is `6502-binary-isolated-v1`:

- One explicitly supplied immutable code fragment in a ROM-address window;
  no automatic whole-ROM discovery or iNES cartridge loader is added.
- Binary arithmetic only. Decimal-enabled execution is refused.
- Stable mapping and no interrupt, concurrent observer, DMA or device service
  during the admitted fragment. These are caller obligations, not discovered
  properties of an arbitrary game.
- Named RAM accesses below `$2000`, resolved through the specified 2 KiB mirror
  mapping. Explicit stack-page observations are refused.
- Indexed RAM accesses require an index established as constant along each
  relevant source path. Dynamic indexing needs a later array-capable profile.
- Balanced PHA/PLA with at most 32 simultaneously saved values; incoming stack
  contents, explicit SP manipulation, calls/returns, backward flow and indirect
  control are refused. The caller defines the cut at fragment exit.
- At most 512 source bytes, 128 expanded instruction visits, 750 generated
  statements and the existing shared-format budgets. Exceeding a bound refuses.

The observation is the final named RAM cells plus A/X/Y and C/Z/N/V under their
logical labels. Intermediate writes, source stack bytes, bus cycles, device
behavior, interrupt scheduling and exact machine-wide state are excluded. Within
the fragment, reads, writes and flag dependencies still execute in order.

All source bytes must decode within the admitted instruction set, including
bytes not taken along a particular branch. Out-of-range control, instruction-
interior branch targets and missing memory bindings refuse. Nothing becomes
an empty successful callee or a made-up device-ready result.

## Executable UDL is retained, not simulated by relabeling UIL

`RecoveredBlock` retains original executable bytes and bindings. The UDL role
uses the same shared document syntax, but changing the role alone does not run
those source instructions. `execute_original` requires an explicit source-CPU
provider and refuses when none is supplied.

An independent source-CPU emulator was **not available in this local runtime**.
Attempts to obtain optional validation packages failed through the environment's
network path. No source CPU run is claimed. The first source/decoder check and
the semantic/native checks below are useful but do not replace that missing edge.

The generated C and JavaScript do execute. They do not call the original body,
a surveyed recompiler, or an embedded source CPU interpreter. They implement the
shared operations directly.

## Mapped-code mechanism

Two different source banks can occupy the same logical source address. A selected
implementation carries a context-owned lease bound to the active backing,
explicit dependencies and restore epoch. Switching or patching a dependency
invalidates affected leases; unrelated selections remain valid. Restoring a
snapshot invalidates old execution authority even when old byte-identical
artifacts can safely be reused.

The integrated native-output demonstration returned **1 -> 3 -> 1** for bank A,
bank B, and a restored bank A. The old A selection was rejected after the switch.
A compiled implementation for the wrong shared description is also rejected.

This is a control-plane mechanism, not a complete cartridge mapper, automatic
proof-dependency discoverer or interrupt scheduler. Dependencies are declared.
Issuing a new lease does not prove a changed helper equivalent. `dispatch` keeps
this registry stable; it does not lock an external emulator bus or roll back
arbitrary external callback effects. Required mutations/reentry during a block
are explicitly refused by this profile.

## Executed results

| Check | Result and exact meaning |
| --- | --- |
| Focused tests | **80 passed**, no skips, on the final local source |
| Decoder cross-check | All **56 accepted encodings** agree with packaged Capstone on mnemonic and length at one declared decode context; not execution equivalence |
| Native C arithmetic | **393,216 unique operation/input cases per compiler configuration**, each passing GCC `-O0`, GCC `-O2`, and Clang `-O2` |
| Total native arithmetic checks | **1,179,648**, repeating the same unique domain under three configurations; not three times the semantic coverage |
| Domain | ADC/SBC: every 256 x 256 operand pair and both carry inputs; CMP: every operand pair and both incoming overflow values; other state uses declared controls |
| JavaScript / shared evaluator | **768 cases**, 128 each for six authored programs, comparing the complete shared state including private temporaries |
| Symbolic queries | **3 UNSAT counterexample searches** for recovered arithmetic IL versus a separately expressed arithmetic specification, with satisfiable entry domains |
| Wrong carry implementation | Detected at A=0, operand=0, carry=1: generated result 0 versus required 1 |
| Retained reconstruction | Exact unchanged source-fragment output; altered semantic input refuses that backing |
| Mapping composition | Two same-address banks, stale rejection and restore produce native results 1, 3, 1 |
| Final safety controls | Unsupported operations, missing observations, changed metadata, forged/stale leases and altered snapshots refuse or report a mismatch |

The arithmetic checker is an authored specification, **not a 6502 emulator**.
Its overflow expectations use signed mathematical bounds, while the recovered
IL uses bit/sign conditions. The symbolic checker independently translates the
shared AST into bit-vector constraints, not native source machine transitions.
These checks share investigator lineage and are not independent hardware proof.

Exact runtime/tool identities and emitted-artifact hashes are retained in the
local delivery's verification receipt. Only meaningful artifacts are hashed;
no byte-by-byte hashing pass is used as a substitute for semantic testing.

## Defects caught during development

1. The first lowering treated an ordinary shared-IL assignment as a narrowing
   conversion. The existing evaluator correctly refused out-of-range values.
   The implementation now uses explicit wrapping arithmetic for the low byte,
   and both targets preserve range-checked assignment rather than silently wrap.
2. Clang's warning-as-error build rejected redundant comparison parentheses.
   Emission was corrected rather than suppressing the warning or ignoring a
   failed compiler result.
3. An initial mixed integer/bit-vector symbolic query timed out. It was reported
   as unknown, then replaced with a small explicitly sized bit-vector query.
   The final three successful checks are new results, not relabeled timeouts.
4. Review identified that guarding a source mapping alone did not bind a callback
   to the selected semantic document. `execute` now checks that identity before
   calling a generated realization. Altered checkpoint and metadata cases were
   added as refusal regressions.

No defect in an external recompiler is claimed to have been executed here.
The earlier external stack omission remains a separately attributed source review.

## Reproduction

Run in a compatible trusted development environment with fDisBull installed.
The native pilot was tested on Linux x86-64 with GCC 14.2.0, Clang 17, Node
22.16.0, Python 3.13.5 and the supplied fDisBull 0.26.0/Z3 packages. It is not a
new macOS qualification.

```sh
python -m pytest -q tests/console_synthesis
python scripts/check_console_synthesis.py --output /new/private/console-pilot
```

The validation script refuses an existing output directory and does not download
or install anything. It requires GCC, Clang, Node and Z3; the optional Capstone
unit check reports a skip if the decoder is not installed. The delivered final
run had all dependencies and no skipped tests. Tests use a local package-path
overlay to add this module beside the installed evaluator, without replacing it.

## Integration and remaining work

The additive patch is intended for review alongside PR #79 and the existing
console implementation in PR #56. It does not rewrite console scaffolds or
register a new public CLI. The C/JS realizations are bounded validation targets;
production target integration should reuse the current UDC capability interfaces
rather than create another parallel framework.

The patch was checked/applied in a disposable tree populated from the supplied
0.26.0 wheel, then tests were rerun from the reconstructed delivery. That is not
a current-main merge test. The unavailable branch may have changed paths, source
profiles, packaging or interfaces. Reconcile those before publication.

Still required: an independent original-CPU run of these fragments; integration
with the current NES/Genesis targets; full bank-switch/device scheduling;
qualified input, sprite/audio effects; indirect calls and general loops;
stateful game/lifecycle testing; and target hardware qualification. These are
not disguised as implemented features by a successful arithmetic test.

The deliverable is a working first-party mechanism slice, not a universal ROM
converter or another complete playable port.
