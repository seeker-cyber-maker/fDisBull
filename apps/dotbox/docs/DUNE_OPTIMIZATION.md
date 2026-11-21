# Dune: sparse observations and bounded native waits

This continues [the first progression run](DUNE_PROGRESS.md) and implements its
two measured overhead reductions. The replacement run began at 23:51 on
18 November 2026 (America/New_York); raw receipts and filenames use UTC.

The delivered research controller can read only its explicit observation
dependencies and let one native request wait for a breakpoint, frame limit or
guest-time limit. A rebuilt DotBox native executable was used for the final
eight paired trials and continued ordinary-input play. Defaults remain the
existing full-reader, single-frame path; optimized modes must be selected
explicitly.

**Continuation added 19 November 2026 (UTC):** the
[travel-map selector guide](DUNE_MAP_SELECTOR.md), topic `dunemap`, documents the
subsequent prepared-choice adapter and its own validation scope. The paired
measurements, runtime qualification and single map trial below remain the
historical optimization slice; the continuation does not expand those results.

## What changed

### Sparse stopped observations

`describe_sparse(read, ds=DS)` and `read_structure_sparse(read, ds=DS)` in
`scripts/experiments/dune_ui_reader.py` accept a synchronous callback that returns
exactly the requested bytes. The reader caches real returned ranges for one
capture. It never fills the unread parts of a synthetic conventional-RAM image
with zeros.

The full scene reader returned the same complete and compact observations as
the original reader on 41 retained real captures covering ordinary menus,
conversation, travel map, troop map, orders and occupation. Each sparse capture
used four reads totaling **21,918 bytes**, compared with a **655,360-byte**
conventional-RAM snapshot. This is coverage of the recorded edition and states,
not proof that every possible Dune scene has been decoded.

Each sparse result keeps the parsed observation, raw control-stability witness,
actual range identities and the precise merged dependencies used by parsing.
The digest of all captured bytes and the digest of parsed dependencies serve
different purposes: an unused prefetched byte must not invalidate an unchanged
menu, while a changed external label must invalidate its binding. A range hash
is neither a full-RAM identity nor a restorable machine checkpoint.

The controller checks stopped session/revision identity around capture and
again checks the selected label, handler and record at dispatch. The sparse
reader alone does not confer readiness or prove agreement with rendered pixels.

### Native bounded execution

The native overlay advertises:

```json
{
  "execution": {
    "bounded_frame_step": {
      "schema": "dotbox-bounded-frame-step-1",
      "max_frames": 10000,
      "max_guest_ms": 30000
    }
  }
}
```

