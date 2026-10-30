# Snippet selection pilot: Colonization and authored fixtures

This pilot implements the first persisted selection and target orchestration
path behind [selectable UDL block layers](UDL_BLOCK_LAYERS.md). It follows the
[orchestration proposal in PR #29](https://github.com/seeker-cyber-maker/fDisBull/pull/29)
and extends the [DOS/Windows food study](COLONIZATION_FOOD_EQUIVALENCIES.md).
The game programs, byte-retaining projects, generated programs and full native
receipts stay in the user's private target package. No game bytes accompany
this report or the tool distribution.

## What was exercised

| Experiment | Observation | Qualification boundary |
| --- | --- | --- |
| Colonization source selection | One immutable UIL food contract; retained 101-byte DOS and 124-byte Windows kernels selected through separate ABI/memory adapters | 64 terrain/mode cases per backing, 128 isolated original-instruction executions. This is CPU block execution, not a Win16 process or a full game proof. |
| DOS food harness | Exact retained DOS body ran in DOSBox for terrain/mode `13/0`, `24/1`, `65535/255`, returning `4`, `1`, `3` | Three independent native cases. Generated harness placement and live source-body hashes were checked; original game executable preserved. |
| Five-dice RNG | LCG and xorshift selected through the same symbolic UIL and logical seed ports | Policy explicitly admits different sequences. Starting from seed 12345, first rolls were `3,4,1,6,5` and `4,6,3,1,3`. No distribution/fairness/equivalence claim. |
| DOS game realization | DB-selected source splices reproduced separately native-tested fixture artifacts byte for byte | Original, LCG and xorshift physical input runs exercised holds, rerolls and scoring. The differing rolls are the discriminator; final totals can coincide. |
| Tic-tac-toe text | UIL text resources drove declared native character-field placements (`GG!!`, `TIE!`) | Source winner/checking logic retained for text-only output. The authored UIL covers the terminal handler, not the entire board checker. |
| Tic-tac-toe rule variant | Explicit misère handler values changed the awarded player on the same terminal board | Intentional rule change with a changed UIL definition. It is not an equivalent replacement under the original winner contract. DB-selected artifacts match separately tested native variants. |
| Generated Windows shell | Real PE32+ emission with bounded functions/loops, per-activation staging and native notification providers | Native Win/Lose, typed values, atomic failures and text events exercised through the existing headless Windows runtime. This is a new authored shell, not a wrapped DOS game. |

The fixture source/oracle material was available during investigation. These
are engineering integration experiments, not blind recovery or clean-room
reconstruction results. Native observations, scalar-model proofs and original
source-body preservation remain separate evidence edges.

## Frictions resolved in this implementation

**Byte identity alone cannot identify an interchangeable operation.** A snippet
now binds source/version, context, extents and payload hashes. A separate typed
contract states the admitted behavior. Candidate/equivalence links remain
attributed declarations with domain, evidence, adapters and unknowns; a stored
claim does not become a proof through repetition or transitivity.

**Segmented globals and local variables differ across compilers.** The DOS food
body uses DOS segment-relative globals; the Windows counterpart uses a frame
local and another selector. Explicit CPU adapters allocate isolated regions,
marshal inputs/outputs, validate the limited source selector replacements and
restore declared caller registers. Original and adapted instruction hashes
remain distinct. NE segment identity is not a live Windows selector.

**A physical register operation can carry extra dependencies.** `ADD` and `ADC`
are interchangeable only when the observable contract and incoming carry allow
it. Authored tests accept carry-neutralized ADC for two-value addition and
return a replayable counterexample for carry-observing ADC. This is output-port
equivalence, not full flag equivalence.

**Canonical identities require order-independent definitions.** Invocation
result aliases and ambiguous source bindings must refuse rather than let JSON
object insertion order change behavior under the same hash. Activation locals
also need fresh initialization; selected function realization commits declared
outputs and preserves caller inputs/other cells.

**Source passthrough is target dependent.** A retained 16-bit body can pass
through a qualified COM placement. It cannot run as native long-mode code inside
a PE64 merely because its logical operation matches. The Windows shell lowers
supported UIL to actual x86-64 and keeps startup, call frames, target services,
resources and source maps in a separate build capsule.

## Remaining work

The first native selection profile explicitly refuses noncanonical port maps,
nonempty input-domain restrictions, additional undeclared effect profiles and
unsupported service meanings. Future native adapters/admission guards should
realize those obligations instead of dropping them. General pointers, buffers,
aliasing, ownership, callbacks, recursion, exception unwinding and arbitrary
file/media services remain outside this profile.

A recovered `read_file` operation can eventually bind a DOS service, Win32 call
or Linux implementation through the same logical interface. That interface
must preserve errors, partial completion, resource identity and ownership as
well as returned bytes. Recognizing an interrupt number alone cannot establish
that operation. The current implementation supplies notification providers;
it does not perform an automatic BIOS-to-Win32 sweep.

The project now has durable snippet relations and selectable implementation
IDs. Automated source-to-UIL recovery, broader native proof, selection cost
models and an interactive comparison/selection view can build on those records.
A synthetic program can choose compatible blocks from different source
variants, but compatibility must still be qualified at each contract/adapter
boundary. A complete Colonization playthrough and complete game regeneration
remain unqualified.
