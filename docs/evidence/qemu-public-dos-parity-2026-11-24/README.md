# Public nested DOS/TSR route and SB16 count: local parity evidence

This is a bounded macOS comparison on the same authored COM parent and child
bytes in DOSBox-X and QEMU. Saved scripts stop after the parent calls a
nonresident child, an AH=31h resident child or an INT 27h resident child.
Public JSON reads the DOS child status and, for resident cases, AX returned by
the callable INT 60h handler, then observes selected-parent exit code 17 and
reaps each process. The existing paired direct-Python cases independently
inspect the resident interrupt vector, handler bytes and MCB ownership for
AH=31h and INT 27h. The native paired batch passed 7/7 with no skips. A
separate original COM exit smoke test passed. All source and original boot
image bytes stayed unchanged. The three new public-route cases were rerun after
adding an explicit `BEEF` parent-continuation marker read; all three passed.

Full host collection succeeds after making the repository's `tests` package
unambiguous and retaining both `src` and `tests` on pytest's path. The broad
macOS run itself failed: 18,062 passed, 1,248 skipped, 10 failed and 23 setup
errors. Eight failures were child Python processes that did not inherit
pytest's source path; all eight passed on a narrow rerun with
`PYTHONPATH=src:tests`. Two failures and all 23 setup errors invoke Linux ELF
fixtures with macOS Mach-O or Apple linker tools. Those Linux tests were not
requalified here. The failed broad run and its private receipt remain retained.

The selected QEMU source tree has the documented Bx/Cx transfer-count fix: it
sets block size from channel samples and sample width without a second stereo
multiplier. Four paired U8 mono/stereo, FIFO on/off tests passed on the selected
QEMU executable and installed DOSBox-X. The old frozen QEMU counterexample
remains valid for its different binary. This does not establish signed-16
count on the selected executable, Doom audio fidelity or general driver parity.

An initial setup attempt supplied a firmware *file* and failed before QEMU
admission with “QEMU firmware must be a directory.” Expansion of the test
initially also failed on two fixture-harness mistakes, corrected before the
clean 7/7 paired batch. The corrected firmware directory passed the COM smoke
test and all accepted native cases. The
[verification record](verification.json) pins the exact inputs and private
JUnit hashes; private images, states and generated target bytes are not here.

Public JSON's DOSBox `debug-memory` route is source-mapped, so the vector and
MCB observations remain in the existing paired direct-Python test. Broader
device/game/audio workloads, core/source/trace/layer group contracts, and
143 surface plus seven campaign qualifications remain open.
DOSBox-X stays default. No CI was run.
