# Parallel research workspaces: fork execution, share evidence

Status: proposed design, not an implemented runtime service.
Date: 2026-11-02.
Default topology: one lead-owned reference instance plus three worker slots.
Target: general fDisBull research orchestration, not a Syndicate-specific feature.

## 1. Intended result

A lead agent obtains a coherent, reusable starting point and creates independently
owned research workspaces. The reference instance can continue forward while a
worker inspects an earlier point, replays an observed event, or explores a changed
condition in its own instance. Other workers can inspect a frozen observation
without paying for an emulator at all.

The independent historical instance, rather than a mixed-time edit to the live
instance, is the preferred mechanism for forensic rewind. Actor-local selective
restoration remains a separate experimental operation inside an explicitly selected
branch. A worker discovering a cause returns evidence to the reference timeline;
it does not rewind that timeline or silently transplant its current RAM.

Three workers is a capacity default, not a quota to fill or a hard-coded backend or model limit. The host-wide active-agent cap always applies. The lead
agent is the coordinator; its reference runtime may be paused, running, absent,
or replaced by a pinned baseline depending on the experiment. Agent count,
workspace count, and number of simultaneously executing native processes are
separate scheduling quantities.

## 2. Four separate layers

| Layer | Purpose | Isolation obligation |
| --- | --- | --- |
| Source worktree | Worker edits scripts, models or proposed code | Private checkout/index and branch; shared Git object history is acceptable |
| Runtime instance | Worker executes, pauses, rewinds and probes a target | Private mutable CPU/RAM/device/input/debugger state |
| Target filesystem | Target reads assets and writes saves/configuration | Immutable shared baseline plus private writable overlay, or a full private copy |
| Evidence/knowledge | Workers reuse analysis and return findings | Shared immutable facts and observations; controlled append-only publications; private hypotheses |

A Git worktree alone is not a runtime boundary. It supplies separate checkouts
while sharing repository data [G1]. Likewise, a disk overlay is not a RAM or
device checkpoint. QEMU documents the difference between temporary disk snapshot
mode and VM snapshots containing CPU, RAM, devices and writable disks [Q1].

For DOSBox, a backend adapter can use separate emulator processes. A complete
outer VM is not mandatory just to obtain separate game instances. A VM/container
can still supply a filesystem namespace or stronger host isolation. These
mechanisms must not be conflated: a container is not itself a qualified guest
snapshot, and four processes are not four validated historical clones.

The runner abstraction should admit native DOSBox, qualified QEMU-backed guests,
static/offline analysis, and recovered UIL interpreters as distinct capabilities.
A semantic-model fork is useful for many tests but is not automatically an
original-binary reproduction.

## 3. Sharing policies

| Profile | Shared | Private | Intended use |
| --- | --- | --- | --- |
| Isolated execution | At most a frozen, read-only input set | Runtime, writable files, analysis changes, logs | Independent trials and hostile/fragile targets |
| Shared observation | One immutable observation stream, analysis and evidence | Each agent's reasoning and proposed annotations | Several specialists reading one world without extra guests |
| Hybrid linked clone (default) | Immutable assets, qualified anchor, pinned analysis, accepted symbols | Runtime changes, disk writes, inputs, breakpoints, hypotheses | Parallel experiments with low duplication |

Shared observation is not several agents concurrently driving one emulator. One
controller owns execution mutations for that instance. Other agents read published
snapshots or ask the owner for an observation. Independent input, stepping or
rewind requires an execution branch or an explicit ownership transfer.

There are two distinct meanings of shared memory:

1. **Knowledge and observation memory:** a versioned fact store, immutable RAM
   pages, normalized state views, causal events and worker summaries. Sharing this
   is desirable, subject to access and experiment-blinding policies.
2. **Writable guest RAM:** sharing this across supposedly independent executions
   violates isolation. It is excluded by default. Physical page sharing is allowed
   only through a qualified read-only/copy-on-write mechanism that gives each
   writer a private page. This is an optimization, not assumed DOSBox functionality.

A lead can compare two snapshots side by side without mapping writable RAM between
emulators. The comparison identifies instance, snapshot, source image, load
mapping, entity generation and observation boundary. Raw address equality alone
does not establish corresponding objects.

