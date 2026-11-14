# DESQview and memory searching

## Contents

- [Select the entry contract](#select-the-entry-contract)
- [Use normal automatic tracking](#use-normal-automatic-tracking)
- [Prepare a cooperative observation](#prepare-a-cooperative-observation)
- [Capture and narrow a value](#capture-and-narrow-a-value)
- [Apply a bounded edit](#apply-a-bounded-edit)
- [Keep evidence scoped](#keep-evidence-scoped)

## Select the entry contract

Import DESQview's actual MZ program normally. Do not import a raw `.DVR` as a
DOS SYS or launch it as a COM. Inspect its own format first:

```sh
fdisbull desqview-module-inspect /private/DOSBUF.DVR
fdisbull desqview-module-inspect /private/old/DOSBUF.DVR --expected-type 'DMA Memory' --expected-version 0x220
fdisbull dos-services --vector 0x21 --registers '{"ax":11009,"cx":17477,"dx":21329}'
```

The newer DVdx module starts at raw offset 0 and receives a far callback context
pointer at SS:[SP+4]. The older first word points to a type descriptor, not code.
Its name length comes from the caller descriptor. Inspecting either contract
does not reconstruct every relocation, export or initialization phase.

For an installed caller-owned image, pin the actual selected members:

```sh
fdisbull desqview-profile /private/dos.img --program '\DV\DV.EXE' --module '\DV\DOSBUF.DVR' --startup '\AUTOEXEC.BAT'
```

Add `--qemm` only when the actual boot CONFIG.SYS selects QEMM and its driver is
present. Keep the returned profile object for JSON `debug-launch` with
`backend="qemu-machine"`, `boot_image` and `guest_profile`. A default profile
string `desqview` selects `\DV\DV.EXE`. Use the profile object for other paths.
The project itself must be the original raw x86 boot image. The profile fixes
one 486 CPU, 32 MiB, no network and a private snapshot disk. It never installs
DESQview or modifies the caller image.

## Use normal automatic tracking

Start with the ordinary session over the original input. Normal DOS launches
and full-machine sessions attach bounded automatic source/mapping tracking;
custom guest probes, nonce reports and manual `runtime-map` calls are not
prerequisites. For DESQview, use the admitted profile object above or
`guest_profile="desqview"` with the default `\DV\DV.EXE` path. Keep one live
owner and use its normal bounded execution and public input methods.

Inspect the tracker after a useful stop:

```json
{"method":"debug-tracking","params":{"run":"RUN"}}
```

The Python equivalent is `session.tracking_status()`. Check current bindings,
matched source spans, task/lifetime qualification and unsupported diagnostics.
The tracker invalidates current relations before execution or input, compares
source bytes at the stopped CPU, captures fresh page mappings and verifies
linear bytes against their translated physical bytes before publishing new
bindings. A source match qualifies only its compared extent; it does not
recover the entire program or prove ownership of every allocation.

The first passive DESQview provider supports one exact original DV2.8 build.
It validates the selected vendor member, the observed INT15 path and original
manager code/current-task linkage. A nonpatching execution breakpoint observes
the manager's natural XDI lifecycle notifications. Source-backed containment
independently crosschecks the task's owner mapping/process record with the
original manager's process lookup; a physical page relation, PSP, CR3, repeated
handle or matching source bytes does not identify an owning process.

A qualified process CREATE/END closes only that process's task/source aliases.
An unrelated process END must not retire another monitored process. Task
CREATE/END/FREE is scoped to its owning process and handle. Process and task
handle reuse creates a fresh episode; its recorded native owner and generation
remain available in `automatic_tracking` and `tracking_status()` process
episodes. Global DESQview END retires all manager episodes. Unknown or malformed
scoped containment retires continuity and returns a visible stop, retaining
rejection evidence. Never replace missing target ownership with current-task
identity: the original swap notifications can identify a process mapping while
DX names the emitter, so their process-mapping evidence has a separate contract.

Attaching to an existing task/process leaves earlier creation unknown. Set a
creation claim only for the corresponding naturally observed CREATE. The
containment implementation and authored tests establish no native positive or
physical relocation by themselves; qualify original-runtime events and fresh
PTE/byte comparisons separately. A missing hook, provider failure, asynchronous resume,
restored state, write or other observation gap retires the old episode.
Matching bytes or a repeated handle do not reconnect that lifetime. Unsupported
builds, formats, ambiguous matches and exhausted budgets stay unqualified; do
not replace those diagnostics with guessed mappings. Native qualification of
this path is separate from implementation and authored contract tests.

For full-machine keyboard input, queue a public key or bounded US-layout ASCII
text, then run through the normal bounded execution path:

```json
{"method":"debug-keyboard-press","params":{"run":"RUN","key":"enter"}}
{"method":"debug-run","params":{"run":"RUN","timeout_ms":1000}}
{"method":"debug-keyboard-state","params":{"run":"RUN"}}
```

Queued input is sent only after GDB execution is actually running, while the
same lifecycle hook remains monitored. Queue acceptance or dispatch is not
proof that the application consumed a key; inspect the resulting stored frame
or relevant state. Pending events can remain after a breakpoint or deadline.
Do not bypass this path with direct QMP `cont`/`send-key` while claiming the
same monitored lifetime. Full-machine input currently has no mouse adapter or
held-key lease support. See source documentation `docs/runtime-mappings.md`
for registry queries and the separate explicit evidence interfaces.

## Prepare a cooperative observation

This optional helper path investigates the helper's own API/report contract.
Use it when that is the question; normal automatic tracking above does not
require it and does not infer another application's identity from its report.

Generate a unique 16-byte nonce and emit the authored helper into a private
guest directory. Run it using the caller's already prepared guest workflow.

```sh
fdisbull desqview-probe /private/FDVAPI.COM --mode file --yields 3 --nonce 0123456789abcdeffedcba9876543210
fdisbull desqview-report /private/FDVAPI.BIN
```

The file mode writes exactly 64 bytes to `FDVAPI.BIN` and exits. The breakpoint
mode returns exported COM offsets for `report`, `ready` and `release`. Stop at
the exact ready offset and use the JSON live method:

```json
{"method":"debug-desqview-observe","params":{"run":"RUN","address":"REPORT_LINEAR","probe_base":"COM_SEGMENT_BASE","expected_nonce":"0123456789abcdeffedcba9876543210"}}
```

Replace all capital placeholders with observed values. `probe_base` is the
paragraph base, without the COM 100h entry offset. Check the returned helper
verification, status, mapping, application hint and screen pointer. Release
only the selected helper's exported release byte using the backend's guarded
write interface, expected 00 → 01, then resume. No code is injected by observation.

Presence is INT21 AX=2B01/CX=4445/DX=5351. No DESQview INT15 call occurs if it is
absent or its kernel is older than 2.00. BX version minor is binary decimal,
not BCD. Never equate a DV/X product label with its kernel API version.
ASSERTMAP is a BX=0 query, with 1117 through 2.25 and DE17 from 2.26.
PAUSE, debugger waits and file I/O remain outside paired BEGINC/ENDC.

## Capture and narrow a value

Use one owned stopped DOSBox or full-machine session. Choose a bounded range
and an explicit task lifetime identifier; do not derive identity just from an
address, CR3, application menu number or window handle. A mapping change, state
restore, task replacement or freed allocation ends that search.

JSON examples for a foreground `serve` session:

```json
{"method":"debug-memory-snapshot","params":{"run":"RUN","address":"0x30000","length":4096,"task_id":"game-task-lifetime-1"}}
{"method":"memory-search-start","params":{"project":"/private/game.fdb","snapshot":"SNAPSHOT_1","width":2,"stride":1,"mode":"unknown"}}
```

Resume only for a controlled game action, stop again, and capture the identical
range with the same observed task lifetime:

```json
{"method":"memory-search-refine","params":{"project":"/private/game.fdb","search":"SEARCH_1","snapshot":"SNAPSHOT_2","mode":"decreased"}}
{"method":"memory-search-results","params":{"project":"/private/game.fdb","search":"SEARCH_2","offset":0,"limit":64}}
```

Starts: `unknown`, `equal` with `value`, or `range` with `minimum`/`maximum`.
Refinements: `equal`, `not_equal`, `changed`, `unchanged`, `increased`,
`decreased`, or nonwrapping `delta`. Width is 1/2/4/8 bytes; signedness,
endianness, stride and bias belong to the search and cannot change midstream.
Use explicit `bias=-1` for stored=displayed−1; use a separate search for an
alternative encoding. Results survive project reopen and retain previous values.

Keep snapshots at most 16 MiB and candidates at most 1,048,576. The default
candidate budget is finite, with at most 65,536 intervals. A budget error is not
a partial complete result. Split a large domain or increase stride explicitly.
Do not expose snapshot bytes in ordinary summaries; return artifact IDs and
bounded result pages. Existing source-bound watchpoints and traces can then
identify writers once the selected candidate's runtime/source relation is known.

## Apply a bounded edit

Plan by candidate offset within the snapshot, not by an arbitrary live address:

```json
{"method":"memory-edit-plan","params":{"project":"/private/game.fdb","search":"SEARCH_2","offset":12,"value":99}}
{"method":"debug-memory-apply","params":{"run":"RUN","plan":"PLAN"}}
```

The default condition is equality with the captured value. Other conditions
are `always`, `not_equal`, `greater`, `greater_equal`, `less`, `less_equal`;
all but `always` require a comparison value except default captured equality.
Apply checks the live run, version, epoch, task, full-region page mapping and
exact expected scalar bytes. Readback must verify. A dispatched uncertain write
closes the guest and retains a structured receipt; never retry that plan.

For explicit repeated edits or freezing, create a rule:

```json
{"method":"memory-rule-create","params":{"project":"/private/game.fdb","search":"SEARCH_2","offset":12,"value":99,"condition":"less","compare_value":50,"max_applications":8,"max_ticks":32}}
{"method":"debug-memory-rule-tick","params":{"run":"RUN","rule":"RULE"}}
{"method":"debug-memory-rule-run","params":{"run":"RUN","rule":"RULE","ticks":8,"interval_ms":100,"timeout_ms":5000}}
{"method":"memory-rule-info","params":{"project":"/private/game.fdb","rule":"RULE"}}
```

Each tick evaluates the fresh value, consumes a finite tick budget and creates
a new guarded one-shot plan only for the originally selected candidate. An
unconditional `always` rule provides bounded freezing. The run operation is
DOSBox-only, begins with an immediate tick and uses finite guest-time slices;
breakpoints, exits, timeouts and stale/uncertain context stop repetition. The
host interval is not a DESQview scheduling guarantee. Manual ticks also work
at qualified single-CPU machine stops. No persistent unattended writer starts.

## Keep evidence scoped

Automatic session tracking supplies its own captures and registry events.
Use the explicit workflow below when recording a separately declared relation
or qualifying a selected manual snapshot; it is not a required setup step for
the automatic path.

The persisted runtime mapping registry can keep separate task incarnations,
bounded source-object relationships, aliases and map/restore events. Start with
`runtime-objects` and `runtime-task-start`; direct `runtime-map` evidence is
caller-recorded, not live authenticated. `runtime-map-snapshot` can check a
local retained snapshot extent without treating its caller task label as a
kernel allocation identity. Register the task with the observed capture epoch,
then take the qualifying new snapshot; old captures cannot qualify a fresh
incarnation. Query historical relations with `runtime-mappings`,
`runtime-resolve` and `runtime-mapping-events`. Reused application numbers do not
reuse an incarnation. A checkpoint restore creates fresh registry lifetimes and
does not restore guest state. See source documentation `docs/runtime-mappings.md`.

Separate configured image, parsed report, verified helper-ready stop, original
kernel instruction witness and complete native environment qualification.
The helper observes its own task. A menu application number is reusable, and a
virtual screen pointer can change with mapping. Original GW versions that
detect DESQview and refuse to run have not become compatible because fDisBull
can cooperate. Keep decrypted captures and vendor files private; publish only
authored source, hashes, semantic findings and sanitized receipts.
