# DOS protected-mode input, RAM and native checkpoints

The matching native DOSBox backend accepts built-in INT33 mouse input while
the CPU is in real, v86 or protected mode. Queue admission checks the physical
interrupt vector rather than reading it through the current paging map. The
normal emulated driver/IRQ path delivers the event; fDisBull does not switch
CPU mode or force a real-mode callback. DOS must be active, its built-in driver
must own INT33, and the ordinary frame, range, device and input guards still
apply. A queued event is not evidence that an application consumed it.

`registers()` exposes the actual stopped CPU mode and, in a matching backend,
`address_context` with CR0/CR3/CR4, paging, A20 and code/stack widths. Native
trace records retain their own observed mode and widths. Protected/v86 CS is a
selector; the DOS source projection never interprets it as a paragraph. Legacy
trace records without mode retain an unknown address context.

## Explicit runtime RAM

An investigation may bind an observed RAM allocation without claiming it is
part of the original static executable. A binding pins source/version, live
run, load identity, restoration epoch, address space and a masked byte witness.
It requires a paused guest and rechecks identity at every read. The caller
must establish the allocation address and record how it was found.

```python
binding = debug.bind_runtime_memory(
    "hud", observed_address, space="physical", length=32,
    expected_hex=observed_identity_hex,
    provenance={"method": "observed native writer and allocation"})
value = debug.runtime_memory(binding["id"], offset=8, length=2)
edit = debug.write_runtime_memory(
    binding["id"], "0a00", offset=8, expected_hex=value["hex"])
assert edit["verified"] and not edit["state_restore_used"]
```

Replace these example values with evidence from the current target. Physical
RAM is explicit and independent of CPU paging; it does not infer a selector,
process or allocation lifetime. Unpaged linear bindings pin observed mode and
A20. Paged linear bindings refuse because CR3 alone does not prove page-table
or allocation identity. Use a qualified physical allocation or retain the
mapping as unknown. Older backends can retain real-mode linear bindings but
must be rebuilt to supply protected/v86 linear address context.

Live writes require equal-length expected/new bytes, an intact binding and no
active real-mode code layer. The native write checks the expected-byte hash;
the controller verifies readback and context. A changed identity witness
invalidates the binding. An uncertain dispatched write closes the owned guest
and records an unknown outcome without replay. Its receipt is explicitly
`live-runtime-ram-edit`, `state_restore_used: false`; it does not establish a
painted HUD or application acceptance. JSON methods are
`debug-bind-runtime-memory`, `debug-runtime-memory` and
`debug-write-runtime-memory`; scripts use their names without `debug-`.

## Full native checkpoints and intervention provenance

`save_state()` and `load_state()` admit real, v86 and protected CPU stops.
They use the native whole-machine serializer, retain exact backend/profile,
source and mounted-file checks, require released input, and verify exposed
registers, CPU mode and address context after loading. Protected/v86 captures
refuse active real-mode code layers. Restores invalidate runtime bindings and
input leases. A partial or mismatched native restore closes the guest.

Every load reports `full-native-checkpoint-restore` and
`live_session_ram_edit: false`, retaining any edited-fork derivation. A HUD
change obtained by restoring an edited state must be reported as a checkpoint
intervention. It cannot be counted as a live RAM edit. Source-addressed DOS
code layers, register setters and edited-checkpoint construction retain their
real-mode limits. Mounted host files are checked but are not rolled back;
cross-build/device/CPU-core compatibility is unqualified.

Native acceptance uses an authored program that enters 32-bit protected mode,
enables paging and remaps linear page zero away from the physical IVT. Separate
gates check queue admission, real INT33 program consumption/release, physical
RAM binding/live edits, whole-state restore and resumed program execution.
These gates do not establish X-COM menu progression or whole-game compatibility.

## Windows remains separately qualified

Win16 uses observed source/selector/descriptor bindings. Win32 and Win64 use
the observed process architecture, image base and project RVA. They share the
Windows keyboard/frame/scene machinery without DOS paragraph arithmetic or a
real-mode input requirement. The DOS RAM-binding API refuses Windows sessions
before issuing a native call. See the [Windows runtime guide](WINDOWS_ORIGINAL_RUNTIME_BRIDGE.md)
for the separate supported operations and dot-mode spectator.
