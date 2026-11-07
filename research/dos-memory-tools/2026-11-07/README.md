# DOS memory-tool investigation helpers

These authored helpers make the Game Wizard fleet and bounded DESQview QEXT
investigation reproducible from caller-supplied originals. They are standalone
research commands, outside the shipped `fdisbull` CLI/API and wheel. The general
before/patch/after interface remains an integration task.

The contribution's merge request carries the investigation summary and report
handoff. Historical receipts retain their original tool versions and code
identities; they are not relabeled as runs of these revised helpers. Use this
directory's source for new experiments. In particular, the decoder witness now
requires complete container coverage, and native runners now enforce their
completion and whole-output contracts.

## Boundaries and dependencies

- Supply your own original archives and programs. No target files are embedded
  or automatically downloaded by these helpers.
- Keep originals, extracted files, FDBs, object stores, emulator states, and raw
  runtime receipts outside Git. Generated JSON is not automatically safe to
  publish; review a closed projection under `docs/EXTERNAL_TARGETS.md`.
- Each extraction or report command requires a new output location. Native
  commands execute originals only in private copied directories and require an
  explicit emulator path.
- The static helpers use Python 3.12+ and the standard library. RAR intake also
  needs system `libarchive`. Original-instruction witnesses need Unicorn 2.1.4.
  Native DOS runs additionally need fDisBull, its agent-capable DOSBox-X backend,
  GNU binutils to build the authored wrappers, and Tesseract for prompt checks.
- Inputs, process completion, output identity, publisher provenance, and whole
  program compatibility are separate claims. A successful witness proves only
  the contract described below.

Run commands below from this directory, replacing `/private/...` with private
paths selected for the task. No command repairs or patches an original input.

## Exact byte comparisons

```sh
python compare_bytes.py /private/before /private/after --output /private/comparison.json
python compare_bytes.py --controls --output /private/comparator-controls.json
```

Inputs are capped at 1 MiB each. The report includes fixed-offset changes,
explicit EOF differences, monotone byte alignment, exact equal-span hashes, and
complete bidirectional reconstruction checks. Unique 64-byte anchors retain
obvious insertion/deletion shifts; small gaps use bounded ordered matching and
large unmatched gaps remain opaque replacements. The algorithm does not claim
minimum edit distance, move recovery, instruction matching, or semantic
equivalence. Its evidence checks remain active under `python -O`.

## Official Game Wizard 3.0a update

```sh
python check_gw_update.py --before /private/before --patch /private/GWPRO30A.UPD \
  --observed-output /private/native-output --candidate-after /private/preserved-after \
  --output /private/update-witness.json
```

This witness accepts the exact inspected UPD hash. It retains 25,207 bytes of
the predecessor's `INSTALL.PRO`, then takes its suffix and the complete `GW`
from the observed payload slices. Both complete predicted files are compared
with the observed updater output. The independent candidate comparison is a
separate result: inherited predecessor differences need not indicate an updater
failure. Exit 1 means the observed output does not equal the reconstruction.
This is a qualified recipe, not a generic vendor-patch parser.

## GW32_FIX configuration witness

```sh
python check_gw32_fix.py /private/GW_FIX.EXE --target /private/before/GW.CFG \
  --candidate-after /private/after/GW.CFG --report /private/fix-witness.json
python check_gw32_fix.py /private/GW_FIX.EXE --controls --report /private/fix-controls.json
```

The exact patcher identity pins the six-byte table format and its position.
The witness checks every expected byte before reconstructing an in-memory
result. A guard failure or unequal supplied candidate gives a nonzero exit.
The whole-file comparison also checks changes outside the patch byte and EOF.
Its strict rejection of a short configuration is a verifier safeguard; it does
not reproduce the original patcher's unchecked short-read behavior. The
original malformed MZ size declaration is preserved.

## Windows 0.85 container and original decoder

```sh
python intake_versions.py /private/archive-directory /private/new-versions
python unpack_win085.py /private/new-versions/win085/W32GWIZ.EXE /private/new-payload
python verify_createinstall_decoder.py /private/new-versions/win085/W32GWIZ.EXE \
  /private/new-payload/inventory.json /private/new-decoder-witness.json
```

The target-specific reader accepts the inspected installer hash. It validates
all framing, names, directory nesting, lengths, EOS endpoints, and the final
container endpoint before writing eight installed files plus the installer
engine DLL. `createinstall_decoder.py` implements the recovered bounded
adaptive-Huffman/LZ stream algorithm. No stored payload CRC was identified.

The separate witness re-parses the complete pinned container and requires the
supplied inventory to match all nine streams in order, with exact identities
and extents. Empty, partial, duplicate, reordered, or altered inventories fail.
Caller JSON never chooses emulation allocation sizes or compressed bounds.
It executes only the original decoder slice and local helpers under an authored
flat 32-bit context with bounded allocation callbacks. Every stream must reach
the exact return endpoint within the time/instruction budgets and match every
decoded byte and consumed-bit endpoint. This does not start the Windows
installer, application, or a Windows process.

