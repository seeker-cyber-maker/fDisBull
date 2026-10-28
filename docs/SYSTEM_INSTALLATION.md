# fDisBull 0.20.0 — shared Mac installation

This installation uses source commit `4f7791baa2cca7bb3c62fc9a997dc8f86316c98d`, tag `v0.20.0`. It is qualified on this Mac; native executables depend on existing host libraries and are not claimed portable to arbitrary Macs. The active version is selected by `/Users/Shared/fDisBull/current`.

Version 0.20.0 includes typed input macros and bounded movement, scene geometry and content readiness, explicit DOS COM support, watch-only dot-mode, a partial AGI inspector, and bounded Z3 model checks. Frame freshness alone does not establish readiness, and bounded proofs establish only their stated model and assumptions. Screenshot hooks and scene probes currently support direct DOSBox. Dot-mode requires a compatible backend and an accessible display; interactive window behavior was not qualified as part of this installation. C/C++ decompilation, UIL engines and automatic route planning remain unimplemented proposals. See the packaged documentation for details and limits.

`RUNTIME.json` identifies version-bound direct DOSBox, DOS-in-QEMU, Wine/QEMU and raw-machine profiles. The Wine guest uses a retained, audited pristine runtime input whose required resources match this package. The DOS guest was rebuilt from that input using the current package broker and exact tag-CI Linux backend, then audited. Three profile doctors passed native-state restore; the raw-machine boot and GDB checks passed separately.

The previous 0.19.0 installation remains available for checkpoints bound to its backend. After activation, `share/rollback-to-0.19.py` can select it only while 0.20.0 remains current. Existing project environments and running processes are not migrated.

The three Python/tool distribution packages and release checksums and verification document are retained under `share/packages`. The Linux offline kit and source companion are retained as published assets and in the release artifact cache, not duplicated in this Mac prefix. `share/verification/ASSET-READBACK.json` records all seven published assets and their identities.

Keep game files, saved games, native states and project databases outside this installation. Verify the sealed payload with the managed interpreter and `share/verify-system.py`.

This tool is not currently suitable for malware analysis or security work.
Must bring your own weapons. I have only done this once before. Safety not guaranteed.

The [0.20.0 GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.20.0) is published. All seven assets were downloaded and matched against their recorded identities.
