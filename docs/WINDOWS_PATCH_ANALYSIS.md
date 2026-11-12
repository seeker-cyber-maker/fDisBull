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
