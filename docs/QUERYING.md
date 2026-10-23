# Current state and address queries

Use `fdisbull analysis-status project.fdb` for the current persisted queue state. `status`, disassembly JSON and new image exports also include it. Historical `analyze` receipts describe their own bounded call; their `stable: false` fields do not override a later completed run.

For the delivered DinoPark snapshot, all **426 seeds are admitted**, pending code/data/seeds/segment scans are zero, and repeated analysis adds zero facts. A check of the actual 0.3 ZIP confirmed this state. `examples/dinopark-review-check.json` records the review check and the instruction at `38ff:2b94`: bytes `c4 1e c7 bf`, raw operands `bx,[0BFC7h]`. It makes no revenue, save/load or runtime-pointer claim.

Stable means a fixed point of implemented static rules. Unresolved/invalid work details can remain in `issues`; they are distinct from pending work. No static receipt proves every possible code path, actual runtime pointer value or business meaning.

## Canonical address keys

SQLite addresses are lowercase hexadecimal text padded to **16 characters**. Within that canonical representation, lexical `ORDER BY address` and comparisons/ranges preserve unsigned numeric ordering, including addresses above signed 64-bit range. `CAST(address AS INTEGER)` parses decimal text and is incorrect for these keys. Normalize query values with `f'{address:016x}'`; retain version and context filters.

```python
import sqlite3

db = sqlite3.connect('file:project.fdb?mode=ro', uri=True)
low, high = 0x10000, 0x20000
rows = db.execute(
    'SELECT context,address,bytes,mnemonic,operands FROM instructions '
    'WHERE version=? AND address>=? AND address<? ORDER BY address,context',
    (1, f'{low:016x}', f'{high:016x}'),
)
for context, address, raw, mnemonic, operands in rows:
    print(context, hex(int(address, 16)), raw, mnemonic, operands)
db.close()
```

DOS physical addresses use `segment*16+offset` under the chosen load model. `dos_edges` retains source and target CS contexts for control flow; data identities are physical. Use public `locate`, `disasm` and `xrefs` to avoid manually reconstructing these relationships. Raw instruction operands remain available alongside shared labels.

## Evidence limits

`operand_refs` records references, not a complete read-versus-write classification. `dos_constants` records supported literal word stores and their provenance, not every writer. Their absence cannot establish that an address is never written. Likewise, absence of a literal far-pointer byte pattern does not prove a DS switch: addresses can be computed, split across stores, near-relative or aliased.

Map static code and references first, then use runtime observations for behavioral questions. The Wine debugger document describes a future observation backend; no runtime observations are fabricated by the static analyzer.

## Writer evidence in schema 4

Use `memory-accesses` for width-aware read/write queries. The unchanged `operand_refs` schema remains a reference index; access effects live in `memory_refs`. To inspect persisted effects directly after `refresh-facts`:

```sql
SELECT m.context, m.source, i.bytes, i.mnemonic, i.operands,
       json_extract(m.detail, '$.access') AS access,
       json_extract(m.detail, '$.width') AS width,
       json_extract(m.detail, '$.segment_selector') AS segment,
       m.detail
FROM memory_refs AS m
JOIN instructions AS i
  ON i.version=m.version AND i.context=m.context AND i.address=m.source
WHERE m.version=1 AND json_extract(m.detail, '$.may_write')=1
ORDER BY m.source, m.context;
```

The JSON detail uses numeric physical targets and interval bounds internally; source keys use canonical hexadecimal text. Do not equate a null target with absence of a write. Indexed updates to DS:6F88 may hit DS:6F90 when BX=8 even though no exact target is stored. Bulk initialization and save-loading buffers require following pointer/length arguments across calls. The [field audit](../examples/dinopark/notes/DINOPARK_FIELD_AUDIT.md) distinguishes those candidates from resolved scalar accesses and traces the save-file prefix.

In 0.5, `dinopark-facts-receipt.json` records explicit forensic seeds that added previously missed load/save and switch-target blocks. They do not establish general jump-table recovery or complete coverage. Ordinary fallthroughs are persisted; `cfg` can independently reconstruct older omitted ones with explicit provenance.
