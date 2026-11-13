# Protected-mode original-source admission on QEMU-DOS

`QemuDOSProcessSession.dos_source_admit` records a fresh stopped LE source view
for an original DOS carrier. It keeps the initial COM/MZ EXEC binding and all
existing control/checkpoint formats intact. DOSBox-X remains default; select
`backend="qemu-dos"` explicitly. This is source-byte admission, not a completed
protected-mode debugger or a general DOS compatibility claim.

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

## Lifetime and existing features

The receipt always records `lifetime_qualified: false` and
`live_mapping_installed: false`. It does not replace `_process.source_mapping`,
attach a selector to every byte, or certify continued task/process ownership.
Call again after execution, mutation, restore or owner replacement.

Existing real-mode source traces keep their format and explicit protected-mode
boundary. Source-addressed layer/hook/redirect admission keeps its existing MZ
ownership rules. A successful stopped LE observation does not authorize those
operations in a new namespace. Existing full checkpoint and experiment/undo
recovery formats are unchanged; this receipt does not establish capture or
restore of an LE binding outside their supported process scope.

The method is classified as a guest-read-only observation by history and
selected-undo guards. It neither invalidates those histories nor grants resume
from frozen partial state. Separate automatic tracking dependencies use the
persistent runtime object/task registry; their recorded relationships and
provider lifetime claims remain distinct from this stricter stopped admission.

## Original target evidence and next boundary

The local private Ultimate Doom witness uses the untouched original EXE/WAD,
the existing MZ launch path and a caller-owned FreeDOS C:/D: directory workspace.
It reaches the title screen on the retained QEMU 10.0.13 candidate and admits
the stopped protected32 code window, entry window, initialized data witness and
symbolic bridge. No prior DOSBox runtime placement is supplied. Original inputs,
the FDB/CAS and native screenshots stay private.

This resolves the stopped source-admission gap. Continuous protected source
mapping, LE source traces, source-addressed hooks/layers and protected checkpoint
binding require their own consumer contracts and acceptance. The broader DOS
campaigns, gameplay/media/timing equivalence, component04 boot and historical
DOSBox startup issue remain separate gates. See the
[maintained handoff](DOS_QEMU_HANDOFF.md) for exact integrated candidate evidence
and the [reuse account](QEMU_DEBUGGER_REUSE.md) for the dependency boundary.
