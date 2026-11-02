# KQ1 JPC-RR evaluation package

Read REPORT.md for measured results, boundaries, limitations and replay commands.

- video/: two timestamp-checked 1x MP4s with original PC-speaker audio.
- movies/: four ordinary input movies (two endpoints, two complete games).
- captures/: automatic, BOW and published-reference native JMD evidence.
- evidence/: timing, independent replay audit, source identities and continuation fixes.
- landmarks/: first complete endpoint/credits images, predecessors and review receipts.
- replays/: all four fresh playback commands, logs and receipts.
- encoding/: frame/audio timing and mux validation records.
- provenance/: reference inputs, attribution, BIOS-variant declaration and video route analysis.
- tools/: replay/audit/encoding tools and the authoring source used for continuation.
- authoring-history/: retained ordinary-input experiments, including failed discarded branches.

Original absolute paths in raw receipts identify the measured runs; the directories
above contain their packaged counterparts. No original game/firmware image or
native authoring savestate is included. The fixed input movies start from power-on.

Scanner example with portable reference paths:

```sh
python3 tools/scan_landmarks.py captures/automatic.jmd --out fresh-landmark-check \
  --endpoint-reference landmarks/automatic/king_steps_aside-match.png \
  --credits-reference landmarks/reference/final_credits-match.png
```

Use a fresh output directory. The decoder/scanner requires Pillow. Stock movie
playback uses Python 3 and Java with the matching JPC-RR media described in REPORT.md.
Authoring is optional and requires the original game-analysis resources.
