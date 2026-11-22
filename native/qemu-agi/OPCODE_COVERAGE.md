# AGI 2.917 native instruction descriptors

The canonical decoder in `overlay/target/agi/decode.c` describes every action
number **0 through 173** and every condition number **0 through 18**, plus
`goto` (`254`) and `if` (`255`). These are instruction facts: names, encoded
extents, typed operands, access roles, ordered conditions and local successor
edges. They do not, by themselves, implement an AGI engine or prove that a
source site executed.

There is one action descriptor table and one framing parser. There is no
second generic `arg0`/`unmodeled` table for recognized commands. Unknown action
numbers 174–253 remain rejected by this profile. The conditional framing
markers are interpreted inside `if`, not as standalone instructions.

## Profiles and admission

The three existing execution profiles retain their numeric identities and
admission rules. Adding a descriptor does not add a command to their native
execution set.

| Profile | Action commands admitted by the existing pilot | Condition evaluation |
| --- | --- | --- |
| `AGI_DECODE_SCALAR` (`0`) | 15 scalar, flag and position commands | Conditions 1–7; at most 8 predicates and 64 instruction bytes |
| `AGI_DECODE_BINDING` (`1`) | The scalar set plus 9 VIEW/actor-binding commands | Same bounded evaluator |
| `AGI_DECODE_INTENT` (`2`) | The binding set plus `draw`, `stop.cycling`, `start.cycling` | Same bounded evaluator; `draw` remains a pending host operation |
| `AGI_DECODE_RUNTIME` (`3`) | Full command **framing**, using an explicitly selected nominal dialect | Full condition framing; actual native/device support belongs to the runtime implementation |

The counts above exclude `goto` and `if`, which the existing pilots also
admit. Profile-disabled pilot commands retain their previous decode/fault
ordering. Metadata-only commands still report an unsupported-opcode fault in
pilot execution before attempting to fetch their operands. A successful
structural decode is independent of `execution_support`.

The explicit runtime profile reuses the canonical parser with the structural
bounds for both decode purposes: at most 1,024 instruction bytes, 64 predicates,
256 condition tokens and 1,024 condition operands. The raw code address space
remains at most 65,536 bytes. Native handler or device support must be declared
separately; selecting broader framing does not demonstrate any handler.

### `trace.on` has an explicit context boundary

For profiles 0–2, `trace.on` is recognized by identity but fails with
`contextual_layout`. It does not claim an instruction extent or successor.
The existing original-context contract permits an extra consumed byte when
tracing is already active; immutable raw bytes do not establish that state.

Only profile 3 selects the **nominal zero-operand** `trace.on` layout. This
matches the pinned ScummVM table and its no-op handler. It is an explicit
runtime dialect policy, not evidence that an arbitrary original interpreter's
tracing state has been recovered. Subsequent bytes remain subsequent
instructions under this policy. Pilot execution continues to reject this
command as before.

## Operand meanings

`AgiDecodedOperand.value` retains the encoded number. A variable operand is a
variable index, a flag operand a flag index, a string operand a string-slot
index, and a controller operand a controller-slot identity. No corresponding
state is read by the decoder. Resource and actor identities remain in separate
domains even when they have the same number.

The appended kinds `AGI_OPERAND_STRING` and `AGI_OPERAND_CONTROLLER` preserve
all previous enum values and the operand structure layout. String contents
and controller state are not substituted into a static record. `word` means
a 16-bit vocabulary-group identifier inside `said`; the `parsed_word_index`
of `word.to.string` is instead an 8-bit index into the current parsed input.

Access tags describe the **explicit encoded operand**, not an exhaustive
read/write set of the whole engine. For example, `lindirectv` reads the pointer
variable and writes a different variable selected at runtime. Its
`destination_pointer` operand is therefore a read, not a false write to the
pointer slot. `parse` can change parser variables and flags that do not appear
as encoded operands. Animation completion flags can be written later by
scheduler behavior. Such implicit effects need the corresponding qualified
runtime contract.

| Action range | Described domains |
| --- | --- |
| 0–17 | Return, scalar arithmetic/assignment, indirect variable access, direct/indirect flags |
| 18–29 | Room transfer, LOGIC loading/calls, picture loading/drawing/overlay/presentation |
| 30–91 | VIEW resources, animated actors, poses, priorities, updates, horizon, collision modes, cycling, motion, direction and blocking |
| 92–100 | Inventory object locations and sound resources/playback |
| 101–121 | Messages, text/screen configuration, string slots, parser input, numeric input and key/controller bindings |
| 122–144 | Picture composition, inventory/status UI, save/restore/restart/quit, RNG, input control, diagnostics and script capacity |
| 145–164 | Scan entries, repositioning, tracing metadata, positioned text, menu/controller entries and dialogue |
| 165–173 | Multiplication/division, window closing, automatic-save description, resource-script stack operations and held-key mode |

All 19 condition identities retain typed operands. Conditions 1–8 describe
scalar/flag tests; 9–10 refer to inventory objects; 11 and 16–18 refer to actor
geometry; 12 refers to a controller; 13 to key input; 14 retains its byte count
and ordered little-endian 16-bit word IDs; 15 reads two string slots. Condition
0 retains the existing `false` identity corresponding to the reference's
unknown-condition false result. Describing input predicates does not consume
input or evaluate them.

