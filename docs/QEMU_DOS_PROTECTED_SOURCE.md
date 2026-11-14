# Protected-mode original-source admission and binding on QEMU-DOS

`QemuDOSProcessSession.dos_source_admit` records a fresh stopped LE source view
for an original DOS carrier. It keeps the initial COM/MZ EXEC binding and all
existing control/checkpoint formats intact. A separate `dos_source_bind`
operation installs an owned recipe for fresh protected32 source observations
and bounded traces. DOSBox-X remains default and retained; select
`backend="qemu-dos"` explicitly. This slice uses local checks, with no CI or
default switch. Its binding/trace implementation has host checks; native
qualification belongs to exact candidate receipts rather than this contract.
Neither operation establishes
general protected-mode or DOS compatibility.

## Public operation

```python
admission = debug.dos_source_admit(
    expected_source_sha256=original_executable_sha256,
    max_compare_bytes=524288,
    max_scan_bytes=16777216,
    timeout_ms=10000,
)
project.debug_export(admission['artifact'], '/private/protected-source.json')
```

The foreground JSON method is `debug-dos-source-admit`, with the selected `run`
and the same optional fields, plus `name` for the private artifact. Capability
`dos_protected_source_admission` identifies the native DOS session operation.
Source/version pins, caller parameters and current machine context are checked.
An original MZ project stays MZ even when it contains an LE application. LE
object IDs such as `le:1` are an additional preferred-address namespace; they
are not ordinary MZ project instruction addresses.

The reply has format `fdisbull-qemu-dos-le-admission-1`, `status` (`admitted` or
`unmatched`), source/version/run/epoch identities, an artifact ID/hash/size, and
a bounded observation. It returns no program instruction bytes. The private
artifact also records producer hashes, GDT identity and the captured readback
plan and full fixup list. The reply summarizes the global exclusions by count;
large observations also truncate span detail and set `reply_truncated`. Export
the artifact for the full evidence. Export and inspect it after closing/reopening the FDB using the existing
artifact interfaces. A saved artifact is historical evidence, not a connection
to its ended native owner.

## Admission and comparison

The operation requires one stopped, observed protected32 CPU, enabled A20,
disabled paging, and agreement between GDB and the observed CS cache. It
refuses active RAM/fetch overlays and cooperating task-private views. GDT
selector index, RPL/DPL/TI policy, executable/present/default32 attributes,
hidden base/limit and the complete 96-byte current extent are checked.
LDT and paged observations remain unsupported in this first operation.

All candidate reads must lie in conventional or extended physical RAM. The
adapter compares physical and linear reads, then rechecks every captured extent
and the CPU/GDT context before publication. No guest execution, code patch,
input dispatch or register write is performed. A single deadline covers lock
admission, source parsing, all reads, revalidation and publication. The comparison
budget counts matcher reads; the separately bounded GDT (at most 64 KiB),
physical/linear copies and stability rechecks add transport reads. Source scans
are bounded independently. Ambiguity, invalid context, corruption and budget
exhaustion refuse rather than publishing a partial admitted result.

The matcher follows the reviewed Doom candidate's bounded evidence strategy:

- One unique current 96-byte code window locates the executable object while
  excluding declared loader-fixup bytes. Its runtime base follows from the
  observed CS-relative address and source offset.
- The declared entry window is compared when applicable; otherwise the current
  window is retained. Matching these windows does not qualify the full object.
- Eight unique offset32 sites must agree on a data-object base, supported by
  an unchanged 32-byte initialized-data witness.
- A bounded 16-bit bridge can match an executable GDT descriptor. Symbolic
  offset16 bytes are excluded. Bridge execution and the excluded operand's
  selector semantics remain unqualified.

The explicit runtime parser follows declared LE, MZ→LE, or MZ→BW→inner MZ→LE
links and preserves original-file coordinates. It does not search the file for
a plausible signature. Ordinary `load_le` static admission remains unchanged;
mixed-width/symbolic runtime parsing is a separate opt-in path.

## Historical admission and explicit source binding

The stopped admission receipt always records `lifetime_qualified: false` and
`live_mapping_installed: false`. It does not replace `_process.source_mapping`,
attach a selector to every byte, or certify continued task/process ownership.
Call again after execution, mutation, restore or owner replacement.

