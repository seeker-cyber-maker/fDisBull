# Recovered media and intake source for 0.35

This adaptation recovers authored source from preserved branches onto the
current integration interfaces. It preserves current QEMU, MADS, Westwood,
CHIP-8, package-version and fast-path guidance. Historical game/corpus/native
receipts remain historical reports, not current native acceptance.

| Preserved head | Recovered capability | Current boundary |
| --- | --- | --- |
| `0daa9cd0` | Bounded archive/image layers, ZIP segments, EXEPACK and explicit installer query probe | Pure authored intake tests; native probe requires separately selected backend and acceptance |
| `5db0b1b6` | Native Inno 5.5.7 Unicode alongside 5.6.2, actual-profile receipts and artifact identity check | Authored installer structures; no installer or external extractor execution |
| `73ec8dfc` | Structural 6502/65816/68000, linked WAD, input/event/intent discovery and WAD media | Bounded source candidates and private extraction; no processor execution or gameplay equivalence |
| `861c0c80` | KINT 6 guest decoder and explicit Sherlock 7 PNG atlas profiles | Static guest facts and pixel/atlas decoding; no guest execution or whole-game reconstruction |
| `94dc9f13` | Sherlock SHI codec and separately packaged native/browser/headless research examples | Authored vectors and pure headless tests; historical native/browser results are not rerun acceptance |
| `b325f4d9` | DinoPark ACT/PIC/ABT, explicit timing/animation, Castles SLB and MVE framing | Bounded codecs and explicit profiles; native backend/mixer/player acceptance remains separate |
| `e7298561` | Explicit Castles II BOB image adapter | Authored images, exact bounds and private PNG extraction; no current commercial-corpus QA claim |

Media and decoder registries retain existing entries and add the recovered
adapters. The common CLI discovers adapters from the current registry. Structural
analysis uses `structure-*`; layered extraction and installer observations have
explicit `fdisbull-unpack` and `fdisbull-installer-probe` entrypoints.
WAD extraction is documented in [WAD media](WAD_MEDIA.md).

The capability response retains its hard 64 KiB output contract, with a measured
48 KiB test ceiling leaving 16 KiB margin. Compact skill-index descriptions
preserve every guide identifier while retaining the 4 KiB selective-discovery
contract. Source-only package validation remains separate from exact-candidate
ordinary/native CI and release acceptance owned by n8n.

No original game input, extracted asset, executable, screenshot, state, database,
model, generated native runtime or private source image is added by this recovery.
