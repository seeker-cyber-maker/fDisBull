# Verification receipt — fDisBull 0.9.0 development

This is a local development receipt, not a publication or release assertion.

## Project debugger

Native macOS Apple Silicon, CPython 3.13.14, the declared Python dependencies, and the patched SDL2/heavy-debug DOSBox agent were used. `tests/test_debugger.py` passes **6 tests** with a real emulator selected by `FDISBULL_DOSBOX`. Coverage includes:

- Refusing source hash mismatch and patched versions before spawning a process.
- Requiring foreground server ownership for live CLI requests.
- Translating a stored disassembly breakpoint from the project load segment to the observed runtime segment and verifying live code bytes, including relocated instruction operands.
- Refusing a breakpoint after a deliberate runtime-byte mismatch without changing the static instruction.
- A real breakpoint stop, native trace addresses, and PNG capture.
- Guest-time fast-forward and host-time timeout, with paused state and normal speed restored.
- Embedded artifacts surviving Project/emulator restart; export hash/signature checks and rejection of project overwrite.
- Runtime evidence remaining on the original version, with no silent inheritance into a patched child.
- Foreground JSON server EOF stopping/reaping its emulator.

The full `python -m pytest -q --tb=short -ra` run with real debugger tests enabled returned **722 passed, 3 skipped, 2 failed, 23 errors**. The two failures and 23 setup errors match the established baseline: Linux ELF fixture construction invokes Apple's compiler/linker, which produces Mach-O or rejects GNU flags. No new failing test was introduced. The six focused tests were rerun after final address annotations and lifecycle cleanup changes and passed.

The earlier native backend fixture acceptance also passes after adding the timing RPC: CPU trace, breakpoint, registers, memory guards, 320×200/640×480 PNGs, palette-only changes, absolute INT33 input/callbacks, clipping, and stale-mode rejection.

## Actual game through the public fDisBull API

`examples/dinopark/verify_debugger.py` passed on the final integration code. It drove a foreground `fdisbull serve` process, not a separate ad hoc emulator API:

- Exact game executable SHA-256: `2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
- Native DOSBox emulator SHA-256: `0f83e85df107ab4a502d3e973a53f8a15f1e9d3e36d08896cab92aefbe449902`.
- Requested skip: 10,000 guest milliseconds; observed **10,305 guest ms in 447.717 host ms**. Speed was restored afterward. These measurements describe one run, not a throughput guarantee.
- Project disassembly `1000:75bc` was translated to runtime `0824:75bc`, its bytes `b80300` were verified, and it triggered an actual breakpoint with mapped project address `0x175bc`.
- A 512-event trace captured the game consuming the New Game click. Trace events include raw runtime identity and project address annotations; driver/BIOS events stay unmapped.
- Input returned BX=1, CX=150, DX=160; the UI advanced through the bank, city, and Real Estate screens.
- Five PNGs and the trace were stored inside `dinopark.fdb`, then exported using a new Project connection after server/emulator exit.
- A separate no-breakpoint run reported timeout and paused/restored speed rather than fabricating a hit.

The prepared local project is `examples/dinopark/local/dinopark-debug.fdb`; original game assets and byte-retaining project databases are ignored and excluded from packages. Exported, hash-bound evidence and full JSON requests/responses are under `experimental/dosbox-x/evidence/integration-2026-10-23/`.

## Backend delivery and boundaries

The current complete backend patch applies to pristine upstream `029bd65c5dcc7cdc7f2e14e35278620d9707d969` and reproduces all **21 source-file hashes** in `experimental/dosbox-x/source-manifest.json`. The original recovery patch remains unchanged. Native fast-forward uses the existing `DOSBOX_UnlockSpeed2` control on the emulation thread; guest elapsed time comes from `PIC_Ticks`. No CPU execution semantics were replaced.

Acceptance is bounded to original unpatched DOS MZ projects and the documented host/game path. It does not establish Windows runtime support, arbitrary guest mouse drivers, complete memory-access tracing, every-game compatibility, a full DinoPark playthrough, or security sandbox isolation. Static analysis remains separate from runtime observations and is not marked stable by this debugger work.

This receipt records verification completed before the integration commit. It does not assert a deployment, tagged release, or package publication.
