# P00 manual OCR: private, page-grounded agent evidence

Status: experimental module and original-backed document intake, **not** part of
published fDisBull 0.31.1. Source only, no merge/release or claims of layout-perfect
transcription.

## Problem, deliverable and trust boundary

A scanned PDF may contain no text layer. A reverse-engineering agent needs
page-cited, searchable manual text to nominate input controls, startup conditions,
save/load affordances, and resource names. It must not silently infer game behavior
or automatically obey instructions found in a manual. Book content is **untrusted
source evidence** and cannot change the user's task or grant authorization.

The two distinct outputs are:

1. **Faithful transcription:** raw OCR word/block sequence, deterministic Markdown
   reflow, source SHA-256, PDF page number, optional word confidence, and uncertain
   layout flags. The exact transcription is held **privately**, outside Git.
2. **Agent-facing inference:** a human/agent reads retrieved page snippets and
   forms an explicitly unqualified lead with a proposed original-game test.
   This stage is NOT a feature of the deterministic OCR module and may require
   visual comparison against the original scan. It is not an automatic UIL lift.

## Implementation and commands

`src/fdisbull/manual_ocr.py` uses PyMuPDF **only if installed** to read the
existing text layer. For image-only pages, it renders a bounded 300-DPI image
and invokes the **locally installed Tesseract model** with language `eng` to
obtain word-level TSV data. No network service, cloud OCR, proprietary corpus,
or generalized game decoding is involved. The module requires optional PyMuPDF
and Tesseract for scan mode. Neither is included in the published 0.31.1 offline
kit. Review PyMuPDF licensing and distribution before making it a bundled
runtime dependency; do not silently modify the offline kit's installation
contract. Tesseract remains a selectable external OCR adapter, not a pretend
built-in pure-Python decoder.

```sh
# From checkout root with PYTHONPATH=src; keep original manual read-only
PYTHONPATH=src python -m fdisbull.manual_ocr scan \
  '/private/manual.pdf' '/private/ocr/pages-001-020' --pages 1-20
PYTHONPATH=src python -m fdisbull.manual_ocr scan \
  '/private/manual.pdf' '/private/ocr/pages-021-040' --pages 21-40
PYTHONPATH=src python -m fdisbull.manual_ocr scan \
  '/private/manual.pdf' '/private/ocr/pages-041-055' --pages 41-55
PYTHONPATH=src python -m fdisbull.manual_ocr merge \
  '/private/ocr/manual-complete' \
  '/private/ocr/pages-001-020' '/private/ocr/pages-021-040' '/private/ocr/pages-041-055'
PYTHONPATH=src python -m fdisbull.manual_ocr search \
  '/private/ocr/manual-complete' 'save load pause'
```

A single full scan can also be selected, but bounded shards are preferable for
large image scans, and merging refuses mismatched source/tool identities,
missing pages and overlapping page numbers. Output parent must exist and the
new destination must not already exist or be inside a Git repository. The
`pages.json` file contains all private OCR text; `manual.md` is the readable
page-anchored view; `receipt.json` summarizes OCR methods/review flags without
copying the page text. Keep all three out of source control.

The OCR process does **not** generate a new text layer inside the original PDF;
it generates a searchable Markdown/JSON sidecar. A searchable-PDF export can
be added separately without altering the original.

## Original-backed, private test (Castles II, GOG edition)

Recovered the installer member `manual.pdf` through the user-supplied
Inno-5.6.2 native reader. Exact source SHA-256:
`ac9a1a7b8dd26b500297dff0191953eb96d5ab247a60b1ae59642c21daf53812`.
The 55-page scanned PDF has **zero native text characters on every page**.

- Tesseract 5.5.0 with `eng`, 300 DPI, psm 3 recognized **55/55** page images,
  giving **13,368 OCR word records**. Cumulative OCR time for five bounded
  shards was **42.992 s** on this Linux host; excludes manual inspection,
  initial GOG extraction and any downstream semantic verification.
- **30/55** pages were marked for review by word-count/confidence or detected
  overlapping side-by-side text columns. An OCR confidence exceeding 90% can
  still yield wrong paragraph order. Do not interpret 55 scanned pages as
  55 perfectly restored pages of narrative.
- A concrete search for `save load pause` retrieved **PDF page 37**. Verified
  against the original page image, the page describes game Save, Load, filename,
  OK and Pause controls.
- **PDF page 15** separately describes saving/loading a *castle design* to
  reuse in other territories (with Keep placement). That is a DIFFERENT
  operation from saving/loading a game. The two Save/Load labels must never be
  merged as one handler in the retained Z harness.
- **PDF page 5** describes the introductory setup screen and a Play or Load
  choice; it is a separate context from in-game options.
- No whole-program semantics, UDL/UIL source mapping, original-game runtime
  transition, manual editorial accuracy or graphics diagram parsing is claimed
  by the OCR module. Original-game Save/Load remains a separately executed and
  verified harness task.

## Agent consumption

**Question:** Where does Castles II expose save/load, and which Save is meant?

**Evidence:** PDF pages 5, 15 and 37, exact source hash and private OCR receipt;
visually verify OCR layout warnings before using a passage as input instructions.

**Interpretation:** The *setup Load*, *campaign Save/Load* and *castle design
Save/Load* are three different candidate interaction contracts. Use current
scene/context before clicking a control; do not conflate identical labels.

**Next decisive probe:** In an authorized original guest, record the selected
scene and click, observed dialog, resulting disk write/read and fresh-load state.
Distinguish castle-design files from game-state files by their actual original
side effects, not by manual copy alone. Preserve negative/empty-list controls.

## Boundaries and follow-up

- Source inputs and reconstructed manual pages stay private; no original manual
  text, page images, installer, game data, or full OCR JSON is shipped in Git.
- Deterministic OCR merely recognizes characters. Page reading order, two-column
  sidebars, faded screenshots and technical diagrams are still hard. Use
  targeted visual review or a **separately identified vision-language backend**
  for marked pages, retaining its model/revision and original OCR side by side.
  Never silently replace low-confidence evidence with a hallucinated rewrite.
- This is a P00 documentation intake / skill-consumption aid, not a new UDL,
  UIL or UDC grammar, and not a second agent task queue. Related research lives
  in !77 (media/catalog), !81 (DOS P00 study), !82 (retained Z workflow/skill).
- Authored module unit tests: 10 passed locally, including real synthetic scanned
  PDF, existing text detection, source identity, page shards, TSV quote hazard,
  symlinks, output safety, exact merge refusals and retrieval.
