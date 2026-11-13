# Windows patch analysis path

The current Windows path has two distinct comparisons. A saved Wine/QEMU
experiment compares **two guarded code layer stacks of one PE version** from a
full native checkpoint. The offline trace helper compares **separately captured
PE versions** only when an investigator supplies evidenced site
correspondences. The debugger does not launch a patched project byte version or
restore one version's checkpoint into another executable. The latter would
require its own compatible-state and input contract.

## Evidence spine

| Stage | Existing component | Evidence and limit |
| --- | --- | --- |
| Identify inputs | Project byte identity, loader provenance, PE image base | Record each binary's hash, build identity and origin independently. Equal project-local version numbers do not establish a pair. |
| Locate candidate changes | Recursive analysis, xrefs, CFG and normalized instruction semantics | A code diff and static reachability are **candidate influence**, including unresolved calls, indirect transfers and memory aliases. They are not observed effects. |
| Map sites | `compare_trace_topology` with reviewed one-to-one correspondence for separate binaries | Record the source of each mapping. Keep unmatched blocks and repeated loop sites unresolved; do not infer a join from matching instruction text or runtime address. |
| Compare one PE under counterfactual layers | Wine/QEMU guarded RAM or execution layers and `compare_experiment` | Restore the same full native checkpoint before each script. Capture completed instruction traces, selected memory, final registers/FLAGS, stop observations and frames. Verify final baseline restoration. |
| Compare independent PE runs | Export each version's qualified trace, then use the offline topology helper | Site correspondence can align paths; input and checkpoint compatibility must be established separately. The helper does not certify both runs began in equivalent states. |
| Build an executable explanation | Authored UIL or a narrow C model with explicit typed ports and effects | Compare model outputs against original execution over chosen inputs and boundaries. Generated C is a realization of the model, not independent evidence that the binary was translated faithfully. |

## BinDiff as a correspondence lead

