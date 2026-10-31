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
| Root module | 213,712 bytes after a 10,128-byte header |
| Overlay tail | 116,951 bytes (not linearly mapped as code) |

All addresses below are in the root load module (`R`), which fDisBull maps at
runtime segment `0x1000`. `R:0D12:0045` is linear `0xD165`, file offset 63,733.

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
to another code segment is relocated at load; unrelocated matches inside the
root are counted as coincidental (1 in this image).

| Runtime linear | Root offset | Caller function (local) | Mode evidence | Interpretation |
|---:|---:|---:|---|---|
| `0x1AE31` | `0xAE31` | `0xADE6` | `sub ax,ax; push ax; push ax` → mode `0` | Per-city turn pass |
| `0x1AE73` | `0xAE73` | `0xADE6` | `mov ax,1` after `cmp [0xB1E8],0` → mode `1` | Same function, display branch |
| `0x1B1E3` | `0xB1E3` | `0xB1CA` | `mov ax,1; cwd; push dx; push ax` → mode `1` | Small display wrapper |
| `0x1B21F` | `0xB21F` | `0xB201` | `sub ax,ax` → mode `0` | Second turn-pass caller |

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

Eleven further far calls to `0045:0D12` exist in the overlay tail
(`0x34C4A` … `0x4FB9A`). Overlay bytes are not relocated, so these are retained
as overlay candidates; their caller functions are identified only by the nearest
prologue and their mode arguments come from registers, not literals.

## BUY guard, price and commit

The city screen's input loop reads a key at `0x71F1`
(`lcall 1D05:0AC9`) and dispatches on it with literal compares. The `b` branch
starts at `0x737D`:

```text
737d  83be10ff62      cmp word [bp-0xf0], 0x62    ; 'b'
7382  7403            je 0x7387
7384  e98902          jmp 0x7610                   ; next key
```

### Price (`0x7387..0x7470`)

Branch on the production kind: improvements use `word [0x1142 + 0x22*id]`,
units use `word [0xBB2 - 0x1E*id]` after `neg`. Both then build the price:

```text
73b1  b8e703          mov ax, 0x3e7       ; arg 999 (clamp) to the text helper
73c1  b80a00          mov ax, 0x0a
73c4  f7aefafe        imul word [bp-0x106] ; 10 * item_cost
73c8  2b87fa70        sub ax, [bx+0x70fa]  ; minus shield stock  -> base
73d9  8b8618ff        mov ax, [bp-0xe8]
73dd  f7ae18ff        imul word [bp-0xe8]  ; base * base
73e2  b91400          mov cx, 0x14
73e5  f7f9            idiv cx              ; / 20
73e7  8b8e18ff        mov cx, [bp-0xe8]
73eb  d1e1            shl cx, 1            ; 2 * base
73ed  03c1            add ax, cx
73ef  898618ff        mov [bp-0xe8], ax    ; price
7446  8a87f570        mov al, [bx+0x70f5]  ; production id
744b  f7d8            neg ax
744d  3d1500          cmp ax, 0x15
7455  d1a618ff        shl word [bp-0xe8], 1 ; double when -id > 21
7461  83bffa7000      cmp word [bx+0x70fa], 0
746b  d1a618ff        shl word [bp-0xe8], 1 ; double when stock is 0
```

So `price = 2b + b*b/20`, `b = 10*item_cost - shield_box`, doubled for units
past index 21 and doubled again when the box is empty. The box text is built at
`0x746F..0x7560` (cost, item name, treasury, then "CIVIL DISORDER" when status
bit 1 is set on an improvement), and `0x1EA8:1F6A`/`1EA8:1E22` append the
decimal fields.

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
- Overlay callers are candidate sites, not resolved functions.
- The field-reference counts are in-segment literal-offset matches; an indirect
  access through a copied pointer is not counted.
- Names (`city_process`, `civ_economy`) are source-backed interpretations of
  civd, not recovered symbols.

## What this changes

`CIV-DOS-CITY-001` moves from `candidate` to **statically proven** for the entry
identity, the calling sites, and the shield reset block. `CIV-DOS-CITY-BUY-001`
is statically proven for the guard, price and commit stores. `CIV-UI-001` stays
`candidate`: scene geometry and controls still need a runtime display/state
comparison.