To continue observing a relation, bind explicitly at an eligible stopped CPU:

```python
bound = debug.dos_source_bind(
    expected_source_sha256=original_executable_sha256,
    max_compare_bytes=524288,
    max_scan_bytes=16777216,
    timeout_ms=10000,
)
status = debug.dos_source_binding()
current = debug.dos_source_binding(refresh=True, timeout_ms=10000)
project.debug_export(bound['artifact']['artifact'], '/private/le-binding.json')
```

`dos_source_bind` makes a new stopped admission and derives its recipe from
that evidence. It does not accept a historical artifact as current authority.
Its keyword arguments and defaults match admission, with
`name='le-source-binding.json'`. The JSON routes are `debug-dos-source-bind`,
`debug-dos-source-binding` and `debug-dos-source-unbind`, each with the owned
`run`. Capability `dos_protected_source_binding` describes the source relation.
`dos_source_binding(refresh=False)` reports the handle and last observation;
`refresh=True` performs fresh validation. `dos_source_unbind()` retires and
removes the handle without executing or changing guest controls.

The binding artifact has format `fdisbull-qemu-dos-le-binding-1`. It contains
the immutable source/version/run/capture-epoch recipe, initial admission,
proven object placements, GDT material and producer identities. `binding_id`
identifies this owned recipe; it is not an OS task ID. Reopening/exporting an
artifact does not reinstall a live handle or reconnect its owner.

## Revalidated endpoints and instruction boundaries

Current source authority is withdrawn before an owned `run` or `step`.
An ordinary run has an unobserved interval: a successful fresh stop observation
establishes an endpoint, reported as `execution_coverage='stopped-endpoints'`.
It does not assert which instructions ran between endpoints. Stepping and
source tracing use `stepped-boundaries`, validating each retained stopped
instruction boundary. A GDB step remains a stop interval, including possible
fault or partial REP progress; it is not an instruction-retirement certificate.

Public states include `qualified-stopped`, `pending-owned-execution`,
`out-of-scope` and `retired`, or `unbound` when no handle is installed. A
`live` summary describes the qualified stopped source relation, not running
ownership or an allocation lifetime. Failed validation withdraws old authority.
A later explicit fresh query can recover an out-of-scope relation if its
recipe still qualifies; a retired recipe requires a new explicit bind.

Source refresh shares a bounded run/step's remaining allowance. If the budget
is exhausted before fresh source I/O, source authority is withdrawn and the
known native stop is retained. This does not create a new ten-second source
allowance or invalidate an otherwise known stopped guest. An actual source
transport failure follows the existing native uncertainty/cleanup contract;
inspect the retained native stop in `error.result`. Trace capture retains its
shared deadline for observation, stepping and persistence.

Every instruction observation rechecks source/version/producer and owner/epoch
identity, protected32 CS cache and GDT agreement, unchanged code anchors and
relocation-pointer witnesses. Physical and linear bytes must agree, and the
stopped read must remain stable before publication. These checks qualify the
current instruction, not every byte in a located object or OS ownership of it.

Admission masks declared fixup bytes while locating a candidate. Instruction
qualification is stricter: the complete decoded instruction must match its
preferred-image canonical bytes after each supported runtime relocation is
accounted for. A whole internal offset32 fixup needs a proved target-object
placement and matching runtime operand. A straddling fixup, symbolic offset16,
unsupported or unproved relocation, altered instruction or incomplete source
extent ends source qualification. The canonical full-instruction hash and the
observed runtime-byte hash remain distinct.

## Capture protected source traces

```python
trace = debug.trace('protected-count.json', count=32, bits=32)
stopped = debug.trace_until(
    {'kind': 'register', 'register': 'eax', 'equals': 7},
    source_view='embedded-le', max_steps=64, timeout_ms=10000,
)
```

`trace` and `trace_until` take `source_view=None` by default. An installed LE
handle selects `embedded-le`; otherwise the existing initial-DOS path is used.
Explicit `source_view='embedded-le'` requires a bound recipe and never binds
implicitly. `source_view='initial-dos'` overrides the handle and retains the
existing real16 COM/MZ rules; it cannot turn protected selectors into DOS
paragraph addresses. An invalid or retired LE handle does not trigger fallback.
The selected view's explicit `bits`, when supplied to `trace`, must be 32 for
LE or 16 for initial DOS.

