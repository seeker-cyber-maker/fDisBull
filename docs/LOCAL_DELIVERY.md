# Temporary local delivery — 2026-10-23

The user-designated DeepSeek project is `~/Conversions/DinoParkTycoon`. For this delivery, ZIP bundles are placed in:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/
```

The 0.10.0 candidate bundle is named `fdisbull-native-debugger-0.10.0-candidate-2026-10-23-SNAPSHOT.zip`, where `SNAPSHOT` identifies the source file manifest. Its `DELIVERY.json` records the base source commit, the uncommitted candidate status, and source/payload hashes. It does not claim a new Git commit or published release. This is a local delivery location; the emulator game directory is still supplied explicitly when launching a session.

The bundle contains the Python wheel and tool source ZIP, the DOSBox-X backend patch and upstream license, state/script documentation, source-only DinoPark verification helpers, and the recorded verification evidence. A separate `backend/native-macos-arm64/dosbox-x` entry provides the exact tested local executable. The Python packages and Git repository contain the backend source patch; the native executable is included only in this local delivery bundle.

The macOS binary uses the libraries already installed on the tested Mac. Other hosts should build the backend from the declared upstream baseline and complete patch. Native states require an exact compatible backend identity; do not mix a checkpoint made by an earlier backend binary with this one.

## DeepSeek usage

Extract the ZIP to a new directory. Use the wheel in an existing Python 3.12+ environment with the declared dependencies. The candidate now reports version `0.10.0`:

```bash
python -m pip install --upgrade --no-deps /absolute/path/to/extracted/packages/fdisbull-0.10.0-py3-none-any.whl
python -m pip check
```

Launch with the extracted backend executable and the intended local game copy. Executable permission may need restoration after extraction:

```bash
chmod +x /absolute/path/to/extracted/backend/native-macos-arm64/dosbox-x
fdisbull debug /absolute/path/to/project.fdb \
  --executable /absolute/path/to/extracted/backend/native-macos-arm64/dosbox-x \
  --game-dir /absolute/path/to/game
```

The running foreground process accepts the debugger's JSON-lines protocol. Alternatively, `fdisbull_from_delivery.py` imports the exact wheel directly using an existing dependency environment, without replacing an installed package. See [native state editing and scripting](DEBUGGER_SCRIPTS.md) and [candidate verification](VERIFICATION-0.10.md). `registers()` exposes runtime `cs` and `ip` aliases. A write watch at project `0x471a6` uses `access="w"`, with optional `length=8`; data watches require no disassembly. Execution breakpoints require analyzed, byte-verified instructions; explicit DOS seeds are now prioritized within the analysis budget.

The bundle contains no original DinoPark assets, in-game save files, native saved-state bytes, or byte-retaining project databases. Create and retain those in local working storage. Exported screenshots, bounded diagnostic traces, and manifests are included as verification evidence.

## Previous delivery

The original `fdisbull-native-debugger-2026-10-23-cd13636.zip` remains unchanged, with SHA-256 `25128411caeaad928056f8cd8e1011e1c48e70e0999be83b1a533e877be2b529`. It reports package version 0.9.0 and source commit `cd13636c5bba6755836cc5a72898661bae41755c`. The 0.10.0 candidate uses the same native backend identity; it adds the queue fix, clearer watch semantics, and the parking experiment's evidence.
