# Read-only movie and native replay audits

`audit_movie.py` statically inspects a stock JPC-RR power-on movie and can compare two freshly decoded native JMD video captures. It does not launch or control a guest, alter a movie, or modify the encoder.

## Audit the final movie

```bash
python3 audit_movie.py candidate.jrsr \
  --reference /path/to/reference-original-bios.jrsr \
  --out candidate-movie-audit.json
```

The report enumerates every keyboard edge, its exact cumulative nanosecond timestamp, scan code and press/release state. It records the first and last keyboard input separately from later rerecord markers. It checks the stock keyboard clock and serialization bound, and lists any keys held at the end. Held keys are advisory: the original reference itself ends with Enter held.

The required initialization is CPU divider 50, memory 4096, BIOS `740f01be58103af0996220bdeb7c4d12`, VGA BIOS `5555c682e62336cb37eb17c903322be1`, game HDD `bd183c472bf2c054bfa944a768f10592`, and FreeDOS disk 0 `f334bc4d5dc5f393feb0ca2d1e1cdc25`, booted as floppy A. Actual initialization rows remain in the report for review of other settings.

A pure stock movie contains `header`, `initialization`, `events`, and optional `diskinfo-*` metadata. The audit rejects `savestate` or `manifest` payload members, a `SAVESTATEID` header, unknown members, and dispatchable actions outside ordinary `Keyboard KEYEDGE` events. It also checks the stock system header and basic project/rerecord header structure.

**Historical `SAVESTATE` rows inside the event stream are allowed.** The stock movie-only save function writes these as rerecord history even when it emits no guest-state payload. They are not restore operations during a power-on movie replay. This distinction is checked directly against bundled stock `PC.saveSavestate` and `EventRecorder` code.

With `--reference`, the audit compares all timed keyboard events through the Escape release at **2.845504878 seconds**, inclusive. The supplied original reference has **24 keyboard edges** in this boot prefix. Rerecord markers and serialization layout may differ; keyboard timestamps and arguments must match exactly. The reference's boundary must itself be an Escape release. `--boot-prefix-end-ns` can change this boundary for a deliberately different audit.

The original reference has 749 keyboard edges and last input at **14.294723718 seconds**. `reference-movie-audit.json` records the independent audit. These are reference-control values, not candidate-route results.

### Metadata review

The report exposes the complete header plus recognized author, game/title and comment fields. The original reference file supplied here contains no author or game-title metadata. Missing author/title fields produce review warnings. Identical reference author fields are also flagged as possible stale sole attribution. The tool does not invent authorship or assume that a matching game name is wrong.

Stock recognized display metadata includes `GAMENAME`, `AUTHORS`, `AUTHORNICKS` and `AUTHORFULL`. `COMMENT` can explicitly explain the borrowed boot prefix and distinguish the new route from the reference. Review all author fields when changing metadata: adding a new field does not remove an older differently named author field. The headless author's existing `header` command can make authorized metadata edits before stock movie export; this audit never edits the movie itself.

Exit status is 0 if the structural, specified-hardware, ordinary-keyboard and requested-prefix checks pass, even if advisory metadata/held-key warnings remain. A failed check returns 1; CLI misuse returns 2. An `--out` report cannot overwrite an input file, including through a symlink or hard link.

## Compare two native replays

```bash
python3 audit_movie.py \
  --compare-jmd first-stock-replay/capture.jmd second-stock-replay/capture.jmd \
  --out native-replay-comparison.json
```

Both closed JMD inputs are read and decoded from their native payloads using the independently validated decoder. Existing JSON frame hashes are not trusted. The comparison covers every named video stream's exact native nanosecond timestamps, dimensions and decoded RGB hashes. It also requires equal final native capture timestamps and at least one video frame.

The report provides source file hashes, per-stream frame counts, canonical decoded-stream hashes and the first differing frame in each mismatched stream. Identical video can pass even when archive bytes differ because non-video metadata differs. Input hashes must remain stable throughout decoding.

Python callers can use:

```python
from pathlib import Path
from audit_movie import audit_movie, compare_native_replays

movie_report = audit_movie(Path("candidate.jrsr"), Path("reference-original-bios.jrsr"))
replay_report = compare_native_replays(Path("first.jmd"), Path("second.jmd"))
```

This comparison establishes captured-video reproducibility for the stated interval. Audio, hidden memory/game state, movie input identity, scene correctness and completion remain separate checks. A successful static movie audit also does not certify submission acceptance or reconstruct how the authoring session was conducted.

## Verification and provenance

Run `python3 test_audit_movie.py`. Seven focused tests cover marker-versus-payload distinction, required hardware, changed/matched boot input, parenthesized stock metadata, malformed archives, keyboard timing and held state, prevention of input overwrite, and native comparison detecting both a changed pixel and a one-nanosecond timing difference. A fixture with different non-video bytes and identical native video verifies the intended comparison scope.

`movie-audit-provenance.json` records the script, tests, validation log and exact bundled stock source contract hashes. The format parser supports the line breaks, parenthesized component syntax, relative/absolute timestamp options and keyboard rules used by the stock implementation. It deliberately limits the final movie audit to the specified hardware and ordinary keyboard event scope.
