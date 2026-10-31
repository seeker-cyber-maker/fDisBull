# Civ city routine: static caller and field trace

Status: **static evidence for the pinned bytes**; runtime reachability remains unproven.

Analyzer: `examples/civ/civ_city_trace.py`
Regression: `tests/test_civ_city_trace.py`

## Question

Does `R:0D12:0045` (Civ64 notation) really contain the city routine, which code
calls it, and does the routine itself perform the `townbuf` reset the
city-production contract depends on?

## Identity

| Item | Value |
|---|---|
| Input | unpacked DOS root `CIV_UNP.EXE` |
| SHA-256 | `aa63aa396cfa62519b131ee6c0a231bed02bb9aefce26b955608b5815a569e57` |
| Bytes | 340,791 |
| Root load module | 203,584 bytes after a 10,128-byte header; declared root file end 213,712 |
| Overlay tail | 127,079 bytes (not linearly mapped as code) |

All addresses below are in the root load module (`R`), which fDisBull maps at
runtime segment `0x1000`. `R:0D12:0045` is linear `0xD165`, file offset 63,733.
Two coordinate kinds appear and are not interchangeable: **module-linear**
addresses (the city routine: `0xD165`, `0xD244`) and **offsets inside module
segment `0A99`** for the input-loop key dispatch, which is a separate 64K
segment (`runtime 1A99`). The dispatch section gives the exact conversion and
the fDisBull `1D12`-window representation of the same bytes.

## Entry proof

```text
d165  55              push bp
d166  8bec            mov bp, sp
d168  81ec0c01        sub sp, 0x10c
d16c  57              push di
d16d  56              push si
d16e  b81c00          mov ax, 0x1c      ; sizeof(struct city)
d171  f76e06          imul word ptr [bp + 6]
d174  8bd8            mov bx, ax
d176  80bff270ff      cmp byte ptr [bx + 0x70f2], 0xff   ; townbuf[city].status
```

`0x70ec` is the recovered `townbuf` base and `0x1c` the 28-byte record, so
`[bx + 0x70f2]` is `townbuf[city].status`. The routine therefore addresses the
same city record model the UIL slice uses. The name `city_process` remains a
source-backed label applied through civd, not a linker symbol.

Field references inside the `0x0D12` segment window:

| Field | Offset | References |
|---|---:|---:|
| `buildings` | `0x00` | 45 |
| `status` | `0x06` | 61 |
| `size` | `0x07` | 85 |
| `production` | `0x09` | 97 |
| `owner` | `0x0B` | 55 |
| `food_box` | `0x0C` | 6 |
| `shield_box` | `0x0E` | 29 |
| `workers` | `0x10` | 11 |

## Shield reset block

```text
d244  81bffa70e703    cmp word ptr [bx + 0x70fa], 0x3e7
d24a  7e03            jle d24f
d24c  e91200          jmp d261
d24f  b81c00          mov ax, 0x1c
d252  f76e06          imul word ptr [bp + 6]
d255  8bd8            mov bx, ax
d257  83bffa7000      cmp word ptr [bx + 0x70fa], 0
d25c  7c03            jl d261
d25e  e90e00          jmp d26f
d261  b81c00          mov ax, 0x1c
d264  f76e06          imul word ptr [bp + 6]
d267  8bd8            mov bx, ax
d269  c787fa700000    mov word ptr [bx + 0x70fa], 0
```

`0x70fa` is `townbuf[city].shield_box`. Both comparisons are **signed**
(`jle`, `jl`), and the store is zero. This is the byte-level form of:

```c
if (shield_box > 999 || shield_box < 0)
    shield_box = 0;
```

The UDC module's `sanitized` precondition corresponds exactly to this block;
the module deliberately does not re-encode the comparison itself.

## Callers

The scan accepts `9A`/`EA` instructions whose operand is `0045:0D12`. A root
hit must also appear in the MZ relocation table, because a real far reference
to another code segment is relocated at load; relocation addresses are normalized as segment * 16 + offset. No unmatched
root target patterns remain in this image. The previous offset-only filter
incorrectly dropped the capunit call whose relocation is 1000:4B2A.

