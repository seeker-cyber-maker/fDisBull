# Protected-mode segment rights candidate

The incremental [source patch](../../../native/qemu-segment-rights/README.md)
adds access direction to the preceding segment-limit checker. It checks selected
integer scalar and per-element string data accesses against the cached segment's
read/write permissions. It also omits these new checks in virtual-8086 mode.
This is a bounded candidate, not complete x86 memory-access coverage.

An authored protected-mode COM probe loaded a read-only data descriptor into DS
and attempted a dword store. The exact QEMU candidate faulted before the store;
the handler observed unchanged backing, reloaded writable DS and retried to one
completion. Frozen DOSBox-X completed the store through read-only DS without
entering the handler. This is a **reference divergence**, recorded alongside the
prior LOCK and null-DS differences; it is not counted as paired parity.

The rights check exposed an invalid write in the existing protected-mode
checkpoint fixture: `inc word [cs:scratch]` wrote through the code segment after
setting CR0.PE. The fixture now writes the same location through writable DS.
The IRQ fixture's exact template matcher was adjusted to that change.

[Verification](verification.json) records the exact candidate and reference
hashes, source patch identity, 29/30 selected-run result, and the subsequent
seven-case and one-case successful focused runs. The selected run's one failure
was in IRQ fixture generation before its VM launched. No single clean 30-case
run is claimed. The affected rights, layer/hook, history, checkpoint and IRQ
cases have successful local native results on the same QEMU binary.

Access rights for other instruction classes, implicit stack operations, vector
and x87 memory paths, TF/IRQ fault interactions, paired DOSBox checkpoint
restore, and the full inventory/campaign gates remain open. DOSBox-X remains
the default; DotBox is unchanged. No CI, release or installation was performed.
