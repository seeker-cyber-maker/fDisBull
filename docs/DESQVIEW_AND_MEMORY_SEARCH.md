# DESQview awareness and persistent memory searches

fDisBull can identify a documented subset of DESQview interrupt calls, inspect
its distinct raw module formats, pin a caller-owned DOS boot image, and emit a
small cooperative guest helper. It also supports persistent scalar searches
across stopped memory snapshots, guarded one-shot edits, and finite conditional
edit rules inspired by DOS memory-search utilities.

The installed workflow is available without a project:

```sh
fdisbull agent-skill --reference references/desqview-and-memory-search.md
```

## Supported behavior

| Surface | Behavior | Boundary |
| --- | --- | --- |
| Existing disassembly and `dos-services` | Full DESQview presence signature, PAUSE, critical sections, version, screen, task-number and mapping selectors | A selector is not proof the current interrupt handler is DESQview |
| `desqview-module-inspect` | Newer `DVdx` marker and raw entry contract; older caller-qualified type/version descriptor | A `.DVR` is not a DOS `.SYS` header or an executable process |
| `desqview-profile` | Hash-pin selected program, modules and optional startup file in an actual FAT12/16 image; optionally admit QEMM too | Selection does not install software or prove boot compatibility |
| `desqview-probe` | Authored 286-compatible COM; presence guard, bounded PAUSE calls, paired BEGINC/ENDC around metadata queries | It runs as its own guest task; it does not make an arbitrary program cooperative |
| `desqview-report`, `debug-desqview-observe` | Strict 64-byte report and private provenance; optional exact helper/nonce/ready-PC checks | Report parsing does not qualify the whole scheduler or another task |
| `debug-memory-snapshot` | Bounded stopped capture with source, run, version, epoch, task and page-mapping context | An address or CR3 alone is not allocation identity |
| `memory-search-start/refine/results` | Unknown, exact and range starts; change, order and delta refinements; retained candidates and pagination | Only previous survivors can remain; budget exhaustion is an error |
| `memory-edit-plan`, `debug-memory-apply` | Conditional one-shot candidate edits with current context, expected bytes and verified readback | A stale plan refuses; uncertain dispatched writes terminate the owned guest |
| `memory-rule-create/info`, `debug-memory-rule-tick/run` | Finite conditional edits/freeze with persistent budgets and new guarded plans per application | Repetition is explicit host assistance, with no unbounded background writer |

### DESQview contracts

The presence check is INT 21h with AX=2B01h, CX=4445h and DX=5351h. Ordinary
DOS set-date calls must retain their normal interpretation. Kernel version BX
has binary integer major/minor bytes: 0219h is 2.25 and 0250h is 2.80. Product
branding and the kernel API version are separate.

The helper queries mapping context with BX=0: selector 1117h for kernels
2.20–2.25 and DE17h from 2.26. It never changes that context. PAUSE (1000h)
runs outside the short BEGINC (101Bh)/ENDC (101Ch) metadata section. DOS file
I/O and waiting at the debugger-ready point also occur outside that section.
GETBUF (1024h) returns ES:DI, CX bytes and DL text/graphics type. These values
belong to the reporting task and its current mapping.

These interfaces follow the original investigated contracts catalogued in
[RBIL's Quarterdeck section](https://fd.lod.bz/rbil/interrup/quarterdeck/index.html),
including [PAUSE](https://fd.lod.bz/rbil/interrup/quarterdeck/151000.html),
[BEGINC](https://fd.lod.bz/rbil/interrup/quarterdeck/15101b.html),
[GETBUF](https://fd.lod.bz/rbil/interrup/quarterdeck/151024.html), and
[older ASSERTMAP](https://fd.lod.bz/rbil/interrup/quarterdeck/151117bx0000.html).
The companion source is authored and reproducible with GNU binutils; it embeds
no vendor instructions.

### Memory identity and edit behavior

Every linear base-view snapshot requires an explicit `task_id` representing one
observed task lifetime; this legacy label is caller-declared. fDisBull includes the full region's 386 page translations in
its identity. Reusing CR3 while changing a PTE therefore invalidates a search;
accessed/dirty activity alone does not. A state restore also changes the capture
epoch. Physical snapshots have physical-address identity, which still does not
identify an application allocation. Callers must end a search when its task or
allocation dies, including reuse that has the same page mapping.

The candidate native QEMU interface adds `memory_snapshot(..., view='base' |
'ram' | 'execute')`; `base` is the legacy debugger view. An explicit `ram` or
`execute` view in a native task-private session requires the selected task's
actual registered native `task_id`, not a caller-chosen label. Its capture binds
the native task lifetime and selected view, backing and generation to the live
run and epoch. `execute` is for inspection; rule edits require the `ram` view.
A different selected task, changed view identity or stale epoch must refuse
before a rule tick or write. A checkpoint restore changes ownership: retain the
old rule as evidence, then take a fresh snapshot and create a new rule rather
than replaying the old one.

A native rule applies verified guarded edits as immutable rule-owned RAM
overlays above the authored task RAM and fetch layers; the other task's private
view and the shared base are separate. Each tick uses fresh values and records
its result. On the explicit virtual clock, the first tick is immediate and
subsequent intervals use bounded native timer ownership. An encountered hook is
dispatched once and stops the interval without an extra tick; other nonordinary
stops also preserve their actual cause and do not trigger replay. This remains
host-assisted control, not unattended scheduling or vendor multitasker parity.
A bounded authored native IRQ witness passed locally: explicit physical RAM
view, guest-mutated A private value and rule-overlay replacement, unchanged B
and shared base, and cold restore retaining IRQ state, hooks and layers. The
old rule refused after restore and a fresh rule succeeded above its retained
overlay. A fresh bounded regression passed 1,159 tests across 72 files with no
failures, errors or skips. This does not establish vendor multitasker parity.

Searches accept 1-, 2-, 4- or 8-byte integers, signed/unsigned interpretation,
little/big endian, explicit stride and a fixed display bias. For example,
`bias=-1` means stored value = displayed value − 1. This is an explicit
interpretation, with no silent wrapping or automatic alternation between
encodings. Start separate searches when comparing encoding hypotheses.

The maximum base-view snapshot is 16 MiB; explicit native RAM/execute views
are limited to 64 KiB. Candidate and interval limits bound search
work and serialized state; callers can select smaller regions or a larger
stride. All snapshots, search states, edit plans and rule progress use the
existing private debugger artifact store. Their hashes detect inconsistency;
they are not a cryptographic authorization mechanism.

## Verification scope

Authored unit tests cover scalar semantics, persistence, candidate monotonicity,
page remaps, stale context, file-output failures and uncertain writes. Helper
instruction tests execute the actual assembled COM with explicit service
doubles; they do not replace a DESQview kernel. Optional native tests execute
an authored counter and the helper's absence path through the real DOSBox
backend. They require `FDISBULL_DOSBOX` and can be required with `--require-native`.

Full DESQview/QEMM startup and application compatibility require their own
installed caller-owned DOS image and a native qualification receipt. No general
multitasking, protected-mode game, Windows/VxD or allocation-lifetime tracker is
claimed by these APIs. Research findings and original-binary witnesses are
delivered separately from the authored tool source.
