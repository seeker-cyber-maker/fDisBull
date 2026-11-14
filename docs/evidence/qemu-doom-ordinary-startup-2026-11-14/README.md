# Ordinary Doom startup, physical input and checkpoint boundary

Native QEMU now has a local ordinary original-Doom witness through launch,
menu selection, a fresh E1M1 game, forward movement and turning. This uses the
public directory-launch and physical-key APIs with `-nosound -nomouse`, without
LE binding, IRQ-mask changes, register/RAM edits or prepared runtime state.
**Protected midgame checkpoint/restore remains unqualified. DOSBox-X stays the
default and retained backend; this is not a 1:1 replacement verdict.**

## What the earlier startup observation meant

The retained 90-virtual-second trial stayed visibly at `R_Init`; it did not
establish a permanent stall. A new bounded run on the **unchanged `29f45ab6`
runtime** reaches the built-in gameplay demo after more virtual execution.
That is startup/rendering evidence, not player control. Separate individually
inspected physical-key requests subsequently reach the main, episode and skill
menus and start E1M1. The new candidate additionally demonstrates movement and
turning in that newly started game.

Stopped DOS I/O observations explain a substantial loading cost. Sixteen
matching INT21 entry/return pairs show successful reads/seeks on handle 5,
identified through the stopped JFT/SFT as the original read-only `DOOM.WAD`.
Two reads immediately after observed backward seeks use 10,925,442 and
10,590,818 native icount increments. The other seven captured reads use
8,582–55,282. Carry is clear and returned lengths match requests. The exact
FreeDOS source defers backward-seek chain traversal to the subsequent read.
Counters include whole-machine and interrupt work; this does not assign every
instruction to a kernel symbol or verify returned buffers against the WAD.

## The bounded loading correction

New workspace volumes of at least 32 MiB prefer 4 KiB clusters when the complete
file/directory inventory fits. Otherwise they retain the prior layout. Empty
files, directory tables, dot entries and per-file rounding participate in the
capacity decision. Smaller volumes, limits, parser and retained-checkpoint
paths are unchanged; existing checkpoint disks are not reformatted.

Independent review caught a preferred-layout FAT-size oscillation at a valid
33,600,000-byte volume. The corrected preferred solver retains a sufficient
upper FAT length. Regression checks cover that malformed-volume case, all
sector-aligned preferred geometries, capacity fallback with many small files,
empty files, exact capacity and existing bounds. The legacy layout calculation
remains unchanged.

The original WAD occupies 24,235 clusters on the earlier layout and 3,030 on
the new one. A controlled native comparison starts at the original MZ entry
and observes the first BIOS-data-area mode-13 write using a public write
watchpoint, with identical native runtime, CPU/profile, original files and
arguments:

Each run has its own nonce-bearing generated parent helper and private disk.
Those derived artifacts differ; identical native tools, source inputs and
machine configuration do not imply byte-identical prepared boot media.

| Measured graphics-initialization boundary | Earlier layout | New layout |
|---|---:|---:|
| Cluster size | 512 bytes | 4,096 bytes |
| Counted instructions | 1,666,377,668 | 254,130,371 |
| QEMU virtual elapsed time | 213.296341504 s | 32.528687488 s |

The earlier run uses about 6.56 times as many counted instructions to that
boundary. This is
**not a wall-time speed claim, completed-frame boundary or whole-game timing
comparison**. Both runs stop first on a mode-3 write, then mode 13, without
tracking stops or a timeout. A separate one-second clock advance occurs after
the measured boundary to obtain a stored image. The raw controller's inherited
`no_clock_budget` flag applies to the measured startup interval only.

## Actual gameplay and checkpoint result

On candidate `43b7da3957ab94f18271eab2876ac01888919555`, six individually
inspected physical keys—Escape, Enter, Enter, Enter, Up, Right—produce the main
menu, episode/skill selection, fresh E1M1 and visible movement/turning. Nine
stored PNGs match their immutable artifacts. Every key retains a complete
two-edge native dispatch receipt; general guest-consumption semantics are not
inferred from dispatch alone.

The normal public `save_state` call then refuses with:

```text
DOS process allocation ownership changed
```

That is the actual first failing guard. The later protected-PC/source-module
guard is not reached, so it must not be reported as the observed failure.
Before/after CPU and cached process documents and PID are equal; state-artifact count
stays zero and the before/after images are identical. A subsequent one-second
virtual advance succeeds and renders gameplay. The refusal preserves the
owner; no raw snapshot bypass or fabricated source-restoration flag is used.
The cached process document is not a fresh MCB scan. This trial does not record
which allocation fields changed or distinguish a legitimate resize from other
ownership changes.

Next acceptance work must establish the extender's allocation evolution and
truthful recovery/source authority. A raw whole-machine state and a source-bound
DOS checkpoint are distinct contracts. Existing selected-undo recovery also
depends on a truthful `source_binding_restored` result. Keep those semantics
explicit while implementing protected-game recovery.

## Verification and preserved limitations

- **27 focused and 176 affected host checks pass**, including the previously
  failing geometry cases. These counts overlap.
- **23 native checks pass, zero skips**, covering prior DOS/CHIP-8 history,
  trials, selected undo, frame ownership, task-private layers, hooks, RNG,
  checkpoints, IRQs, containment, paired small-game controls, native readiness,
  relative assets, open-handle/CRUD restore and real short-write/full-disk
  refusal without automatic keeps.
- All **710** runtime files match committed source, private wheel and installed
  prefix. Wheel SHA-256:
  `630e97c7d1bed4f2e821547b8d1e97e5312ebecb9108328e1185920bc00ef37e`.
  The existing native QEMU executable is reused; no native rebuild occurred.
- Earlier unsuccessful controller windows, a 1 GiB supervisor-estimate
  interruption before checkpointing, the original 90-second trial and rejected
  candidate geometry remain separate retained evidence. The completed gameplay
  run uses a corrected 3 GiB estimate and closes/reaps normally.

The [sanitized receipt](verification.json) binds primary evidence without game
bytes, images, saves, FDB/CAS or private paths. Originals and frozen packages
remain unchanged. Doom guest exit, protected recovery, audio/mouse and broad
DOSBox-X compatibility are not qualified by this slice. The older strict paired
DOSBox-X ATTT cold-restore display gap remains open. Further DESQview completion
is deferred unless it blocks ordinary DOS operation.

No CI, native rebuild, release, merge, default switch or shared activation.
