# Colonization: shared DOS / Win16 production helpers

**Revision in progress. New bounded source analysis and executed CPU comparison,
30 October 2026 (America/Toronto).**

This extends the food correspondence in PRs #31/#36/#38/#42 with two adjacent
helper pairs. The result is one address-free UIL definition per operation, not
one edition-specific program disguised behind a shared name. The published
[authored generator](../scripts/colonization_shared_helpers.py) emits existing
`fdisbull-il-1` documents; [tests](../tests/test_colonization_shared_helpers.py)
exercise the real evaluator without game files. This changes no core schema.

## 1. Sources and investigation route

The supplied GOG installer was inspected without running its installer code.
Its DOS file was extracted and its raw-sector CD read as ISO 9660. The Windows
program is the original 1995 pre-patch executable in `INSTALL/COLONIZE.$00`, not
the later 34-segment patched release. A bounded ARCV decoder, informed by the
public OpenCol decoder, reproduced the exact prior target identity. This is
prior-work-assisted investigation, not a blind comparison.

| Source | SHA-256 |
| --- | --- |
| DOS `VICEROY.EXE` | `a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3` |
| Win16 `COLONIZE.EXE` (1,175,040 bytes, 33 NE segments) | `ae7d9149f056766a534fe8f0006c9512aac1e1004e9776ab3cca818e4833b650` |

The earlier reports provided leads. Original instructions and NE selector
fixups were inspected anew. Both new helpers have closed local control flow and
no helper calls. Their wrappers separately support interpreting the inputs as
production/demand/stock. The labels below are authored interpretations, not
recovered historical symbol names.

| Helper | DOS file range, half-open | Win16 logical range / file range |
| --- | --- | --- |
| Net production | `[0x8DBC,0x8E01)` (69 bytes) | `ne:4:[0x47DD,0x4864)` / `[0xBDDD,0xBE64)` (135 bytes) |
| Input balance | `[0x8E02,0x8E46)` (68 bytes) | `ne:4:[0x4869,0x48E9)` / `[0xBE69,0xBEE9)` (128 bytes) |

The Windows net helper's seven selector relocations and balance helper's five
resolve to logical NE segment 20. These are not observed live Windows selectors.
The private harness applies exactly those twelve declared selector fixups.
DOS bodies are retained byte-for-byte; neither game executable is modified.

## 2. Common operation: calculate input balance

The shared input ports are `supply`, `demand`, and `available`, interpreted as
signed 16-bit values. The output ports are `consumed`, `shortage`, and `unmet`.
Let `w16` reduce to a 16-bit word and reinterpret it as signed.

```
consumed = demand
shortage = 0
unmet = 0
if demand > supply:                       # signed comparison
    shortage = w16(demand - supply)
available_total = w16(supply + available)
if available_total < demand:              # signed comparison AFTER wrapping
    unmet = w16(demand - available_total)
```

The DOS source expresses the last subtraction as `demand - available - supply`;
the Windows source subtracts the wrapped sum. Those expressions agree modulo
65536. Neither performs an arbitrary-precision mathematical calculation followed
by a conventional zero clamp.

In ordinary small nonnegative examples, supply=4, demand=7, available=2 produces
`consumed=7, shortage=3, unmet=1`; available=5 instead gives unmet=0. These are
illustrative model evaluations, not a claim about a particular live colony.

The less intuitive boundary matters: supply=32767, demand=0, available=1 wraps
the sum negative and yields unmet=-32768. Widening the arithmetic without
retaining that transition changes behavior. This does not force 16-bit physical
storage: a modern UDC can use wider carriers with explicit wrapping.

The existing IL lacks general relational operators. The authored definition
uses its signed variables, wrapping subtraction and sign-bit conditions to
express signed comparison. A separate bit-vector check validates that expansion
for every pair of signed 16-bit values. There is no new comparison opcode.

## 3. Common operation: calculate net production

The shared ports are `produced`, `consumed`, `has_mapped_adjustment`,
`mapped_adjustment`, `has_report_target`, and prior `reported_adjustment`.
The first two and adjustment values are signed 16-bit; presence ports are Boolean.

```
net = w16(produced - consumed)
report_written = false
if has_mapped_adjustment:
    net = w16(net - mapped_adjustment)
    if has_report_target:
        reported_adjustment = mapped_adjustment
        report_written = true
# Otherwise retain the previous reported_adjustment, not zero.
```

The raw source's signed mapping byte and index lookup are in the edition's UDL
adapter, not in this UIL. Negative mapping values select no adjustment;
nonnegative values select a table entry. The optional report pointer is near in
DOS and far in Windows; its representation likewise stays in the binding.
`report_written` describes a declared optional effect, not an extra original
memory cell. Native runs compared its resulting value; the same-value-write
case was not separately traced with a write watch.

These helpers read scratch production accounting. They do not by themselves
commit a warehouse update, advance time, or establish an entire colony turn.
The distinct 16-word warehouse and earlier 20-entry scratch-cache interpretation
must not be conflated.

## 4. Executable UDL and source bindings

Each operation has two original executable backings. The private executor
marshals the same logical inputs into each source's locations, invokes the real
x86-16 body, and reads its declared outputs. The common UIL has no physical
addresses. Both generated role documents have identical operation syntax;
changing the `role` field alone does not authorize native execution.

