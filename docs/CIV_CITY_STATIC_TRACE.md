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

## BUY commit block

The Civ64 crosswalk names the city screen's buy question at
`R:0D12:4CDF..4E37` (`docs/DOS-PROFILE.md` row 87, `docs/dos/SCENES-PLAY.md`
7.1). Decoding the window `R:0D12:4C00..4E40` in the unpacked root
(`0xd165 + offset`) yields the cost computation and the commit:

```text
4c00  8b1e4865      mov bx, [0x6548]        ; civ index
4c04  d1e3          shl bx, 1
4c06  8b87d6b1      mov ax, [bx-0x4e2a]     ; DGROUP gold table (16-bit wrap)
...
4c2b  8b87b20b      mov ax, [bx+0xbb2]      ; unit cost table, 0x1E-byte records
4c2f  f76eb6        imul word [bp-0x4a]     ; multiplier (unrecovered)
4c32  2b84fa70      sub ax, [si+0x70fa]     ; minus shield stock
4c37  9a7c00c41d    lcall 1dc4:007c         ; build the question text
...
4de2  0187fa70      add [bx+0x70fa], ax     ; shields += cost
4dec  8b8634ff      mov ax, [bp-0xcc]
4df0  d1e0          shl ax, 1               ; 2 * cost
4df2  2987d6b1      sub [bx-0x4e2a], ax     ; gold -= 2 * cost
4dfe  80a7f270ef    and byte [bx+0x70f2], 0xef ; clear the buy flag
```

Two further branches compute the same cost with different divisors and an
extra surcharge:

- `4ca1..4ca7` (`idiv 3`), `4d03..4d08` (`idiv 3`) and `4d76..4d7e`
  (`sar 2`) select the divisor by city status and production kind.
- `4daf..4dd2`: when the gold table entry exceeds `0x7D0` (2000), the cost
  gains `value / 512`.

Sale of a building (`4e03..4f0e`) continues past this window and is not traced.

Limits: the multiplier `[bp-0x4a]` and both cost tables are unresolved; the
surcharge divisor and the status conditions are recorded but not modelled. The
commit itself (shields up, gold down by twice the cost, flag cleared) is
unambiguous.

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
is statically proven for the commit arithmetic only. `CIV-UI-001` stays
`candidate`: scene geometry and controls still need a runtime display/state
comparison.
