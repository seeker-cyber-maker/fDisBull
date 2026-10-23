# 0.11.0 verification and release gates — 2026-10-23

Version 0.11.0 consolidates the layered-code and screenshot/click development snapshots without rewriting their receipts. Release promotion requires the committed source to pass both the [ordinary Linux tests and package checks](https://github.com/seeker-cyber-maker/fDisBull/actions/workflows/ci.yml) and the [native Linux acceptance matrix](https://github.com/seeker-cyber-maker/fDisBull/actions/workflows/native-debugger.yml). Inspect the run's commit identity and conclusion; a successful earlier version or a skipped native suite does not qualify the release.

## Native source and acceptance profiles

Both profiles start at DOSBox-X `029bd65c5dcc7cdc7f2e14e35278620d9707d969`. The established complete patch is SHA-256 `26ca8457aee6b2369a901c8fab59b89a3fe4bc2f40c72d4830571146eef535ce`; the layers complete patch is SHA-256 `fed837151e85fa1d59e1630fc75be92f7635c8572c5e7274dc1d5bac1407060f`. Independent replay matched all 27 declared changed source files in each profile. CI repeats that check before compiling the backend, records the new Linux executable identity and retains JUnit/log artifacts.

The established backend runs `tests/test_debugger.py` and `tests/test_screenshot_grid.py`. The layers backend also runs `tests/test_code_layers.py`. Both use `--require-native`, which rejects missing or unusable executable paths before collection. Actual integration tests reject incompatible protocol/CPU behavior. The ordinary suite continues to permit native skips when no backend is configured.

The tested local Mac layers executable is SHA-256 `0876e686d6a85f8c1b790db03314b81f471f5a5791dcad4929b90b63a1ebeced`. The established Mac executable remains `e749b6e50775de2807c2515f83e455dc705cdf6ddcdfb257e781f215d987865a`. Native compatibility is tied to the actual executable/profile and mounted input manifest; these Mac hashes are not the identities of future Linux builds.

## Preserved runtime evidence

[Initial layer acceptance](VERIFICATION-LAYERS.md) and [later grid/click evidence](../experimental/dosbox-x/layers/evidence/2026-10-23/grid8-followup/verification.json) retain their original development version and source identities. They demonstrate:

- Alternate instruction bytes execute while guest data reads and a guest self-code CRC see original RAM.
- A guest integrity check detects a RAM patch; entry/exit hooks restore originals for the check, then re-enable the experiment.
- Guarded stack composition/removal, runtime code snapshots, branch helpers and fetch-only caves with normalized far returns.
- Compatible native checkpoints restoring both views in a fresh emulator; original static byte versions remain isolated.
- Actual DinoPark traces taking different successors for an observed `JE` versus layered `JNE`, with underlying code RAM unchanged.
- An eight-pixel grid and marked OLD GAME click reaching the Load Game dialog in one public script request. Clean frames, source hashes and native coordinates remain retained after restart.

All 192 game inputs and the existing user grid helper remained unchanged. Original game files, machine-state payloads and byte-retaining project databases are excluded from Git and distributions. Selected screenshots and bounded traces are diagnostic evidence, not packaged game inputs.

## Claim limits

The pre-release Mac full suite reported 759 passed, 3 skipped, 2 failed and 23 setup errors. All 25 failing/error identities matched the 0.10 Mac baseline for Linux ELF fixture compilation on Apple's toolchain; that full Mac suite is not globally green. Linux acceptance must come from the actual release-commit workflow results.

Execution overlays are scoped to normal-core real-mode instruction fetch and guarded conventional RAM. There is no automatic static reanalysis/xref rebuilding, instruction rewind, general protected-mode support, zero host overhead or security-sandbox guarantee. Checkpoints do not roll back mounted host files. A changed DinoPark branch is a bounded control-flow observation, not proof of a valid complete game transaction or execution of DinoPark's own integrity routine.
