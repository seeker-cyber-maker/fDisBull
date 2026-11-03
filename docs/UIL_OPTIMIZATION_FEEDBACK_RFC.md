# RFC: reversible UIL feedback from iterative UDC block fusion

**Status: experimental study and proposed architecture.** This MR adds a small working C -> optimized LLVM IR -> UIL-shaped representation loop, not a general original-binary decompiler or a modification to the versioned common UIL schema. It is separate from the original Win32 runtime bridge in [MR !60](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/60) and architecture consolidation in [MR !45](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/45).

## Goal

Given two source-backed, ordered native/UDL blocks A and B, find a shorter candidate F for their **composition**. Feed qualified F upward as an optional implementation of the UIL parent, without destroying A, B, their descendants, source mappings or the exact original implementation.

The user's proposed method is to alternate compiler and semantic-import passes **until the normalized representation stops changing**. Returning to two operations is a valid no-improvement result; it must not be reported as a successful optimization.

~~~
original A + original B
   -> source-qualified UDL A;B
   -> a single typed C function
   -> Clang optimization / optimized LLVM IR
   -> strictly admitted semantic importer
   -> UIL candidate F
   -> proof of F(s) == B(A(s)) on a declared observable contract
   -> cost/termination gate
   -> [if strictly smaller and proved] F -> C -> optimizer -> UIL -> ...
   -> stop: stable hash / no reduction / repeat / bounded budget / refusal
   -> optional parent realization, never destructive replacement
~~~

**Important:** A successful C compilation, smaller emitted C, or equality of two independently constructed *models* does not prove original PE32/Win16 code equivalence. Machine-register flags, memory effects, aliasing, exceptions, imported API calls, callbacks, time, partial failure, self-modification and live intermediate observations can all prevent otherwise tempting fusion.

## Existing infrastructure to reuse

- **common_uil.fold_function / expand_fold:** exact retained child graph, digested recovery, nested transparent views. This is a view/recovery facility; it does not prove a transformed body.
- **uil_catalog.py:** content-addressed normalized model identities, separate implementation metadata, source provenance. It currently does not perform arbitrary algebraic rewriting, inlining or general equivalence proofs. Do not forge a prior semantic ID by assigning a label to different computation.
- **uil-components and native link lock:** nested typed requirements and selectable implementations. Preserve explicit implementation digests and source/target/ABI bindings rather than silently changing the chosen runtime.
- **udc_qualify.py / udc_layers.py:** bounded pure-IL qualification and explicit implementation selection, with separate original/source/target proof obligations.
- **console_synthesis.c_frontend.import_c:** a *different* existing Clang AST import path for trusted, restricted C into fdisbull-il-1. Its LP64 ABI, admitted operators, and source-to-native scope are bounded; this pilot does not quietly extend it to arbitrary decompiled C or PE32.
- **code_blocks.py:** grouping of x86-16/32 source instructions, without automatic instruction lifting or relocation. Pair discovery must check CFG and live state, not merely neighboring file offsets.

## Proposed reversible parent representation

~~~
UIL parent P = crc32.update_byte(state:u32, byte:u8)
  original ordered realization:
    A.mix_byte                    source + original machine backing
    B.eight_bit_steps             source + original machine backing
      B1.logical_shift
      B2.conditional_polynomial_xor
    each child retains its own selectable descendants
  optional optimized realization:
    AB.lookup = (state >> 8) XOR table[(state XOR byte) & 255]
    separate implementation identity, table hash, proved domain, source bindings
  other selectable realization:
    AB.branchless
  optional future parent:
    P + C, preserving A/B/C through an immutable DAG
~~~

**Two distinct feedback events:**
1. **Implementation feedback:** A+B can be performed by F. Add F as a candidate realization under the *same proven parent semantics*. Do not erase A+B.
2. **Semantic feedback:** The pair might express a recognizable operation (e.g. CRC32 update). Record that as a hypothesized parent meaning, but require independent code/runtime evidence before giving it a qualified intent name.

