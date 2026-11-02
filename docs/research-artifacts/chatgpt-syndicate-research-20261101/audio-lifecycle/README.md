# Syndicate audio lifecycle research bundle

Start with [REPORT.md](REPORT.md). This is a local research delivery, not a
submitted PR, production feature, release or game package.

## Included

- The report and source-free lifecycle/census/model receipts.
- `tools/xmi_lifecycle.py`: bounded source-informed IFF/EVNT census. Standard
  library only; does not play audio or modify input. Output creation is exclusive.
- `tools/check_status_projection.py`: the authored partial-register model.
  Requires separately installed `z3-solver`; no original game input is needed.
- `tests/test_xmi_lifecycle.py`: 21 authored tests, including truncation,
  repeat/delay placement, EOT tails, and refusal to overwrite a receipt.
- Private receipt identities, not private raw payloads.

## Reproduction

```sh
python -m unittest discover -s tests -v
python tools/xmi_lifecycle.py /your/private/INTRO.XMI /your/private/SYNGAME.XMI --output /your/private/new-census.json
python tools/check_status_projection.py --output /your/private/new-model-check.json
```

The parser is a limited study profile. It treats low bytes as additive delays,
requires explicit channel status, and admits four-byte VLQs. Note-on/off duration
handling follows the examined driver profile. It is not a generic MIDI parser,
complete XMIDI specification, event player, loop reachability solver, or proof
that a replacement is safe. Lexical repeat issues remain explicit. Event-clock
units must not be reported as seconds without the real tempo/timer contract.

No original executables, media, event streams, images, runtime memory, byte-bearing
analysis databases, or live arbitrary-command controller are included. The live
results require the exact original inputs and a separately qualified DOSBox
setup; parser/model replay alone does not reproduce those observations.

No GitHub operation was performed. The pending PR is supplied separately and
must be reconciled with current upstream before publication. Earlier drafts and
results remain historical rather than silently replaced.
