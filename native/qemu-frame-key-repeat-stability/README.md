# Retain overdue keyboard repeat across stopped checkpoints

Apply the QEMU 10.0.13 delta after the
[VBE 101h page-flip profile](../qemu-video-vbe101-flip/README.md).
The [source manifest](source-manifest.json) pins the preimage.

The held key and its absolute virtual deadline are the logical repeat state.
Save and restore leave an already-due timer detached while the VM is stopped.
A stopped or timer-masked callback preserves the logical state. On normal
resume, QEMU rearms the retained deadline and delivers at most one repeat
make, with its next deadline anchored to the saved cadence. A synchronous
stop during execution retains its existing precedence over delivery.

This applies to both the hardware and DOSBox-millisecond QEMU repeat profiles.
Checkpoint format and producer identity requirements remain the same.
