# Self-modifying code and layers — 2026-11-13

This acceptance uses authored targets on the actual DOSBox and Wine/QEMU
backends. It checks guest-originated writes to executable bytes, guarded layer
conflicts, explicit recovery, immutable observations and native checkpoints.
No supplied historical executable or game is run. The final source head,
commands, component hashes and sanitized observations are bound by the draft MR
verification report. This is not a release or system-installation qualification.

## DOS normal-core real mode

`tests/test_layer_self_modifying_dos.py` creates a small MZ program whose
`MOV byte [0021h],44h` changes the immediate of `MOV AX,1111h`. It uses the
selected native macOS ARM64 layers backend:

```text
DOSBox-X 2026.10.01 SDL2, RPC protocol 1.0
backend SHA-256 df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e
```

| Observation | Required result |
| --- | --- |
| Guest write with an execution theory active | Data watch identifies the writing instruction; RAM immediate becomes `4411` |
| Later fetch under the old theory | `outcome="layer_conflict"` at IP `0020h`, before the alternate MOV executes |
| Disable the stale theory | Actual RAM code executes with `AX=1144h` |
| Rebase against changed RAM | Alternate fetch executes with `AX=5555h`; RAM remains `4411` |
| Guest overwrites a RAM theory `3333` | CPU executes `AX=3344h`; ordinary stack clearing refuses conflicting bytes |
| Explicit `keep_changed` | Preserve changed low byte `44`, restore unchanged high byte to `11` |
| Native checkpoint rewind | Earlier registers and instruction bytes `1111` return; a new future repeats the guest write |

DOS access watches report after the instruction. The tests explicitly verify
that boundary rather than treating the stop as a pre-write event. Earlier
capture bytes, static instruction rows, static version count and the original
MZ file remain unchanged, including after reopening the project. Captures stay
marked `execution_proven=false`; watches, register outcomes and traces provide
the separate execution evidence. Checkpoint navigation is not deterministic
reverse execution or host-file rollback.

## Wine/QEMU PE64

`tests/fixtures/self_modifying_wine.S` is an import-only-Kernel32 PE64 console
target. Its main-image `.smc` section is readable, writable and executable.
The victim is `MOV EAX,1; RET`. A writer on a different page changes the victim
immediate, then the guest calls `FlushInstructionCache` before executing it
again. Exported markers remain outside the 15-byte overlay lookahead window;
no software execution breakpoint overlaps a modified byte.

The fixture imports only `GetCurrentProcess`, `FlushInstructionCache` and
`ExitProcess`. The separate writer and explicit self-writer allow effective
RIP-relative instructions to run in the real execution-layer scratch buffer.
Their writes must retain the original memory target after relocation.

```text
fixture SHA-256 591a22e9d9ce8a4cd25a9b5582600cce51f9f068f4fd543cbed93031d25f6ac5
QEMU 11.1.3, Linux 6.1.0-50-amd64, Wine 9.0
guest memory 4096 MiB, two vCPUs, no networking
```

`tests/test_layer_self_modifying_wine.py` checks five cases in one initial
session, restoring the immutable whole-VM checkpoint between cases:

| Case | First result | Second result | Underlying victim RAM |
| --- | ---: | ---: | --- |
| No layer or victim-page write watch | 1 | 2 | `B8 02 00 00 00 C3` |
| Execution theory returns 3 | 3 | Stale guard refuses; disabling yields 2 | Changed immediate remains 2 |
| RAM theory returns 3 | 3 | 2 after explicit `keep_changed` | Guest-written immediate remains 2 |
| Relocated writer changes its effective immediate 2 to 4 | 1 | 4 | Write lands in the original victim, not scratch RAM |
| Guest writes the value 1 already in RAM | 3 | 3 | Bytes remain original; the write watch still observes the store |

Wine access watches stop **before** the write. After observing that stop, the
test removes the watch and completes one real instruction. It checks the trace
and changed RAM together. The unlayered warmed-code control deliberately has
no victim-page guard/watch; its guest write and cache-flush sequence runs to
the next marker normally.

Wine stale execution guards raise
`DebuggerError("Execution layer RAM guard changed before execution")`, rather
than returning the DOS `layer_conflict` outcome. The target remains stopped,
the guest write is retained and the stale alternate has not executed. Clearing
the layer exposes the modified RAM; a new expected-byte definition can rebase
the theory. The test also executes a rebased value 4 while physical RAM stays 2.

The explicit self-writer starts as `C6 05 FF FF FF FF 01 C3`. Its execution
layer changes the immediate to 2. The relocated instruction completes and
writes **its own original immediate**, producing `C6 05 FF FF FF FF 02 C3` in
main-image RAM. Its trace retains original, effective and native relocated
bytes. On the next invocation the stale guard refuses. This is a pre-fetch
guard, not a write veto or automatic rollback. Same-value writes demonstrate
the corresponding limit: unchanged bytes satisfy the guard, so write-event
observation requires an access watch.

Native checkpoint restoration recovers registers, original victim/self-writer
bytes and the empty layer stack. Earlier code captures and static facts remain
unchanged. PE bounded CPU deltas admit writable **non-executable** main-image
RAM and are not used to claim restoration of modified code; this test uses a
whole-VM native checkpoint.

## Runtime and reproducibility boundaries

The installed Wine image's recorded resources did not match the current host
package. A new private runtime was prepared offline from the retained image,
appending the current guest resources. The VM's actual greeting verified the
matching source hashes. No package activation or installed image was changed.

```text
retained base SHA-256 6bb4cc83baa9e1764bf515a36a3f36f3ed4aa4813b41f6ca640e9c19db757d42
matching runtime SHA-256 13d1d88ba30639a6bb947e910e7c717126cc18ac522e06df14d2a49c44cb7cdc
```

The native Wine acceptance requires explicit `FDISBULL_SMC_WINE_QEMU`,
`FDISBULL_SMC_WINE_KERNEL`, `FDISBULL_SMC_WINE_RUNTIME`,
`FDISBULL_SMC_WINE_FIXTURE` and `FDISBULL_SMC_WINE_EVIDENCE` paths. Set
`FDISBULL_REQUIRE_SMC_WINE=1` to make missing inputs fail. Supply a new private
external evidence directory and a short external `TMPDIR` for QEMU sockets.
Run the VM test through the local heavy-job guard; the tested configuration
declares a 6 GiB aggregate peak for its 4 GiB guest. DOSBox tests use
`FDISBULL_DOSBOX` and ordinary native-test execution.

Qualification is for this DOS real-mode normal-core profile and this PE64
Wine/QEMU process. Microsoft Windows, other Wine releases, DOS protected-mode
or dynamic cores, devices/DMA, injected allocations outside the main-image
layer authority, concurrent writers and arbitrary anti-debugging/self-checking
programs remain unqualified. Runtime captures do not automatically promote
self-modified code into new static analysis. Original inputs, native states,
runtime images and raw byte-retaining databases remain outside Git/uploads.
