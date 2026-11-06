# Entity state, observation and staged completion: X-COM/TFTD continuation

Date: 2026-11-05. Continuation of MR !82 at the owner's request.

**Scope:** a source-grounded methodology synthesis from retained reports, the owner's reverse-engineering experience, a supplied finite-state-machine transcript, and the parallel AITD/Jack investigation. No new original-game execution, worker trial, performance measurement, runtime feature, production schema or equivalence proof is claimed. This document does not overwrite historical reports or activate a shipped skill.

## 1. Why this belongs in !82

The UFO/TFTD workers and the AITD/Jack investigation reached related distinctions: persistent entities versus active instances; stored records versus live state; input selection versus effect; and changed memory versus the image currently available to the observer. The supplied state-machine lesson gives these observations a common language. This is convergence on a reusable method, not a separate engine proposal or an attribution of game-specific findings to the video.

The existing !82 operation-goal and navigation work already separates file operations, state adoption, continuation and redraw. Extend that framework rather than introducing a second scheduler, mandatory evidence ledger or universal FSM interpreter.

The central rule is:

> Recover entities and their relationships, follow their transitions across contexts, and qualify each result at the boundary needed by its next consumer. Do not treat a command return, copied buffer, meaningful state change and refreshed display as interchangeable evidence.

## 2. Evidence recovered for this continuation

### Reviewed experiment reports, not a new replay

The three existing GitLab report attachments were downloaded again and their SHA-256 values matched the identities recorded in !82:

