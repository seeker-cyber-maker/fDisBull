# Dirty-page execution overlay candidate

Apply the patch after the exact `qemu-high-execute` source listed in
[source-manifest.json](source-manifest.json). The manifest identifies the
predecessor, the four source preimages and their replacements, and the
private macOS arm64 build of the x86_64 TCG emulator.

Each physical 4 KiB RAM subpage containing an execute override keeps its TLB
write callback, including after a write to an unrelated byte. The callback
compares the store's byte range with the override map using the resolved RAM
offset. Ordinary code on other pages keeps its usual translated block size.

For an overlapping store in a multi-instruction block, QEMU restores the
writing instruction and replays it alone using the watchpoint mechanism. It
commits the store, invalidates the execute layer, and returns a debug stop
before the next instruction. A store already in a single-instruction block
can complete there. Without a recoverable block, QEMU stops before the access.

Permission probes of length zero leave the overlay active. While an overlay
is active, x86 helpers that prepare a span for stores, including FXSAVE,
check permissions and route the individual writes through the store helpers.

Qualification covers ordinary guest stores on a single TCG vCPU. Hardware
page-table accessed/dirty updates through direct pointers can bypass
notification. Conditional atomic operations can report overlap before a
write commits. Replaying an instruction with multiple accesses can repeat
earlier side effects. Writable high-address RAM layers are a separate feature.

See the [paired test procedure](../bochs-pae-reference/README.md#compare-writes-to-overlaid-bytes-on-dirty-pages).
