# QEMU runtime RAM bindings

The native `qemu-dos` session supports `debug-bind-runtime-memory`,
`debug-runtime-memory` and `debug-write-runtime-memory`, plus the corresponding
saved-script operations. Their existing signatures and witness/mask/provenance
fields are retained. The capability is `runtime_memory_bindings`.

A binding identifies an explicitly witnessed RAM region within one owned
machine lifetime. It does not infer an allocation, DOS task, selector, static
source mapping or completed guest frame from its address. `identity.runtime_load`
is `null`; QEMU's initial DOS load evidence remains in `dos_process_info()`.

## Supported address contexts

- Physical bindings use explicit conventional or extended PC RAM. Their address
  identity can survive CPU mode and paging changes between observations.
- Linear bindings require a positively observed, single-vCPU, unpaged real,
  protected or V86 context. They pin the observed mode and A20 state. Extended
  linear RAM requires A20 enabled; real-mode linear bindings stay below 1 MiB.
- Paged linear mappings, ROM/VGA/MMIO ranges, unknown CPU contexts, active code
  or RAM layers, and native task-private views refuse before byte access. Use
  the existing mapping/view-qualified APIs for those other contexts.

Every capture checks the witness again and brackets the data read with stopped
CPU/address observations under the owned VM lock. One inherited host deadline
covers the complete operation; a standalone request has a 10-second budget.
Saved scripts validate each literal parameter before executing any step, even
when other parameters contain result references. Admission does not query the
guest. A lost direct control channel closes its owner and preserves the original
error if cleanup also fails.

## Lifetime and restore

Bindings pin the live VM and native process objects, project/run/version/source,
DOS capture epoch and checkpoint epoch. A replaced owner or advanced epoch
invalidates both binding IDs and names. An explicitly frozen selected CPU/RAM
projection also requires a fresh witness; read-only bindings do not thaw it.

Full native restore never reinstalls a runtime RAM handle. After an owned-machine
restore, a caller may create a fresh explicit witness even when the original DOS
source mapping is retired. This grants only a RAM observation, not source or
allocation authority. Closed machines cannot use their former handles.

## Guarded live writes

Writes require equal-sized replacement and expected bytes. The adapter checks
the binding witness, live address context and current bytes, then invokes the
existing QEMU guarded memory writer. It verifies readback and owner/context
continuity, records the edit, and invalidates a binding whose masked witness was
consumed. It uses no save/load operation.

The normal history, selected-state freeze, source-retirement and save-provenance
guards remain active. A dispatched write that fails readback, context validation
or evidence publication closes the owned machine without rollback or replay. A
post-return deadline failure preserves its verified receipt and closes the owner.
Wrong expected bytes detected before dispatch leave guest RAM unchanged.

## Verification scope

`tests/test_qemu_runtime_memory.py` covers public routing, real FDB evidence,
protected LE observations, actual owned-loader replacement, stale handles,
mask/witness consumption, task/layer refusals and uncertain-write cleanup through
the native I/O boundary seam. `tests/test_qemu_runtime_memory_native.py` supplies
authored flat protected LE and paged V86 witnesses with explicit native inputs.
Only executed native receipts establish those runtime outcomes; host tests alone
do not qualify the migration campaign or change the default backend.

The two authored native witnesses passed against the private Linux QEMU ELF
`71bef609647922544bfca23811caa0c08843a09d6b48c70293ab5ebd6cdb1a40`.
They exercised real protected-mode RAM writes and witness consumption, native
owned-checkpoint replacement and stale-handle rejection, and paged V86 linear
refusal with physical RAM still usable. All owners were reaped. These are scoped
RAM contract witnesses; they do not establish allocation ownership, paged linear
binding support or qualification of the entire migration campaign.