A capability-aware caller sends both limits to `frame.step`. The native target
returns a stopped result at an observed debugger stop, completed-frame limit or
guest PIC-tick limit. The receipt reports actual completed frames, before/after
ticks, tick width, elapsed guest time and stop cause. A breakpoint coincident
with a limit takes precedence over the budget. Calling with neither limit
retains the legacy one-frame behavior. See [the native protocol](../native/README.md#bounded-execution).

The controller validates the receipt rather than assuming that the requested
number of frames completed. This includes frames completed before a breakpoint,
modular tick arithmetic, the matching native revision and the exact stop cause.
Absent or incompatible capabilities are refused; an older backend may ignore
unknown fields, so an implicit native fallback would be unsafe.

A successful guest-limit response is a known stopped partial result. A host
RPC timeout or lost response remains uncertain and does not permit replay or
automatic continuation. A retained screenshot can exist after a zero-frame
guest limit; `frame_available` does not establish freshness.

### Recovery from a controller-owned guest deadline

A deadline may stop inside a drawing overlay with a temporary CS or DS.
Input-free reconciliation may resume only the exact budget stop previously
validated by that controller. It still requires real 16-bit code and stack,
disabled paging, unchanged hook bytes and no foreign probes. The eventual owned
input-loop stop must satisfy the original CS/DS mapping before the controller
can issue a new actionable token.

Deleting the controller's observer also advances the native revision. Cleanup
now adopts only the acknowledged expected transition with the same stop reason;
an extra revision or different stop is not treated as the controller's own
state. This avoids both a false refusal after legitimate cleanup and accidental
adoption of an unrelated stop.

A real-game check sent one ordinary close-conversation click, stopped at a
200-guest-millisecond budget inside the drawing overlay, removed its observer,
then reached a fresh input boundary with input-free reconciliation. There was
**exactly one click** and no replay. Negative tests retain foreign/changed-stop,
protected-mode, 32-bit, paging and wrong-DS-at-return refusals.

## Explicit research API

The caller still owns the existing native adapter and its input-generation
fences. It supplies the measured executable and a private evidence directory
outside the repository and game mount.

```python
controller = ProgressController(
    call, describe, private_evidence_directory,
    session_id=owned_session_id,
    source_path=dune_executable,
    wait_strategy="native",
    read_strategy="sparse",
    capabilities=native_capabilities,
    sparse_reader=describe_sparse,
    structure_reader=read_structure_sparse,
)
ready = controller.await_ready(
    max_frames=1800, max_guest_ms=15000, host_budget_ms=30000,
)
# Select an applicable observed control only after outcome == "input_boundary".
# Reuse ready["after"]["scene_token"] in this same controller.
```

`wait_strategy="frame"` and `read_strategy="full"` remain the defaults.
Neither construction nor observation launches the game, selects a story goal,
takes ownership, restores state or calls a model. A new controller cannot
inherit an old controller's private stop merely because both name one session.

## Controlled measurements

All eight final trials restored the same Carthag-Harg machine checkpoint in the
same graphics-initialized process and used the same newly built native binary.
Two runs of each combination were taken in mirrored order:

`frame/full, frame/sparse, native/full, native/sparse,`
`native/sparse, native/full, frame/sparse, frame/full`.

The frame/full baseline used the original controller and reader from commit
`d5d730d365e18dec818377158b3621b2697297c4`; the other combinations used the
qualified final source. Each trial entered the chief's conversation and then
advanced one dialogue page. Each action retained its dispatch, readiness,
input-neutrality, observer-cleanup and outcome evidence.

| Wait / reader | Conversation entry, mean host ms | RPCs | Next page, mean host ms | RPCs | Bytes read per action |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frame / full | 1,459.680 | 227 | 247.360 | 75 | 1,572,879 |
| Frame / sparse | 1,270.799 | 222 | 171.046 | 70 | 117,315 |
| Native / full | 1,320.058 | 61 | 218.654 | 61 | 1,572,879 |
| Native / sparse | 1,259.475 | 56 | 164.114 | 56 | 117,315 |

The combined strategy reduced calls from **227 to 56** for entry (75.3%) and
**75 to 56** for the next page (25.3%). Memory transfer per action fell **92.5%**.
These totals include the controller's admission, dispatch, control-stability
and after-action reads, not just the final scene capture.

All eight trials had the same final image hash, menu-admission hash and dialogue
witness for each corresponding action. Entry completed 85 frames and advanced
1,213 guest milliseconds; the next page completed nine frames and advanced
128 milliseconds. Full/current sparse/original reader comparisons after each
trial were also exact. That separate untimed audit used ten full memory RPCs
and four sparse RPCs and is excluded from the measured action totals.

Two repetitions per combination are a descriptive host-timing sample, not a
general latency guarantee or a statistically established speedup. Earlier
candidate runs included native entry timings near or above the frame baseline.
The reliable result is less transfer and polling while retaining equivalent
measured behavior; the original animation still consumes its guest time.

Each case changed a closed canary file after checkpoint creation, inventoried
the mounted files before restore and after the actions, and preserved the exact
disk inventory. Machine rewind did not roll files back.

The [sanitized receipt](evidence/dune-optimization-2026-11-19.json) retains
individual measured timings, source identities, image/state hashes, qualification
checks and limits without commercial assets or raw memory.

## Rebuilt native qualification

The tested Linux x86-64 executable has SHA-256:

`af4d353c128dbb58fa433a0f8601cb92d8fb93acc907e25827c038d6dea77e8e`

The fresh source audit reapplied both patches to the exact pinned upstream tree
and verified all 38 resulting recipe files. The retained upstream commit's
metadata differed from the pin, but its tree matched; this distinction is kept
in the receipt. The generated ownership overlay includes all eight result files,
including the pending-breakpoint checks at the safe native stop boundaries.

Six actual native bounded-wait fixtures, four existing headless native fixtures
and ten source/overlay fixtures passed without skips. The bounded cases cover
multi-frame and legacy calls, a zero-frame guest deadline, an exact
breakpoint/guest-time collision, a pending breakpoint at the first completed
frame while an authored CPU is halted, foreign-breakpoint preemption and
invalid bounds with no state mutation.

Removing only the coincident-breakpoint check in a private negative-control
build made the exact guest-time regression fail as intended. The correct source
was restored and rebuilt to the same qualified binary hash. A proposed
cross-restore renderer collision did not establish matching frame phase and
was discarded; its failed receipt is retained. Pending data-access collision
handling was reviewed in source but has no separate live fixture.

The Python tests additionally exercise sparse capture/coherence and dispatch
revalidation, native receipt validation, frame/tick accounting, owned-budget
reconciliation, cleanup provenance and refusal after uncertain transport.
Installed-package checks verify the exported guide and evidence alongside the
runtime and resource catalog; public resources remain authored material.

## Restored progression and handoff

The replacement recovered the previous checkpoint through the already qualified
graphics-initialization workaround. From the recorded run start to usable
restored controls and an ordinary action with changed pixels/state took
**49.410 seconds**, within the declared 180-second warm-recovery target.
The first source-snapshot layout caused an evidence-path refusal before control;
the attempt is retained as instrumentation/recovery evidence. The prior run's
longer recovery interval remains a separate recorded result.

Ordinary input then reached Carthag-Tuek, met Gurney and completed four bounded
dialogue actions. The macro used **224 RPCs**, read **469,260 bytes**, completed
**100 frames**, advanced **1,427 guest milliseconds** and took **1.611 host
seconds**. No model call occurred inside the macro. The predecessor's full-reader
Gurney run is useful recovered history but is not a paired timing comparison.

The final frontier is inside Carthag-Tuek, site record `0250`, at the ordinary
menu with map, Gurney and Fremen choices. The conversation is closed. Gurney's
introduction and discussion were observed, but **COME WITH ME was not selected**;
party membership has not been established. No new spice-harvest quantity was
measured.

A complete machine checkpoint, `gurney_after_dialogue.sav`, was saved privately:

`d14439aaa272fc39767cb084ee5e0c7d51fb332fd62875c43cfbc29c388f6221`

Input was neutral and no observers remained before the isolated process was
closed and confirmed reaped. Restore must reacquire current ownership generation
and readiness; a saved action token does not survive a process replacement.
The predecessor's unavailable process handle has no confirmed closure receipt
and is not conflated with this replacement process.

### Separately qualified map dispatch

Map point selection uses the non-rectangle callback path, not the menu
controller's selected-record hook at `0824:D326`. A root-owned ordinary click
trial observed `0824:D2FE`, verified the live vector at `DS:2A5C`, its selected
callback, mode, gate, viewport and point identity, then observed the accepted
site path at `0824:4D74`. At acceptance, both `DI` and `DS:4258` named the
intended Carthag-Tuek record `0250`. Flight readiness and subsequent arrival
were observed separately.

For this trial, the vector pointer was `2176`, the selected callback `4D4E`,
the gate `04`, and the viewport `(81,45,241,134)`, inclusive at its lower bounds
and exclusive at its upper bounds. The point `(169,118)` was uniquely nearest
at Manhattan distance zero, with the next eligible point 16 away; the original
acceptance threshold is below nine. These are edition-bound witnesses.

This is a qualified single route, not a packaged general map adapter. The next
adapter must explicitly bind the vector, gate and viewport in addition to the
point records. Their presence in a prefetched range does not make them parsed
dependencies. Retain negative cases for changed callback/gate/mode/viewport,
missing or moved points, ineligible or tied candidates, active rectangle overlap,
wrong accepted destination, exhausted bounds, foreign stops and uncertain replies.
None should trigger an automatic second click.

**Subsequent implementation, 19 November 2026 (UTC):**
[`MapSelector`](DUNE_MAP_SELECTOR.md) now supplies that bounded travel-menu
adapter with read-only preparation, a single-use selected intent, the complete
pinned callback vector, and separate acceptance/readiness reports. Its 124
authored protocol tests and final live evidence have a separate record in the
new guide. The single trial described in this section is preserved as earlier
route qualification and is not substituted for the new adapter's validation.

## Remaining boundaries

The work qualifies the recorded headless Linux native build and supplied DOS
edition. It does not qualify original-Dot desktop takeover, the new bounded path
on macOS, arbitrary editions or cross-build snapshots, a general strategic
simulation, or production action transactions.

The existing text-mode-to-graphics restore defect remains open. Initializing
the matching game's graphics normally before load and checking a subsequent
visible mutation qualifies this narrow path; it does not repair the native VGA
serializer/handler issue. Private machine state, game files, screenshots and
raw memory stay outside Git. Publication advances two independent repository
branches without merging their histories or claiming release integration.
