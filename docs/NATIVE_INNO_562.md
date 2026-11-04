# fDisBull Native GOG/Inno 5.6.2 Extractor

**Status:** Experimental, source-only, independently qualified subset. GitLab review required. Compatible with the `gog-list` / `gog-unpack` response contracts from fDisBull 0.31.1. It **replaces the external `innoextract` dependency for the supported profile**, without executing installers, Wine, or spawning a subprocess.

## Supported / refused

- **Supported:** Inno Setup 5.6.2 Unicode bootstrap table (`rDlPtS`, CRC32); LZMA1 metadata blocks with 4096-byte CRC-framed chunks; header file-location tables; stored and LZMA2 data chunks; Inno 5.3.9+ x86 CALL/JMP address filter; GOG Galaxy zlib-compressed part reconstruction; file-size, per-location SHA1, per-output MD5, input/manifest SHA256; directories and collision safety; new-output-only extraction.
- **Refused:** Other Inno versions, external multipart source slices, encrypted/password-protected files, unknown compression or bytecode layouts, unsupported filename namespaces, unknown GOG Galaxy scripts, malformed headers, bad checksums and unsafe paths. No auto-upgrade from a merely listed source to proved executable game equivalence.
- **Not yet verified:** generic Inno variants, upstream fDisBull's full Linux CI, native DOS game execution, complete runtime-equivalence with original installers, save/registration behavior, target-specific compatibility and plugin integration into a published release. The `timeout` is a bounded cooperative stage deadline.

## Components

- `native_inno.py`: standalone native format reader, data-stream validator and reassembler.
- `gog_unpack.py`: replacement for `src/fdisbull/gog_unpack.py`, preserving the existing `gog-unpack-manifest.json` and response names, `include` filtering and existing-output refusal.
- `test_gog_unpack_repo.py`: replaces obsolete mock-subprocess test cases and checks 18 authored no-original contracts.
- `test_gog_original_562.py`: optional original-backed oracle suite; read-only source location provided by `FDISBULL_PRIVATE_GOG_INSTALLERS`. Skips without the user's private installers.

## Qualification on November 4, 2026

| Original installer | Native inventory | Independently observed reference inventory | Complete native extraction |
|---|---:|---:|---|
| Castles 1.03 DLC | 190 | 190 | 190/190 verified |
| Castles II 1.0 | 259 | 259 | 259/259 verified |
| Alone in the Dark 1.0 CS | 218 | 218 | 218/218 verified |

Seven representative targets (including the 38 MB Game Configurator, AITD FITD.exe and full 748.7 MB Castles II `C2CD.gog`) matched their independent reference SHA-256. All reconstructed output parts are checked against their source SHA1 or GOG MD5. The Castles II CD image's output SHA-256 is `7bf4c0d9fee03245132cc1010e71f7760f3aad6cddaf16ef3b77f20af1e7302e` and its mode-1/2352 ISO9660 metadata was separately recognized by fDisBull's `disc-inspect`. This is **not** native game-play qualification.

## Integration

Place `native_inno.py` alongside `gog_unpack.py` in `src/fdisbull/`. Preserve normal CLI `gog-list`/`gog-unpack` dispatch; their import remains from `fdisbull.gog_unpack`. Replace tests `tests/test_gog_unpack.py` with the authored mock-NativeInno suite, and add the opt-in original-backed file. Update CLI help strings mentioning `innoextract` before public release, then run ordinary and native qualification on an exact-source commit.

Example with the user-owned installer:

```sh
fdisbull gog-list 'setup_castles_2_1.0_(28043).exe'
fdisbull gog-unpack --include C2CDTOOL.EXE 'setup_castles_2_1.0_(28043).exe' '/private/new-castles2-output'
```

All user-supplied installers and extracted game payloads remain outside Git, source ZIPs, wheels and review artifacts. This package contains **code, documentation and authored tests only**.

## Attribution

The input profile and decoded layout were independently checked against the publicly available [innoextract](https://github.com/dscharrer/innoextract) implementation by Daniel Scharrer, used here as a reference oracle. Its zlib-licensed source was consulted as documentation; no binary or bundled third-party source was copied into this deliverable. Keep original attribution when referencing it.