# Bounded DOSBox-X parent/child cold restore and QEMU checkpoints

On a separate DOSBox-X candidate, the selected parent COM PSP survived a cold
restore while its EXEC child was current. The child returned through the
parent's DOS wait path; the parent observed its child status and marker, then
exited with code 17 under the original PSP. The same authored behavior passed
on QEMU. The engines used their own native checkpoint formats; this is a
bounded paired behavior witness, not a checkpoint-format or full-parity claim.

The candidate's selected-process identity check admits the selected PSP when
it is current or a validated ancestor of the current PSP. It validates the
PSP against the main DOS MCB chain and bounds the ancestry walk to 32 links.
The paired cold test was attempted ten times: early harness/address/allocation
assumptions, denied memory-lock admission, and input/profile/fixture mistakes
were retained; attempt 10 passed. Attempt 5 was denied before the guest run and
has no JUnit report. The detailed attempt list and hashes are in
[`verification.json`](verification.json); the raw reports remain private.

The paired regression gate also passed the existing authored COM hot/fresh-
owner checkpoint and input behavior with the candidate and QEMU. It recorded
the expected common guest result and reaped owners. This checks a neighboring
path, not arbitrary DOS applications.

## QEMU checkpoint slice

Two QEMU-owned machine recovery cases passed after the guest shrank its DOS
allocation in place. The authored program kept an open file handle across the
checkpoint, observed `AA` before restore and `BB` afterward, and verified CPU,
RAM, executable layers, and a linear hook. The two cases cover physical exit
and TSR return. Four additional COM/MZ cases passed cold QEMU checkpoint
recovery with source/backing layers and hooks.

These QEMU machine checkpoints retire the prior source mapping and do not
weaken the ordinary source-bound process checkpoint. The Python and DOSBox-X
native state limits are 256 MiB and 128 MiB respectively. The QEMU MCB walk
caps at 512 blocks, the candidate's main-MCB-chain walk at 4,096 entries, and
selected-parent ancestry at 32 links. This does not establish arbitrary
allocation histories.

## Candidate and qualification limits

The final arm64 candidate executable SHA-256 is
`bab81ba19db7014236ca8ee729f44d3d5624d8f18c30281e2a9fcebb345a2fda`; the
patch SHA-256 is
`93997f19c73174b31cdef9c000d33bda7a30ebf4b17bdb4befd4c6fd2f9ea349`.
The separately installed DOSBox-X binary remains unchanged at SHA-256
`df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e`.
DOSBox-X remains the default; the candidate was not installed or activated.

The final affected host selection reported 108 passed and 35 opt-in skips in
3.55 s, plus one expected duplicate ZIP-name warning. Skips are not native
passes. No CI, release, merge, or activation was performed. Full DOSBox-X/QEMU
parity remains open. Direct RPC artifact metadata is not issuer-authenticated,
and the invalid-state-file test does not exercise partial or mid-load
corruption.

A broader macOS checkout run reported 18,133 passed, 1,298 skipped, 10 failed,
and 23 setup errors. Eight fresh-process failures passed when rerun with
`PYTHONPATH=src`; the checkout was not installed in that interpreter. The other
two failures and the setup errors exercised Linux ELF fixtures with macOS
`gcc`/Mach-O output. This broader run is not a green full-suite gate and was
not used to qualify Linux behavior.

Private JUnit and build evidence are represented by basename/hash entries in
the external `cold-parent-child-manifest.json`; no private paths, JUnit XML,
target media, DOS states, or raw receipts are included in this repository.
