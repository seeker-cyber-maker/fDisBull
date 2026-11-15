# Choose and execute the next probe

Use this when the methodology makes sense but the next operation does not.
Read only the recipe matching the question. Once it supplies your next call,
try that call; open another reference only to resolve a specific missing fact. These examples are authored static
fixtures, not claims about a game, and never execute their target bytes.

## A small decision loop

Keep the requested outcome visible. Find its nearest missing prerequisite, name
at most two competing explanations, and choose a supported probe whose possible
results would change the next action. After a useful result, record the finding,
evidence reference and next unlocked question. After a failure, classify it
before retrying. This is a reasoning aid, not a required per-call form.

| You have | Useful next question | First probe / next branch |
| --- | --- | --- |
| A file, unknown mapping | What architecture and address space am I querying? | `identify`/`inspect` on the binary; `status` on an existing FDB; import only with a justified image/mode. Recipe 1. |
| An FDB but empty disassembly | Is the address wrong, not yet decoded, or outside retained bytes? | Read `status PROJECT` for mapping and `analysis-status`; query the mapped entry, then bounded `analyze` if needed. Empty output is not proof of empty code. |
| A few decoded instructions | What data and branches affect the requested output? | Follow those operands/xrefs; separate concrete inputs from unknown runtime state. Stop once the requested claim is supported. |
| A candidate field/table | Is this a file record, mapped constant or live mutable state? | Verify provenance/mapping, then bounded bytes and a candidate layout. Recipe 2 and [types/addresses](analysis-types.md). |
| A live value changing | Which candidate changes with the relevant action rather than ordinary time? | Baseline versus one controlled action; narrow candidates, then watch a writer. Use the memory-search guide for exact backend calls. |
| A meaningful string | Is it displayed text, a lookup key or unreachable data? | Find references and inspect the consumer; do not infer behavior from wording alone. |
| An unsupported tool result | Is the target unsupported or only this operation/mode? | Check the exact error and one required capability; use an existing compatible alternative or return a bounded partial result. |

Use the established executable and matching Python environment. The examples
assume its `fdisbull` command is on PATH; do not silently use another install.
Create a fresh scratch directory for each recipe so an old FDB is not overwritten.
For unknown flags consult that command's `--help`, not an invented API.

## Recipe 1: get from bytes to one supported output claim

Question: what value does this small entry return, assuming it is entered in
64-bit x86 mode? First discover its mapping and instructions; runtime execution
is not necessary to answer this bounded arithmetic question.

```sh
python - <<'PY'
from pathlib import Path
Path('entry.bin').write_bytes(bytes.fromhex('b80500000083c007c3'))
PY
fdisbull import entry.bin entry.fdb --arch x86 --bits 64 --base 0x1000
fdisbull status entry.fdb
fdisbull analyze entry.fdb --max-instructions 32
fdisbull analysis-status entry.fdb
fdisbull disasm entry.fdb --address 0x1000 --lines 4
```

The status response should report `entry: "0x1000"`, `arch: "x86"`, `bits: 64`
and a loader mapping from file offset 0 to virtual address 0x1000. Use `status`
for a project: `inspect` parses an input file and would inspect the SQLite FDB
as raw file contents rather than report its analysis mapping.

The import selects a raw-image interpretation explicitly; the filename does not
establish architecture. The disassembly should contain `mov eax,5`, `add eax,7`
and `ret` (formatting may vary). The entry's EAX result is therefore 12, subject
to the stated entry/mode assumption. This is a static derived result, not a
recorded run or proof of a caller's behavior.

**Deliberately take a wrong turn, then recover:**

```sh
fdisbull disasm entry.fdb --address 0 --lines 4
```

No instruction at address zero does not contradict the previous result. File
offset zero maps to 0x1000 here. Use `status entry.fdb` and the import's recorded base to
recover the right address; query 0x1000 again. Do not reimport at zero merely to
make the query succeed. For raw images, address = base + file offset. Other
formats use their loader's mappings; this addition is not a universal rule.

Branches:
- No stored instructions at the mapped entry: check analysis status and run a
  small analysis budget before deciding the bytes are data.