| Runtime linear | Root offset | Caller function (local) | Mode evidence | Interpretation |
|---:|---:|---:|---|---|
| `0x1AE31` | `0xAE31` | `0xADE6` | `sub ax,ax; push ax; push ax` → mode `0` | Per-city turn pass |
| `0x1AE73` | `0xAE73` | `0xADE6` | `mov ax,1` after `cmp [0xB1E8],0` → mode `1` | Same function, display branch |
| `0x1B1E3` | `0xB1E3` | `0xB1CA` | `mov ax,1; cwd; push dx; push ax` → mode `1` | Small display wrapper |
| `0x1B21F` | `0xB21F` | `0xB201` | `mov ax,FFFFh; push ax` → mode `-1` | `find_slot` recalculation |
| `0x24B27` | `0x14B27` | `0x14590` | `mov ax,1; cwd; push dx; push ax` → mode `1` | `capunit` display caller |

Caller `0xADE6` matches `civ_economy()` in civd `ECONOMY.C` structurally:

```text
for (i = 0; i < 0x80; i++)                    ; 128 cities
  if (townbuf[i].status != 0xff)              ; free record
     && townbuf[i].owner == civ)              ; [si + 0x70f7] == [bp + 6]
     city_process(i, 0);                      ; push 0,0,i
     ...
     if (show_city_display) city_process(i, 1);
```

The owner comparison uses field `0x0B` (`0x70f7`), the loop bound is `0x80`, and
the status test is `0xFF`, all matching the recorded source. The display call is
guarded by `cmp word ptr [0xB1E8], 0`, consistent with the
`show_city_display` global.

Five resident target sites are retained, including the independently checked
compiler/map boundary for capunit. Argument recovery is a local constant slice,
not an all-path proof. INT 3F dispatch descriptors prevent naive linear decoding
of capunit; its complete reviewed MSC call tail supplies the mode evidence.

Eleven further far-call byte patterns to `0045:0D12` exist in the overlay tail
(`0x34C4A` … `0x4FB9A`). Their overlay fixups and logical mappings are not decoded, so these remain
file-offset candidates. The analyzer emits no invented runtime address, caller
function or mode value for them.

## BUY guard, price and commit

The city screen's input loop reads a key at `0x71F1`
(`lcall 1D05:0AC9`) and dispatches on it with literal compares. The `b` branch
starts at `0x737D`:

```text
737d  83be10ff62      cmp word [bp-0xf0], 0x62    ; 'b'
7382  7403            je 0x7387
7384  e98902          jmp 0x7610                   ; next key
```

### Cost lookup and price (`0x7387..0x7470`)

The sign of the production byte at `city + 0x70F5` selects the kind. Both
tables hold the shield cost **divided by ten** in the word at record offset
`+0x18`, and both reads are `DS`-relative:

```text
7387  b81c00        mov ax, 0x1c
738a  f76e06        imul word [bp+6]      ; bx = 28 * city
738f  80bff57000    cmp byte [bx+0x70f5], 0
7394  7d03          jge 0x7399             ; production >= 0 -> unit
7396  e95d00        jmp 0x73f6             ; production <  0 -> building
7399  b81c00        mov ax, 0x1c           ; unit branch
739c  f76e06        imul word [bp+6]
739f  8bd8          mov bx, ax
73a1  b022          mov al, 0x22
73a3  f6aff570      imul byte [bx+0x70f5]  ; 34 * unit id
73a7  8bd8          mov bx, ax
73a9  8b874211      mov ax, [bx+0x1142]    ; unit table word +0x18 = cost/10
73f6  b81c00        mov ax, 0x1c           ; building branch
73fe  8a87f570      mov al, [bx+0x70f5]
7402  98            cwde
7403  f7d8          neg ax                 ; k = -production
7405  b91e00        mov cx, 0x1e
7408  f7e9          imul cx                ; 30 * k
740c  8b87b20b      mov ax, [bx+0xbb2]     ; improvement word +0x18 = cost/10
```

The unit table starts at `DS:0x112A` (34-byte records, name at `+0`) and its
`+0x18` words are `4,1,2,2,3,3,2,4,4,4,4,8` for Settlers, Militia, Phalanx,
Legion, Musketeers, Riflemen, Cavalry, Knights, Catapult, Cannon, Chariot,
Armor — Civ1's unit shield costs 40, 10, 20, 20, 30, 30, 20, 40, 40, 40, 40,
80 divided by ten. The improvement records are named from `DS:0xB9A + 0x1E*k`
(Palace at `k = 1`, `0xBB8`) and the same `+0x18` word is their cost/10
(Palace 20, Barracks 4, Granary 6, Temple 4, Marketplace 8, Library 8).

Then the shared peak, through `ClampInt`:

