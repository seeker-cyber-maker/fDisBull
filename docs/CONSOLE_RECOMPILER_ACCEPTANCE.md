# Console provider acceptance and matched-method benchmark

**Revision in progress. Proposed protocol, 31 October 2026.**

Companion to the [integration plan](CONSOLE_RECOMPILER_INTEGRATION_PLAN.md).
The cases below have not been executed by this documentation change. They define
what a future implementation must demonstrate, not new tool APIs or status enums.
A provider qualifies for its declared subset; it need not solve all consoles or
all games to be useful. Unsupported cases remain visible rather than becoming
successful no-ops or vanishing from the workload denominator.

## 1. Keep the comparison questions separate

Compare three routes only where they support the same requested output contract:

1. Original target execution, with an explicit CPU/device/reference implementation.
2. fDisBull executable UDL bindings -> shared UIL -> selected UDC and runtime.
3. An external direct recompiler or retained compatibility implementation.

An external provider can serve either as a candidate or as one reference, but
must not certify itself. A second implementation sharing the same CPU core or
annotations is not fully independent. Keep source/manual-derived expectations
for small cases and record where reference behavior is itself uncertain.

NES-to-SNES can use Project Nested as the external route. NES-to-Genesis can
investigate the specific romdev backend, initially as a nonqualified experimental
candidate. Desktop-only frameworks are not physical-cartridge competitors.
Do not count source backings running in an emulator as target-native instruction
translation, or literal translation as recovered high-level UIL intent.

Use exact source editions, input schedules, starting states and observation
contracts. Compare logical fields through qualified state maps rather than
requiring identical RAM layouts. For sub-frame behavior, compare ordered device
events and their relevant time relation. Application-tick comparison is suitable
only where its projection preserves the claimed behavior. Do not silently align
away an input delay that the contract promises to preserve.

## 2. Admission levels, not one compatibility checkbox

| Level | Claim admitted | What does not follow |
| --- | --- | --- |
| A0: artifact | Header/layout valid; build reproducible under its pinned recipe | The game executes correctly |
| A1: local semantics | Selected values, dependencies and effects match at a declared cut | Complete machine, timing or device equivalence |
| A2: composition | Repeated calls, state ownership, aliases and continuations agree | All reachable game paths |
| A3: devices | Selected input, display/audio and scheduling behaviors agree | Electrical or untested hardware fidelity |
| A4: playable route | Cold boot, active play, transitions and failure/retry behavior pass | Full-game completion or unsupported peripherals |
| A5: physical target | Recorded board/region/cartridge setup passes the stated experiment | Unmeasured latency or every hardware revision |

Keep exact reconstruction, semantic equivalence, compatibility execution and
intentional adaptation separate. A changed renderer can be an accepted gameplay
projection without being pixel-identical. A transformed audio backend must still
preserve the selected completion/order/fidelity contract. Do not report a tested
request to play sound as tested audible output.

## 3. Prospective conformance cases

These are case families. A future result must name inputs, target variants,
coverage, refusals and actual observations. Small models or text-retrieval tests
alone do not execute this matrix.

| ID | Experiment | Required discriminator / acceptance |
| --- | --- | --- |
| CR-A01 | Save a byte, overwrite the working value, restore it, then store it | Valid 6502 PHA/PLA probe from the plan stores 1, not 2; no silent deletion of saved state |
| CR-A02 | Carry/borrow chains across loads, stores and arithmetic | Preserve the flags actually consumed; include both carry inputs, wrapping boundaries and a wrong-carry mutant |
| CR-A03 | High-bit indexed addressing, zero-page wrap and RAM mirrors | Distinguish addressing modes; selecting an index >=128 must not accidentally become a negative displacement |
| CR-A04 | Operand destinations, shifts, rotates and indirect memory | Check all declared read/write locations and the next consumer, not only a plausible accumulator value |
| CR-A05 | Missing callee, unsupported opcode or unknown required effect | Qualified build refuses; explicitly selected triage output lists every stub/residual and cannot pass as complete |
| CR-A06 | Calls, nested saved state and MMIO adapter clobbers | Caller-live values survive; one supported callback/reentry case or explicit refusal closes the scope |
| CR-A07 | Two physical banks expose different code at the same address | Selection follows the current mapping; stale compiled body is not reused after switch |
| CR-A08 | RAM-installed code or overlay changes after restore | Byte/load/context identity requalifies selection; valid fallback is visible, not suppressed |
| CR-A09 | Controller press/release and frame publication | Same logical input produces matched state; startup and publication delays are recorded rather than inferred |
| CR-A10 | One sprite/tile update crossing an interrupt/DMA boundary | Observe the relevant ordering and deadline; a framebuffer snapshot alone is insufficient where reads depend on timing |
| CR-A11 | One sound request with stop/completion or looping | Verify the selected audio contract; dropped writes and synthetic success fail; no sample-exact claim from event-only tests |
| CR-A12 | Death, restart, scene transition and neutral-input replay | No inherited working state, duplicated effect or unauthorized source fallback changes the result |
| CR-A13 | Save/load in a fresh process, including bank/runtime state | Persistence is isolated between candidates; restoration reproduces the declared continuation |
| CR-A14 | Bad expected state, missing watched write and altered semantic operand | Checker fails and reports first divergence; self-comparison alone does not qualify the checker |
| CR-A15 | Target ROM/RAM/bank/stack and execution budget boundary | Reject or select an explicitly qualified alternative when the realization exceeds its budget; measure runtime overhead |
| CR-A16 | Patch one backing while retaining an unrelated component | Invalidate the affected dependency closure; incremental result agrees with separately recovered patched behavior |

