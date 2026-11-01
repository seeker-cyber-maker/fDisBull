# Next release: database-backed C/C++ view and debugger

User requirements recorded on 27 October 2026 while the 0.18 release gate is
running. This is an implementation contract for the next version, not a claim
that fDisBull currently has a C/C++ decompiler or source-level debugger. This
working document is deliberately outside the fixed 0.18 release commit.

## One database, several synchronized views

The persistent project database remains authoritative. A decompiler adapter
consumes the selected immutable byte/context version and database facts, then
returns structured output with provenance and instruction mappings. Rendered
C/C++-like text is a view of those records, not a second symbol database.

- Resolve function/global/field names, types, prototypes, enums and supported
  constants from shared identities. A rename/type edit from either the C view
  or disassembly writes the same versioned annotation with authorship and
  refreshes all linked views. Preserve raw decoder operands and original bytes.
- Give recovered locals stable identities scoped by function, byte version,
  storage/lifetime and decompiler provenance. Distinct locals can reuse one
  stack slot/register; one recovered variable can have several machine locations.
  Do not key locals by printed names, line numbers or machine address alone.
- Keep asserted facts, inferred data-flow values and observed runtime values
  distinct. Propagate constants only where supported by width, signedness,
  control flow, aliases and calls. Unknown values stay unknown. A value observed
  in one paused run/thread/frame must not become an unconditional static constant.
- Bind cached output to engine/version/configuration, input byte/context hashes
  and a database annotation revision. Rename/type changes refresh presentation;
  byte/layer changes invalidate affected analysis and instruction mappings.
- Preserve earlier output, mappings, hypotheses and evidence across restart.
  External engine caches cannot silently override current database names/types.

## C/C++ as the primary debugger view

An agent or user should be able to open a recovered function, choose a statement
or expression, set a breakpoint, run/step with a timeout and inspect variables
without repeatedly translating C text into disassembly addresses. Keep the
underlying instruction and register view available to explain every stop.

The adapter must emit a many-to-many mapping from stable function/statement/
expression identities to original machine instruction identities/ranges, byte
version and segment context. It must retain mapping quality and unresolved
origins. Display line numbers are presentation, not persistent breakpoint keys.

For a source-view breakpoint:

1. Resolve the selected node against the current database and active byte/layer
   interpretation. Reject a stale or incompatible mapping.
2. Prefer a verified instruction before the selected statement's effect. Select
   a meaningful entry/evaluation instruction, not simply the lowest numeric
   address. Conditions may map to comparisons/branches; their precise stop
   semantics must be returned to the caller.
3. Where the node has multiple independent entries, offer a bounded set of
   breakpoints or an explicit best-effort selection. Return candidate addresses,
   selected instructions, bytes, coverage/ambiguity and the selection reason.
   Unmapped or optimized-away expressions must remain explicit failures/unknowns.
4. Use the existing relocation/byte verification and debugger stop machinery.
   Never hide a guess behind an apparently precise C line breakpoint.
5. At the stop, highlight mapped statements/subexpressions and retain the actual
   CS:IP/RIP, instruction bytes, registers, stop cause, context and temporal view.

Source stepping means bounded execution toward an explicitly mapped next
statement/node. It must preserve execution/data breakpoints, hooks, guest errors
and host/guest timeouts. It does not imply recovered original source, exact
compiler sequence points, reverse execution or deterministic replay.

Live variable inspection uses proven storage descriptions and the selected
paused context. Missing/ambiguous locations are shown as unavailable or inferred,
not fabricated values. Editing recovered C text is separate from safely patching
machine bytes; no automatic compile-and-inject behavior is implied.

## Acceptance before calling it integrated

1. Qualify a pinned DOS-capable decompiler on authored arithmetic/branch and
   near/far-call examples; preserve width/wrap, segment and ABI semantics. See
   [the existing research](DOS_DECOMPILERS_RESEARCH.md).
2. Rename a global, local and struct field; change a prototype/type/enum; verify
   that C and disassembly/data views agree before and after project restart.
   Test changes from both directions without replacing raw instruction evidence.
3. Verify constant propagation across supported branches and explicit unknowns
   at alias/call barriers. Keep live observed values scoped to their run/frame.
4. Set a C-statement breakpoint in a native fixture, hit a byte-verified backing
   instruction before its effect and display matching live variable/register
   values. Cover a multi-entry/ambiguous node and an unmapped expression.
5. Patch/toggle a layer, restore a checkpoint and regenerate the function. Stale
   mappings must be rejected/rebound explicitly; earlier byte versions and
   breakpoint intent remain preserved.
6. Repeat one understood original-game routine with the C view as the main
   interface, checking the actual instruction stop and a bounded trace. Finite
   route coverage does not establish whole-game decompilation fidelity.

Choose the next implementation probe by expected decision value per cost along
with confidence. Recover one useful, auditable function/debugging loop before
attempting an entire game's C/C++ reconstruction or a general graphical editor.
