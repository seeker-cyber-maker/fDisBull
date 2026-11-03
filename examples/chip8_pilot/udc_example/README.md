# Reviewed CC0-derived Python UDC example: Snek

`udc_snek.py` was produced by `chip8_udc.compiler` from the pinned archive's
Snek (`snek.ch8`) source, after the 22-rule catalog was registered. It
contains only PC/word guarded Python source, not the full ROM bytes. The ROM
must be separately supplied to `create_machine()` and SHA-256 verified.

`manifest.json` preserves the candidate mapping, selected registered templates
and source hash; `local-check.json` is evidence from comparison against the
original authored `chip8lab.vm` only. No historical CHIP-8 parity is implied.
This is a checked example, **not** production UDC or accepted canonical UIL.

The exact generator and test runner are in the sibling `chip8_udc/` package.