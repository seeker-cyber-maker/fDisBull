# Syndicate graphics-contract continuation

This source-and-evidence bundle contains no original game bytes, decoded assets, raw native traces or byte-retaining databases. Keep all generated private work outside Git. `REPORT.md` describes results, limitations and the uncompleted GitHub publication.

## Read first

- [Report](REPORT.md): new findings, exact source coordinates, evidence scope and implementation recommendations.
- [Knowledge Pack](Knowledge_Pack.md): compact continuation handoff.
- `evidence/continuation-audit.json`: byte/length audit, stored counts, native outcomes and preserved assets.
- `evidence/graphics-native-cases.json` and `evidence/sprite-native-cases.json`: sanitized 176-case and 86-case ledgers. Private raw receipt hashes identify evidence but do not recreate those withheld payloads.
- `evidence/resource-domains.json`: source resource counts and shared-chain identities.
- `pr/`: the three intended repository files, PR body and title. `diagnostic-graphics-friction.patch` adds only those three files.

## Run the source-free arithmetic checks

```sh
python tools/check_contract_models.py --require-z3
```

This requires optional `z3-solver`; the recorded run used 5.3.2.0. Without `--require-z3`, missing Z3 is reported as unavailable. The exhaustive standard-library check remains available. This script is not a native-code or production-analyzer conformance test.

## Reproduce original-code experiments privately

These commands require your exact owned original MAIN.EXE and installer, the privately installed fDisBull 0.26.0 and its Capstone/iced-x86 dependencies, optional Z3 for source-bound arithmetic checking, Linux x86-64 with permitted ptrace/compatibility execution, and a native C compiler. The C launcher is authored host support, not a DOS emulator or security sandbox. Do not run arbitrary untrusted binaries with this harness.

Choose a new directory outside Git. Set `PY` to that private environment's Python and `BUNDLE` to this extracted bundle. `WORK` is an absolute private path with no existing `runtime` directory:

```sh
export PY=/absolute/path/to/private-venv/bin/python
export BUNDLE=/absolute/path/to/this-bundle
export WORK=/absolute/path/to/new-private-study
export SYNDICATE_PRIVATE="$WORK/runtime"
export SYNDICATE_RESEARCH="$WORK"
export SYNDICATE_INSTALLER=/absolute/path/to/owned/setup_syndicate_plus_1.01_gog_v2_\(85807\).exe

"$PY" "$BUNDLE/tools/prepare_private.py" /absolute/path/to/owned/MAIN.EXE "$SYNDICATE_PRIVATE"
cc -O2 -Wall -Wextra -o "$SYNDICATE_PRIVATE/slice_loader64" "$BUNDLE/tools/slice_loader64.c"
"$PY" "$BUNDLE/tools/recover_selected_assets.py"
"$PY" "$BUNDLE/tools/decode_resources.py" "$SYNDICATE_PRIVATE/game" "$SYNDICATE_PRIVATE/decoded"
"$PY" "$BUNDLE/tools/graphics_matrix.py"
"$PY" "$BUNDLE/tools/sprite_matrix.py"
"$PY" "$BUNDLE/tools/qualify_graphics_bounds.py"
```

The recovery helper reuses the supplied manifest's exact hashes and labels. It is a bounded zlib-payload recovery path for this exact installer, not a generic Inno Setup extractor or new validation of original installer path semantics. The probes and decoder create private pixel/source-containing receipts. Do not publish them. The two matrix output directories refuse existing paths, so use a fresh prepared runtime rather than overwriting prior trials.

The bundled probe harness is byte-identical to the tested research harness. The matrix scripts differ only in the local import filename. The packaged source-binding checker was rerun successfully. The entire 262-case matrix was not redundantly rerun for packaging.

## Reproduce static candidate discovery

Use the privately retained **22,910-instruction** checkpoint from the earlier LE scope study, not the already-expanded database:

```sh
"$PY" "$BUNDLE/tools/replay_candidates.py" /private/syndicate-baseline.fdb /private/new-replay.fdb
```

The merged replay plan was tested in a fresh destination and exactly reproduced all 68,186 stored instruction rows. It intentionally pins fDisBull 0.26.0 and uses a private candidate queue seam. Do not open this legacy byte-containing database as a publication artifact or mistake it for the newer schema-9 external-object format. No checkpoint is distributed here.

## Publish the prepared PR

No PR was created by this session. From a clean, authenticated checkout of `seeker-cyber-maker/fDisBull`, the patch can be applied with `git am`, reviewed and pushed; `PUBLISH_PR.sh` provides a guarded GitHub CLI route. The script was syntax-checked, not executed against GitHub. It requires `gh` authentication and explicit execution by the operator. It does not merge or release anything. The patch was checked by applying it in a separate local Git repository and comparing every resulting file.

## Attribution

The RNC reader and its decoder wrapper are retained from the earlier reference-guided study. `tools/rnc1.py` documents the FreeSynd-derived GPL provenance. `LICENSE-GPL-2.0.txt` is included. The new probe/matrix/model scripts are authored research tools. The independent pixel and arithmetic oracles are source-informed; they are not blind rediscovery.
