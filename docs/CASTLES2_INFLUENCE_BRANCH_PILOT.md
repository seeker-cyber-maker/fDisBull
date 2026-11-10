# Castles II CMP/JAE influence and Z3 negative control

A fresh fDisBull 0.34.1 private import of the user-supplied Castles II installer recovered this actual code at entry-relative locations: 1000:0067 CMP DI,0200h; 1000:006b JAE short 0075h. Source C2CDTOOL.EXE SHA-256: 512efad4a4d771f6c975702cad9a688aeef10f8d81798b8c7260e37c74e87d43.

A consciously *hand-modeled*, path-local atomic state graph identifies CF as the only comparison flag needed for the immediate branch decision; other flag outputs are merely dead-written candidates for that particular observer. A Z3 16-bit equivalence check shows NOT(ULT(DI,0x200)) == ULE(0x200,DI) under full u16 domain; its intentionally reversed predicate produces SAT/counterexample.

It does NOT establish QEMU lifting, original instruction semantics, interrupt safety, flag liveness across the rest of the game, or a valid native replacement. The source bytes and saves remain private; this test contains only addresses, source hash, and an authored semantic model. Local test: six focused influence tests passed, including this specimen. Full suite and hosted CI not run.

Next test must compare original execution vs a generated block at the exact original boundary with live flags, memory, and observable state included, including IRQ/PUSHF counterexamples.