```text
73c1  b80a00        mov ax, 0x0a
73c4  f7aefafe      imul word [bp-0x106]  ; 10 * cost10
73c8  2b87fa70      sub ax, [bx+0x70fa]   ; - shield_box -> base
73cc  50            push ax               ; value
73cd  9a7c00c41d    lcall 1DC4:007C       ; ClampInt(base, 0, 999)
73d5  898618ff      mov [bp-0xe8], ax
```

`R:1DC4:007C` is `ClampInt` (the port's `11C8:0063`, `docs/dos/CORRESPONDENCE.md
line 366`; signed clamp, `docs/dos/TIMING.md` line 510), called here with
bounds 0 and 999. So `base = ClampInt(10*cost10 - shield_box, 0, 999)`.

The two kinds then price differently:

```text
73d9  ...                   ; unit
73dd  f7ae18ff    imul word [bp-0xe8]   ; base * base
73e1  99          cdq                   ; discard the product's high word
73e2  b91400      mov cx, 0x14
73e5  f7f9        idiv cx               ; i16(base*base) / 20
73e7  b8...       mov cx, [bp-0xe8]
73eb  d1e1        shl cx, 1             ; 2 * base
73ed  03c1        add ax, cx
73ef  898618ff    mov [bp-0xe8], ax     ; unit price = 2b + b*b/20
73f3  e96300      jmp 0x7459            ; skips the building-only doubling
7430  9a7c00c41d  lcall 1DC4:007C       ; building: ClampInt(base, 0, 999)
7435  83c406      add sp, 6
7438  d1e0        shl ax, 1             ; building price = 2b
743a  898618ff    mov [bp-0xe8], ax
7446  8a87f570    mov al, [bx+0x70f5]   ; building-only tail
744b  f7d8        neg ax
744d  3d1500      cmp ax, 0x15
7450  7f03        jg 0x7455
7455  d1a618ff    shl word [bp-0xe8], 1 ; double when k > 21
7459  ...
7461  83bffa7000  cmp word [bx+0x70fa], 0
7466  7403        je 0x746b
746b  d1a618ff    shl word [bp-0xe8], 1 ; double when shield_box == 0
```

So a unit costs `2b + i16(b*b)/20` and a building `2b`, the unit branch jumps
over the `k > 21` doubling, and both double when the box is empty. The `cdq`
at `0x73E1` is what makes the square a wrapping 16-bit value: cost code 30
gives `b = 300`, `300*300 mod 65536 = 24464`, `24464/20 = 1223`, price
`600 + 1223 = 1823`, doubled to 3646 for an empty box.

`ClampInt` is why a city that has already stored more shields than the item
costs buys it for zero: `base` clamps to 0 and the price follows.

The box text is built at `0x746F..0x7560` (cost, item name, treasury, then
"CIVIL DISORDER" when status bit 1 is set on an improvement), and
`0x1EA8:1F6A`/`0x1EA8:1E22` append the decimal fields.

### Guard (`0x75D2..0x75E2`)

After "Yes" (`0x75CA` returns zero), the source compares treasury with the
price and skips the commit when gold is short:

```text
75d2  8b1e4865        mov bx, [0x6548]
75d6  d1e3            shl bx, 1
75d8  8b8618ff        mov ax, [bp-0xe8]
75dc  3987d6b1        cmp [bx-0x4e2a], ax
75e0  7d03            jge 0x75e5
75e2  e92300          jmp 0x7608
```

### Commit (`0x75E5..0x7608`)

```text
75e5  b80a00          mov ax, 0x0a
75e8  f7aefafe        imul word [bp-0x106]  ; 10 * item_cost
75ec  8bc8            mov cx, ax
75f6  898ffa70        mov [bx+0x70fa], cx   ; shield box := full cost
75fe  d1e3            shl bx, 1
7604  2987d6b1        sub [bx-0x4e2a], ax   ; treasury -= price
```

### Key dispatch

The input loop reads a word key (`lcall 1D05:0AC9`) into `[bp-0xF0]` and
compares it against literals in one chain: each site is
`cmp word [bp-0xF0], imm8` followed by `je <handler>` / `jmp <next compare>`.
`examples/civ/civ_city_trace.py:key_dispatch` enumerates all fifteen sites from
the unpacked root and labels each one.

**Address identity.** The offsets below are offsets inside module segment
`0A99` (runtime `1A99` with the default `0x1000` load paragraph), so
`runtime linear = 0x1A990 + offset`. fDisBull's MZ paragraph map attributes the
same bytes to the `1D12` window; that representation is `offset + 0xA990`
module linear, `+0x10000` runtime linear. `0A99:7785` is therefore
`1D12:4FF5`, linear `0x22115`. The city-record routine addresses elsewhere in
this document (`0xD165`, `0xD244`) are module-linear inside segment `0xD12`;
do not add `0xA990` to those.

| key | site (`0A99`) | module linear | action | basis |
|---|---|---|---|---|
| `A` | `0x724F` | `0x11BDF` | `status ^= 0x10`; when the bit is set, `find_slot` and production replacement | binary-static |
| (sentinel) | `0x734A` | `0x11CDA` | compare against `-1`; falls through to the non-key path | binary-static |
| `b` | `0x737D` | `0x11D0D` | buy prompt, price guard and commit (above) | binary-static |
| `c` | `0x7626` | `0x11FB6` | `lcall 0ADE:0421(city, owner)` - the production chooser; result stored at `city+0x70F5`, then the loop exits | binary-static |
| `i` | `0x76C7` | `0x12057` | sets view mode `0` (`INFO`) | binary-static |
| `h` | `0x76DA` | `0x1206A` | sets view mode `1` (`HAPPY`) | binary-static |
| `m` | `0x76ED` | `0x1207D` | sets view mode `2` (`MAP`) | binary-static |
| `v` | `0x7700` | `0x12090` | sets view mode `3`, then `0x7756`: `push -1; push city; int 3F` entry `0x0013` - the city-view overlay call | binary-static |
| `a` | `0x7785` | `0x12115` | unit-list cursor (below) | binary-static |
| `s` | `0x799E` | `0x1232E` | sell-building cursor (below) | binary-static |
| `1`..`9` | `0x7ABE`, `0x7AC8` | `0x1244E`, `0x12458` | specialist slot `key - '1'`; requires `size >= 5`, else the specialist warning | binary-static |
| `p` | `0x7B58` | `0x124E8` | city-radius tile cursor: eight-direction move, radius/visibility guard, Enter/Space toggles the worker | binary-static (linear decode; analyzer traversal stops at the far key read) |
| `M` | `0x7DCF` | `0x1275F` | building-page flag: `flag & 2` gate, then `flag ^= 1` and page base reload | binary-static |
| `r` | `0x7E01` | `0x12791` | rename-city overlay (`int 3F`) after the button hit test | binary-static |

The `b` branch header, decoded with the same convention:

```text
737d  83be10ff62      cmp word [bp-0xf0], 0x62    ; 'b'
7382  7403            je 0x7387
7384  e98902          jmp 0x7610                   ; next key
```

#### `a` - unit-list cursor (`0x7785..0x799E`)

The handler walks the city's units and returns the cursor cell:

- `0x778F` seeds `choice = 0`, then advances while
  `armydata[owner][unit_list[choice]].status & 0xCF` is zero (`0x77AC`);
  when the scan reaches `unit_count` the index resets to `0` (`0x77D5`);
- draws the cell at `((choice % 6) * 18 + 100, (choice / 6) * 16 + 116)`
  (`0x77EC`, `0x7801`) with `1D12:710D` (`0x7818`, tile panel) and
  `2AEA:0FB3` (`0x7841`, unit sprite), `flip(10)` between passes, and repeats
  until `3045:2098` (`0x7855`, keyboard status) reports a key, then reads it
  with `2D05:0AC9` (`0x7862`);
- arrows move the cursor (`0x78B1`): `0x4D00` +1, `0x4B00` -1, `0x5000` +6,
  `0x4800` -6; any other key keeps the cell; `2DC4:007C` (`0x78E1`,
  `ClampInt`) bounds it to `0 .. unit_count-1`;
- `0x0D` or `0x20` (`0x78ED`) commits the unit: when `status & 9`, `moves`
  becomes `utypes[type].moves * 3` (`0x7941`); then `status &= 0x30`
  (`0x7963`) and `goto_x = 0xFF` (-1) (`0x797F`);
- `0x1B` (Esc, `0x7984`) exits and stores the cursor in `[0x70DC]` (`0x7992`).

civd `CITYMGT.C` 1483-1524 carries the same loop and the same coordinate
formula, which is the source-backed cross-check for the binary decode.

#### `s` - sell-building cursor (`0x799E..0x7ABE`)

- refused when `townbuf[city].status & 0x80` is set (`0x79B0`);
- `0x79BA` seeds `choice = 0`, then draws the selected row with two
  `recolour_rect` calls through `1000:0784`: `(scrbuf, 252,
  (choice + wonders) * 6 + 3, 56, 7, 9, 1)` and then the same rectangle with
  `1, 9`, `flip(10)` between passes (`0x7A38` keyboard status, `0x7A45` key
  read), looping until a key arrives;
- `0x5000` +1, `0x4800` -1 (`0x7A70`, `0x7A78`); `2DC4:007C` (`0x7A83`)
  bounds it to `0 .. bld_count-1`;
- `0x0D` or `0x20` jumps to the sell path at `0A99:7ED0` (runtime linear `0x22860`),
  which walks the 24-bit `buildings` mask (`[si+0x70EC]`/`[si+0x70EE]`) for
  the selected slot and performs the sale; `0x1B` returns to the chain.

civd `CITYMGT.C` 1527-1548 and its `label_sell` block match both the guard and
the 24-slot mask walk.

#### `p` - city-radius tile cursor (`0x7B58..0x7DCF`)

- `0x7B62` initialises the cursor to `(0, 0)` the first time and sets the
  tile-key flag;
- the cell is drawn at `(160 + 16 * cursor_x, 56 + 16 * cursor_y)`
  (`0x7B7D`): `blit(scrbuf, ...)` through `1000:07FB`, `draw_box(..., 15, 15,
  15)` through `2D05:0A05`, `flip(10)`, then the reverse `blit` from
  `[0x19D4]`; `[0x6B64]` is marked as a map view change (`0x7C31`);
- `0x7C54` reads the key and the ladder at `0x7CAF` maps the eight directions:
  `0x4800` y-1, `0x4900` y-1/x+1, `0x4D00` x+1, `0x5100` x+1/y+1, `0x5000`
  y+1, `0x4F00` x-1/y+1, `0x4B00` x-1, `0x4700` x-1/y-1;
- the guard at `0x7CFA` rejects `|cursor| > 2`, any corner
  `|x| + |y| >= 4`, and a radius tile not visible to the current civ
  (`[0x63F2]` far pointer, bit `1 << [0xD7EE]`), restoring the saved cursor
  (`0x7D85`);
- `0x0D`/`0x20` (`0x7D95`) saves the cursor and jumps to the worker-toggle
  path; `0x1B` (`0x7DBC`) clears the tile-key flag and returns to the main
  loop.

civd `CITYMGT.C` 1569-1627 carries the same draw pair, eight direction keys,
radius guard, visibility bit and worker toggle.

The mouse CHANGE button reaches the same chooser at `0x727F`
(`lcall 0ADE:0421`); its result is compared with `0x63` at `0x7294`, which is
the cancel code.

Crosswalk note: Civ64 names the city view as `O19:0000(city, -1)`. The DOS
call is an `int 3F` overlay entry `0x0013`, so the overlay-to-segment mapping of
`O19` is an inference, not a proven identity.

### Retracted earlier reading

`0x4C00..0x4E03` also ends with `add [bx+0x70fa], ax` and
`shl ax,1 / sub [bx-0x4e2a], ax`, which reads like a purchase, but it is not
reached from the `b` branch and it masks production status with
`and byte [bx+0x70f2], 0xef`. Its caller and action stay unattributed
(candidate); no model claims it.

## Limits

- Static decode only. No runtime reachability, dispatch order, or mode-1
  parameter position is claimed. `0xB1CA` reads its city argument at `[bp+8]`;
  whether that is a second parameter or part of a long first argument is
  unresolved.
- The dispatch chain is complete as a set of compare sites (`key_dispatch`
  returns all fifteen). Handler interior spans are decoded for `a`, `s` and
  `p`; the `p` span is a linear decode because the analyzer's traversal stops
  at its far key read, so its branch targets are not CFG-verified.
- Overlay callers are candidate sites, not resolved functions.
- The field-reference counts are in-segment literal-offset matches; an indirect
  access through a copied pointer is not counted.
- Names (`city_process`, `civ_economy`) are source-backed interpretations of
  civd, not recovered symbols.

## What this changes

`CIV-DOS-CITY-001` moves from `candidate` to **statically proven** for the entry
identity, the calling sites, the shield reset block and the fifteen-site key
dispatch. The `a` and `s` handlers are now decoded with civd source agreement
for their cursor loop, clamp, commit/exit and sell-path guard.
`CIV-DOS-CITY-BUY-001` is statically proven for the guard, price and commit
stores. `CIV-UI-001` stays `candidate`: scene geometry and controls still need
a runtime display/state comparison.

