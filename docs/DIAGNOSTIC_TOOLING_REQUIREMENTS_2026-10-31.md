# Tooling follow-ups from diagnostic code recovery

Status: proposed implementation requirements, 31 October 2026. No new public
API, executor, schema, publication permission or production test result is
introduced here. The [fresh Syndicate study](SYNDICATE_GRAPHICS_CONTRACTS_2026-10-31.md)
is the motivating evidence. PR #69 supplies the broader methodology for
investigation outside ordinary progression; this document specifies narrower
implementation work rather than repeating that guidance.

## Existing seams and observed friction

The actual study ran pinned 0.26.0. Repository source was separately checked at
`90e748c8bc6a4f068f9136f4d4ec989672421a03` to avoid describing all proposals as
missing capabilities in the newer tool.

- In the inspected native `analyze(start=...)`, an explicit start is also entered
  as a user-seed function candidate. The study needed switch-case decoding without
  adding a function or a proved indirect edge. The private `_queue_code` seam
  worked, but required version-specific code and direct queue access.
- Public `represent(..., 'code', defer=True)` is an existing alternative with
  explicit representation/invalidation semantics. Do not remove it or pretend it
  is absent; a candidate-only evidence batch should not require falsely asserting
  an authoritative representation or resetting unrelated discoveries.
- Drawing indices require a loop lower invariant, partial-register facts and
  relevant callee preservation. A signed upper bound or larger global budget is
  insufficient. Research receipts hold these facts outside the normal graph.
- A missing main-executable path can actually belong to a loaded module or a
  resource-linked animation. Following the artifact graph requires reusable
  reverse links, not repeated unaudited scans or a blanket assumption of dead code.
- Native/source-backed block capture and explicit bounded relayout already exist.
  Their source/structural identity checks are not ordinary-game reachability,
  semantic equivalence or authority to run arbitrary code in a host process.
- Schema 9's external target store already separates raw payloads from FDBs.
  New probe/capture records must use that boundary; do not create another embedded
  framebuffer/source BLOB path or call an externalized database publication-ready.

## P0: evidence-only candidate admission

Provide an additive, bounded, persistent batch mechanism using the existing
address and byte-version identities. Suggested behavior, not a reserved method
name: admit candidate instruction entries with source evidence and a hypothesis
kind, then let normal recursive analysis process them.

Separate these statuses: offered address, already stored entry, new pending work,
blocked/invalid candidate, decoded instruction, function hypothesis, conditionally
mapped dispatch target and proved/observed control edge. A single `success` bit
cannot represent them. Include ISA/mode, module/address context, source version,
originating table or caller and the qualification boundary. Stable addresses
must be parsed through the tool's address API, not compared as arbitrary SQL
strings versus integers.

Preserve overlapping interpretations, existing annotations and earlier byte
versions. An initial relocated pointer is evidence for a candidate, not proof
of runtime immutability. User-authored code representations and deliberate
function seeds retain their existing meaning. A local guard receipt can be
attached without minting a resolved edge or claiming every predecessor passes
through it. Deduplicate work, but retain distinct contributing evidence.

## P0: preflighted experiment sessions and irreversible receipts

The strongest observed execution friction was in the authored research harness,
not the product: importing a helper launched 64 target calls before an existing
output path was rejected. This motivates first-class safeguards if a routine-
probe surface is integrated.

Before any target execution, validate capabilities, source identity, selected
mode/module, input extents, requested stop conditions and all output destinations.
Reserve a unique run/attempt identity atomically. Reject reuse before any target
request. Imports, command discovery, recipe validation and dry runs perform no
native launch, guest input, restore, file write to the target or time advancement.
A collision cannot become an implicit overwrite or silent restart.

Persist the initial recipe and pending state before dispatch. Append case results
as they complete, rather than holding an entire matrix until its last line.
Record pending, returned, selected-stop, access-fault, rejected-environment,
instruction-budget, wall-limit, interrupted and unknown outcomes distinctly.
Never rerun a completed or unknown-effect case merely because writing a summary
failed. Repair summaries from receipts where possible. A requested rerun is a new
attempt linked to its predecessor, with all attempts included in counts.

Recipes identify the selected implementation and execution substrate separately:
original instructions versus an external decoder/model, DOS backend versus
compatibility CPU context, observed versus injected registers/flags/stack,
region permissions, explicit services, entry/return ABI, observation boundaries,
budgets and cleanup ownership. A resource decoder can be probed without a full
playthrough, but a successful host-CPU call does not acquire DOS device behavior.
Do not integrate the research ptrace harness as an alleged security sandbox.

Keep one controller per live guest. Whole-guest save/restore, disposable CPU
state and host-file rollback have different guarantees. Missing dependencies,
unsupported CPU/environment instructions and faults stay visible; no automatic
zero-memory growth or fabricated successful service replies to force a pass.

## P1: compact local contracts and exact effect observations

