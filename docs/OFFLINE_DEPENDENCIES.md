# Offline dependency bundles

`scripts/offline_dependencies.py` builds a hash-locked wheel bundle for Linux
x86-64 / Python 3.13. It contains third-party dependencies only; `fdisbull` and
`fdisbull-player` remain separate release wheels. That separation lets a later
release reuse the previous dependency bundle when the constraints have not
changed.

The default group is the core runtime plus the `proof` extra: Capstone,
iced-x86, LIEF, Pillow and Z3. Use `--extra managed` or `--extra test` to add a
declared optional group. The selected groups are part of the fingerprint.

## Build once

Run this inside a Linux x86-64 Python 3.13 environment, normally the
`fdisbull-linux` Apple container:

```sh
python scripts/offline_dependencies.py build \
  --project-root . --output dist
```

The output is `dist/fdisbull-<version>-linux-x86_64-dependencies.tar.gz` and a
`.sha256` sidecar. The archive contains:

- `wheels/` with only compatible binary wheels;
- `manifest.json` with the constraints, resolved wheel hashes and fingerprint;
- `requirements.txt` with `--hash` pins;
- `install.sh` and `SHA256SUMS` for a no-index install.

The build never packages a source distribution. The manifest records only the
resolved wheels that were actually downloaded; the fingerprint records the
declared constraints and target, so a later release does not silently pick a
newer compatible Pillow just because the index changed.

## Diff and reuse

Before building a later release, compare the new constraints with the previous
bundle:

```sh
python scripts/offline_dependencies.py check \
  --project-root . --previous /path/to/previous-dependencies.tar.gz
```

`status: reuse` means the target, selected extras and declared constraints all
match; every file hash in the previous archive was rechecked. `status: rebuild`
includes `added`, `removed`, `version_changed`, `target_changed` and
`extras_changed` fields.

To perform the release step and require reuse:

```sh
python scripts/offline_dependencies.py build \
  --project-root . --previous /path/to/previous-dependencies.tar.gz \
  --require-reuse --output dist
```

When reusable, this copies the previous archive byte-for-byte; it does not
contact the package index or compile anything. Without `--require-reuse`, a
changed fingerprint causes a normal rebuild. The output name may change with
the release version while the package bytes and internal fingerprint remain the
same.

## Install offline

Unpack the archive on a compatible Linux x86-64 machine and run:

```sh
./install.sh /absolute/path/to/new-venv
```

The installer checks Python 3.13, verifies `SHA256SUMS`, installs only the
bundled wheels with pip's `--no-index --require-hashes`, then imports the
decoders, Pillow and Z3 and runs an equivalence/counterexample check. It does
not install the application wheels.

## Use with the full offline kit

`scripts/build_offline_kit.py` accepts the reusable bundle directly:

```sh
python scripts/build_offline_kit.py \
  --wheelhouse APP_WHEELHOUSE \
  --dependency-bundle /path/to/fdisbull-*-dependencies.tar.gz \
  --backend DOSBOX_X --sdl-lib LIBSDL2_NET \
  --source-companion SOURCE_COMPANION.tar --source-commit FULL_COMMIT \
  --dosbox-license COPYING --sdl-license SDL2_NET_COPYRIGHT \
  --backend-receipt RECEIPT.json --patch-manifest source-manifest.json \
  --output NEW_OUTPUT_DIRECTORY
```

`APP_WHEELHOUSE` contains only the `fdisbull` and `fdisbull-player` wheels; the
builder merges the verified dependency bundle, rejects duplicates, and packages
the complete wheel set into the offline kit. A dependency bundle extracted from
a previous release remains valid for the kit as long as its target and
fingerprint match the release constraints.

The generated full-kit installer accepts
`./install.sh --python /absolute/path/to/python3.13 NEW_VENV_PATH` as well as
`FDISBULL_PYTHON`. Before the payload checksum sweep it checks the interpreter,
Linux x86-64, `sha256sum`, `ldd` and every missing backend soname. The generated
`bin/dosbox` wrapper repeats that `ldd` preflight before starting the debugger,
so a missing host library such as `libncurses.so.6` is reported by name before
any native process starts. Neither bootstrap bundles CPython or the host
native-library environment layer.

## Limits

Hash verification and reuse prove byte identity and spec equality, not that a
wheel runs on a particular host. The install script performs import and Z3
smoke checks. Native backend, DOS acceptance and the project test suite remain
separate release gates. The bundle does not contain game files, saved states,
project databases or application wheels.