- Analysis stopped on a budget: resume/increase only enough for the relevant
  path; an unfinished queue is not a stable fixed point.
- An instruction depends on an unknown register, memory, branch or mode: name
  that missing input and obtain it or keep the output conditional. Do not borrow
  the example's answer for another target.
- Decoder rejects a legal opcode: identify the architecture/mode and whether
  this is a specialized subset. Check an available general decoder before
  building one. A local decode failure is not invalid target code.

Local stopping point: the requested output and its input assumptions are
explained by the relevant instructions. Do not build a complete harness merely
to report this constant. If live behavior was requested, this is an intermediate
result and the next prerequisite is a compatible execution backend.

## Recipe 2: decode a table without inventing live state

Question: what do these two records contain? Names are neutral candidate labels;
this fixture does not establish gameplay meaning or a runtime loader.

```sh
python - <<'PY'
import json
from pathlib import Path
Path('stub.bin').write_bytes(bytes.fromhex('90c3'))
Path('records.dat').write_bytes(bytes.fromhex('0300020007000400'))
Path('record.json').write_text(json.dumps({'kind':'struct','size':4,'fields':[
    {'name':'count','offset':0,'type':'u16'},
    {'name':'flags','offset':2,'type':'u16'}]}))
Path('records.json').write_text(json.dumps({'kind':'array','element':'Record','count':2}))
PY
fdisbull import stub.bin records.fdb --arch x86 --bits 64 --base 0x1000
fdisbull attach-file records.fdb records.dat --name records.dat --kind resource
fdisbull file-bytes records.fdb records.dat --offset 0 --size 8
fdisbull define-type records.fdb Record record.json
fdisbull define-type records.fdb Records records.json
fdisbull apply-file-type records.fdb records.dat Records --offset 0 --name records
fdisbull file-data records.fdb records.dat --offset 0 --max-items 16
```

The raw bytes are `0300020007000400`. Typed leaves should report count=3,
flags=2, count=7, flags=4 at offsets 0,2,4,6. `03 00` means 3 under this
little-endian u16 layout, not 768; neither interpretation supplies units or
proves what the producer intended. Count values and bit-flag names remain
interpretations until qualified by the file format or its consumer.

**Wrong starting offset, with recovery:**

```sh
fdisbull file-data records.fdb records.dat --offset 1 --max-items 16
```

A typed query selects a binding's start, not every interior byte. An error or
missing binding at offset 1 does not mean the resource is corrupt. Check
`file-bytes` and the known binding at offset 0, then query that start. Preserve
the failed attempt; do not create overlapping bindings to conceal it.

Branches:
- Too few retained bytes: inspect the actual file size/layout and bound the
  proposed record; do not pad the original with zeros.
- Values look implausible: compare original bytes, widths, signedness and
  consumer behavior before changing names or declaring corruption.
- You need live player state: a file attachment is not process memory. Establish
  a loader correspondence or read a live state through the matching backend.
- You need the writer: inspect candidate code accesses only after establishing
  the native address. A file offset is not that native address.

Local stopping point: bytes and proposed field interpretation are reproducible.
For a semantic claim, the next step is to inspect the actual reader/writer or
compare controlled runtime changes. Do not call a successful type binding proof.

When the operation succeeds but some cases contradict the explanation, use
[contradiction recovery](contradiction-recovery.md). A tool error and a wrong
interpretation need different recovery paths.

## Failure recovery and escalation

Preserve the exact error and useful outputs. Change one hypothesis or parameter
that could explain the failure; do not repeat an identical low-information probe.
If the tool is missing, distinguish wrong install from unsupported capability.
If a trace cannot observe a boundary, keep observer failure separate from target
failure. Existing observations may still answer a narrower question.

When a required prerequisite remains unavailable after a bounded discriminator,
return the supported partial finding, the missing prerequisite, and the next
specific action or question needed. Continue independent useful work. A new
backend, adapter or replacement implementation is a scope decision, not the
automatic response to every failure. See [analysis approach](analysis-approach.md)
for higher-level choices and [workflows](workflows.md) for command families.
