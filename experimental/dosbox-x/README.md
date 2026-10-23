# DOSBox-X headless agent: unfinished checkpoint

Recovered on 2026-10-23 from interrupted development. This experimental branch preserves the work separately from the completed fDisBull tool. No emulator executable is shipped.

Upstream: https://github.com/joncampbell123/dosbox-x
Baseline: `029bd65c5dcc7cdc7f2e14e35278620d9707d969`

The patch contains 12 modified upstream files and 6 new files, including transport code, headless SDL2 startup, cached-frame PNG screenshots, absolute INT33 mouse input, a Python launcher, and a DOS acceptance fixture. It was checked by applying it to pristine baseline files and comparing every recovered file byte-for-byte.

## Apply to a separate upstream checkout

```bash
git checkout 029bd65c5dcc7cdc7f2e14e35278620d9707d969
git apply --check /path/to/recovered-work.patch
git apply /path/to/recovered-work.patch
```

## Known incomplete work

- The Python launcher imports `PipeTransport`, which is not implemented in the recovered Python client. Its `transport=pipe` configuration is also not accepted there. The launcher currently raises ImportError.
- The `MOUSEVID.asm` acceptance fixture exists; its referenced verification runner does not.
- No complete emulator build or guest-observed screenshot/click acceptance result was recovered.
- The existing Python suite ran 16 tests: 7 passed, 3 failed and 6 errored. This execution environment denies Unix-socket creation; a direct compiled transport probe reproduced that restriction.
- Absolute mouse support is scoped to the built-in INT33 real/v8086 driver. It does not cover PS/2/AUX, PC-98 or external guest drivers.
- Complete memory-access tracing, native macOS verification and security sandbox isolation are not established.

Continue by completing Python pipe integration, finishing the SDL2 debug-agent build, then validating screenshots, absolute coordinates, click callbacks and debugger operations in the DOS fixture. Only then integrate a tested backend into fDisBull.

## License and provenance

This is a modified DOSBox-X work, separate from fDisBull. Upstream source headers identify GPL-2.0-or-later. The upstream GPL v2 text is retained verbatim in `COPYING`; source notices in the patch remain intact. Modifications were authored during TiGa's fDisBull development and recovered on the date above. No claim is made that upstream adopted or verified these modifications.
