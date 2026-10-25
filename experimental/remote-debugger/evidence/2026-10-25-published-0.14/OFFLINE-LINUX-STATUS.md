# Offline Linux installation and qualification

The reported target is Linux x86-64, CPython 3.13.5 at `/opt/pyvenv/bin/python3`.
This kit addresses the missing capstone, iced-x86, lief/Pillow and SDL2_net
requirements with genuine hash-locked wheels and a private loader/library set.
It does not replace a system library or the existing Python environment.

Create a new environment outside the delivery:

```bash
/opt/pyvenv/bin/python3 INSTALL-OFFLINE.py --venv ../fdisbull-014-venv --with-tests
../fdisbull-014-venv/bin/fdisbull --help
../fdisbull-014-venv/bin/python fdisbull_delivery.py
```

Use `dos_options()` on Linux; it selects `backend/linux-amd64/dosbox-x-offline`.
That wrapper starts the unchanged tag-CI ELF through its private loader and
libraries, including SDL2_net. Its configuration does not disable CRC checks.
The compact Linux kit contains direct DOS debugging; QEMU/Wine runtime images
and Mac executables are supplied in the full delivery instead.

In a separate, networking-disabled Linux CPython 3.13.5 environment, the offline
installer completed, all real engines loaded, the CLI inspected an authored PE,
and all needed DOSBox libraries resolved from the private bundle. The native
suite reported **49 passed, 2 failed**. Actual breakpoints, watches, layers,
screenshots/clicks, traces, persistence and image exports were exercised.

**Native-state restoration is not fully qualified in this emulated probe.**
Two state cases produced a bad CRC in the native ZIP `Vga` record. The same
failure reproduced with the raw tag-CI ELF and system libraries. Baseline CPU
and uncompressed-state experiments did not resolve it. Failed receipts are
retained under `verification/offline-linux313/`; no invalid state was repaired
or accepted to manufacture a passing result.

The original Linux tag CI separately passed all 38 layers/endpoint cases, and
the Mac delivery passed all 51 clean-offline checks. These scopes are distinct.
The actual external `/opt/pyvenv` environment has not been modified or verified
here. Run the installer and local checks there before claiming that installation
works. For state-dependent work, use the separately qualified Mac backend until
this additional Linux/TCG state issue is resolved or validated locally.

No games, game saves, captured emulator states or project databases are included.
