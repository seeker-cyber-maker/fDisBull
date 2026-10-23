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
