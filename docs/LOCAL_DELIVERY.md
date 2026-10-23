# Temporary local delivery — 2026-10-23

The user-designated DeepSeek project is `~/Conversions/DinoParkTycoon`. For this delivery, ZIP bundles are placed in:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/
```

A bundle is named `fdisbull-native-debugger-2026-10-23-COMMIT.zip`, where `COMMIT` is the short source commit. Its `DELIVERY.json` records the full source commit and file hashes. This is a local delivery location; the emulator game directory is still supplied explicitly when launching a session.

The bundle contains the Python wheel and tool source ZIP, the DOSBox-X backend patch and upstream license, state/script documentation, source-only DinoPark verification helpers, and the recorded verification evidence. A separate `backend/native-macos-arm64/dosbox-x` entry provides the exact tested local executable. The Python packages and Git repository contain the backend source patch; the native executable is included only in this local delivery bundle.

The macOS binary uses the libraries already installed on the tested Mac. Other hosts should build the backend from the declared upstream baseline and complete patch. Native states require an exact compatible backend identity; do not mix a checkpoint made by an earlier backend binary with this one.

## DeepSeek usage

Extract the ZIP to a new directory. Use the wheel in an existing Python 3.12+ environment with the declared dependencies. The package version remains `0.9.0`, so an environment with the earlier 0.9.0 integration needs an explicit reinstall of this wheel:

```bash
python -m pip install --force-reinstall --no-deps /absolute/path/to/extracted/packages/fdisbull-0.9.0-py3-none-any.whl
python -m pip check
```

Launch with the extracted backend executable and the intended local game copy. Executable permission may need restoration after extraction:

```bash
chmod +x /absolute/path/to/extracted/backend/native-macos-arm64/dosbox-x
fdisbull debug /absolute/path/to/project.fdb \
  --executable /absolute/path/to/extracted/backend/native-macos-arm64/dosbox-x \
  --game-dir /absolute/path/to/game
```

The running foreground process accepts the debugger's JSON-lines protocol. See [native state editing and scripting](DEBUGGER_SCRIPTS.md) and [verification](VERIFICATION-STATES.md). `registers()` exposes runtime `cs` and `ip` aliases. A write watch at project `0x471a6` uses `access="w"`, with optional `length=8`; data watches require no disassembly. Execution breakpoints require analyzed, byte-verified instructions.

The bundle contains no original DinoPark assets, in-game save files, native saved-state bytes, or byte-retaining project databases. Create and retain those in local working storage. Exported screenshots, bounded diagnostic traces, and manifests are included as verification evidence.