Agents may propose conflicting annotations. Accepted knowledge is versioned;
worker hypotheses do not overwrite one another or become consensus because more
than one worker repeated the same source-derived assumption. Blind experiments
can deliberately withhold other workers' hypotheses and external references.

## 4. The fork capsule

A cloneable starting point is a compound artifact, not merely a .sav filename.
It binds:

- Target source identity and selected code/version/layers.
- Backend binary identity, configuration, machine model and snapshot format.
- A qualified native checkpoint, or an explicitly weaker application-save seed.
- A point-in-time filesystem manifest and immutable file/block contents.
- Input queues and ownership policy, clocks/RNG/device coverage, and any replay log
  prefix that is required to reproduce the selected historical path.
- A consistent analysis revision, semantic schema, runtime mappings and source
  bindings, with compatibility/rebinding requirements.
- Parent instance, anchor, branch, capture boundary, guest time and host time.
- Allowed interventions, budgets and private/public evidence policy.

The capsule states its restoration level: `native_checkpoint`,
`application_save`, `semantic_snapshot`, or `static_only`. These are proposed
metadata values, not existing product schema fields. A full-file manifest hash
is evidence of identity, not a mechanism for restoring those files.

An application save can jump-start research while omitting transient state,
callbacks and current CPU position. It must never be called instruction-exact
cloning. The recent Syndicate research seed is an appropriate first application-
save experiment because a fresh process load and subsequent research update were
previously observed [L2]. Re-running those checks in private worker filesystems is
still required before claiming parallel-isolation qualification.

## 5. Clone lifecycle

1. Admit the job against backend capability, available workers, storage, memory,
   execution budget and the parent's latency policy. Validate all intended edits
   before touching the parent or allocating large payloads.
2. Choose a retained anchor or capture a new one at a coherent stopped boundary.
   Synchronize the writable filesystem version with that capture. Do not copy a
   changing save directory alongside an unrelated memory image.
3. Freeze the anchor and its filesystem base. Give the reference instance a new
   private writable layer if needed, then release its capture pause. Child launch
   and validation should not keep the reference paused unnecessarily.
4. Allocate a private workspace, process/socket/port namespace, writable layer,
   analysis overlay, input ownership and append-only event namespace for each child.
5. Restore through a backend-supported route. Validate code, registers, selected
   memory invariants, mounted-file identity, expected mode and input ownership.
   Qualify host-path remapping explicitly; do not delete compatibility checks.
6. Hand the paused child to exactly one worker controller using a generation-bound
   lease. Static-only workers need no native process.
7. Run the bounded trial. Receipts distinguish ordinary inputs, diagnostic
   preparations, native rewind, selective/mixed-state edits and model execution.
8. Publish an immutable result packet; compare against a baseline; retain negative
   controls and first divergence. Promotion of conclusions is separate from
   promotion of code or runtime state.
9. Close/reap the worker's owned processes, preserve required artifacts, and retire
   temporary overlays only after references have been checked. A child failure
   must not restore, reset or kill the parent.

Lease expiry is not proof the old process stopped. Before a replacement controller
receives mutation authority, fence the old generation and confirm stop/termination
or quarantine the old instance. Never let two generations concurrently own input.

If a backend snapshot embeds host file paths, the adapter needs a consistent
sandbox-internal namespace or a verified supported remapping procedure. Merely
changing a metadata string is not a qualified restore. Guest file descriptors,
open-file positions and caches also belong to the backend's coverage contract.

## 6. Linked clones and copy-on-write

A linked clone should reference an **immutable point-in-time base**, not the
parent's currently changing disk. Each branch writes to its own overlay. QEMU's
backing-file/overlay model provides a relevant disk mechanism [Q2]; it does not
by itself give RAM cloning, snapshot portability, or deterministic execution.

The first implementation may simply duplicate guest RAM through ordinary native
save/load while sharing immutable asset bytes. Correctness comes before page-level
sharing. Later, backend-specific copy-on-write RAM or filesystem reflinks can
reduce duplication after cross-process state and lifecycle support are qualified.
Hard-linking mutable saves is not copy-on-write.