Google's [BinDiff matching concepts](https://github.com/google/bindiff/blob/main/docs/concepts.md)
make it a useful upstream source of candidate function and basic-block matches.
Its first signatures use flow-graph block, edge and call counts; later methods
use call-graph neighborhoods, names, hashes, strings and other anchors. BinDiff
reports **confidence in the match** separately from **structural similarity**.
The [zynamics BinDiff manual](https://www.zynamics.com/bindiff/manual/index.html)
notes that similarity can overlook changed operands and immediates when
mnemonics match. Neither number measures equality of intent or
runtime effects.

An eventual adapter should retain the original and selected-version hashes of
both binaries, each [BinExport](https://github.com/google/binexport) artifact
identity, disassembler and address-base convention, match method, confidence,
similarity and unmatched regions. The BinExport2 format can carry an executable
ID, commonly a source SHA-256, but the adapter must verify that value against
each owning fDisBull project rather than trust the field. A function or block
match narrows where to inspect; it is not yet the one-to-one instruction-site
correspondence required by `compare_trace_topology`. Changed instructions,
repeated loop sites and ambiguous matches stay unresolved until independent
anchors and trace evidence establish their alignment.

Once sites are established, the API-role and register-transfer helpers below
ask a different question: what the matched or divergent paths actually do at
the selected boundary. This separation lets a high-confidence BinDiff match
contain a critical operand change, or a low-similarity obfuscated path carry
the same bounded register transfer. BinDiff has not been run on the current PE
fixtures or wired into this prototype; this section defines the evidence an
adapter must preserve.

## Intent evidence from PE import calls

The `fdisbull.patch_roles` helper adds a narrow context layer to the offline
topology report. Given a raw Wine/QEMU PE trace, an owning `Project`, and one
analyzed function entry, `observed_pe_import_roles` joins each observed call
site to that function's non-stale declared-import binding. It checks the
project's original source hash, selected code-version hash, PE architecture,
trace identity, executed CALL instruction, analysis budget and static binding
stability. It also checks that the executed instruction bytes match the stored
analyzed instruction. A changed execution layer, ambiguous binding or missing identity
leaves the role unresolved. The helper does not scan the whole binary; callers
must account for functions outside the selected analysis.

`compare_divergent_import_roles` recomputes topology from the supplied traces,
checks the exact trace digest for each projection, and highlights a repeated
declared API role in evidenced divergent spans. This gives an investigator a lead when two
different instruction paths reach the same framework boundary. It never marks
the paths or their intent equivalent: argument values, call order, return
values, memory effects, error paths and runtime DLL resolution still need
independent comparison. A shared API name may implement different intent; a
changed API name may implement the same intent. The topology's path and sampled
state verdicts are unchanged.

The user's CHimpREC pair provides a concrete static illustration. Read-only
inspection of the supplied PE32 and PE64 executables found width-specific
thunk walks: each reads a pointer-sized entry, tests for zero, advances by the
entry width and repeats. Both expose IAT search/rebuild actions and import
Win32 process-memory and module APIs. The common *candidate role* is import
discovery across a thunk table, despite different machine encodings and
registers. That is a bounded structural interpretation of these binaries;
the inspection did not execute them or prove whole-binary API coverage, the
complete algorithm, or behavioral equivalence. Existing
[`CHIMPREC.md`](CHIMPREC.md) documents the separate offline import-recovery
work; this patch context layer does not duplicate that recovery engine.

The supplied *64-bit Unpacking* lab and *Unpacking Theory* slides add a useful
counterexample to name-only reasoning. They describe fake IAT separators,
redirected and emulated APIs, forwarded exports, and traps for unbounded
automated tracing. Those descriptions are historical course claims, not
instructions to execute or patch their targets. They reinforce why a declared
import is only a candidate role: a patch analysis must compare the surrounding
data flow and ordered effects, and preserve unresolved cases, before it can
claim that two paths express the same UIL intent.

## Guard decisions, difference witnesses and backward slices

`fdisbull.pe_guard_analysis.compare_pe_patch_paths` combines the existing
register-transfer report with `compare_pe_patch_guards`. The guard analysis
accepts raw PE32/PE64 traces under the same identity and completed-step
contract. It evaluates all 16 direct Jcc predicates from captured FLAGS,
checks the recorded successor and preserved state, and admits full-width
register MOV, register/register or register/immediate CMP, NOP and direct
JMP/Jcc prefixes. CMP arithmetic FLAGS are independently modeled and checked
against the next sample. Unsupported operations, memory operands, partial
registers or inconsistent state stop extraction at an explicit frontier.

Only branches paired by evidenced common topology are compared, and both
prefixes must start at a common entry. Each guard carries a backward data
slice through the latest CMP and contributing MOV definitions to entry
registers or entry FLAGS, plus prior control-decision indices. Overwritten
definitions are excluded. These are captured-prefix guard slices; arbitrary
memory dependencies and external outcome slices remain unresolved. Unmatched
guards and partial extraction remain explicit even when other pairs compare.
Each normalized predicate has a semantic ID independent of instruction
addresses and temporary MOV definitions, with explicit entry-register names
and widths retained. For example, `CMP RCX,RBX` and `MOV RAX,RCX; CMP RAX,RBX`
reduce to the same guard expression. The latter still clobbers RAX, so equal
guard IDs do not authorize contracting both whole regions as equivalent.
The original trace digests, instruction indices and slices remain expandable
evidence for this scoped reduction.

Different predicates trigger a finite search over boundary and sampled values
under one shared entry register/FLAGS assignment. Earlier modeled branch
decisions must hold on both captured prefixes. A found witness includes that
entry state, both guard decisions and predicted successors; it establishes a
decision difference in the admitted models. It does not establish an external
behavioral difference or native replay. In particular, taken/not-taken can
differ while target equals fallthrough, and branch inversion may accompany
swapped destinations. Successor correspondence remains uncompared. Search
exhaustion or a candidate-budget stop proves no equivalence. Reports include
source/version hashes and exact trace-document digests.

The homegrown JA-to-JAE test generates the equality-boundary witness, traces
its inputs through MOV and CMP, and independently replays that witness in
Unicorn to confirm different successor instructions. All Jcc predicates are
checked against Unicorn for all combinations of CF/PF/ZF/SF/OF in PE32 and
PE64. This validates the bounded model, not a native Wine/QEMU capture.

## Regional equivalence and controlled contraction

`fdisbull.pe_region_equivalence.compare_pe_regions` proves equivalence of two
captured regions under an explicit live-state contract, using the optional
existing `proof` extra (Z3). Only entry and exit correspondence is required;
the interiors may have different instruction counts and graph shapes. The
comparison builds shared symbolic entry registers, FLAGS and byte-addressed
RAM, proves both captured path domains feasible and equal, then checks for a
counterexample in live outputs and memory effects. Unsatisfiable domain and
effect differences authorize `equivalent_under_contract`. Unsupported behavior,
missing evidence, solver absence or timeout return unknown without contraction.
This is equivalence over the captured paths' domains, not every path through
the surrounding functions.

The caller must establish liveness at the boundary. Defaults keep every
general register and all 32 captured FLAGS bits live. A narrower
`live_registers` list or `live_flags` mask is an explicit assumption retained
in the result. The admitted register model includes full-width MOV, ADD, SUB,
XOR, AND, OR and CMP, plus NOP and direct JMP/Jcc. Undefined AF after logical
operations prevents a live-AF proof unless a later operation defines it.
Partial register aliases, calls, legacy prefixes and unsupported implicit
effects remain unknown. All captured register/defined-FLAGS transitions are
checked against the model independently of the symbolic equivalence query.

MOV loads and stores use at most 256 bytes of explicitly declared
`private_ordinary_ram`. Addresses can be symbolic, including scaled indices
and pointers loaded from symbolic RAM. Optional `entry_register_ranges`
provide inclusive unsigned `min`/`max` bounds; fixed `entry_registers` remain
available. Observed pointers alone never establish a bound. Each access must
be proved safe under the entry assumptions and guards **preceding that
access**. A later guard cannot hide an earlier unsafe access. Access bounds
are proof obligations, not assumptions that shrink the compared path domain.
An unsafe alternative returns unknown with a safety counterexample even if
the captured pointer was valid.

Symbolic reads select the current byte map, and writes conditionally update
every possibly aliased byte. The model preserves little-endian values,
overlapping stores and store-to-load aliases. Ordered effects compare symbolic
addresses as well as values. Access spans cannot wrap through address zero.
Exact entry/exit memory snapshots remain required, and the modeled exit must
agree. Code overlap, unproved bounds and contradictory evidence prevent
contraction. All declared RAM bytes remain live, and other memory is framed
as untouched by admitted code. Symbolic alias expansion is bounded to 32,768
byte-cell operations per region. A cumulative proof deadline covers model
construction and solver queries; reduced-effect presentation follows the
proof. Exhaustion produces unknown, never an equivalence result.

`memory_observation="ordered"` is the default: read/write kind, address,
width, value and final bytes must agree. The explicit `"final"` mode compares
final private RAM and can discard an overwritten temporary store; it assumes
no concurrent or external observer of intermediate accesses. Equal sample
bytes do not suffice: the solver can expose a differing overlapping write for
another input and returns a concrete model counterexample for replay.

Successful contraction produces one region node containing the live-state
contract, solver version/budget, proof outcomes, boundary identities, original
event indices and exact trace/memory digests. It also presents typed symbolic
live outputs, path domain, RAM bytes and ordered accesses as the reduced
operation, with explicit presentation truncation if needed. These expressions
describe the modeled operation; they are not an executable UIL program or a
solver certificate. `expand_pe_contraction` verifies
those identities and returns copies of the original evidence. The digest is
an integrity check, not an authenticated proof signature. No source bytes are
deleted or replaced, and no broader human intent label is inferred.

The existing combined API accepts `region_contract` and optional
`baseline_memory`/`layer_memory`, returning the proof in `regional` alongside
guard and register-path evidence:

```python
report = compare_pe_patch_paths(old_trace, new_trace, same_source=True,
    region_contract={"live_registers": ["rax"], "live_flags": 0})
if report["regional"]["status"] == "equivalent_under_contract":
    node = report["regional"]["contraction"]
    original = expand_pe_contraction(node, old_trace, new_trace)
```

The omitted registers/FLAGS in this example must be proved dead by the caller.
Native CPU-model tests cover live clobbers, arithmetic cancellation, guarded
domains, ordered versus final RAM, byte aliases, memory loads through
temporaries, contraction expansion and independent counterexample replay.
They do not qualify a native Wine/QEMU run or external effects.

## BLA source-region qualification

`scripts/verify_bla_patch_regions.py` runs a bounded campaign against an
existing external [BLA](https://github.com/qybaihe/bla) checkout at the reviewed
revision `0269b5b0f4f2941e53070c9b3ffbda88d5348437`. It pins the selected L1
source hash and validates selected source cleanliness, exact pure-expression
patterns, module sections and opcode profiles. Original challenge files stay
outside this repository. The runner emits a sanitized JSON report with
artifact hashes, source-region offsets, proof assumptions and runtime receipts.

The actual BLA crackmes in this corpus are JS/CommonJS and Wasm. They do not
qualify as x86 inputs to `compare_pe_regions`. The campaign establishes these
separate region claims:

- Three matched L1 opaque predicates reduce to constant true. Two square
  predicates require `seed & 3 == 1`; a consecutive-product predicate is
  universally true for the u32 input profile. The standard `Math.imul`
  intrinsic is assumed. Z3 counterqueries are unsatisfiable, and Node checks
  264 deterministic seeds per expression. Seed zero falsifies the two square
  reductions outside their stated invariant.
- The clean v6 Wasm module is 98 bytes and the decoded hardened module is
  6,880,354 bytes, with 2 versus 252 exports. Their type/function sections and
  53-byte executable code section are identical. The admitted `mix`/`seal`
  regions have no imports, memory, table, globals, start, element or data
  sections, and use a checked pure-i32 opcode profile. Both actual modules
  agree on 144 `mix` pairs and 144 `seal` inputs in Node, also matching an
  independent interpreter of the parsed bodies.

The Wasm result is code-region identity beneath changed presentation, not a
proof that different instruction bodies were normalized. The JS result is a
source-matched predicate reduction, not whole-function equivalence: corpus
integrity, shadow-heap writes, calls, module exports and timing remain outside
the proof. Finite runtime agreement stays separate from the symbolic claims.
The runner executes only matched pure expressions and admitted Wasm modules,
with bounded Node memory/time; it does not run the complete CJS targets.

## BLA complete-function qualification

`scripts/verify_bla_functions.py` extends that source campaign to the complete
`sha256Hex` and `tryUnlock` exports and the latter's `decodeFlagCipher` and
`deriveFlagMask` call closure in the original v6 L1, L2 and L3 CJS artifacts.
It checks the owning checkout revision, selected-source cleanliness, exact file
hashes and published commitments before execution. Existing Babel modules are
supplied explicitly; the runner downloads no dependencies. For example:

```sh
python scripts/verify_bla_functions.py \
  --root /external/bla-upstream \
  --babel-root /external/trusted/node_modules \
  --output /external/evidence/bla-functions.json
```

The source reducer in `scripts/bla_function_analysis.cjs` recognizes only exact
pure opaque-predicate patterns and records their modular low-bit proofs and
source hashes/offsets. It folds literal string fragments and normalizes bound
local names, rejecting name collisions, shadowed dependencies and guard
contraction that could change declaration scope. The four reduced function
ASTs and five constant initializers must match the materialized clean template.
The contraction ledger preserves the connection to the original source; the
original artifact is never rewritten or replaced by the reduction.

Shadow-heap calls require a separate effect contract. The analyzer checks
literal heap initialization, references, direct ignored calls, pure numeric
arguments and the mutator's dependency/call surface. It retains the mutator's
source identity and heap shape. Projecting away those calls assumes the pinned
heap is ordinary and unaliased, with stable intrinsics/prototypes and no
permitted private-heap observer. The preservation and termination obligations
are now checked separately as described below. All three hardened targets
really mutate their heaps; full-state equivalence to the clean template is false.

`scripts/bla_function_runtime.cjs` separately runs the original CJS exports in
bounded Node VM contexts, under an explicit crypto/Buffer call boundary. Its
observer compares return values, exception names/messages, ordered external
calls, controlled input-coercion effects and exported constant state. A second
diagnostic execution logs private heap writes through proxies and must agree
with an uninstrumented execution on returns, calls and final heap contents.
Reports contain only hashes/counts of those observations. The VM wrappers are
diagnostic isolation; Node's VM is not a hostile-code security boundary.

The pinned L1/L2/L3 campaign checks two process-seed bases, verifies the actual
corpus digest and `seed & 3 == 1` invariant, and observes agreement in 204
actual-crypto calls across 17 input classes. Another 42 controlled crypto-call
scenarios exercise downstream success, rejection and exception paths. These
modeled scenarios do not establish actual valid-key acceptance. The reference
is the original clean template materialized with commitment-checked target
constants, not an independently built original release.

Two deliberate counterexamples keep the boundary visible: passing each module's
own function as input exposes source differences, and poisoning `Math.imul`
through a coercion callback makes later hardened calls differ. Source/name
reflection, exception stacks, timing, resource exhaustion and hostile callbacks
are outside the admitted contract. The composed source proof below establishes
selected whole-function observational equivalence under explicit contracts;
finite observations remain separate. Universal JS contextual equivalence and
whole-module equivalence remain unproved.
This is a JS source experiment, not native Windows whole-function qualification.

### Shadow-heap induction and termination

`scripts/bla_shadow_heap_proof.cjs` checks the original parsed mutator and heap
initializer against a narrow numeric heap model. Source hashes alone do not
authorize a proof. Unsupported statements, structural writes, unsafe accesses
or unrecognized loops return `unknown`. The complete-function campaign requires
a `proved` certificate tied to both the target source and the exact mutator
before it reports the preservation and termination obligations as discharged.

The entry invariant describes ordinary writable own data properties, dense
fixed-length arrays, existing slots with four words, equal-length share arrays,
and numeric fields in `0..2^31-1`. Initialization establishes the base case.
The checker generalizes these numeric values rather than assuming the original
contents. It checks the admitted arithmetic, indexed accesses and writes against
the invariant, retaining structural identities and unchanged metadata. Masked
writes return to the unsigned 31-bit range; the unmasked share XOR also stays
there because both operands have a zero sign bit. Addition bounds keep the
integer intermediates exactly representable as JavaScript Numbers. Nonnegative
remainder operands and positive immutable lengths keep slot/cursor accesses
within existing arrays.

The two admitted loops have natural-number ranking functions `8 - i` and
`share_length - k`. The counters start at zero and advance by one, and neither
their bounds nor their progress can be changed by the body. Each iteration
preserves the heap invariant, giving an inductive postcondition for each loop
and the whole mutator. For all three original targets, one invocation executes
at most **51 loop iterations**: eight slot iterations and 43 share iterations.
The source-derived numeric write bound is **165 for L1** and **169 for L2/L3**.
Together, initialization and the mutator postcondition establish preservation
under any finite sequence of admitted invocations, without bounding that
sequence to the sampled runtime tests.

The runtime campaign separately checks the invariant after original exported
function calls and compares original mutator executions with an independently
authored concrete transition model on boundary heaps and numeric deltas. These
finite crosschecks exercise the proof model against the unchanged real target
code; they are not the induction or termination proof. Independent Z3
counterqueries check the arithmetic closure, access bounds and ranking lemmas,
with satisfiable negative cases when essential constraints are removed.

The discharged obligations are specifically numeric heap preservation and
mutator termination in the admitted source/model. Ordinary writable objects,
no getters/proxies or external aliases, stable standard intrinsics/prototypes,
and an execution model excluding resource exhaustion remain explicit boundary
conditions. These checks do not establish arbitrary JavaScript termination,
crypto-provider totality, universal contextual equivalence or equality of the
private heaps. The earlier reflection and intrinsic-poisoning counterexamples
continue to distinguish the original programs outside the contract.

### Noninterference and whole-function composition

`scripts/bla_heap_noninterference.cjs` establishes a two-run private-state
relation. Two executions may have independently different admitted heaps and
the same permitted public state. The checker independently reparses the source,
recomputes the heap transition proof and audits lexical separation, exact
binding ownership and escape paths. Each selected private call must evaluate a
pure safe-integer literal and discard its result. Totality, the private write
frame and empty observable trace then make that call a finite silent step:
it preserves the public state in either run and can be erased. All three BLA
tiers have four selected call sites. Three other module call sites are recorded
and remain outside the selected closure.

`scripts/bla_function_equivalence.cjs` composes that result with the guard and
call contracts. It independently replays the admitted pure guard/literal
rewrites from original source, checks the exact private-call sites against the
noninterference certificate, and compares all four complete normalized function
ASTs and their five constant dependencies. The private-step erasure is binding
aware: a local parameter with the same spelling as the mutator cannot authorize
removing its call. Stale or mismatched source, guard, contraction or heap
evidence cannot produce an equivalence certificate.

The composer checks the remaining call closure and method receiver types,
including hash creation/update/digest, Buffer construction/allocation and
decoding, primitive String conversion and string predicates. It substitutes
the acyclic helper contracts into callers using AST congruence and private-step
stuttering. The proof compares return values, exception names/messages, ordered
provider operations and related reachable public data. The private heaps may
continue to differ. These are whole selected function proofs for all admitted
inputs and related entry states, relative to the checked source model and
explicit leaf-call contracts.

The input domain is all ECMAScript primitives for `sha256Hex`. `tryUnlock`
accepts any value; its checked type gate rejects nonstrings before coercion or
provider calls. Helper inputs are strings. The literal-corpus seed condition
is discharged by the source proof below. Public constants and the
exported `LICENSE_RPC` object must remain related ordinary data. The SHA-256 and
Buffer providers must be coupled total synchronous providers: equal admitted
operations on related receivers/arguments return related hash objects and
nonoverlapping logical Buffer byte views
and equal primitives, or throw matching exception names/messages. They cannot
reenter the functions, inspect private/source/caller state or mutate the
intrinsics or public data. Buffer backing-store identity, allocator state,
outside-view bytes and metadata mutation are excluded. Logical lengths remain
stable under the admitted operations. Stable standard String/object/array semantics and
the earlier observer exclusions remain part of the contract. Provider totality
is a leaf contract; it is not inferred from private-heap termination.

The real-target campaign separately runs repeated calls with zero/maximum
numeric private cells and different cursor positions while preserving the same
public inputs/provider state. It compares both target executions with the
materialized clean reference on 123 two-heap cases across L1/L2/L3, including
BigInt, NaN, infinities and the modeled collaborator exceptions. The existing
204 actual-crypto observations, 42 modeled call scenarios and 144 direct-mutator
boundary checks remain separate receipts. Runtime agreement checks the source
proof against original code; it does not replace the noninterference or
composition argument. Module initialization, CLI behavior, unrestricted JS
contexts and native Windows whole-function equivalence remain unqualified.

### Intact-corpus seed proof and real provider qualification

`scripts/bla_seed_invariant.cjs` proves the digest/seed initialization prefix
from the original source. It checks the literal own-string corpus, the complete
digest function AST and their binding identities, then evaluates the exact
UTF-16 code units with an independent BigInt multiply/rotate model. The corpus
cannot escape into other functions or be changed before the seed declaration.
The exact first three executable statements establish that no intervening
effect changes the data or the digest calculation. Embedded instruction-like
payloads are string data throughout this check; they are never evaluated.

| Original tier | Proved corpus digest | Entries | UTF-16 loop iterations |
| --- | ---: | ---: | ---: |
| L1 | 4129934667 | 4 | 817 |
| L2 | 3543391658 | 6 | 1078 |
| L3 | 919223159 | 8 | 2400 |

Each calculated digest equals its embedded commitment. The checked initializer
clears the clock's low two bits with `0x7fffc` and ORs the now-proved commitment
bit `1`. Consequently `(seed & 3) === 1` for every admitted process-clock BigInt,
Date-clock Number and fallback value, including negative/wrapped clock values.
The digest loops terminate over fixed literal strings and the seed binding is
immutable. Normal synchronous clock interfaces and standard numeric/string/
array semantics remain explicit environmental conditions. The composer
recomputes this certificate and links its digest, replacing the earlier
unproved corpus-equality premise for these three original artifacts.

`scripts/bla_provider_validation.cjs` separately checks the actual Node
`node:crypto` and `node:buffer` implementations. Its 73 finite cases cover four
SHA-256 known vectors, padding/chunk boundaries, independent SHA-256 arithmetic,
primitive/Unicode UTF-8 encoding, hex-prefix and malformed UTF-8 decoding,
buffer zeroing/indexing/copying and native exception/state behavior. The receipt
records the Node executable hash, Node/OpenSSL versions, FIPS mode and selected
builtin JavaScript source hashes. It identifies the tested runtime rather than
establishing universal native-code correctness or a complete library provenance
chain.

Native Buffers demonstrate why the observation boundary matters. Distinct
logical views can share an allocation pool, and a whole-backing-store observer
can inspect bytes outside a view. A Buffer's `length` property can also be
shadowed through metadata operations. The provider relation therefore covers
nonoverlapping logical byte views and lengths preserved by the admitted BLA
operations; it excludes backing-store/allocator observers, metadata changes,
detachment and concurrent observation. The selected typed source never uses
those excluded capabilities.

`scripts/bla_native_functions.cjs` adds a fresh bounded native CJS execution for
each artifact. It compiles the exact source through Node's ordinary CommonJS
loader, with real crypto/Buffer globals, no target observer suffix and no
provider substitutions. The CLI entry is not invoked. All 102 native primitive
export observations agree with the instrumented VM and materialized clean
reference on return/throw digests. These native runs do not intercept the call
trace. Their executable/version/OpenSSL/FIPS identities must match the provider
validation receipt. They are authorized-target probes, not hostile-code
sandboxes.

The seed result is a source proof. The native provider and loader receipts are
finite implementation evidence. The whole-function theorem retains its typed
relational provider contract, stable intrinsic semantics and observer limits;
those native contracts are not universally discharged by sampled conformance.
No actual valid-key acceptance or native Windows qualification is inferred.

## BLA module initialization and terminating CLI

`scripts/verify_bla_modules.py` extends the pinned function campaign with an
independent module composition and fresh native module/CLI observations:

```sh
python scripts/verify_bla_modules.py \
  --root /external/bla-upstream \
  --babel-root /external/lasik-src/node_modules \
  --output /external/evidence/bla-modules.json
```

An optional `--valid-key-file /private/external/key.json` supplies a UTF-8 key
or a JSON object with a `key` or `authorization_key` string. The file is bounded
and its candidate must match the pinned archive's key commitment before target
execution. The runner never emits the key, ciphertext, returned flag or source.
It records hashes and classifications. This is an authorized-target native
probe, not a hostile-code sandbox.

The original three modules **are different from the materialized clean
reference under a global initialization observer**. The source checker
classifies all 93/121/151 top-level statements, preserving order, lexical
function declarations, pure allocations and reached effects. Each module
installs a configurable non-enumerable getter on `globalThis` when its named
property is absent. An event-capable host additionally sees 6/10/10 listener
registrations. L2/L3 have a reached bounded crypto block with 36 SHA-256 and
4 HMAC operations when the checked native builtin interfaces complete normally.
Those calls remain explicit in the effect inventory even though their results
are discarded. Getter names and source regions are retained as hashes/offsets.

Native import observations independently confirm the added getter for every
tier. Exported functions also retain different `.name` values, another
reflection-level difference. The same six export keys and related constants
and function contracts do not establish equality of the entire exported object
under reflection. An unclassified initializer or changed control profile
prevents the module certificate from claiming a complete inventory.

The CLI has a stronger, separate result. The source-bound checker recomputes
the seed, heap and selected-function proofs, extends heap noninterference to
the two CLI functions, and compares their complete normalized ASTs. It checks
the executed startup prefix and exact `require.main === module` dispatch order.
Every admitted normal path prints usage, grant or denial output and reaches
native `process.exit`. The decorative initializers occur later and cannot run
on those paths. Each tier therefore has CLI `equivalent_under_contract` while
its CommonJS initialization status remains `different`.

This CLI theorem observes ordered normal console writes and exit status under
ordinary string/undefined `argv[2]`, stable intrinsics, normally completing
crypto/Buffer/console interfaces, native immediate exit and no exit handlers
or reentry. Provider throws, failed writes, exception-stack formatting,
reflection, resource/timing and concurrent observers remain outside that
contract. The theorem covers the checked source paths; it does not establish
that an unknown input satisfies a cryptographic acceptance predicate.

The native oracle compiles exact unmodified source with real providers and
uses a CommonJS main-module/argv bridge. No target suffix, body rewrite,
provider replacement or exit substitution is installed. Its nine no-witness
cases cover missing/empty arguments, short, minimum/maximum-length wrong keys,
overlong and Unicode inputs, the honeypot string and an ordinary wrong key.
All 27 original-target CLI cases agree byte-for-byte with the materialized
reference on stdout/stderr and exit status; reports retain hashes and lengths.
The corresponding 27 exported `tryUnlock` calls return null. A separate direct
Node invocation of the original files crosschecks those same 27 CLI cases
against the bridge. Finite observations and the static theorem remain separate.

Actual valid-key acceptance for this **archived tiered v6** remains unverified:
the later solved v6 is a different edition and its witness does not match the
archive's commitment. Without a matching external key, the oracle reports
`verified_finite_rejections_real_acceptance_pending`. With one, it additionally
requires original exported acceptance, a returned flag matching its commitment,
real CLI grant/exit zero, acceptance with an extra CLI argument and rejection
of a one-character key mutation. Authored acceptance regressions qualify that
harness branch; they never qualify acceptance on the original targets.

Reading native global descriptors can itself initialize Node's lazy globals.
The oracle records that observer bootstrap separately, reaches a bounded stable
baseline, and then measures target initialization. The independently observed
getter difference does not depend on those bootstrap effects. Full module
equivalence remains false; reduced core/CLI intent does not erase reached
ambient effects.

## LASIK as a reduction candidate

The requested project is [LASIK](https://github.com/pktq/lasik), a static
deobfuscator aimed specifically at BLA, with CLI, library and MCP interfaces.
Its source has known-bits guard reductions, corpus-interlock evaluation,
string recovery, private-state pruning and runtime-decoy removal. The latter
[deliberately removes decoy global/listener blocks](https://github.com/pktq/lasik/blob/main/src/js/passes/runtime-decoys.ts).
Those are useful candidates for recovering core intent; the observer contract
still determines whether removal preserves the behavior being compared.

A finite static trial used the existing local LASIK 0.3.0 distribution alongside
checkout `58f47e047a4d858e29186e5c3dab38ebba8a7786`, without downloads, setup,
target execution or the prompt-firewall transform (`firewall: false`). It reduced
the exact archived L1/L2/L3 files as follows:

| Tier | Original bytes | Reduced bytes |
| --- | ---: | ---: |
| L1 | 78,614 | 2,731 |
| L2 | 163,626 | 2,434 |
| L3 | 189,095 | 2,449 |

The trial fingerprints the compiled entry and reduced outputs; it does not
establish build provenance or behavioral equivalence of LASIK's output. Our
module counterexample shows why output size and successful deobfuscation cannot
authorize a whole-module contraction. LASIK's published multi-format v6
benchmark also uses a different challenge edition from this archived tiered
corpus. Candidate correspondence, checked reductions, retained effects and
native witnesses remain distinct evidence.

## Current v6/v7 originals and LASIK reductions

`scripts/verify_bla_current_modules.py` compares the current Harden-Native v6
and Meridian v7 editions against fresh LASIK reductions, using external
commitment-matching key files. These editions remain distinct from the archived
single-file L1/L2/L3 experiment above.

```sh
python scripts/verify_bla_current_modules.py \
  --root /external/bla-upstream \
  --lasik-root /external/lasik-src \
  --prepared /external/current-lasik/preparation.json \
  --v6-key-file /private/external/v6-key.json \
  --v7-key-file /private/external/v7-key.json \
  --output /external/evidence/current-modules.json
```

For a new preparation, replace `--prepared` with `--prepare-output` naming a
new external directory, after storage admission for the planned allocation.
The preparer refuses an existing destination. It checks originals against the
pinned release seals and Git objects, fingerprints the existing LASIK
distribution, creates independent original/reduced trees and decompresses the
v6 Wasm for its real host. The campaign replays the exact static JS/HTML/Wasm
reductions in memory and checks every prepared file before and after native
execution. Changed candidate bytes cannot be qualified merely by updating a
manifest hash. Symlinks, unlisted files and shared original/candidate inodes
prevent qualification. No dependencies are downloaded or installed.

The comparison records separate results:

| Boundary | Current v6 | Current v7 |
| --- | --- | --- |
| Plain native CLI | All ten cases agree, including real valid/mutated keys and three actual retired-key honeypots | Eleven of twelve agree; the recovered valid key succeeds only on the original |
| Initialization | Missing input exits before the decorative tail; the measured valid/mutated-key inputs allow the original's added getter to run while async main is suspended | `process.exitCode` allows the original's later getter initializer to run |
| Exported API samples | The host invokes async main automatically; it exposes no activation API | Fourteen synchronous calls cover all nine exported product functions; thirteen result/throw projections agree, and valid-key activation differs |
| Wasm interface | Exports change from 252 to 2 and the `name` custom section is removed | Not used by this edition |
| Whole-module equivalence | Refuted by initialization and Wasm reflection | Refuted by real activation and initialization differences |

The v6 selected `mix`/`seal` exports retain the same indices, types and function
bodies. The admitted pure-i32 decoder confirms identity of the type, function
and 53-byte code sections. That supports preservation of these two computations
under standard Wasm semantics. The removed export aliases and custom sections
remain observable through ordinary Wasm reflection, so complete module equality
does not follow from code-section identity.

V7 has a concrete source-byte dependency. Its retained integrity helper hashes
five JS files and returns the digest to the activation seed builder. The
binding-aware slice connects exported `activate`, file reads, the immutable
SHA-256 receiver and returned digest, seed definitions, `timingSafeEqual` and
the conditional return. Every measured original/reduced file pair differs.
Running the candidate from its **own reduced tree** rejects the recovered key
through both the CLI and original exported API. Compiling reduced text with an
original filename would give its relative reads the wrong filesystem context.

A separate causal diagnostic installs a phase-guarded filesystem wrapper before
loading the reduced graph. During all module loading it delegates unchanged;
only during synchronous activation does it optionally supply the five pinned
original source-byte inputs. The same-wrapper control rejects the valid key,
the five-input substitution restores the committed certificate, and disabling
substitution rejects again. Mutated keys reject throughout. All substituted
reads and their byte hashes are recorded. This experiment explicitly changes
the filesystem provider contract; the native standalone reduction still fails.
It supports the observed byte-to-integrity-to-acceptance chain without proving
every other transformation preserves behavior.

`bla_current_module_analysis.cjs` inventories calls, writes, reflection,
CommonJS edges, initialization phases and syntactic dependency slices. It
retains unresolved receivers/callbacks and marks the inventory incomplete.
Matching fragments, counts and finite native agreement never authorize a
universal JS equivalence claim. Discarded reads remain effects but do not become
digest-input edges unless linked to the returned hash receiver.

`bla_current_module_runtime.cjs` separates plain CLI execution from measured
CLI/module execution. Plain runs have no exit listener or descriptor priming.
Measured runs declare both, record synchronous return separately from actual
exit, and observe global descriptors, process listeners, bounded exports and
call results. A listener observes its own registration-order point, not effects
of later exit callbacks. Pre-existing object internals, arbitrary file writes,
browser event registrations, unawaited async export results and resource/timing
behavior are not exhaustively traced. Native filesystem, crypto, Buffer, Wasm
and exit interfaces remain unmodified in the baseline comparison. Raw keys,
target bytes and returned flags/certificates stay outside Git and uploads.

## Authored BLA calibration curriculum

The archived crackmes remain useful adversarial examples, but recovering a key
from a cryptographic flaw does not measure recovery of an original algorithm.
`fixtures/behavior-curriculum/` provides an MIT, known-source PE64 DLL target
with no imports, entry point, secret or flag. Keep its source and independent
integer oracle available to the evaluator; a future blind recovery exercise
must receive its own declared input packet without those answers.

The exported wrapper accepts unsigned 64-bit `x`, `limit` and a caller output
pointer. It leaves the output untouched when `x > limit`; otherwise it stores
`((x XOR 90) + 7) modulo 2^64`. The separately exported, non-inlined core makes
the guard and output boundary explicit. Caller output must be disjoint from the
DLL image and active stack: allowing it to alias BLA's shadow heap would change
the equivalence question, even on rejected inputs.

Run the verifier from a source checkout with an existing reviewed BLA 3.2.4
distribution and compiler/linker. It creates a new external output directory
after a 50 MB storage admission; it does not install a toolchain or execute the
teaching EXEs supplied with the research discussion.

```sh
PYTHONPATH=src python scripts/verify_bla_curriculum.py \
  --output /external/evidence/authored-bla-01 \
  --bla-cli /external/bla/dist/cli.js \
  --node /existing/supported/node \
  --clang /existing/clang \
  --linker /existing/lld-link \
  --seed fdisbull-known-target-v1 --max-level 3
```

`--max-level 0` builds the baseline and mandatory guard mutation only; higher
values add these retained stages in order:

| Level | Construction | What it exercises |
| --- | --- | --- |
| 0 | Original authored C, `-O1` | Plain guard, wraparound and one output store |
| 1 | Original build plus BLA `protect --intensity stealth` | Post-build section/slack/trailer noise |
| 2 | Generated C header at `stealth`, explicitly called anchor, then `protect stealth` | Reachable generated work and private image mutations |
| 3 | Generated header and post-build pass at `balanced` | More retained generated material under the same caller contract |

These are construction levels, not a measured difficulty scale. The reviewed
native BLA post-build path does not rewrite the customer's reachable kernel.
The source-authored wrapper explicitly discards the generated anchor's return;
it still executes its volatile writes. This is distinct from an agent-authored
weave that makes the business result depend on protection state.

The campaign retains original compiled DLLs, protected DLLs, object files,
generated headers, complete command arguments/logs, tool and artifact hashes,
external analysis databases, and exact core trace/RAM evidence. The extracted
BLA distribution is identified by its payload hashes and package version;
matching an upstream version string does not establish source-build provenance.
Target fixtures remain outside tool-only packages.

The initial local qualification used Clang/LLD 23.1.4, supported Node 26.13.0
and BLA 3.2.4. All four unchanged variants passed 254 complete-wrapper Unicorn
calls each. One retained CPU per variant preserves image state between calls.
Cases cover unsigned boundaries, equality, modulo wraparound, seeded inputs
and same-input repetitions after other calls. The verifier checks every output
value and permitted store count, canaries, stack restoration and Win64
nonvolatile general registers. Writes outside output, stack and declared
writable image sections fail the campaign. Anchor variants executed four
private image writes per call; post-build-only protection executed none.

fDisBull imports and recursively analyzes each exact DLL, verifies a stable
analysis stop and reopens the database to verify persistence. For accepted and
rejected **core** paths it checks explicit cross-file boundary correspondence,
live nonvolatile registers/stack, dead FLAGS and the caller's eight RAM bytes.
The baseline and three unchanged levels each yielded two
`equivalent_under_contract` results. Each contraction was expanded back into
the exact traces and RAM evidence. This does not contract the complete BLA
wrapper or prove private-heap noninterference for every input.

The separate `GUARD_MUTATION` build changes rejection from `>` to `>=`.
Every call is checked against that exact mutated contract, so an arbitrary
broken implementation cannot pass merely by producing one difference. It
differed from the baseline on 79 of 254 cases, all at equality (including one
store-event difference with identical final bytes). Both aligned
core-path comparisons found a guard-domain difference; their symbolic
input/output-memory projections were replayed on complete wrappers and
produced a real output/store difference at `x == limit`. For example, with
`x = limit = 0` and initial output `0x0123456789abcdef`, the original stores
97 while the mutation leaves the initial value. Pairing an accepted path with
a rejected path can produce unrelated domain counterexamples, so the verifier
aligns accepted with accepted and rejected with rejected before replay.

Repeated complete builds with the same seed/options produced byte-identical
DLLs and headers in this local environment. That observation does not promise
cross-toolchain determinism. Execution here means direct function calls under
Unicorn, normalized to the existing PE completed-step evidence schema; it does
not establish Wine or native Windows loader behavior. SIMD state, timing,
resource effects, arbitrary aliasing, agent recovery quality and training
improvement remain unqualified.

## Register-only transfer projection

`fdisbull.pe_path_transfer.compare_pe_register_paths` now composes a symbolic
mapping from each captured entry register to the selected-thread general
registers at a common exit. It accepts completed, source-hash-recorded PE
traces with evidenced topology from a common entry to a common exit. Every
executed step before the exit must be a full-width register MOV checked against
the existing UIL step model, a one-byte NOP, or a direct near branch. It
checks each next PC and all sampled general registers and FLAGS, then walks
MOV dependencies backward to identify writes overwritten before use. A memory
operand, call, partial register, malformed step, changed undeclared state or
unresolved path makes the projection unknown.

Two encodings of `MOV RAX,RBX` can therefore have equal admitted register
transfer despite different bytes. In the authored detour test, one path first
copies `RCX` to `RAX`, then both paths copy `RBX` to `RAX`; the detour's first
write is dead at the common exit. A separate Unicorn execution test checks the
two captured paths and their register states. The result reports the *register
transfer conditional on each captured path*, plus dead writes and path shape.
It reports sampled entry and exit register-state equality separately; the same
transfer mapping can produce different exits when entry values differ.
It does not equate branch guards, timing, external effects, hidden machine
state or the complete UIL intent. In particular, changing a conditional
branch to an unconditional one can alter behavior even when the admitted
register transfer at the sampled exit is identical.

For the first patch lift, prefer **typed UIL as the semantic source and C11 as
the readable executable view**. Keep arithmetic widths and wraparound,
individual FLAGS, byte-addressed memory, and unknown effects explicit. Signed C
overflow, pointer aliasing and optimizer assumptions can otherwise make a
plausible reconstruction differ from x86. Rust is a useful later independent
implementation of a bounded model; JavaScript/TypeScript fit report inspection
and visualization, but 64-bit arithmetic needs deliberate BigInt handling.
This is a choice of validation workflow, not a promise that C is intrinsically
equivalent to the source binary.

At an aligned PE trace site, the runtime instruction pointer is treated as the
paired site identity **only when it equals the recorded runtime site**. This
prevents a load-base or code-placement difference from appearing as a
behavioral register change.
Other register values remain raw: a general register may hold an image pointer,
but automatically rebasing it could hide a real data difference. EFLAGS/RFLAGS
remain part of the observed state. A rejoin is a common control site, not a
state merge; compare the registers and selected memory at that point and at
later boundaries.

The measured effect envelope is only what the script captured. Selected-thread
traces are completed steps with pre-instruction registers; they are not a log
of all memory reads/writes or peer-thread scheduling. Selected memory ranges
show net bytes at their sampling points. Hidden CPU state, heap outside those
ranges, other threads, devices, files and timing stay unknown. A widened
static blast radius must retain those unknown effects, while a narrow observed
effect can be reported without assuming every reachable object changed.

## A bounded PE pilot

The homegrown PE64 GUI oracle in `tests/wine_gui_fixture.c` exposes an
`experiment_value` function and a `counter`. The native test in
`tests/test_wine_advanced.py` saves a checkpoint, runs the same click and trace
script under baseline and an execution layer, checks the counter byte change,
the topology report and final restoration. It requires `FDISBULL_PE_QEMU`,
`FDISBULL_PE_KERNEL`, `FDISBULL_PE_INITRAMFS` and `FDISBULL_PE_FIXTURE`; without
them pytest skips native acceptance. Synthetic PE32/PE64 trace tests cover
rebased instruction pointers, divergent paths and FLAGS at a rejoin. Those
tests check the report logic, not a native PE32 run.

The pure `fdisbull.pe_step_model.check_pe_step_model` helper adds one small
source/model check. Given two adjacent completed PE trace events for the same
thread, it decodes the first event's **executed** bytes through the existing
single-instruction x86-to-UIL adapter, runs that typed model, and compares its
declared full-width register and six arithmetic-flag outputs with the next
event's pre-instruction state. It accepts the saved-experiment trace token or
the exact native PE trace semantics recorded by `debug.trace()`. It returns
agreement, mismatch, unsupported or unknown, with the instruction hash and
semantic model ID. The supported set is
register MOV/INC/ADD/ADC. Partial register aliases, memory operands, other
instructions, a nonsequential next PC, missing next state and mismatched
threads are not upgraded into agreement. This is a finite step observation; it
does not establish a whole block lift or complete Windows process behavior.
Existing independent CPU
tests for that adapter remain a separate gate.

For a real old/new Windows binary pair, a first qualified pilot should use a
redistributable homegrown PE pair with a stable callable boundary. Preserve
both original hashes, public symbols or reviewed block correspondences, the
input recipe and per-version runtime receipts. Compare the pair's outputs and
selected state before attaching a UIL/C explanation to either binary. A
successful finite differential run supports that input set and observation
boundary; it does not prove cross-language or whole-program equivalence.

This organization follows the useful *shape* of two public case studies:
[Anthropic's Windows binary-to-C account](https://www.anthropic.com/research/discovering-vulnerabilities-with-claude)
describes an annotated C program for relevant features checked against the
binary, while its [Windows N-day study](https://www.anthropic.com/research/n-days)
uses vulnerable/patched binaries, symbols, decompilation and a function-level
diff. Neither establishes lossless translation of arbitrary Windows binaries.
The current fDisBull UIL/C backends are bounded typed-model realizations, as
documented in [Common UIL](COMMON_UIL_CONTRACT.md),
[native realization](COMMON_UIL_NATIVE.md) and [UDC C](UDC_LINUX_AND_C.md).
