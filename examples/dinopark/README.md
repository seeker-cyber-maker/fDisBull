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
