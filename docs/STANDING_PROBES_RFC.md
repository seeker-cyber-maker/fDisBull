# Durable standing probes for rare code and meaningful data

Status: proposed tool implementation; bundled skill guidance updated in this
change. No durable probe API is implemented by this document. Baseline reviewed:
`498c0887f8d15ca3b2fb3dc8994d2de24e144273` on 2026-11-01. This proposal is separate
from the original-backed DinoPark work in GitLab !18 / local PR #41.

## Problem and evidence

Unknown code may activate naturally after the investigator stops targeting it.
Leaving a selective breakpoint armed during normal use can turn an unexpected
first hit into a high-value analysis lead. Missing direct references and repeated
no-hit runs are insufficient to classify an entry as dead code. A meaningful
data field can provide the same opportunity when it changes or is accessed.

The DinoPark investigation retained 97 unresolved entry probes in a live original
game. Before/after inventories verified actual enabled addresses, `once=False`
and zero execution/input/restore changes from inspection. No probe hit during
that bounded route, and 13 asset candidates remained unresolved. The following
park-operation work continues the same experiment; this RFC does not predeclare
its outcome. Earlier oversized inventory replies required artifact-backed
readback, so compact inspection is part of the proposed contract.

Current source already provides useful primitives:

| Existing seam | Verified source behavior | Remaining integration |
| --- | --- | --- |
| `debug-breakpoint` / `DebugSession.breakpoint` | Execution breakpoints check mapped instruction bytes; native `once=False`; data access kinds `r`, `w`, `rw` are capability-gated | Project-owned definitions and explicit per-run binding state |
| `ExperimentSessionMixin._remember_breakpoints` | Keeps specifications in session memory for experiment control | Durable plans, source-qualified reattachment, first-hit analysis queue |
| `debug-hook` / `LayerSessionMixin.hook` | Bounded actions set layers, redirect or edit checked registers | A separate passive capture mode with no intervention authority |
| Persisted debug events and bounded runs | Retain operation evidence and stop context | Atomic first-hit receipts, suppression accounting and compact probe inventory |

Source references: `src/fdisbull/debugger.py`, `debug_experiments.py`,
`code_layers.py` and the method catalogue in `src/fdisbull/cli.py`. These existing
primitives do not establish a portable cross-run standing-probe service. Query
actual capabilities before using any proposed interface below.

## Selection and lifetime

Strongly recommend standing execution probes on plausible unknown code and
candidate functions during an ongoing authorized investigation. The recommendation
requires judgment about evidence, backend capacity and overhead; it does not mean
placing a breakpoint at every byte or believing every candidate is a function.
Record why selected candidates are useful and why others were deferred.

Select data watchpoints only for bounded meaningful locations: an unresolved
callback pointer, an observed table slot, a visitor/event state field, an unknown
counter with a writer, or a transition that distinguishes live alternatives.
Specify width, access kind, allocation/module lifetime and optional supported
predicate. A logical pointer currently equal to zero is eligible; arbitrary null
padding, alignment filler and unclassified zero-filled holes are not useful
default targets. A later writer, remap or execution can reopen that exclusion.

"Permanent" means a durable definition retained across normal sessions, with an
explicit binding and sampling policy. It does not mean an immortal guest, a
background job, a probe silently rebound to a different allocation, or unlimited
repeated stops. Default policy: keep armed until a first natural hit, durably
capture it, then latch off pending analysis. Rearming is deliberate. Optional
bounded sampling must declare limits, suppressed counts and actual backend cost.

## Proposed model and API

Names are proposals, not shipped commands. Fit them to existing method naming
and storage conventions during implementation.

- `probe-plan`: create or revise a project-owned manifest, with an immutable
  definition revision and authored reason for each entry.
- `probe-bind`: bind a selected plan to an already authorized live run after
  source, bytes/region, mapping, generation and capability validation.
- `probe-status`: compact paginated desired/installed/deferred/latched inventory,
  with a full artifact export when requested. No execution or input side effects.
- `probe-hits`: paginated immutable hit receipts and associated analysis leads.
- `probe-update`: explicit enable, defer, retire, latch acknowledgement or rearm;
  operate only on owned native identifiers and preserve prior revisions/hits.

Minimum definition fields: stable ID/revision; project and source SHA-256;
selected byte version; module/region identity; project location and address-space
kind; expected instruction bytes or justified data-region/lifetime guard; reason
and evidence links; execution or data access kind; width; supported condition;
owner; first-hit/sampling policy; budgets; and desired lifecycle state. Do not
serialize runtime absolute addresses or native IDs as portable identity.

Keep bindings separate: plan revision, run/session ID, backend identity and
capabilities, current translation and generation, verified identity/byte result,
native IDs, installation result and timestamp. One definition may need several
native data breakpoints. Several segmented aliases may share a physical location;
deduplicate installation while retaining each original candidate identity and
the uncertainty of its function boundary.

Do not conflate `desired`, `armed_verified`, `deferred_capacity`,
`unsupported_backend`, `source_mismatch`, `unresolved_mapping`, `invalidated`,
`hit_capture_pending`, `latched_for_review` and `retired`. A saved definition is
not evidence of an armed probe. A lost binding must never appear as a zero-hit
success. Install bounded batches; if an entry fails, report exact admitted and
unadmitted sets, retain valid existing bindings, and never clear unrelated probes.

