# Owned QEMU DOS machine recovery

`save_machine_state` and `load_machine_state` recover an owned DOS-launched
machine when its current execution no longer has the original COM/MZ source
ownership required by `save_state`. DOSBox-X remains the default backend.

```python
saved = debug.save_machine_state('midgame.qcow2', max_bytes=128 * 1024**2)
# Continue to a different stopped endpoint.
restored = debug.load_machine_state(saved['artifact'], timeout_ms=60000)
assert restored['machine_state_restored'] is True
assert restored['source_binding_restored'] is False
```

The capability is `owned_machine_checkpoints`. In a live `fdisbull serve` or
`fdisbull debug` JSON session, use `debug-save-machine-state` and
`debug-load-machine-state`, with `run` and the same parameters. Saved scripts
must explicitly select `backend: "qemu-dos"`; their operation names are
`save-machine-state` and `load-machine-state`. A saved artifact reference such
as `$saved.artifact` is supported. Names, budgets and timeouts must be literal.
Scripts reject unsupported backends, unavailable capabilities, caller-owned
transactions and malformed options before executing earlier steps. Live state
admission is checked again at the actual stopped boundary.

The distinct `machine-state` artifact uses
`fdisbull-qemu-owned-machine-qcow2-v1`, containing `machine.qcow2` and
`owned-machine.json`. It binds the original source/version and launch arguments
as provenance, the admitted runtime and firmware, the complete private writable
disk graph, stopped CPU/address state, architectural RAM witnesses, the helper
completion channel, supported native controls and workspace/instrumentation
sidecars. Restore verifies a fresh machine before replacing the old owner. The
saved guest disk is restored; host files are untouched.

Admission requires one observed vCPU, real/protected/V86 mode, supported
non-PAE address translation, and code/stack witness pages in conventional or
extended RAM. ROM and unsupported address contexts refuse. These are bounded
machine checks, separate from executable allocation or source-lifetime proof.

Explicit native physical/linear RAM and fetch layers and linear hooks with
guarded register or native-layer actions can cross this boundary. Source-based
controls, task-private layers, task bindings/scheduler owners and active save
provenance observers require their existing source-bound checkpoint contracts;
the machine API refuses unsupported state. Ordinary queued/leased input,
unresolved observers and active host synchronization also refuse. Supported
frame-owned keys and clock/audio/display/retrace profiles use the existing
native instrumentation restore contract.

Restore retires the original MZ live ranges, the old protected LE binding and
runtime tracker, and advances the capture epoch. A later resident DOS return
does not recreate that source authority. Original launch facts remain available
as historical process provenance. Machine memory, input, execution and new
captures remain usable. Old source-bound history, trial and selected-undo
anchors retain their stronger source checks; they do not accept machine-state
artifacts. A verified full machine recovery can clear a selected-undo freeze
without reviving its invalid history or claiming source restoration.

For an eligible protected32 LE carrier, explicitly request a **fresh stopped
source admission** inside the restore operation:

```python
restored = debug.load_machine_state(
    saved['artifact'], timeout_ms=60000, rebind_protected_source=True)
assert restored['source_binding_restored'] is False
assert restored['protected_source_rebound'] is True
binding = restored['protected_source_binding']
assert binding['live'] and binding['source_view'] == 'embedded-le'
```

The flag must be a literal Boolean in Python/JSON and saved scripts; omission
keeps machine-only recovery. The saved machine must be unlayered, unpaged
protected32 with A20 and a single observed CPU, and the retained original must
be an eligible x86 LE carrier. Static incompatibilities refuse before spawning
a replacement. After machine restoration, the existing LE matcher and stopped
instruction proof run again against the restored CPU, RAM and GDT. A new
binding ID and current capture epoch are issued before the restore completion
receipt. Both phases share the controller lock and one absolute deadline.
Revalidation or publication failure closes the uncertain owner and does not
complete selected-undo recovery.

This option does not serialize a source handle or revive the saved recipe,
original MZ live ranges, allocation lifetime, task-private source views or old
source-bound histories/trials/undo. Active native layers remain supported by
machine-only recovery; they are ineligible for this optional LE admission.
Native hooks and instrumentation retain their machine checkpoint contracts.
Even an otherwise valid machine can fail fresh source admission, for example
when initialized data witnesses changed. Earlier and newly bound LE traces can
be queried after reopening the project using their own captured source proof
and validated machine-restore provenance.

`debug-state-info` can inspect these artifacts offline after reopening the
project. `load_state`, Anchor Stone loading and state forks do not accept them
as source-bound checkpoints. Keep checkpoint bytes, private guest files and
byte-retaining databases outside Git and release packages.

The separate [persisted LE checkpoint/history contract](DOS_LE_SOURCE_CHECKPOINTS.md)
now joins saved source proofs to full machine states and revalidates them before
completion. It keeps this machine archive format and the false MZ source flag.
Broader DOS game compatibility, task/allocation lifetime and overall DOSBox-X
parity remain separate qualification gates. No CI is dispatched by these operations.