| Source | Identity | Relevant scope |
| --- | --- | --- |
| [results.md](https://gitlab.com/brewster-jennings-group/fdisbull/uploads/c24b2309210f2578b50710e6450c2edd/results.md) | `942a460971a8dd6749abc8391980010159d81d1204888c56d890f2406c263ca3` | Sections 2-6 distinguish the paired live study, independent workflow/structure trials, prepared-harness demonstrations, assisted continuations and latest cold native-contract trial. |
| [agent-feedback-and-next-work.md](https://gitlab.com/brewster-jennings-group/fdisbull/uploads/875ff453b3b9b5c275354d9879dd30bf/agent-feedback-and-next-work.md) | `70d6d226e08002c4e3bcdaa49080291e119c3b83372f9936b40bd88ef14cece3` | Repeated worker feedback explicitly separates buffer change, state adoption, continuation and display; a compact response hid a decisive successful transfer. |
| [project-state-and-methodology.md](https://gitlab.com/brewster-jennings-group/fdisbull/uploads/a764d95dba09096a725f720f1e8f526c/project-state-and-methodology.md) | `152c34d50852378986ce81c9c08a3838b249741b4bce17546b9fe7c4bc589968` | Existing operation goals, dependency-local blocking, batched probes, reusable actions and original-call contracts. |

The [human overview in !82](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/82#note_4162157681) is a useful entry point; the attachments above retain the distinctions behind it.

Library searches located the shared `KNOWLEDGE.md` MR-intake account and unrelated extended Civilization logs, but did **not locate the extended raw UFO/TFTD experiment logs**. This is a retrieval limit, not a claim that those logs do not exist. The retrieved reports explicitly place detailed reports/audits in their private experiment workspaces and exclude raw logs. Useful retrieval keys are `xcom-crossover-20261103`, `xcom-live-20261103`, `ufo-cold-20261103`, `serializer-z-20261103`, `z-controller-money-20261103`, `feedback-retest-20261104` and `native-contract-20261104`. Do not label the unrelated Civilization logs as X-COM evidence.

### What the UFO evidence actually establishes

In `native-contract-20261104`, an original reader capture transferred the prefixed LIGLOB bytes into a **sampled destination buffer**. A subsequent, separate direct reader replay failed at a cannot-open message. The retained report does not establish the whole strategic loader, authoritative state adoption or a refreshed changed-funds display for that cold attempt. The later failed replay does not erase the earlier captured transfer. Restoring the file on disk does not establish restoration of the running process.

Other runs did show funds changes and restoration on screen: the November 3 UI workflow, the prepared-harness serializer trial, the assisted UFO continuation, and separate coordinator known-binding smokes. Those remain different experiments. Their success cannot be borrowed to complete the latest cold attempt. The exact reader-transfer example is reported for **UFO**, not asserted as a demonstrated TFTD failure too. [Results, sections 3-6](https://gitlab.com/brewster-jennings-group/fdisbull/uploads/c24b2309210f2578b50710e6450c2edd/results.md)

The worker-feedback report records a separate communication failure: a compact response hid the decisive buffer delta, and a worker missed the successful transfer. Thus the remedy is both a better operation model and a better bounded summary. It is not merely 'wait another frame.' [Repeated worker feedback](https://gitlab.com/brewster-jennings-group/fdisbull/uploads/875ff453b3b9b5c275354d9879dd30bf/agent-feedback-and-next-work.md)

### Convergent AITD/Jack evidence

The retained `fdisbull-aitd-original-harness-report-20261104.md` explicitly records a fresh load where selected actor values had returned while the rendered frame was still black; the scene guard waited for the settled attic. Report SHA-256: `d9b56ff364b8334ffa7700f7f1a6fd9c90c78e0bfb8244bb16569970a1d0cef7`. This is stronger selected-state evidence than the UFO sampled-buffer observation, but still not all-field or whole-game equivalence.

The AITD object study separately records persistent lamp identity surviving removal and recreation of its active actor in a different slot, and distinguishes selecting Drop from executing it. The Jack report records the same tested persistent-object/active-actor distinction for two pickups while requiring different record profiles. `fdisbull-jack-transfer-report-20261105.md`, SHA-256 `75cfd835ca9dd79972616bc9597fe5ae85ff8289d382b6b6460e166d8f37f9f0`, preserves its scope: two original-runtime replays of a bounded shop slice, not a completed game. These reports were read as retained evidence, not rerun here. Their private game/reference payloads are not copied into this MR.

## 3. Use the transcript for concepts, not a game-state oracle

Source: owner-supplied `Pasted text(4).txt`, a WEBVTT-style transcript with embedded timestamps; SHA-256 `2055e48d8185c9c2baa61139da2f3b3f05e1ec49f91707f48a8d90b2f8ec7835`. No video URL or diagram was supplied for this transcript. It is **not assumed to be the same video** as the earlier CPU-video assessment already attached to !82. The full transcript is not republished here.

Relevant concepts, paraphrased from the supplied text:

- **00:22-00:39:** state retains the relevant history for future behavior; identify inputs, outputs and state variables explicitly.
- **00:46-00:58 and 01:21-01:31:** selection, computation and committed update differ; a value presented at an input is not yet captured storage.
- **03:43-03:49 and 07:43-07:48:** define behavior for the admitted state/input combinations; an omitted combination is not automatically a safe default.
- **04:22-04:32 and 05:41-05:47:** outputs may depend on state or state plus input; the placement of an output changes observation timing.
- **18:23-18:53:** compare input/output sequences, not only final states, and retain meaningful state names alongside their binary encodings.

The object-ecosystem model and software loading application below are our synthesis. The transcript's clocked-circuit examples do not prove a particular game-loop order, a universal one-frame delay or that every game uses one explicit FSM variable. Its final example also contains a caption/trace mismatch around 17:08-17:42; do not use that example as an unquestioned executable test oracle.

## 4. Represent three related things, not one giant state variable

**Entity relationships** describe identity and composition: roster membership, inventory ownership, room containment, and which temporary actor represents a persistent object. A relationship such as 'contains' is not a temporal transition such as 'becomes carried.'

**Behavioral transitions** describe an event under conditions, the relevant state before and after, outputs, and affected entities. Keep independent dimensions separate rather than enumerating every possible cross-product of location, ownership, action mode and appearance. Multi-entity changes may form a useful high-level operation without being atomic in the original implementation.

**Observation state** describes what is known and at what boundary: copied bytes, a current entity read, rendered output, or control readiness. An unknown observation is not necessarily an in-game state called 'unknown.' A stale picture can coexist with correctly adopted game state, but copied bytes can also belong to staging storage rather than authoritative state. Preserve these alternatives until the next discriminating probe settles them.

A recovered transition dossier needs only the relevant entity identities, entry context, event/input, guards, reads/writes, relationship changes, outputs, continuation/completion condition, and evidence references. These are logical obligations for existing project artifacts, **not new JSON fields or a registered format**. Keep source and model interpretations separately labeled.

## 5. Save/load is the immediate worked example

Use a set of separately witnessed boundaries. The following is a diagnostic decomposition, **not a claim that all engines implement this exact total order or separate routines**:

| Boundary | Useful evidence | What it does not establish |
| --- | --- | --- |
| Request/selection | Correct slot/path and accepted original input or qualified native call entry | File opened or anything restored |
| Transfer | Expected bytes read into a specified sampled buffer, with source and extent | Complete file family, authoritative state adoption or display |
| Adoption | Current entity/state binding reflects the intended distinguishable saved values | Required derived caches, scene entry or ready controls |
| Continuation | Required original return/initialization/update path reaches its admitted endpoint | A captured picture necessarily represents that endpoint |
| Presentation | A relevant post-change render, with matched source/run/mode and correct discriminating pixels | Input readiness or every unobserved field |
| Control readiness | Applicable scene/content/control guards pass after the required continuation | Whole-game equivalence or arbitrary future behavior |

For a pure record-analysis task, transfer or adoption may be the required endpoint; do not force a screenshot gate on independent file work. For an agent-player action that promises a loaded playable scene, include the necessary presentation and control conditions. Successful child results should release their own consumers while unresolved dependents remain blocked.

### When RAM changes but the screenshot does not

1. Retain the successful transfer or state witness, its exact source/version/run/restore epoch, and the operation's partial result. Surface the changed range/count or selected value in the compact reply, with the raw observation linked.
2. Determine whether the bytes are staging data or current adopted state. Re-resolve relocated runtime objects after loading or restoring; a previously valid address is not permanent identity.
3. Check whether the original call is paused before its necessary continuation. Advance only through the qualified owned continuation, under bounded guest time and stop conditions. A foreign debugger stop is not permission to resume.
4. Distinguish **an old captured frame** from **a newly captured or rendered image whose UI still represents an earlier state**. A capture RPC revision is not a render-state revision, and a larger frame ID alone does not prove correct semantic content. Keep mode, palette/geometry assumptions, render identity and capture order explicit. Separate state/frame reads are not automatically atomic.
5. Use the smallest discriminating readiness/outcome predicate. Known-state scanlines or sparse pixels need no repeated model interpretation. Preserve full frames or a bounded sequence for an unfamiliar transition or contradiction, using an available capture API; merely calling a capture 'burst' does not prove complete intermediate coverage.
6. Stop at the first unresolved required boundary. Do not repeat a possibly completed Load or Save to obtain a prettier screenshot, reject a plausible field solely because a stale screen disagrees, or count a visually similar old screen as proof of restoration.

A suitable compact account is: 'Original read observed into buffer B; authoritative adoption unverified; later replay failed to open its path; no refreshed funds witness; file restored, live restoration unknown.' For the different AITD case: 'Selected actor fields restored; presentation not ready yet; bounded original continuation later satisfied the attic guard.' These sentences preserve the evidence instead of flattening both runs into 'load failed' or 'load passed.'

## 6. Soldiers, aliens, room objects: the same method at different levels

The owner supplied prior reverse-engineering experience connecting soldiers at rest in a base with their battle representations and an expanded tactical entity roster including aliens. Preserve that as an owner-provided lead for reusable analysis, not a newly established address/layout result from this document.

The retained UFO evidence supports a narrower result: a complete census of 250 soldier **record positions**, and later eight same-campaign names joined to UNITREF using candidate stride/offset assumptions. Occupancy and full meanings remain unresolved. A shared name is evidence for a correspondence candidate, not a unique cross-context entity identifier by itself. [Results, sections 3 and 5](https://gitlab.com/brewster-jennings-group/fdisbull/uploads/c24b2309210f2578b50710e6450c2edd/results.md)

The reusable capability chain is:

**Recognize one instance -> enumerate compatible peers -> follow transitions between contexts -> recover shared and variant behavior -> compose higher-level drafts -> propagate qualified rules.**

This combines three directions of generalization:

- Across instances: one room/record reader enumerates the compatible population.
- Across contexts: a persistent soldier or object is related to its current tactical or actor representation through an observed transformation, reference or lifecycle.
- Upward composition: records, relationships, geometry, scripts and transitions form a higher-level scene or operation.

For the AITD/Jack pair, the object-catalogue pilot generated 49 **object-referenced** room drafts, not every actual room. A staircase observed in original execution was absent from the initial object's room references. That is why room-directory completeness must be separate from object census completeness. The retained census report is `fdisbull-room-draft-census-report-20261105.md`, SHA-256 `f3f7230863e5904a137867c65c7f68c96cec0817588b03fe3dd15d7bf80a2129`.

A representation or shared consumer qualified on one instance can justify batch recovery within its compatibility scope. One observed special-case behavior cannot automatically authorize every similar entity. Put layouts, counts, text/action IDs, field encodings and special callbacks in explicit target profiles; share the reader/controller/transition method. Shared game ancestry is a reason to test transfer, not permission to copy addresses, strides or whole-scene success claims.

UFO/TFTD and AITD/Jack are analogous related-game investigations, **not matched performance experiments**. Keep their task scope, assistance, versions, timelines and evidence separate.

## 7. Proposed shared skill addition

Integrate this short policy into the maintained investigation/reference guidance, using the existing task framing, operation goals, record frontiers and scene evidence:

> After identifying a recurring representation, enumerate its compatible instances deterministically and preserve unplaced, inactive and unresolved records. Follow entities across lifecycle and context transitions; retain stable identity separately from active slots and storage addresses. Recover guards, effects, outputs and cross-entity dependencies rather than treating records as unrelated fields. Propagate shared structure and behavior only within established compatibility, preserving variants and exceptions. For every consequential action, distinguish input, transfer, adoption, continuation, presentation and readiness as required by its consumer. A completed child effect must remain visible in compact output even when the parent is incomplete. Resume only the missing qualified continuation; do not repeat an uncertain effect or discard successful evidence because its visual output is stale. Validate relevant traces and negative cases, not merely the final screenshot.

Keep this policy shared. Game-specific offsets, anchors and recognition examples remain adapter data. Preserve the historical old/revised skill snapshots; updating a maintained skill must also update its maintained inventory and tests rather than rewriting archived study inputs. This commit supplies the reviewable policy and evidence; it does not claim the maintained/installed skill has adopted it.

## 8. Concrete acceptance work for the existing operation-goal owner

These are proposed tests, **not tests executed for this update**:

| Case | Required distinction |
| --- | --- |
| Original read succeeds but later replay fails on path | Keep first transfer fact; retain later failure and do not infer whole load completion. |
| Only a staging buffer changes | Transfer succeeds, adoption remains unknown/false. |
| Adopted values change while framebuffer is old or black | Preserve adoption; no premature control input; bounded continuation can qualify presentation. |
| A fresh frame still displays old content | Render freshness alone is insufficient; required content predicate still fails. |
| Two epochs/owners contribute state and frame | Reject their combination as a coherent current observation. |
| Wrong slot or deliberately changed state without loading | Reject a broad background/menu match as restoration. |
| A popup appears before a queued click | Handle only its qualified policy, then recheck the pending action's scene and relevance. |
| Restore only the save file after a partial live load | Disk restoration must not imply live restoration. |
| A new related-game profile has different strides/IDs | Reuse machinery, refuse incompatible bindings, keep opaque fields. |
| A dormant or empty entity row exists | Enumerate it without calling it active, visible, carried or accessible. |
| Two identical current observations produce different later outcomes | Investigate omitted state/context/input or timing; do not invent deterministic equivalence. |

The next useful live proof remains the original !82 goal: complete the required serializer family, authoritative adoption and valid continuation, demonstrate a discriminating changed value in the refreshed view, then restore at every claimed boundary. In parallel, soldier/record analysis can proceed on already qualified immutable data. No need to solve every field or display detail before another independent capability advances.

## 9. Publication boundary

This is one source documentation addition to the existing X-COM/TFTD MR. Its references identify retained report evidence, owner-provided knowledge and new methodological inference separately. No original executable, save, screenshot, memory dump, full commercial transcript, secret, private raw agent log or new runtime code is committed. No game tests, independent worker comparison, hosted CI, merge, tag, package or installation change is part of this update.