On launch/reload/restore/layer change or allocation reuse, invalidate affected
bindings and revalidate before attaching again. Persisted history does not
reconnect an exited runtime. An explicitly selected per-project rearm policy may
attach to an already authorized matching run; it may not launch, restore, change
time or replay input. No force-bind option should bypass source identity guards.

## Passive first-hit capture

Use a dedicated read-only capture path; do not repurpose mutating hook actions
as an observational guarantee. A hit receipt should contain:

- Definition revision, run/backend/source identity, installed native IDs and
  event sequence; physical PC plus project/segmented aliases and byte guards.
- Available registers, bounded private stack/argument bytes and a bounded recent
  trace or caller edge when actually supported. Distinguish a recorded return
  address, a candidate caller and a verified call edge.
- Current canonical action/root, queued input IDs and recent event references,
  without resending any input or asserting its completion from the stop alone.
- Selected value before/after only when both were observed; access instruction
  and access address/width; backend-specific pre/post-access semantics. Existing
  DOS data stops report completion as unknown, so do not promise exact writers
  or old values from a single stop.
- Host UTC/timezone, guest RTC, game/simulation date and random-state evidence
  as separate optional fields, with unavailable fields explicitly unknown.
- Capture limits, missing fields, dropped/suppressed events and recovery state.

Write the hit durably before deleting or latching its native probe. Capture
failure keeps a visible pending hit and paused context for read-only recovery;
it must not silently discard the hit or replay the triggering action. A stored
receipt permits idempotent recovery without duplicating the analysis lead.
Continuation belongs to the existing controller/action contract. Never swallow
another breakpoint or resume a guest that was already paused by its owner.

A first natural hit raises analysis priority and carries the context that makes
the path interesting. It does not automatically name the function, prove a
feature, resolve every alias or certify the enclosing action. Review can select
a narrow caller/condition analysis and then rearm, sample or retire the probe.

For example, a hypothetical application might invoke an otherwise unseen
routine on one real-world weekday, only when a particular device is present,
after a long delay, or after a rare random outcome. This motivates retaining
probes during ordinary use. It is not evidence that DinoPark has any of these
conditions. Distinguish real-world, emulated RTC and game calendars. Controlled
clock experiments, if later authorized, should use an isolated guest clock
with a declared intervention; do not change the host clock as a convenience.

## Cost, privacy and recovery

Expose backend capacity and installation cost before admitting a plan. A data
range may consume one native breakpoint per byte; software probes and frequent
matches can impose substantial overhead even without transport payloads.
Budget native count, width, stop rate, captures/bytes, RPCs and host/guest time.
Compare an instrumented ordinary route with an appropriate bounded control when
making performance claims. Record loss and suppression, not just saved hits.

Store raw registers, stack/code bytes and game-containing traces privately under
the existing external-target rules. Publish only authored definitions that pass
sanitation, hashes, counts and bounded findings. Provide summaries and stable
pages instead of a single large inline inventory. Read-only inventory/hit queries
must have zero execution, input and restore deltas.

Shutdown retains definitions, prior bindings, hit receipts and unresolved state;
it marks live bindings disconnected. No scheduler, autonomous time advance or
new monitoring process is implied. Recovery preserves provider/context ownership
and uses existing reconciliation contracts. The caller sees pending capture,
provider loss and unknown effect as distinct states.

Integrate event references with GitLab !30's proposed frame/input timeline and
revalidation with !14/!16's rewind/experiment work. Those proposals do not grant
this feature automatic restore, full-state equivalence or intervention authority.

## Implementation slices and acceptance

1. Persist definitions and revisions, read-only status/hits, and pure identity
   validation. Restart preserves definitions, exclusions and receipts without
   claiming a live connection. Changed source/bytes refuse binding.
2. Bind an owned execution probe to the actual backend and verify inventory.
   Repeated binding is idempotent; segmented aliases deduplicate physically;
   unrelated breakpoints survive install failure, rebind and retirement.
3. Passive first-hit capture, durable-before-latch ordering and recovery. Exercise
   an injected capture/readback failure: one hit, one analysis lead, no replay,
   preserved paused context and explicit unknown fields.
4. Selective data watches with width/lifetime guards and actual access semantics.
   Meaningful zero-valued fields are accepted; unexplained padding is excluded
   or requires a recorded, explicit reason. Unsupported predicates are refused.
5. Reload/restore/layer invalidation, capacity/overhead admission, compact paging
   and checked rearming. Inventory queries have zero execution/input/restore
   deltas, including artifact-backed and oversized-response paths.
6. Bounded native qualification with original inputs and an authored rare-event
   fixture. A delayed/specific-weekday branch in the fixture proves the mechanism;
   it does not establish a calendar dependency in the game. Keep no-hit game
   coverage and all deferred candidates visible.

Use host tests for storage/idempotence/guard failures and actual native tests for
binding, access semantics, pause ownership and first-hit recovery. Benchmark
representative counts and data widths before choosing defaults. Package and
release qualification remain separate authorized work.

## Guidance delivered with this proposal

The investigation skill now strongly recommends selective standing probes and
provides a detailed procedure in its existing methodology reference. This is
usable today with verified live breakpoints and a reviewed manifest. Durable
cross-run APIs, passive capture and analysis-queue integration above remain
implementation work; do not advertise them as shipped.
