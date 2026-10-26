# Saved experiment: DinoPark gift-price lookup

The installed 0.15.0 candidate ran a real DinoPark baseline/layer comparison on
macOS ARM64 using the tested native DOSBox layers backend. The game and pmm save
were copied into a private directory outside Git. All 192 original and copied
input files remained unchanged. No native states or project database were
exported into this evidence folder.

The driver saved the catalogue checkpoint with an execution breakpoint at
`334b:0ca3`, eight read-watch bytes at project `0x46a75..0x46a7c`, and a once-hook
at `1000:75bc`. The hook performs a checked FS-to-itself assignment so its firing
does not change the price theory. All these controls were deliberately deleted,
then the emulator and project were closed. A fresh project/session ran the
saved experiment and restored every control before each trial and afterward.

| Observation | Baseline | Execution layer |
| --- | --- | --- |
| Price-read originating instruction | `0x3414e` / `334b:0c9e` | same |
| Price loaded into AX | `0x1d4c` = **7,500** | `0x1388` = **5,000** |
| Effective guarded instruction | `8b877568` (`mov ax,[bx+6875h]`) | `8b877168` (`mov ax,[bx+6871h]`) |
| Subsequent execution stop | `0x34153` / `334b:0ca3` | same |
| Once-hook hits | 1 | 1 |
| Bounded continuation trace | 16 fetch records | 16 fetch records |

With BX=4, the alternate displacement selects the 5,000 entry instead of the
7,500 entry. The original RAM instruction and the price table remain unchanged.
The catalogue still advertises the original list prices; the access stop and
register snapshots establish the changed lookup value. This is not a purchase
or a claim that one lookup patch changes every later price consumer.

The route asserts the read-watch instruction and the subsequent execution
breakpoint explicitly. `controls-and-hooks.json` contains three actual
`restore-experiment` events and two once-hook hits, each at hit count 1. Final
restoration leaves the eight watch bytes and execution breakpoint armed, the
once-hook present at hit count 0, and the baseline layer stack active.

The baseline and layer reports retain their script outcomes, intermediate
registers, stop reasons, 8px click frames, completed screenshots and bounded
traces. `comparison.json` reports captured differences. DOS traces are
pre-execution fetch records with the final record pending; they are not an
instruction-by-instruction reverse execution log. All exports were read from
the stored project after the emulators had exited and the project was reopened.

`PROVENANCE.json` binds source and tested-wheel entries and records exact file
copies. `SHA256SUMS.json` covers this final selected evidence. The `verification/`
subdirectory includes native test receipts and a separately labeled **authored
PE64 fixture**, whose counter changed from 8 to 10 and restored to 7; it is not
a Windows version of DinoPark.