Do not start with raw host `fork()` of an arbitrary running emulator. That would
need a backend-supported quiescent point and explicit treatment of threads,
locks, external descriptors, timers, sockets and ownership. The proposed baseline
is a supported snapshot/restore adapter, not a claim that process fork is safe.

For analysis databases, take a transactional snapshot, such as SQLite's backup
API, rather than copying an active database file without coordinating its state
[DB1]. Each worker receives its own writable overlay/database. Evidence publication
is brokered or transactional; workers never overwrite a shared stream's current
entry using only a guest tick as the key.

## 7. Rewind while the reference continues

The reference and historical child are independent execution timelines after the
fork. The parent can advance from t0 to t100 while the child remains at t0 or
replays a recorded interval. This removes the requirement to rewind the reference
for every forensic query. It does not eliminate the original capture cost or
competition for CPU, RAM and disk bandwidth.

An older event needs an older retained anchor and sufficient continuation
information. Cloning the present cannot recover uncaptured overwritten memory.
In a backend with deterministic record/replay, clocks, interrupts and external
input must be controlled or recorded. QEMU's replay documentation explicitly
includes these events [Q3, Q4]. Those QEMU features do not automatically confer
record/replay support on fDisBull's DOSBox adapter or a nested configuration.

Use two separate operating modes:

- **Historical reproduction:** consume the qualified recorded input/environment
  prefix; compare at relevant boundaries; stop and report divergence.
- **Counterfactual experiment:** start at the same qualified point, declare the
  intervention and new inputs, and create a new branch. Do not claim later output
  matches the original recorded future after deliberately changing its cause.

Even two identical starting checkpoints do not justify a determinism claim until
the relevant clock/input/device behavior has been qualified. A semantic-only
match and full-state equality are different comparison scopes.

## 8. Review, history and result transfer

Each event carries workspace/run/branch/epoch identity and a monotonic local
sequence, plus guest time when available. An effect slot, timestamp, event text
or health decrement is not an occurrence identity. All review operations name
an immutable point; an asynchronous result arriving late remains attached to
that earlier point, not silently to the current actor or world.

Use three separate result types:

| Result type | Promotion behavior |
| --- | --- |
| Knowledge | Publish a claim, evidence, source/version dependencies and uncertainty |
| Code/model | Review a patch, then run appropriate tests against the selected base |
| Runtime state | Choose a complete child branch, replay a qualified action plan on current state, or perform a separately specified state transplant |

Raw runtime states do not have a general Git-style merge. A successful worker
may have spent funds, killed an actor or consumed RNG differently. Choosing its
whole timeline is explicit branch promotion. Replaying its plan on the live
parent requires fresh preconditions. Selective transplantation retains the earlier
mixed-state consistency requirements [L1]. Preserve the old history in all cases.

Shared knowledge is not necessarily player-visible knowledge. Diagnostic details
from hidden entities or replay should not leak into a fair-play projection. Worker
models and citations remain separately attributable; identical derivations are
not independent verification.

## 9. Lead/worker usage examples

### Damage investigation

The reference continues ordinary play while W1 replays the recipient's health
write, W2 examines candidate vehicle contact, and W3 checks targeting/source
semantics on frozen data. A worker identifying a shooter returns a causal record
bound to the original event and branch. It does not update a stale live actor
pointer or change the reference actor's health.

### Campaign and research

All workers load copies of one qualified partial-research seed. W1 measures the
minimum funding path, W2 the maximum, W3 topic-switch/cancellation and persistence.
The baseline remains unchanged. Compare eligible update counts, cost, graph and
unlock transitions. The original game's save writer can itself have state effects;
preparation must record them instead of assuming a save is neutral [L2].

### General applications

The same orchestration can support X-COM research/manufacturing/mission-save
variants; installer failure and rollback; document-format parsers; compiler output
variants; and API/service mock environments. Each adapter defines its persistence,
external effects and snapshot guarantees. No X-COM execution or compatibility is
claimed here. Parser-only workers may require files and analysis, not an emulator.