CPU vector admission must distinguish source variants, not merely select a folder
called 6502: NES/RP2A03 assumptions, decimal behavior, undocumented instructions
and device accesses need appropriate profiles. A known CPU disagreement should
block the affected subset, not invalidate unrelated accepted operations. A host
compiler or assembled ROM is not a substitute for source/target CPU execution.

The stack discriminator is currently a source-derived prediction for a pinned
romdev path. Before attributing a new executed bug, invoke that path, retain its
emitted source, assemble it, run both sides and record the actual outcome.
Fixes can preserve a value in a temporary rather than recreate the physical
stack. The acceptance concerns meaning, not a mandatory implementation technique.

## 4. Benchmark the investigation method as well as the runtime

Use a small pilot first: one pure/stateful slice and one device-bearing
interaction, then an unseen bank/overlay case. Do not start a complete factorial
study across all consoles, tools, agents and information modes.

Select the information condition before opening target-specific material:

| Condition | Supplied prior work | What must be charged/reported |
| --- | --- | --- |
| Independent recovery | Target and agreed tools, no supplied target-specific analysis | Fresh context/workspace; this informed review cannot be that worker |
| Notes-assisted | Frozen guides, disassembly notes or documented mechanics | Reading, translation, collation and correction; shared upstream lineage |
| Results-derived | Existing reconstruction/port and permitted interfaces | Import, contract recovery, adapters and verification; code comments are prior knowledge |

First hold one information condition fixed while changing the translation route.
Then hold a route fixed to measure the value of notes or reusable implementations.
Use the same acceptance boundary but do not pretend equal starting knowledge.
Keep hidden cases out of worker prompts. Counterbalance order and retain failed,
refused and budget-exhausted tasks. Fresh contexts do not establish absence from
model training. A source-assisted Miniplanets specialization is a reuse baseline,
not a blind general-decompiler result.

For each run, record elapsed and aggregate worker/tool effort, setup, analysis,
adapter construction, compilation, validation, corrections and warm reuse.
Measure code size, peak target memory, deadlines and latency at the target, not
just host generation time. Cache-hit results are reuse, not a new execution.
Report startup separately and retain its cost; do not compare a warm persistent
provider against another provider's repeated cold launches without saying so.

Use explicit coverage denominators:

- Static coverage: admitted source bytes/entries within a declared scope; avoid
  double-counting overlapping code and keep code/data uncertainty visible.
- Executed coverage: original instructions or declared transitions actually
  exercised; count interpreter, JIT, AOT and replacement paths separately.
- Semantic coverage: qualified contracts and effects, not friendly variable names.
- Gameplay coverage: named paths/states, not just screenshots or title count.

If the provider cannot expose fallback counts, record them as unknown rather than
zero. Sampling a no-fallback route does not prove an interpreter-free whole game.
A direct recompiler may outperform a semantic route in cold setup; a UIL route
may repay its cost through a second target or patch. Measure both without
preselecting the winner.

## 5. Receipt and publication requirements

A run receipt should bind source/resource identity, provider and adapter revision,
CPU/mapping/device profile, starting-state recipe, inputs, observed boundary,
selected implementations, assumptions, completion/failure, stubs/fallbacks and
actual result artifacts. One existing receipt mechanism should carry this where
possible; this document does not introduce an executable JSON schema.

Retain a bounded first-divergence window and replay recipe rather than flooding
routine agent output with every instruction. Hash meaningful artifacts once at
intake and after mutation boundaries; do not hash each byte as an investigative
ritual. Evidence identity is useful, but is not semantic evidence by itself.

Allow only reviewed/licensed fixtures and explicit user inputs. Do not auto-fetch
commercial ROMs, BIOS files or dependencies. Do not merge upstream code or change
external repositories merely because a source-review prediction exists. An
upstream contribution should include a minimal authored reproducer, exact version,
correct scope and the maintainer's contribution requirements.

For a future acceptance report, state what was actually built/executed and list
remaining gaps. This documentation-only increment performs no external execution,
full fDisBull suite, game test or hardware comparison. Its own validation concerns
Markdown structure, references and the published change only.