## Professional archive and disk lineage

```sh
python intake_pro.py /private/archive-directory /private/new-pro/extracted
python inspect_pro_disks.py /private/new-pro/extracted /private/new-pro/disks
python compare_pro_lineage.py /private/new-pro /private/pro-lineage.json
```

The intake scripts expect the supplied archive filenames listed in their source.
ZIP/RAR members retain separate container and extracted-file identities. FAT12
intake validates geometry, both FAT copies, allocated chains, bounds, cycles and
cross-links. The DFI offset of 2,048 bytes belongs to this input profile; this is
not a universal DFI reader. Compare logical files separately from unused/bad
clusters. File equality does not authenticate a publisher or establish a
pristine distribution.

`intake_versions.py` inventories the older DOS/Windows ZIPs and nested ZIPs with
path, type, count, depth, and byte bounds. Its executable-header helper keeps
32-byte DOS MZ headers distinct from headers containing `e_lfanew`.

## Bounded DESQview QEXT branch experiment

```sh
python qext_branch_probe.py /private/dv242/QEXT.SYS /private/dv280/QEXT.SYS \
  /private/qext-branch-witness.json
```

The probe pins both original SYS hashes. It runs 256 authored character inputs
per source through a selected original instruction slice, stops before either
branch destination, and checks the branch predicate and selected registers.
DF=0 and the chosen memory/register context are experiment inputs. The report
keeps arithmetic-flag differences distinct from branch equality. This does not
qualify the full driver, DESQview scheduling, or an original QEMM boot.

## Native patch experiments

Build each authored wrapper independently; its exact bytes are pinned by the
matching runner because the completion labels are part of the experiment:

```sh
as --32 -o /private/fix_bootstrap.o fix_bootstrap.S
ld -m elf_i386 -Ttext 0x100 --oformat binary -o /private/FIXBOOT.COM /private/fix_bootstrap.o
as --32 -o /private/patch_bootstrap.o patch_bootstrap.S
ld -m elf_i386 -Ttext 0x100 --oformat binary -o /private/PATCHBOOT.COM /private/patch_bootstrap.o
```

Select private 0700 stores outside Git/symlink ancestry before using fDisBull:

```sh
export FDISBULL_TARGET_STORE=/private/objects
export FDISBULL_OUTPUT_ARTIFACT_DIR=/private/output-artifacts
python run_fix_experiment.py --patcher /private/GW_FIX.EXE \
  --config /private/original/GW.CFG --bootstrap /private/FIXBOOT.COM \
  --emulator /private/backend/bin/dosbox --case real --output /private/new-native-fix
python native_patch_experiment.py --before /private/before --patch /private/official-patch \
  --candidate /private/preserved-after --bootstrap /private/PATCHBOOT.COM \
  --emulator /private/backend/bin/dosbox --output /private/new-native-update
```

The configuration runner also supports `already_fixed`, `wrong_byte`, `short`,
and `missing`. These are explicit derivatives of the pinned real configuration.
The short case qualifies the recorded 16-byte fixture only.

Native success requires the exact armed completion breakpoint and runtime
address, matching final CS:IP, and the complete expected file manifest.
Unexpected modifications, timeout, wrong stop, or wrapper failure produce a
failure receipt and nonzero exit. DOS exit AL alone is insufficient, and a frame
captured immediately after a stop may still display the earlier prompt. The
vendor updater uses a directory-backed C: drive and an authored A: alias; this
is not a physical-floppy qualification.

The vendor runner admits three exact `GW`/`INSTALL.PRO` pairs: the supplied
3.0 donor, the preserved 3.0a disk, and the donor-updated 3.0a lineage. Admission
does not itself qualify execution of a profile. Auxiliary predecessor files
are copied from immutable snapshots and must remain byte-identical.

## Local regression selection and integration work

From the repository root:

```sh
python -m pytest -q tests/test_dos_memory_research.py tests/test_dos_memory_native_witness.py
```

The tests use authored inputs and metadata, with no original corpus embedded.
They cover identity/extent rejection, incomplete decoder inventories, changed
bootstraps, wrong native stops, complete output effects, byte-alignment
reconstruction, archive path rejection, and short MZ header interpretation.
Reproducing original-program results additionally requires the private inputs.

Future production integration should expose separately qualified stages for
container intake, exact file comparison, patch reconstruction, and original
execution. Keep unmatched regions and unsupported formats explicit. For a
future DESQview/QEMM memory-search workflow, attach execution mode, task and
mapping identity to captured addresses before comparing snapshots. These
helpers do not yet implement that runtime tracking or a DESQview scheduler
observer.

The inspected fleet is now a regression corpus. Reserve different inputs for
future blind qualification.