The existing `debug-trace`, `debug-trace-until`, `trace` and `trace-until` script
routes carry this view. Bind through the public session operation before the
script. Source-view values and trace-until descriptors are validated during
whole-script preflight, before an earlier write can execute. Queued input
actions remain refused for native trace-until; dispatch input with a separate
bounded run, then choose a new stopped capture boundary.

The count route retains N pre-step events for N attempts and inspects its final
endpoint separately. Trace-until includes the initial boundary and stops on a
qualified predicate, source boundary, foreign stop or budget. An unqualified
LE endpoint cannot satisfy a source predicate or authorize another step.
LE regions must be explicitly declared in runtime `linear` space; MZ project
regions are not reused. Limits remain 10,000 retained events, 8 KiB per stopped
observation and 16 MiB per trace, with finite host and step budgets.

LE captures use `fdisbull-qemu-dos-le-capture-1` with source scope
`owned-revalidated-LE-stop-sequence`, a binding ID and the actual step policy.
They retain the recipe and binding artifact identity plus the GDT once in
capture metadata; events carry CPU and readback witnesses tied to that GDT.
No event asserts retirement. Existing initial-DOS capture formats remain
unchanged.

Source locations use `source_view='embedded-le'`, application SHA-256, object
ID/index, object offset and preferred LE address. Event-search sites use
`space='embedded-le'`, an object-relative `address` and the canonical instruction
hash. These identities can be compared across proved runtime placements;
their preferred addresses are not MZ project addresses or live selectors.
LE event `project_address` and `task_id` remain unset. Cold trace/query/search
consumers recheck linked binding receipts and original source/whole-instruction
proofs rather than trusting a qualification flag. Source boundaries keep their
observed runtime PC while exposing no qualified source site.

## Lifecycle and existing features

Asynchronous resume, unmonitored mutation, source/version/producer drift,
owner replacement and capture-epoch changes retire source authority. Register
or memory edits and supported restore, history/frame rewind, experiment
recovery or selected-undo recovery paths retire the handle before changing
state. Bind again explicitly after a supported recovery. Existing checkpoint
formats do not capture or restore this LE handle.

Active RAM/fetch layers and task-private views remain outside LE source
observation admission. Existing layer/hook/redirect definitions and controls
keep their supported address/ownership rules. Neither a stopped admission nor
a source binding authorizes LE source-addressed layers, hooks, redirects,
checkpoints or task-private control. The source recipe does not replace or
clear those systems. Trials, histories, selected undo, frame ownership, native
IRQs and existing checkpoint formats retain their separate contracts.

Source admission, bind/status/unbind are classified as guest-read-only by
history and selected-undo guards. They do not invalidate those histories or
grant resume from frozen partial state; actual trace stepping retains the
existing execution guards. Separate automatic tracking dependencies use the
persistent runtime object/task registry; their recorded relationships and
provider lifetime claims remain distinct from this stricter stopped admission.

## Earlier target evidence and current qualification boundary

The earlier local private Ultimate Doom admission witness used the untouched original EXE/WAD,
the existing MZ launch path and a caller-owned FreeDOS C:/D: directory workspace.
It reached the title screen on the retained QEMU 10.0.13 candidate and admitted
the stopped protected32 code window, entry window, initialized data witness and
symbolic bridge. No prior DOSBox runtime placement is supplied. Original inputs,
the FDB/CAS and native screenshots stay private.

That result establishes stopped admission only. The current owned recipe,
per-step source qualification and cold LE trace/search consumers have host
checks; their native qualification belongs to exact candidate receipts. Source-addressed
LE hooks/layers and protected checkpoint binding remain separate acceptance
work. The broader DOS
campaigns, gameplay/media/timing equivalence, component04 boot and historical
DOSBox startup issue remain separate gates. See the
[maintained handoff](DOS_QEMU_HANDOFF.md) for exact integrated candidate evidence
and the [reuse account](QEMU_DEBUGGER_REUSE.md) for the dependency boundary.
