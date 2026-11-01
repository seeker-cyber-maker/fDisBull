# KQ1 JPC-RR evaluation: sanitized research import

This directory preserves selected source, input movies and evidence from the
2026-11-01 external evaluation. It is research material, outside the normal
fDisBull tool-package selectors. The original report describes Linux/Java 17
runs; this import does not establish a macOS replay, a new record, TASVideos
acceptance, or equivalence of every hidden machine state.

[Complete original evaluation ZIP](/uploads/09b2a5aedeb7b2c84b578d82d14aaeeb/KQ1-JPC-RR-TAS-Evaluation-2026-11-01.zip)
is retained as a private GitLab project upload, outside Git. Its SHA-256 is
`52040dc1d6b0c25c64255c9e3af68e432b267ac5382a72aa1348d391b4521118`
and its size is 20,755,106 bytes. The publishing agent verified byte-identical
upload readback. The [import manifest](provenance/import-manifest.json) records
all 159 archive members, including exclusions, and original/imported hashes
for every selected member.

The unmodified [original report](original/REPORT.md) and
[original package inventory](original/README.md) are historical documents.
Their references to videos, native captures, screenshots, raw replay logs and
authoring histories refer to the complete private ZIP. Those materials are
excluded from this Git import. Historical test and completion statements remain
attributed to that evaluation rather than freshly reproduced by this import.

## Included material and boundaries

- `tools/`: Python/Java source and its original documentation.
- `movies/`: four attributed power-on keyboard-input movies. Their JRSR
  containers retain input events and disk identity/catalogue metadata, with no
  embedded savestate or game/firmware file contents.
- `evidence/`: identities, timing, route comparison, continuation corrections
  and historical independent replay review. Cloud roots in the JSON review are
  replaced by `original-run/` and `reference-run/` provenance labels; these are
  not runnable paths. Detailed original per-edge audits remain in the private ZIP.
- `provenance/`: original download/BIOS-variant declarations and the import manifest.
- `checks/`: focused import checks and their fresh result receipt.

The movies retain DrD2k9's 24-edge boot prefix through 2.845504878 seconds and
credit Robb's route inspiration. Preserve their author/comment headers. They
are attributed derivative inputs, not clean-room inputs. The original-BIOS
reference movie remains in the private ZIP; the BIOS change is declared in
`provenance/original-bios-variant.json` and does not alter input event bytes.
No game image, firmware, JAR, native savestate, JMD capture or screenshot is
provided here. Hashes identify recorded bytes; they establish neither ownership
nor permission. The archive contains no explicit license grant, and this import
does not invent a license for third-party inputs or assert independent source
authorship.

`tools/route-candidate.json` is an earlier 282-step semantic proposal, explicitly
marked as unexecuted in the stock emulator. It remains separate from the final
fixed input movies. Its status is preserved rather than upgraded by the report.

## Adapted source

Three files differ from the archive:

1. `route_support.py` retains lengths and SHA-256 hashes for 43 original-code
   witnesses rather than 196 original bytes. Its verifier preserves per-witness
   `match` and aggregate `complete` behavior while reporting hashes, never raw
   expected or observed target bytes. Matching hashes are layout qualification,
   not a wider runtime-equivalence proof.
2. `scan_landmarks.py` requires both private reference-image paths explicitly.
3. `replay_batch.py` accepts explicit JAR, disk-library and private-output paths;
   its default movie directory is this import's `movies/`. `--dry-run` prints
   the four sequential commands without creating output or launching Java.

Example planning command (does not execute a guest):

```sh
python tools/replay_batch.py --jar /path/to/jpcrr-r11.2.jar \
  --library /path/to/private-disklibrary --out /path/to/new-private-captures \
  --dry-run
```

Actual replay remains a separate authorized run using matching private media,
a working Java executable on `PATH`, and storage admission for the output.
Landmark scanning likewise needs private images:

```sh
python tools/scan_landmarks.py /path/to/closed-capture.jmd \
  --out /path/to/new-private-landmarks \
  --endpoint-reference /path/to/king-message.png \
  --credits-reference /path/to/final-credits.png
```

## Fresh checks

Run from this directory with a Python environment that includes Pillow:

```sh
python -B checks/verify_import.py --original-root /path/to/private-original-extraction
```

The check verifies the original helper's identity, reads its witness constants
without executing original source, compares all hash witnesses, exercises
successful and altered/truncated RAM projections, audits all four input movies,
checks argument parsing and batch dry-run behavior, and rechecks import hashes.
It starts no Java process and no guest. `checks/verification.json` records the
fresh result; no timing or completion measurements are added.

The historical documentation references `test_audit_movie.py`,
`test_jmd_capture.py` and `test_pcm_audio.py`; those test sources were absent
from the delivered archive. Their reported historical results remain unverified
here. The new import checks cover the declared sanitation and portability seams.

Zork scene/window recovery is tracked independently in draft GitLab MR !36.
This research import does not merge that feature or the debugger drafts.
