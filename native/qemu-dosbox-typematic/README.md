# Legacy DOSBox-X repeat pacing

Apply this optional patch to QEMU 10.0.13 after the native frame-key repeat
patch. Verify every preimage using the source manifest.

A native DOS COM/MZ session can select
`qemu_key_repeat_profile="dosbox-millisecond"` with `qemu_clock="virtual"`.
The launcher applies the private PS/2 property
`-global ps2-kbd.fdisbull-dosbox-typematic=on`. Without selection the existing
hardware delay and rate apply.

The compatibility profile initializes at 500 ms delay and 33 ms period.
Guest F3 programming selects the DOSBox-X integer-millisecond rate table and
preserves an already scheduled expiry. Guest F5, F6 and reset retain the
programmed delay and rate under this profile. The existing QEMU key owner
still cancels its repeat timer when the keyboard is reset.

The selected profile changes the native pacing within the QEMU virtual
clock. Native FIFO availability, IRQ delivery and existing safe-stop
precedence still apply. Scanning-disabled repeat suspension, other reset
effects and exact keyboard tick phase remain separate parity checks.

The launch receipt and format-4 repeat proof bind the explicit profile.
A hardware receipt keeps its original fields. Restore requires the same
producer and selected profile and uses the saved absolute QEMU deadline.