The drawing case supports a useful small proof obligation: clipped coordinates
establish a nonnegative remainder, the loop decreases it, and selected callees
preserve its carrier. Attach source spans/revisions, admitted inputs, memory
alias assumptions, loop invariants, helper summaries and exit domain. Reopen only
affected claims after a source, model, resource or helper change.

Include negative controls. Dropping the lower invariant or permitting an unknown
callee clobber must invalidate the claimed range. A modulo or signed comparison
must retain actual widths. Do not label a conditional slice globally qualified
when an alternate entry bypasses its setup.

Observation tooling should support a caller-selected independent effect oracle,
whole-region or sparse comparisons, guards/canaries and relevant register/flag
observations. Keep the compared byte set and exclusions explicit. Exact behavior
can disagree with an ideal model: the sprite's one-row shift and inherited EAX
return must remain visible. A no-draw case is not a no-effect case. An intentional
fix belongs to a new behavior contract, not a relabelled fidelity pass.

Specifically, a function summary must allow outputs to depend on **incoming
register state** even when conventional ABI guesses call it a Boolean helper.
Caller projections may inspect only AX, not EAX. Preserve width, prior-value
provenance, conditional writes and unused/unknown output bits. Do not silently
initialize unwritten return registers to zero or normalize nonzero to one.

## P1: reusable resource-to-code reverse links

Support bounded typed relations through existing file/type/evidence facilities
where possible, rather than inventing a second universal scene format. Examples
are sprite-table byte displacement to entry, element to frame, frame to animation
start, native state case to animation selection and registered service to module.
Bind each link to exact files, entry widths, endian/offset bases and source
versions. Track cycles, terminal values, invalid links and partial coverage.

A query should distinguish references present in this artifact set from observed
fetches and legal player paths. Negative corpus results need a denominator:
no flags-3 element among 10,486 inspected records is not proof that variant 3 is
unreachable from all callers. Keep original resource bytes private and return
compact IDs, ranges and evidence handles rather than full media by default.

## Acceptance cases

These are prospective acceptance requirements, not tests executed by this
hand-off PR. The study's separate research checks must not be counted as product
conformance.

| ID | Required result |
| --- | --- |
| DIA01 | A batch of switch-case candidates preserves prior facts and adds no function or resolved edge solely from admission. Repeated addresses retain additional evidence without duplicate work. |
| DIA02 | Equal addresses supplied in accepted representations resolve to one identity; a different source version, module or decode context remains distinct. Report offered/already-stored/new/blocked counts accurately. |
| DIA03 | Two entry-qualified overlapping interpretations remain materializable and are union-counted physically; candidate admission cannot erase either. |
| DIA04 | An occupied output/run ID fails before a fake provider observes any call. Import, help, validation and dry-run also produce zero target calls. |
| DIA05 | Stop after a completed case but before summary writing. Reopen receipts without replay; unresolved dispatch stays unknown. Explicit retry creates a new attempt, not an overwrite. |
| DIA06 | Missing mapping, invalid return context, unsupported environment opcode and each budget stop produce distinct retained outcomes with owned-child cleanup. No fabricated success or automatic dependency invention. |
| DIA07 | The remainder proof needs both a lower invariant and the relevant helper summary. Remove either and retain an explicit counterexample/unknown; source changes invalidate dependent claims. |
| DIA08 | Compare full affected memory plus guards and relevant register/flag state. A conventional vertical-flip oracle detects the observed one-row difference; no-draw controls do not imply preserved registers. |
| DIA09 | An authored helper has true, false and inherited-EAX exits. A caller testing AX can distinguish incoming values; summary/lowering must preserve that dependence or refuse the abstraction. |
| DIA10 | Cyclic element/frame/animation graphs terminate bounded queries and report exact input coverage. Resource references, diagnostic execution and ordinary reachability remain distinct. |
| DIA11 | Store raw source, memory and traces outside SQLite/WAL under the existing external-object boundary; missing/corrupt objects fail clearly. Source-free summaries do not certify publication safety. |
| DIA12 | A current-run ledger includes calibrations, negative controls, faults, aborted and duplicate attempts. Aggregate counts reconcile with per-attempt receipts and never claim a new full-game run. |

## Integration and scope

The study's public-source check establishes the `analyze(start)` and private-queue
behavior at the pinned main revision. It does not assert the absence of every
possible extension in other branches. Reuse existing capabilities and reconcile
pending PRs before selecting an implementation seam. Avoid inventing method names
in the skill before a real API is implemented and tested.

Related contracts: [source backings](CODE_BACKINGS.md),
[native UDL-to-UDC](NATIVE_UDL_UDC.md),
[external target storage](EXTERNAL_TARGETS.md), and
[definitions and roadmap](DEFINITIONS_AND_ROADMAP.md). PR #69 remains the separate
methodology amendment. Nothing here weakens source-layer approval, source
retention, unsupported-domain refusal or raw-evidence privacy. No release,
installation, generic interpreter, full LE writer or native sound player is
implemented by adding this document.
