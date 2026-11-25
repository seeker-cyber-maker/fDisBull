# Protected-mode stack-segment limit witness

The authored 32-bit COM probe used an EBP-based dword read, which selects SS.
Its small, present writable stack segment had a `0x1fff` limit. The faulting
read used offset `0x2100`, while ESP stayed at `0x1800`, leaving the complete
16-byte exception frame within the valid stack range. The handler recorded the
frame and state, loaded a wide SS descriptor, and retried once. An otherwise
matching in-range control read from `0x1000`.

On the exact QEMU candidate, the out-of-limit read entered the authored #SS
handler with error code zero and EIP at the read. Target RAM and general
registers remained unchanged at the fault; retry completed. Frozen DOSBox-X
completed that read through the small SS without entering the handler. This is
an explicit **reference divergence**, not a paired parity pass. Both engines
completed the in-range control. [AMD's architecture manual](https://docs.amd.com/api/khub/documents/j44LvPXzuuXgM0WyHKQfeQ/content)
lists a stack-segment-limit violation as a cause of #SS.

The [verification receipt](verification.json) binds the observed paths to the
same native QEMU and DOSBox-X binaries used for the preceding access-rights
and RMW witnesses, and to a clean two-case local JUnit result. No QEMU source
change was needed for this fixture.

The result does not qualify other stack operations, access rights for a
read-only SS, guest TF/IRQ fault interactions, paired DOSBox checkpoint restore,
trace retirement or the full migration inventory. DOSBox-X remains the
default; DotBox is unchanged. No CI, release or installation was performed.
