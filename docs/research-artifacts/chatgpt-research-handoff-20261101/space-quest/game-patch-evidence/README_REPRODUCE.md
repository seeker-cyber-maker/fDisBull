# Reproduce the Space Quest game-patch study

This package contains analysis tools and receipts, not games, installers, fonts,
native checkpoints or a production fDisBull implementation. It has two separate
tracks: the supplied GOG updater's target data, and five upstream ScummVM
Space Quest VGA script patch recipes. The latter are not part of the identified
GOG replacement manifest. The old GOG build remains unavailable.

## Inputs and environment

Keep the following user-owned files in an input directory:

- `patch_space_quest_1_-_the_sarien_encounter_2.2_galaxy_hotfix_(20261)_to_2.2_GOG_v2_(88857).exe`
- `setup_space_quest_1_-_the_sarien_encounter_2.2_gog_v2_(88857).exe`

The extractor requires their exact recorded SHA-256 identities and refuses a
different installer. Python 3.13.5, pycparser and GCC 14.2.0 were used. A C11
compiler called `gcc` is required for the compiled check. The tools use only
local files and never execute Windows setup or game code. They are bounded
research probes, not hardened arbitrary-input parsers. Do not use Python `-O`:
the inherited extraction scripts use assertions for some integrity checks.

## Run in a new private directory

Extract this package outside a Git checkout. The `intake` output directory must
not exist. Set INPUT_DIR to the directory holding the two installers, then run:

```sh
python prepare_sq_intake.py --input-dir "$INPUT_DIR"
python sci_extract.py
python compare_game_patches.py
python verify_generated_c.py
python verify_patch_oracles.py --input-dir "$INPUT_DIR"
python make_report.py
```

`prepare_sq_intake.py` is a portability wrapper around the original extraction
functions; it selects only the two Space Quest inputs and makes temporary
read-only file references. `bootstrap_intake.py` is retained from the earlier
three-installer study and also supports that original input set. Only the
Space Quest input set is needed by this wrapper.

The `intake/` and `resources/` folders generated during reproduction contain
licensed game data. Do not publish them or add them to fDisBull. Selected
before/after byte spans appear in the bounded generated C verifier and analysis
receipts. The public PR addition contains the sanitized report only.

Running the checks again replaces the packaged `results/` files and timings.
Keep an untouched copy of the evidence package to retain the original receipts.
`pilot_timing_superseded.json` is an earlier run, deliberately excluded from the
final reported timings because the C-rendering saved-read fix followed it.

## What is tested

- Five patch signatures must match exactly once in the selected code blocks.
- Candidates must equal the specified transformation; mutations inside or
  outside the declared writes must be rejected.
- All original bytes outside those writes remain unchanged.
- Twelve isolated before/after effect blocks are compared over 65,536 selected
  numeric inputs each, plus ten additional branch checks. This is not exhaustive
  validation of full machine state or an original-interpreter/game replay.
- The old object/numeric ID comparison remains explicitly unresolved.
- C lifting and the byte-stream test interpreter share stated property-call
  summaries. The additional implementation is not an independent native oracle.
- The second LZW decoder checks the same resources using a different algorithmic
  structure but the same documented format profile.

The recorded GCC invocation completed with two misleading-indentation warnings
in the compact VM switch. They are preserved in `c_compile.stderr`; there is no
warning-free build claim. The selected model tests passed.

Three recipes have a recorded ScummVM v2.2.0 Git blob identity. The bar/Orat
recipes were obtained through a retrieved master excerpt, not independently
bound to an immutable upstream commit. The report retains that provenance gap.

## PR delivery status

`PR20-game-patch-study.patch` adds only
`docs/GAME_PATCH_DIFFERENTIAL_STUDY.md`. It has been checked with `git apply
--check` in a fresh repository. It was NOT pushed to GitHub in this turn:
the exposed GitHub connector has read operations but no create/update action.
Do not confuse a prepared patch with an opened or updated remote PR.