| Role | DOS binding | Windows binding |
| --- | --- | --- |
| Production | DS:8DC8 + 2*index | NE20:0122 + 2*index |
| Consumption | DS:8E0A + 2*index | NE20:0164 + 2*index |
| First shortage | DS:8E32 + 2*index | NE20:018C + 2*index |
| Second shortage/adjustment | DS:8E5A + 2*index | NE20:01B4 + 2*index |
| Signed mapping byte | DS:02A2 + index | NE20:00A6 + index |
| Optional report target | 16-bit near pointer | 32-bit selector:offset far pointer |

Source addresses above are bindings, not UIL labels or guaranteed live placement.
Both adapters use valid isolated storage and a separate nonaliasing report cell.
The source repeats some reads; stable input tables and no intervening callbacks
are explicit assumptions. A volatile source, aliasing report target, interrupted
write, invalid address or noncanonical caller needs a different qualification.

## 5. New execution and checking

A generated COM harness was assembled with GNU binutils. It allocates an
isolated data segment, initializes inputs and scratch sentinels, calls the
retained source helpers, and writes a bounded result stream. The Windows code
executes as x86-16 under DOSBox after the declared selector adaptation; this is
NOT an original Win16 process or a full Windows game execution.

| Check | Fresh result |
| --- | --- |
| Paired original-body executions | 3,072 cases per edition, two helpers per case: 12,288 helper invocations |
| DOS / adapted Win16 results | All 3,072 six-word records match byte-for-byte |
| Actual fDisBull 0.26.0 UIL evaluator | 6,144 evaluations agree with both native-body result streams |
| Symbolic correspondence | Three unsat counterexample queries: balance versus separate DOS/Win models, and net with an explicit mapping-sign state relation |
| Negative/sensitivity controls | Five: unsigned mapping, incorrectly cleared report, omitted adjustment, widened arithmetic, and altered UIL subtraction |
| Independent fresh harness process | Same generated source bodies and output digest reproduced; not counted as additional unique input coverage |
| Public authored fixture tests | 10 passed against the genuine 0.26.0 evaluator and installed Z3 |

The input set contains 1,024 selected arithmetic-boundary/optional-output cases
and 2,048 seeded pseudorandom cases. Native index coverage uses 0..19 and mapping
values -128, -1, 0, 1 and 19. That is a declared harness domain, not proof of the
complete source table extent or ordinary in-game reachability. Symbolic checks
cover their declared abstract domains without enumerating every machine state.

The output record is `(case_id, consumed, shortage, unmet, net, report_value)`,
serialized as six little-endian words. Both result streams have SHA-256:

`efb9ee541d2dc84fdec4eb36758e77c450db78bbb3c86508e6acc024670b1894`.

The SMT expressions are source-derived models, not a formal proof of the x86
transition decoder. The sources, AST builder and expectations share investigator
lineage. Native instruction execution provides an additional check over the
selected states. Final declared outputs are compared; scratch registers/flags,
exact stack contents, timing, faults and intermediate writes are excluded.

## 6. How this extends a shared Colonization blueprint

An incremental common program can now catalog:

- center-food staging: the previously reported common operation;
- input balance: the newly tested common operation;
- net-production calculation: the newly tested common operation;
- warehouse commit, bonus helpers, calendar and services: retained unresolved
  dependencies, not fabricated successes.

A provisional Z colony-report scene may use the named calculations as a
comparison view once its input-state binding is qualified. It must not label a
preview as a committed turn or expose a guessed native action. A whole-game UIL
or a completed normal-play campaign is not delivered here.

The next concrete extension is the warehouse update: bind the current colony,
16-word stock loop, net-helper call, extra food adjustment and signed lower clamp
in both editions. Validate that the update runs once at the intended phase.
Resource/improvement bonuses and current-state initialization remain separate.

## 7. Reproduction and publication boundary

Generate the authored definitions from this checkout:

```sh
python scripts/colonization_shared_helpers.py --output /new/private/definitions
python -m pytest -q tests/test_colonization_shared_helpers.py
```

These commands need no commercial game bytes. The user delivery separately
contains a native harness builder/replay runner requiring the two exact owned
executables and the qualified DOSBox backend. Original source bytes are read
from the user's files only at reproduction time. No game code, generated
retaining COM files, resources, save files or emulator states are published.
The source archives ship `scripts` and `tests`; no test imports a pruned examples
module. No full-repository test run or new production API is claimed.

Prior reports: [paired food study](https://github.com/seeker-cyber-maker/fDisBull/blob/cd9b4f892b549209020c8b74890a818e11462d2a/docs/COLONIZATION_FOOD_EQUIVALENCIES.md)
and [structural pilot](https://github.com/seeker-cyber-maker/fDisBull/blob/465c725/docs/COLONIZATION_DOS_WIN16_PILOT.md).
ARCV intake reference: [OpenCol isoimport.c](https://github.com/OpenCol/win-port/blob/d49a3ac1018057bdcaecfdec3e4af9940d41abef/src/launcher/isoimport.c).
These references guided discovery; the new original-byte inspection and runs
above are separate from their previous results.
