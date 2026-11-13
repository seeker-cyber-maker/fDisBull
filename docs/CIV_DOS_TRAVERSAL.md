# Bounded DOS CIV traversal receipt

This is the reproducible static traversal receipt for the exact DOS image. It
is deliberately **not** presented as a whole-game UIL: the input is an
EXEPACK-packed root and the local intake does not contain the `CIV_UNP.EXE`
load module used by the Civ64 listings.

## Seed and result

| Field | Observed value |
| --- | --- |
| Input | `CIV.EXE`, 305,030 bytes |
| Source SHA-256 | `22de2748e3089793644c7e501e2a95b553010ddec34a7ff42f4395cf779c9c2a` |
| fDisBull profile | x86, 16-bit, MZ |
| Seed | linear `0x3a030`, segmented `3a02:0010` |
| Instruction budget | 512 |
| Attempted | 21 |
| Decoded | 17 |
| Data facts | 3 |
| Pending work after traversal | 0 |
| Budget exhausted | false |
| Bounded result | stable for the implemented static rules |
| Stored version digest | `7f76cb7496b8697816cd781ffcf0330c886be0a98863a717930420ef1de2e23e` |
| Canonical disassembly receipt | `8c4e5646575db36cd45442558463b84c584b14ae27f02074b31cb7d0ee7256fc` |

Two fresh reads of the persisted project and the same seed produced the same
canonical disassembly receipt. The result is therefore restart-deterministic
for this bounded root traversal.

## Three instruction spot checks

The first five decoded instructions include these byte-linked facts:

| Segmented address | Bytes | Decoded instruction |
| --- | --- | --- |
| `3a02:0010` | `8c c0` | `mov ax, es` |
| `3a02:0012` | `05 10 00` | `add ax, 10h` |
| `3a02:0017` | `a3 04 00` | `mov [4], ax` |

The seed is the packed entry/loader path, not the city-management overlay. The
17-instruction result must not be promoted to full executable coverage. A
semantic interaction-UIL lowering for the DOS image requires authenticated
overlay bytes and a source/effect mapping; those prerequisites remain open.
The city-production UIL in `CIV_PRODUCTION_UDC.md` is therefore a source-backed
semantic slice, not an automatic lowering of these loader instructions.