The caller-visible contract, not the optimizer's own last return value, defines observability. If a breakpoint or third block can see the A/B boundary, ordinary fused F lacks that physical stop. Offer the original backing for true substep rewind or separately qualify virtual observations. Never call reconstructed intermediate states native events.

## Automatic candidate search

1. **Propose pairs:** choose a CFG-connected A -> B with a single admitted entry, known exits, matching typed state/ports and useful liveness data. Prefer straight-line pure regions with likely constant propagation/copy elimination. Later permit guarded branches, inlining, loops and special patterns.
2. **Reject or defer:** external entry to B, shared tails, unresolved jumps, overlapping instruction interpretations, flag/memory/stack effects, alias uncertainty, volatile operations, SEH/unwind, Win32 API ordering, timing dependence, self-modification, or a required original midpoint. A richer qualified observation contract may permit some later, but no guessed side-effect elimination.
3. **Compose and optimize:** form trusted typed C using explicit fixed-width wrap/shift and declared ABI; compile with a pinned compiler and flags. Retain hashes of the original pair, C text, optimized IR, compiler identity, ABI/width and the set of admitted assumptions.
4. **Convert optimized IR to candidate UIL:** use a real semantics importer, not only the decompiler's pretty-printed name or a string substitution. Unsupported instructions refuse and do not become no-ops.
5. **Independently challenge equivalence:** bit-vector SMT for admitted pure scalar domains plus separate source-to-original and native execution gates. Retain SAT counterexamples, solver timeout/unknowns and insufficient observation coverage. A proof about an authored scalar model never proves unqualified arbitrary original binaries.
6. **Compare cost and iterate:** alpha-normalize expression/port/operation order, canonicalize and hash the candidate. In the first conservative version accept only **strictly decreasing nonnegative IR operation count**, then recompile the candidate. Equal or larger outputs stop with the best known original/qualified implementation; do not accidentally bounce between two spellings. Keep seen state hashes for cycle detection, a hard round budget and a monotonic best-so-far snapshot. Stable normalized hash is a **toolchain-local fixed point**, not a globally smallest equivalent program.
7. **Offer the result, never switch silently:** publish immutable parent P with selectable ORIGINAL(A,B), FUSED(AB), PORTABLE(C) and later variants. Every selection has its own proof, context/domain, exact implementation hash, measured cost, required services and stepping granularity. Changed source, ABI, semantics, domain or compiler evidence invalidates F until requalified.

**Search economics:** score likely wins by hotness/size, cheap structural rewrite opportunities and expected solver cost. Cache by the full pair+contract+compiler fingerprint, cap the beam and number of rounds. Explore equal-cost pivots only in a separately bounded deterministic search with cycle detection and no promotion without eventual gain.

**Cost and qualification are separate:** A reduction from two modeled operations to one is not automatically a smaller PE32 executable or faster code. Measure actual bytes, instructions, branches, register pressure, table-size overhead, runtime, proof expense and replay expense individually. Functional equivalence also does not prove timing/anti-debug equivalence.

## Small working prototype in this MR

- Source: examples/uil_common/feedback_fusion.py
- Tests: tests/test_feedback_fusion.py
- Input: exactly two **authored**, nonempty, constant-operand u32 operation lists (xor, add, sub, and, or, mul, bounded shifts). No globals, pointers, stack, memory, flags, calls, exceptions or observation of intermediate states.
- Toolchain: real Clang C11 -O2, targeting x86_64-unknown-linux-gnu, emitting **optimized LLVM IR**, *not a Windows EXE*. A deliberately narrow, fail-closed i32 SSA parser returns an explicitly **toy UIL-shaped expression**. This prototype does **not** use the production common UIL parser or prove original PE32 correspondence.
- Admission: actual Z3 32-bit bit-vector proof of unchanged whole-function output for all 2^32 inputs. A shortened candidate is only eligible after a subsequent fixed-point round and is **never selected by default**. Rejected, unfinished and unknown cases leave the original available.
- Evidence: hashes for emitted C and LLVM, Clang version, normalized candidate hashes, per-round operation counts and proof/refusal status. The original child blocks are always retained.
- Checks: two XOR blocks collapse to one, add followed by sub becomes identity, unchanged two-operation pair stays original, improper shift/effect/memory/branch refuses, wrong compiler output yields SMT counterexample, and one-round budget does not promote an unstable candidate.

