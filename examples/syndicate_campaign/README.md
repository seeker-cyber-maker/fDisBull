# Syndicate campaign/research study D008

Start with the [original campaign/research report](https://chatgpt.com/library?file_id=libfile_7c70110ac540819183fb3a4dfec18a90&account_id=personal). This package adds a qualified campaign data
reader, a read-only Z-player projection, and recovered research/admission models.
It does **not** replace the original campaign or perform unattended game actions.

## Read the recorded screen views now

- [WORLD.txt](WORLD.txt): all 50 territory labels and initial admission.
- [RESEARCH.txt](RESEARCH.txt): active UZI project, exact funding and progress.
- [MODS.txt](MODS.txt): the recovered three-level modification catalog.
- [EQUIPMENT.txt](EQUIPMENT.txt): weapon-project states.
- [SAVE_FORMAT.md](SAVE_FORMAT.md): selected save layout and unknown fields.
- [SAVE_CORPUS_METHOD.md](SAVE_CORPUS_METHOD.md): generalized seed methodology.

The recorded semantic observation is not an original `.gam` file. It excludes
uninterpreted source payload and cannot be loaded as an original game save.
The native-generated 25% save stays in the private investigation workspace.

## Repeat the source-free checks

Use an explicit environment containing the genuine supplied Player package:

```sh
/path/to/venv/bin/python -B tools/verify_review.py --output /new/private/check
```

This runs 51 authored cases and nine commands against the actual Player over a
fresh recorded-state backend. It does not start a game or claim native replay.
Distribution versions in its receipt are installed metadata when available;
null means the source fixture has no installed metadata. It is not proof of a
missing module or a native installation check.

To use the provider from the existing player:

```sh
/path/to/venv/bin/python -m fdisbull_player --backend-command \
  '/path/to/venv/bin/python -B /path/to/study/tools/campaign_endpoint.py --observation /path/to/study/evidence/recorded-partial-campaign.json --catalog /path/to/study/evidence/campaign-catalog.json --observed-no-override'
```

Commands: `look`, `examine mission selection`, `examine research`,
`examine research graph`, `examine modifications`, `examine equipment`.
All mutations are refused. `--observed-no-override` states an external observation
for this recorded fixture; it must not be inferred automatically from a new save.

## Inspect another privately supplied compatible save

```sh
/path/to/venv/bin/python tools/campaign.py \
  --save /private/copied/00.GAM --catalog evidence/campaign-catalog.json \
  --source-sha256 bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078 \
  --view research
```

The source hash argument is a caller assertion; use `extract_catalog.py` against
an exact original MAIN to check the actual executable when constructing a new
catalog. No same-length donor is automatically admitted to native execution.
The read-only decoder checks its bounded profile, not all original validity rules.

## Native evidence and resumption

The JSON receipts distinguish live DOSBox I/O/hourly updates from isolated
original-x86 helper tests. The latter execute the real retained instruction bytes
with explicit inputs but are not DOS/4GW runs. Complete native details, private
states and source payload remain outside this package. Bounded source-only
reproduction tools can consume the exact original and private save; see the
source locations and specimen hashes in the report.

Next actual native work should load the verified private seed in a newly owned
guest, validate the current object mappings and progress state, then investigate
one topic switch or completion. Do not reconnect to the closed D008 processes or
reuse numerical addresses as a binding certificate.
