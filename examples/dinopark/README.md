# DinoPark: external-file and shared-label example

This directory illustrates fDisBull with one real reverse-engineering investigation. It is separate from the tool and excluded from wheels, source distributions, and standalone tool ZIPs.

Included: authored structures in `layouts/`, field/resource audits in `notes/`, and selected historical disassembly/typed-data renders in `images/`.

The original executable, `VARS.DAT`, `DINOSG.*` saves and the byte-retaining analysis database are local inputs. Keep your own copies in `local/`, which is ignored by Git. The original database contained executable bytes and is excluded from public history.

## Create a local project

From the repository root, after placing your own inputs in `examples/dinopark/local/`:

```bash
fdisbull import examples/dinopark/local/DINOPARK.EXE examples/dinopark/local/dinopark.fdb --load-segment 0x1000
fdisbull analyze examples/dinopark/local/dinopark.fdb --max-instructions 10000
fdisbull analysis-status examples/dinopark/local/dinopark.fdb
```

Repeat bounded analysis as needed and inspect pending work. A budget stop is not convergence. Older databases may need `refresh-dos-state`; see the external-file guide.

## Attach and type the data

```bash
fdisbull attach-file examples/dinopark/local/dinopark.fdb examples/dinopark/local/VARS.DAT --kind resource
fdisbull attach-file examples/dinopark/local/dinopark.fdb examples/dinopark/local/DINOSG.000 --kind save
fdisbull define-type examples/dinopark/local/dinopark.fdb ConcessionWords examples/dinopark/layouts/ConcessionWords-layout.json
fdisbull define-type examples/dinopark/local/dinopark.fdb StaffWords examples/dinopark/layouts/StaffWords-layout.json
fdisbull define-type examples/dinopark/local/dinopark.fdb SaveFields examples/dinopark/layouts/SaveFields-layout.json
fdisbull apply-file-type examples/dinopark/local/dinopark.fdb DINOSG.000 SaveFields --offset 0 --name save
fdisbull file-data examples/dinopark/local/dinopark.fdb DINOSG.000 --offset 3872
```

`vars-layout.json` preserves the parameter-table layout with qualified field names. A matching numeric value does not prove which resource field supplies an instruction operand.

## Link only verified coordinates

The reported concession block occupies save bytes 3872–3879 and four adjacent 16-bit words at `DS:6FA6–6FAD`. With the investigation's `DS=0x4020` static load context, its linear address is `0x471A6`. A different load context needs a different address.

After verifying that correspondence for your exact inputs, use `link-labels` and `rename-file` as shown in [EXTERNAL_FILES.md](../../docs/EXTERNAL_FILES.md). `file-reference` records an instruction-to-file relationship; `link-labels` records corresponding field identity. The accessing instruction keeps a separate identity.

The notes and renders are historical evidence, not proof that every fact is current in a newly created project. No emulator, original game, or complete economic simulation is included.

## Project debugger replay

The 0.9.0 integration was verified through fDisBull's public JSON interface with the actual game. It skips guest time using native fast-forward, verifies a relocated disassembly breakpoint, records a 512-instruction input trace, saves PNGs inside the project, and checks bounded timeout/pause and export after restart. See [DOSBOX_DEBUGGER.md](../../docs/DOSBOX_DEBUGGER.md).

```bash
python examples/dinopark/verify_debugger.py \
  --executable /path/to/patched/dosbox-x \
  --game-dir /path/to/dinopark \
  --output /path/to/new-evidence-directory
```

The output includes `dinopark.fdb`, which retains the original game bytes and is a local input/evidence file, excluded from public packages and Git history. The script itself includes no game assets.

## Editable DOSBox machine states

`verify_states.py --executable PATH --game-dir DIR --output NEW_LOCAL_DIR` captures a native DOSBox state, restores it after emulator restart, forks it with checked RAM edits, reinjects the derivative, hits an execution breakpoint, captures a trace, verifies CPU data watches, and restores the unchanged parent. Native state bytes stay embedded in the local `.fdb`. This is distinct from loading a DinoPark `DINOSG` file through the menu; that menu route is used only to prepare the test fixture. See [state editing and scripting](../../docs/DEBUGGER_SCRIPTS.md).

## Parking purchase observation

The [preserved parking experiment](evidence/parking-commit-2026-10-23/RESULT.md) establishes the staged-to-live counter copy during shop OK for the available pmm save. It includes bounded traces, controls, screenshots, and file hashes; game files, native state bytes, and the local database are excluded. [Replay instructions](../../docs/PARKING_COMMIT.md) explain how `replay_parking_commit.py` validates another wheel against the corresponding private checkpoint in a fresh emulator session.

## Published 0.11.0: gift price and reversible code layers

[The gift-price investigation](notes/CONCESSION_PRICE_0.11.md) traces 7,500 to the executable-initialized WORD at project `0x46a79` / static `4020:6879`, then follows selection, staged cash and shop-OK accounting. [The companion replay](verify_concession_price.py) uses the delivered wheel/backend, restores native checkpoints in fresh emulators, compares an execution layer on/off, and drives the catalogue with 8px `click-frame` grids. Original instructions charge 7,500; the three-site layer charges and accounts for 5,000 while code RAM and the price table remain unchanged. A declared native-state cash fork makes both trials affordable; original checkpoints and inputs are preserved. Private game/database/state output must remain outside Git.
