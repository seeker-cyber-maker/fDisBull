# Stored indirect-transfer scope diagnostic

## Scope

Read-only inspection of the post-pass `working/syndicate.fdb`, version 1, context `x86:32:little`. SQLite used `mode=ro`, `query_only=ON`, and one read transaction. Three stored owner results, short stored instruction windows, memory references, LE fixups, and installed semantic code were inspected. Ten already-stored instructions were normalized to expose IR. No new analysis, seeds, target decoding, project mutation, or guest execution. JSON preserves the stored summaries, exact fixups, normalized IR, and source excerpts.

## Indexed dispatch 0x10779

`jmp dword [cs:eax*4+10550h]` belongs to owner `0x105E0`: **done**, **stable at 491 steps**, not budget exhausted. Recovery examined zero table entries, targets, or memory reads. The stored proposal is `unbounded_or_nondominating_index`, symbol `write:x86:32:little@0x10772:eax`.

Nearby code compares `word [eax+9BE3Eh]` to `10h`, branches above to `0x10D3D`, reloads the stack-held selector offset, executes `xor eax,eax; mov ax,[edx+9BE3Eh]`, and dispatches. Current `_guard` bounds a register or supported masked-register projection compared with a constant; this comparison is a memory load. Normalized `mov ax,[...]` has no assignment and clobbers the EAX family, losing the zero-extension relationship. CS is already given a flat-base-zero assumption in stored memory references; it is not the recorded blocker.

The LE map supplies **17 exact offset32 entries**, **11 unique initial targets**, and **10 target starts lacking stored instructions**. The table is in executable, nonwritable object 1. Only `0x10D3D` is already decoded, appearing seven times.

| Selector | Table slot | Loaded target | Fixup index | Stored instruction |
|---:|---|---|---:|---|
| 0 | `0x10550` | `0x10781` | 110 | no |
| 1 | `0x10554` | `0x10790` | 109 | no |
| 2 | `0x10558` | `0x10855` | 108 | no |
| 3 | `0x1055c` | `0x10889` | 107 | no |
| 4 | `0x10560` | `0x10d3d` | 106 | yes |
| 5 | `0x10564` | `0x108b8` | 105 | no |
| 6 | `0x10568` | `0x10d3d` | 104 | yes |
| 7 | `0x1056c` | `0x10d3d` | 103 | yes |
| 8 | `0x10570` | `0x10d3d` | 102 | yes |
| 9 | `0x10574` | `0x10d3d` | 101 | yes |
| 10 | `0x10578` | `0x10966` | 100 | no |
| 11 | `0x1057c` | `0x109bf` | 99 | no |
| 12 | `0x10580` | `0x10d3d` | 98 | yes |
| 13 | `0x10584` | `0x10d3d` | 97 | yes |
| 14 | `0x10588` | `0x10a90` | 96 | no |
| 15 | `0x1058c` | `0x10ac8` | 95 | no |
| 16 | `0x10590` | `0x10b65` | 94 | no |

**Next bounded probe:** qualify compare/reload identity and relevant write assumptions, unsigned fallthrough range 0..16, and partial-register semantics. Then inspect these 17 slots and ten absent starts. That bound is not already proved in stored solver results. Fixups alone do not prove runtime reachability.

## Callback 0x3D644 through 0x5BFF4

Owner `0x3D641` is **done**, stable at **27 steps**, not budget exhausted. Four calls at `0x3D644`, `0x3D64A`, `0x3D656`, and `0x3D65C` use slots `0x5BFF4`, `0x5BFF8`, and `0x5BFFC`. All four stored rejections are `snapshot_memory_may_be_modified`; four entries/targets were examined and no memory read accepted.

All three LE-loaded defaults are `0x3D640`, a stored `ret`. The slots lie in writable object 2. Their fixup indices are 9974, 9973, and 9972; record file offsets 88063, 88054, and 88045; source word file offsets 400372, 400376, and 400380. These establish initial no-op defaults, not runtime pointer immutability.

The rejection concerns may-write history, not simply the writable flag. The installed read helper does not reject by that flag. Local `push ebp` writes a logical symbolic-stack cell but records a 32-bit-masked physical address. `_reader_allowed` exempts unresolved plain `stack` expressions, while `and(stack(...),0xffffffff)` fails that shape check and conservatively blocks mapped snapshot reads. Subsequent unknown calls add further effects.

The masked-stack explanation is **derived from current source, normalized IR, and the local prologue**. The rejection is directly stored; raw incoming states are not persisted, so there is no persisted incoming-state witness. An earlier read-only stored-reference survey found no exact overlapping write facts and 5,207 distinct broad possible-alias sources per slot. Those possibilities are not demonstrated callback writes.

**Next bounded probe:** separate stack-alias representation qualification from actual initialization/writer discovery. Preserve true absolute and unknown-store hazards and declare any stack-disjointness assumption. Initial pointers must not automatically restore old snapshot-only edges.

## Budget contrast and scope boundary

Owner `0x274A0` also includes these callbacks. It is **partial after 25,000 steps**, six pending items, with `incomplete_dataflow` proposals. This larger caller has a genuine budget limitation, but more budget alone cannot resolve the alias/effect blocker already shown by the smaller stable owner.

The dispatch has a finite relocation-backed next probe. The callbacks require separating initial values, actual writes, and conservative alias modeling. These are concrete remaining scope boundaries; no broad analysis retry or implementation change was made.