## Handler-specific distinctions

The reference's compact display-parameter letters are not a sufficient source
for every operand's meaning. The pinned handlers establish these distinctions:

| Command | Exact static distinction |
| --- | --- |
| `lindirectv`, `lindirectn` | Read the first variable as the destination pointer; do not claim the indirect destination has been resolved. |
| `rindirect` | The first encoded variable is written; the second is read as a pointer to another variable. The project retains the canonical `rindirect` spelling even though the reference display table labels opcode 10 `lindirect`. |
| `put` | Literal inventory-object ID followed by a **variable** containing the room. The reference display table says `nn`, while `cmdPut` reads the second operand with `getVar`. |
| `put.v` | Both inventory object and room are selected through variables. |
| `get.room.v` | Read a variable for the inventory-object ID, then write the destination variable. |
| `move.obj.v` | Actor is literal; x, y and step size are variables; completion flag is a direct flag index. The display table's final `v` does not match `cmdMoveObjF`. |
| `get.priority` | Actor is literal and destination is a written variable, despite the reference display table's `nn`. |
| `set.string`, `get.string` | First operand identifies a written string slot; message references remain message identities. |
| `word.to.string` | Destination string slot comes first, parsed-word index second. |
| `set.simple` | Operand identifies the string slot containing the automatic-save description. It is not a message ID or picture ID in this profile. |
| `clear.lines` | Third operand is a color selector, not a message reference. |
| `print.at.v` | Only the message operand is variable; row, column and width remain literals. |
| `set.key` | The first two bytes encode ASCII and scan-code components; the third is the controller slot, whose occurrence flag is reset by the handler. |
| `set.menu.item`, `enable.item`, `disable.item` | Controller IDs identify menu actions; they are not inventory objects. |

`set.upper.left` retains its nominal row/column arguments, but the selected
2.917 reference handler is a no-op. `trace.info` retains nominal LOGIC and
trace-window arguments, while the reference also leaves it unimplemented.
These names do not qualify original display geometry or tracing behavior.
Resource-script operations similarly do not establish a qualified save/restore
implementation merely because their operands and intent are described.

## Control flow and uncertainty

Return and room transfer have no invented local continuation. LOGIC calls
have `assumed_return` edges because a raw-code address space does not contain
the external callee or prove that it returns. Restore, restart and quit retain
`assumed_fallthrough` edges: cancellation/failure can permit continuation,
whereas successful state replacement or exit does not establish it. This is
a conservative edge, including when a particular quit operand may eliminate
the prompt.

Other named commands have their structural fallthrough edge. This establishes
the encoded next address, not successful host-service completion or preserved
guest state. GOTO displacement is signed 16-bit; IF displacement is unsigned
16-bit. Out-of-range destinations remain visible with `in_range=false`.

Truncation, unsupported commands/conditions, malformed OR/NOT framing, fetch
limits and condition budgets fail without claiming a complete instruction
extent or successor. The bounded callback only reads admitted source offsets.

## Verification

`tests/test_qemu_agi_full_descriptors.py` compiles the real `decode.c` with a
small checked-reader adapter using the system C compiler (`-std=c11 -Wall
-Wextra -Werror`). It checks all action identities and widths across the three
legacy profiles, their separate execution admission, every truncated fixed
action prefix, all condition identities, indirect/string/controller meanings,
signed/unsigned edges, unknown numbers, contextual tracing and parser bounds.
The explicit runtime profile receives a separate full-framing batch.

These are authored byte sequences and standalone C decoder checks. They run
without a QEMU build, game files or guest execution. The existing scene
discovery test now expects typed `mul.n` metadata and separately preserves its
archived `unmodeled`-record fallback test. Full QMP/runtime tests still require
their explicitly configured binaries and do not become qualified by this
standalone compilation.

Run the focused checks from the repository root:

```sh
python -m pytest -q tests/test_qemu_agi_full_descriptors.py tests/test_qemu_agi_discovery.py
```

## Sources and profile exclusions

Format widths/names retain the repository facts from
[`agi_layout.py`](../../src/fdisbull/agi_layout.py) and
[`agi_scenes.py`](../../src/fdisbull/agi_scenes.py) at commit
`1b27110bb43fe91fec5d09b4cffa7227771cb5e9`. Native parsing remains independent
of those Python decoders, including the previously qualified unsigned IF rule.

Operand facts were checked against ScummVM commit
`f7403b6efaae2f033e8abea80b3fb6bee5303369`:

- [`opcodes.cpp`](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/opcodes.cpp), blob `676ce925b2d6df3cdec60ba8512bb9f47c1571ac`.
- [`op_cmd.cpp`](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_cmd.cpp), blob `6d27452bd4cbfa09b9ca02f3d20d495ad0da9b4e`.
- [`op_test.cpp`](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_test.cpp), blob `bc843b58b1c3dfc72ade4d5f2c3b943e760d7e6b`.

Only instruction-format and operand facts informed the independently authored
descriptors and tests; reference handler implementation code is not copied.
The selected profile does not infer AGI version or platform from source bytes.
AGI1, earlier variable-width commands, AGI3 mouse/platform opcodes, Apple IIgs
opcode remapping, AGI256 `set.simple` and AGIMOUSE `push.script` extensions
remain outside this profile. A reference interpreter's compatibility
workaround is not silently added to the native contract.
