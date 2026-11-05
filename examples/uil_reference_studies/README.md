# Portable UIL reference studies

These examples preserve three distinct research formats and a small bridge to the
repository's text Player. They support local experiments with typed values,
invocation-boundary history and observer-scoped views. They do not install a core
format, replace `common-uil-1` or the indexed-record implementation, or establish
compatibility between arbitrary UIL documents.

| Study | Format | Supported scope |
| --- | --- | --- |
| `z_harness/uil_text_study.py` | `uil-text-study-1` | Typed arithmetic and text values; staged text-display plans; atomic modeled refusal |
| `z_harness/z_harness_study.py` | `z-uil-binding-study-1` | One calendar-slice envelope, public turn/year projection, session-owned checkpoints and retained branches |
| `world_view/world_view.py` | `z-world-view-study-1` | Passive views over explicitly authored partial worlds, observer knowledge, pagination and epoch-bound cursors |

The calendar model's time unit is a successful committed **UIL invocation**. Its
checkpoints are private references inside one harness session. They are not
durable saves, native instruction checkpoints or a whole End Turn operation.
The text evaluator wraps declared integer widths and evaluates both `select`
arms eagerly. A pending text effect does not commit state or perform host I/O.

The three world-view fixtures are synthetic designs inspired by Civilization,
Colonization and Syndicate. Their coordinates, IDs, states and proposed actions
are authored examples. The adapter projects admitted observer records, including
remembered and unknown information; it does not simulate games or execute the
unbound actions. Hidden authoritative state must not determine public membership.

## Run the portable contracts

From the repository root, using Python 3.10 or newer:

```bash
python -B -S -m unittest discover -s examples/uil_reference_studies/z_harness -p test_z_harness.py -v
python -B -S -m unittest discover -s examples/uil_reference_studies/z_harness -p test_uil_text.py -v
python -B -S -m unittest discover -s examples/uil_reference_studies/world_view -p test_world_view.py -v
PYTHONPATH=player python -B -S -m unittest discover -s examples/uil_reference_studies/z_harness -p test_calendar_player.py -v
```

The final command imports the actual repository `fdisbull_player.Player` through
the `player/` source path. `calendar_player_adapter.py` translates that Player's
observation/action protocol to the existing calendar harness. The harness remains
the state owner. The bridge supports `advance calendar` and passive inspection;
save/load explicitly remain unsupported. It is specific to this calendar study.

The contract tests cover hidden-state comparison, stale tokens, immutable history,
pending effects, refusal, input immutability, exact text formatting, passive Player
inspection, actual Player dispatch, cross-view identity, knowledge filtering and
cursor ownership. The test commands derive success from their real test outcomes.
No archived `VERIFICATION.json` or hardcoded component-status runner is used.

## Inspect and rebuild examples

```bash
python -B -S examples/uil_reference_studies/z_harness/z_harness_study.py
python -B -S examples/uil_reference_studies/world_view/world_view.py civilization --view city-1
```

`z_harness/build_scene.py` regenerates the authored calendar envelope and deliberate
faulty variant from `examples/civ_calendar.json`. `world_view/build_examples.py`
regenerates the three synthetic world fixtures. Both builders write only their
adjacent example JSON files when explicitly run.

The faulty calendar variant keeps the same public turn/year display while omitting
hidden word updates. It is a discriminating counterexample, not an alternative
accepted implementation. `compare_variant` compares two portable models at one
entry state and their declared required-slot projection; it does not execute an
original machine or prove general equivalence.

## Provenance and selection

The evaluator, harness, builders, portable contract tests and six fixtures come
from [UDL/UIL/UDC Reference v0.10, version 8](https://chatgpt.com/library?file_id=libfile_f496d1e247dc8191b6df5621581971bd&account_id=personal).
The same 13 original files are byte-identical in
[Offline Reference v0.30.0 (4)](https://chatgpt.com/library?file_id=libfile_38a38c74029c8191a62b4e4b645de7d0&account_id=personal).
Their identities were absent from main
`dc6d7e7709802e743e79cf46e648a4e87b2a0a27` and pending !43
`c1cd753e8819cf54cc1a47d30166b03d2d559fbf` at import review.

The unchanged Player adapter and selected `CalendarPlayerTests` / `TextServiceTests`
come from the [v0.30 feature assessment](https://chatgpt.com/library?file_id=libfile_1a87142c35a081919884844354c74d75&account_id=personal).
Only their local imports and fixture paths were adapted. The original assessment
used an older reference package; this import checks the selected bridge with the
actual Player source matching the pinned current main.

| Origin archive | SHA-256 |
| --- | --- |
| `UDL_UIL_UDC_Reference_v0.10.zip` | `d6cce1b06a43200203216d60010d7d3c68dae676fef560039229fd1ede0f1842` |
| `fDisBull_ChatGPT_Offline_Reference_v0.30.0(4).zip` | `3b6fb2b1fb930f0988b62bb49361c6231aff9455b707db39d2152310c558d236` |
| `fDisBull_v030_Analysis_Feature_Assessment_2026-11-02.zip` | `4d38c0aca6a0aab0fa620baf463a4518a321fe44500fa5107d76d2b4620d8090` |

The calendar semantic documents retain their original `source_evidence` metadata.
Receipt names there identify historical originating evidence; those receipts are
not included or newly reproduced here. No native equivalence claim follows from
these portable tests.

This selection excludes native probes and observations, private payloads, raw
memory, original games/resources, standalone reports, historical verification
receipts and generated observation outputs. The single harness test that depended
on a retained native observation was removed, along with that fixture. Every other
original harness contract is retained. The original broad assessment runner and
unrelated Player/word16/scene tests are also outside this focused example.