## 10. Performance and operational policy

Default to hybrid linked clones with three worker slots, no nested worker fan-out
without admission, and a configurable cap. A worker need not remain resident when
it is only inspecting exported facts. Allow serial scheduling under resource
pressure without changing the experiment's identity.

Measure parent capture pause, child startup, validation, branch execution, event
publication lag, peak private memory, dirty-page/overlay growth, disk read/write
volume, and parent frame-publication p95/p99/max gaps. Do not substitute a small
copy-on-write allocation or low RPC count for evidence of smooth playback.

Reserve foreground CPU/IO resources for the reference. Suppress worker output
windows and audible host output by default while retaining guest-visible emulated
audio/device behavior. Freeze unrelated network/host effects by policy. Do not
claim native snapshots roll back email, network services or files outside the
controlled sandbox. Runtime clones are not a general security sandbox unless the
host isolation boundary separately provides one.

Capture once and fan out several jobs from that immutable anchor. Reuse a short
ring of anchors plus recorded inputs where supported. Garbage collection follows
reference ownership: retiring a parent cannot remove a base used by live linked
children or retained reproducibility evidence.

## 11. Current supplied source: useful primitive and missing seams

See the [supplied source audit](https://chatgpt.com/library?file_id=libfile_dec14b5dcc6c819195f5a4de05a96f0e&account_id=personal) for line ranges and SHA-256 identities. The import also compared all 557 supplied source files to GitLab main at `dc6d7e7709802e743e79cf46e648a4e87b2a0a27`; their Git blob identities matched. Relevant pinned implementations are [debugger.py](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/dc6d7e7709802e743e79cf46e648a4e87b2a0a27/src/fdisbull/debugger.py), [debug_state.py](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/dc6d7e7709802e743e79cf46e648a4e87b2a0a27/src/fdisbull/debug_state.py) and [debug_rewind.py](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/dc6d7e7709802e743e79cf46e648a4e87b2a0a27/src/fdisbull/debug_rewind.py).

- `DebugProjectMixin.debug_fork_state` already starts a temporary debugger, restores
  a state, applies at least one explicit edit, saves a derived state and closes
  that debugger. It is a useful precursor, not a persistent worker-pool API.
- The DOS state-edit path and project checkpoint capture currently enforce real
  mode. The protected-mode Syndicate path must not bypass those checks.
- Native state restore checks source/version/emulator/load/profile and `game_dir`,
  then compares mounted-file manifests. Arbitrarily copied private directories
  therefore need an explicit supported clone/rebinding adapter.
- The source records `disk_restore:false`. Snapshot identity verification is not
  filesystem rollback.
- Existing rewind history is tied to a live run identity. A child needs its own
  owner, timeline and provenance; it cannot inherit the parent's RPC object.
- Existing investigation guidance already requires one controller per live guest
  and isolated files for independent trials. The proposal operationalizes that
  rule rather than replacing it.

The original proposal reviewed the supplied v0.30 bundle and launched no native clones, worktrees, containers, VMs or sub-agents. The subsequent source-identity comparison qualifies the current-source statements above; no native clone qualification was added.

## 12. Implementation stages

1. Implement workspace descriptors, leases, immutable shared artifacts, private
   filesystem roots and branch-scoped evidence. Exercise static-only workers and
   three application-save trials without claiming exact native cloning.
2. Qualify unchanged native checkpoint cloning in a supported mode. Do not require
   dummy edits merely to create a baseline clone. Hold a reference plus three
   long-lived workers, and verify both isolation and shared review.
3. Add protected-mode/module-aware clone qualification and filesystem remapping
   for the Syndicate path, including full selected context validation and recovery.
4. Add rewind/replay workers, event-triggered fan-out, and guarded baseline versus
   intervention comparison. Preserve deterministic and non-deterministic modes.
5. Optimize disk/RAM sharing, eviction and low-pause capture only after correctness
   and measurement. Optional VM-backed runners use their own qualified capabilities.

The concrete first acceptance goal is: three workers independently modify, save,
rewind and exit from one immutable seed while the reference advances and a shared
review shows all four histories without cross-instance mutation.

## 13. Acceptance requirements (prospective, not executed)

| ID | Required observation |
| --- | --- |
| PRW01 | One reference plus three worker slots is the default; caps and agent/runtime counts are independently configurable. |
| PRW02 | An unchanged clone is allowed; its initial admitted state matches the source capsule and its identity is new. |
| PRW03 | Child RAM, CPU, device, input and breakpoint changes do not change siblings or reference. |
| PRW04 | Child save/write/delete operations remain in its filesystem; all branches can safely reuse the same guest-relative save name. |
| PRW05 | Mutating or deleting an immutable base is refused while referenced; linked children do not follow later parent writes. |
| PRW06 | A relocated host directory requires validated mapping or explicit refusal, never stripped identity checks. |
| PRW07 | One mutation owner per instance; stale generations, duplicate control and unsafe lease takeover are rejected. |
| PRW08 | Concurrent observations identify a coherent published snapshot rather than mixed-time reads. |
| PRW09 | Reproduction distinguishes missing history, unsupported replay, observed agreement and first divergence. |
| PRW10 | A counterfactual branch cannot masquerade as the parent's historical future or silently join its runtime state. |
| PRW11 | Equal-looking events from different branches/epochs remain distinct; duplicate transport delivery is idempotent. |
| PRW12 | Shared knowledge preserves source/provenance, disagreements, visibility policy and experiment blinding. |
| PRW13 | Child crash, timeout or failed restore quarantines that child without killing or restoring the reference. |
| PRW14 | Snapshot/overlay capture is coherent across RAM and files; snapshot identity alone does not claim disk restoration. |
| PRW15 | Resource admission and parent latency monitoring apply to bulk startup, capture and replay. |
| PRW16 | Analysis snapshot and per-worker writes remain consistent under concurrency; evidence publication is durable. |
| PRW17 | Source-worktree, application-save, semantic-model and native-state forks retain distinct qualification levels. |
| PRW18 | Promotion of evidence, code and runtime state has distinct operations and retained provenance. |
| PRW19 | Published manifests/summaries exclude original binaries, private memory/checkpoints, credentials and game saves. |
| PRW20 | Cleanup confirms process ownership and reference safety; retained results survive worker disposal. |

## References

[G1] Git, git-worktree: https://git-scm.com/docs/git-worktree
[Q1] QEMU, Disk Images: https://www.qemu.org/docs/master/system/images.html
[Q2] QEMU, Live Block Device Operations: https://www.qemu.org/docs/master/interop/live-block-operations.html
[Q3] QEMU, Record/replay: https://www.qemu.org/docs/master/system/replay.html
[Q4] QEMU, Execution Record/Replay: https://www.qemu.org/docs/master/devel/replay.html
[DB1] SQLite, Online Backup API: https://www.sqlite.org/backup.html
[L1] [Supplied Syndicate selective-rewind study, D007](https://chatgpt.com/library?file_id=libfile_17ed165b07fc81918b8941eb8752f216&account_id=personal), especially composition and history sections.
[L2] [Supplied Syndicate campaign research, D008](https://chatgpt.com/library?file_id=libfile_7c70110ac540819183fb3a4dfec18a90&account_id=personal), especially save qualification and writer effects.
[L3] Supplied fDisBull_ChatGPT_Offline_Reference_v0.30.0(4).zip, exact identities in the [source audit](https://chatgpt.com/library?file_id=libfile_dec14b5dcc6c819195f5a4de05a96f0e&account_id=personal).

Web references retrieved 2026-11-02. Their documented mechanisms are design
references, not evidence that the installed fDisBull runtime already implements
this orchestration or inherits every listed QEMU capability.

## Related delegation policy

[Draft MR !47](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/47)
adds explicit task roles, context modes and completion criteria to the existing
investigation skill. Conversation-context isolation and runtime-state isolation
remain separate decisions. This RFC does not replace that policy or install its
[suggested skill wording](PARALLEL_RESEARCH_SKILL_ADDITION.md). The companion
[descriptor](examples/parallel-research-workspaces.proposal.json) is illustrative;
its fields grant no capabilities.