~~~
# Requires real Clang, Python, pytest and z3-solver. Installs nothing.
python examples/uil_common/feedback_fusion.py
python -m pytest -q tests/test_feedback_fusion.py
~~~

The locally authored test run on an isolated Linux x86-64 Python 3.13.5/Clang/Z3 environment passed **10/10** in the source preparation workspace. This is not an installed fDisBull release/native Win32 acceptance, and hosted GitLab CI remains separate.

## CRC32 as a subsequent synthesis target

The earlier independently authored CRC32 fusion demo defines A as the input-byte XOR and B as eight reflected polynomial bit steps. A proven table implementation is a useful optional fused backing. **The ordinary Clang peephole pass is not expected to invent the 256-entry CRC table.** That candidate should come from an explicit recognized rewrite, enumerative synthesis or a bounded library of equivalent kernels and then pass full u32/u8 proof, table digest, and original-backed tests. The user's earlier separate CRC32 demonstration ZIP is not bundled in this MR or represented as production schema support.

A good first live PE32 benchmark is a self-authored key-checking fixture with A: update temporary and B: comparison, including a deliberately live EFLAGS or external intermediate observer that must block fusion. Later use user-owned crackmes privately through the proposed Win32 debugger in MR !60. Do not upload proprietary crackmes or native snapshots to GitLab.

## Integration milestones

**M1: stable UIL contract:** add an additive content-addressed optimization receipt or catalog adapter without replacing existing versioned common UIL schemas. Prove persistence/reopen and exact reversibility through the existing fold/expand recovery API. Include staleness invalidation, nested shared-child DAGs and deterministic original-vs-fused selection.

**M2: richer discovery:** connect source-backed block grouping, inlining/SSA/canonicalization and a bounded rewrite/proof engine; add CRC32 table synthesis and semantic intent recognition only when code evidence supports them.

**M3: original Windows oracle:** once the PE32 WoW64 runtime debugger is qualified, observe original A+B and candidate F at matching machine states, including EFLAGS, memory, exceptional/partial effects and API ordering. Separate native source proof from model self-consistency.

**M4: agent-facing cascading menu:** display the parent and every preserved original child, alternative backings, proof domain, expected runtime support, costs and truthful rewind granularity; user/agent opt-in selection remains explicit.

## Historical reference and attribution

Igor Skochinsky of Hex-Rays presented **Practical C++ decompilation** at **REcon 2011, July 9, 2011**, as documented by the REcon schedule and Hex-Rays:
- https://recon.cx/2011/schedule/events/95.en.html
- https://hex-rays.com/blog/recon-2011-practical-c-decompilation

The description of repeatedly compiling/decompiling into a fixed point is **the project owner's recollection** of that period. The public talk description checked does **not** independently establish that Igor stated that exact algorithm, so this RFC does not attribute a quotation or exclusive invention to him. Current Hex-Rays microcode documentation separately describes global optimization to a fixed point:
- https://ida-domain.docs.hex-rays.com/ref/microcode/

## Scope and publication

This RFC and example introduce **no new native runtime, automatic optimizer or production UIL format**. No game/crackme bytes, private FDBs, saved VMs or proprietary material are committed. Draft MRs keep hosted CI skipped per the repository's anti-abuse policy. The Mac-local mirror synchronization and full installed-package suite have not been run from this environment.