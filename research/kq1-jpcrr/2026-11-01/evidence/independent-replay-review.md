# Independent final replay review

**PASS.** The four completed stock replay captures satisfy the checks below. No emulator was operated during this review.

## Repeated captures

| Variant | Bytes compared | Fresh SHA-256 | Result |
| --- | ---: | --- | --- |
| automatic | 15,828,730 | `19eb9148a3d20f5d4550b5826bb77b6e7936e7496aa5ff803e5aecf29c4b0fa2` | Byte-identical |
| bow | 15,862,773 | `b84c2571e3c5d8f3f22c848e2d4edcc062e2e6f4b82bfae9807ac403862f8269` | Byte-identical |

Both pairs were compared directly in full; equality was not inferred merely from saved hashes. Each capture was also freshly hashed and matched its replay receipt. These results cover the recorded audio/video streams, timestamps and container bytes. They do **not** establish equality of all hidden game or machine state.

## Stock runtime and immutability

All four recorded commands run only the official stock JPC-RR 11.2 JAR through `java -jar`; their autoexec files load only the disk library, stock RAWDumper and stock PCRunner. No authoring classes or adaptive input appear in those commands. Every receipt records exit 0, no timeout and unchanged movie/JAR. Independent log scans found no error, exception, fatal, critical or triple-fault lines. Fresh movie and JAR hashes match their receipts, and the JAR matches the previously identified official archive. All six disk-library file hashes also match the saved input identities.

Each native stream ends at 35,000,000,000 ns and contains 2,450 captured video frames. Host replay durations were 66.869211883 s and 66.515641507 s for automatic; 67.662908548 s and 67.884776130 s for BOW. These are host execution costs, including capture and JVM work.

## Input and configuration comparison

An independent component/event parser reread the reference and all four endpoint/complete JRSR movies. All **15 initialization rows**, including initial RTC, VGA timing mode, FPU/SoundCard modules and optional machine flags, agree exactly and in order with the original-BIOS reference. Every corresponding audit report also matches the freshly parsed rows. The movies have power-on structure, no embedded savestate payload and only ordinary keyboard dispatch events.

All four movies share **1,660 identical timed keyboard edges through 32.035330750 s inclusive**. Their last common edge is at 32.035146312 s. Thus the automatic and BOW alternatives share the same recorded input history to the stated checkpoint. This input comparison does not itself prove equality of hidden state.

## Borrowed boot inputs and F5

All four movies preserve the same **24 boot-prefix keyboard edges through 2.845504878 s** as DrD2k9 submission 8484. F5 (scan code 63) is pressed at **2.088645780 s** and released at **2.089312440 s**, before the first `C:` command key at 2.089979100 s and before `KQ1` begins at 2.095312380 s. The launch Enter occurs at 2.099312340 s. Its chronology places this F5 in DOS startup, not an in-game intervention. This review does not independently prove which FreeDOS handler consumed it.

Every movie header explicitly credits DrD2k9 for the boot prefix, gives the 24-edge cutoff and submission number, credits Robb for route inspiration rather than the new exact inputs, and states that this is an experimental evaluation with no record or publication-acceptance claim.

## Review limits

The parent owns visual completion, final score and exact gameplay/finish landmark interpretation. The review does not certify TASVideos acceptance. The reference uses its documented original 740f01be BIOS variant. The known audit-helper gaps were covered directly here: all initialization rows were compared, and unchanged flags plus fresh hashes were required independently of process exit.

Complete machine-readable evidence: `independent-replay-review.json`.
