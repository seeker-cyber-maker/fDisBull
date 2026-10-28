# Linux offline kit 0.20

The builder packages only explicitly selected tool artifacts, never game files, user states, or databases. It targets Linux x86-64 and Python 3.13.5. The wheelhouse must contain one compatible wheel each for fdisbull 0.20.0, iced-x86 1.21.0, capstone 5.0.9, lief 1.0.0, Pillow >=10.4,<13 and z3-solver 5.3.2.0. The fdisbull wheel and native backend must be the artifacts actually built and tested for the release; their identity is an input to the build, not something wheel metadata can establish.

```sh
python scripts/build_offline_kit.py --wheelhouse WHEELHOUSE \
  --backend DOSBOX_X --sdl-lib LIBSDL2_NET \
  --source-companion SOURCE_COMPANION.tar --source-commit FULL_COMMIT \
  --dosbox-license COPYING --sdl-license SDL2_NET_COPYRIGHT \
  --backend-receipt RECEIPT.json --patch-manifest source-manifest.json \
  --output NEW_OUTPUT_DIRECTORY
```

Repeat `--sdl-lib` for each private SDL2_net library. The receipt must bind the backend hash and fDisBull source commit to the patch hash and upstream baseline in the patch manifest. The builder records these inputs and hashes every included file; it does not itself establish that the backend was tested or that its native runtime dependencies are complete. Check the backend's `ldd` output on the target environment and run the native acceptance tests before treating a kit as validated.

The paired source companion must be independently checked against the patch manifest, including every listed patched source file and its upstream baseline, before distribution. The builder records its hash but cannot establish that it is corresponding source. Supply both archives together for GPL compliance; do not distribute the binary alone on the basis of this document. The source companion's provenance and licensing must be reviewed against the actual backend and all included libraries.

On a compatible offline machine, unpack the binary archive and run `./install.sh /path/to/new-venv`. It verifies the bundle hashes, refuses an existing destination, installs only the pinned wheels with pip's offline hash checking, checks the installed version, and performs one Z3 equivalence and one counterexample query. It does not launch DOSBox or perform the project's native acceptance suite. Those are separate release checks. The backend and private libraries remain in the unpacked bundle; `install.sh` prints their paths. The install does not need the source companion, which must nevertheless accompany redistribution.

Hashes detect accidental corruption only when the manifest or its enclosing archive is obtained from a trusted source. The installer may leave a newly created partial environment if installation fails; remove that destination before retrying.

The native Linux workflow generates the corresponding source with `build_dosbox_source_companion.py`: it archives only the pinned upstream Git tree and verifies every manifest-listed overlay file before archiving it. It then builds the binary kit, installs with no index into a fresh Python 3.13.5 environment, and calls `verify_offline_kit.py` with source-path injection disabled. That acceptance requires real Z3 results, BIOS keyboard consumption, memory readback, screenshot storage, native restore, post-restore input, and project restart. The paired source archive and license notices accompany the binary archive. `bin/dosbox` selects the private SDL2_net library automatically.
