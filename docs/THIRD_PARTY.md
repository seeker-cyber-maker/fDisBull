# Third-party engines and recovery provenance

Dependencies are installed separately; their upstream licenses apply. This archive does not vendor their source or native wheels.

| Component | Role | Source |
| --- | --- | --- |
| iced-x86 1.21.0 | Native x86 16/32/64-bit decoding | [icedland/iced](https://github.com/icedland/iced) |
| Capstone Python 5.0.9 | Native ARM64 decoding | [capstone-engine/capstone](https://github.com/capstone-engine/capstone) |
| LIEF 1.0.0 | Executable loading and metadata | [lief-project/LIEF](https://github.com/lief-project/LIEF) |
| Pillow | GUI-free PNG export | [python-pillow/Pillow](https://github.com/python-pillow/Pillow) |
| pytest | Test execution | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |

## CHimpREC methodology

Offline import recovery attributes its candidate-slot/export-resolution approach to [TiGa's CHimpREC repository](https://github.com/seeker-cyber-maker/CHimpREC), pinned to [commit 50495c0b9962130c17939bfbef806aecd41040ad](https://github.com/seeker-cyber-maker/CHimpREC/tree/50495c0b9962130c17939bfbef806aecd41040ad). The same provenance is returned in recovery receipts.

`chimprec.py` is an offline adaptation over supplied mapped bytes and export-address evidence. It retains ambiguous aliases and reports bounds. It does not bundle the Windows application, attach to a live process, discover runtime modules, follow forwarders or rebuild a fixed executable/import table. Static PE import-directory parsing is performed separately through LIEF.

The first-party project has no distribution license selected in this handoff. No upstream relicensing or redistribution permission is asserted. Select an appropriate first-party license before distributing it as an open-source project.
