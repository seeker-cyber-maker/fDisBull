# SB16 documented channel-sample counts

The new native producer removes the extra single-cycle stereo multiplication.
The same authored nonwrapping DMA oracle now passes all eight paired variants
against the installed DOSBox-X reference: U8/S16, mono/stereo, FIFO off/on. The
previous frozen QEMU passes four mono controls and doubles all four stereo
transfers. See [verification](verification.json) for exact sources and receipts.

Separate Linux and macOS builds pass. Linux corrected U8 single/ring/initial/
draining and combined/initial OPL checkpoint cases pass. The first adjacent
selection retains 16 passes and two tone failures: the old analyzer demanded
100 ms from a program requesting 64 ms. A separate test correction uses the
documented requested duration at the observed output rate. All original pitch,
channel, strength and rail assertions remain; exact64ms positives, a one-frame-
short refusal and swapped/duplicated-lane negatives pass independently. The two
corrected native tone cases then pass with unchanged guest and native bytes.

The older single-cycle fixture compensated for the emulator bug by halving its
programmed stereo count; it now requests every intended channel sample. The
auto-init ring fixture independently programmed128samples while describing a
256-byte block; it now requests256samples and asserts the native block size.
Historical exact-replay receipts remain valid for their original programs and
producers, while correct IRQ/block cadence requires these new witnesses.

## Open producer identity counterexample

The old-producer state rejection test found a host admission defect: byte-
identical shell launchers hide different executing QEMU binaries from the old
fingerprint. With other inputs held fixed, their portable compatibility values
are identical. The test stopped before loading state and reaped both owners.
A separate host change must bind the executing binary and compare a fresh
replacement before state load. These playback/count results do not establish
that still-open producer rejection guarantee.

S16 guest playback does not extend the existing U8-only voice checkpoint
contract. Four explicit S16 refusals preserve the stopped owner, CPU, clock and
device state. Native macOS playback and actual Doom regression on the corrected
producer remain separate gates, as do Miles compatibility and full fidelity.
