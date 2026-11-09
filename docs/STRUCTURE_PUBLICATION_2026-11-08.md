# Structural discovery publication receipt

Date: 2026-11-08. This publication resumes the interrupted connector transfer under MR !119.

## Published scope

All 37 files in the retained Doom/Genesis structural-discovery contribution are now committed, not merely described in an attachment. They cover native/VM data and code candidates, menu episodes and guarded collection, NES/SNES/Genesis fact producers, linked classic-WAD map drafts, bounded nested MZ/LE source views, intent/composition/trace analysis, authored tests and maintained scene-recovery guidance.

Verified source head before this receipt: `52cf4fbd2a7c3e5015a07fdefc684344361abdbd`.
Source branch: `agent/structural-console-intents-20261108`.
Review target: `release/0.33.0`.
Retained source baseline: `c80bff03e4cd2b946a93e7aecab61e5ff9281f81` (0.32.0 candidate).

The following GitLab subtree identities match trees calculated independently from the supplied baseline plus the retained source contribution:

| Subtree | Git tree identity |
| --- | --- |
| `src/fdisbull` | `70a6504ecac08d60797b717ce7897d1531ec0252` |
| `tests` | `a45dabd8fcc279596e1ca2407c5bf32968fb71a0` |
| `examples/menu_event_probe` | `59becd26d581f700be5491b03edec3f2baa31658` |
| `examples/structural_discovery` | `ccf05513b1c0fd23bd706eacf52bbe3849ce4b00` |
| `examples/structure_composition` | `4734869490b33fa28ec88d0917a07da1579cfebd` |

README and all four contribution documents were also compared individually by Git blob identity and match exactly. These readbacks establish transfer integrity. They are not native-game acceptance tests.

## Fresh tests in this publication session

The private local source candidate used Python 3.13 and isolated dependencies from the supplied offline kit. The command below passed **303 tests with no skips**:

```sh
PYTHONPATH=src:/path/to/private/dependencies python -m pytest -q \
  tests/test_structure* tests/test_menu_event_probe.py
```

The first attempt could not collect tests because Capstone was missing. Installing the offline dependencies into a private target directory resolved that environment prerequisite. No shared system installation was modified.

The separately prepared WAD-media candidate passed **408 tests with no skips** in the same session when `tests/test_wad_media.py tests/test_media_modules.py` were added. That is a separate candidate and belongs to the stacked WAD MR, not a claim that !119 itself supplies the media decoder.

Earlier original-game, corpus, installed-wheel and timing results remain historical, source-qualified experiments. They were not rerun by this publication. No full-project suite or hosted pipeline was executed.

## Historical document interpretation

The retained investigation documents preserve their original checkpoints, including statements that publication had not happened at the time. This receipt and the current MR description supersede those publication-status statements only; they do not retroactively broaden the experiments.

The later Doom/Genesis extension increased `structure-scan`'s default per-file budget to **32 MiB**, its maximum to **64 MiB**, and retains the default aggregate budget of **64 MiB**. These current values supersede the earlier 2/16-MiB discussion in `STRUCTURE_CONSOLE_INTENTS.md`. Explicit caller limits remain binding.

This is source publication on a review branch, not a merge into the active release, a new package release, or a shared installation. Reconcile the existing integration branch and any overlap with !82/!114 before merging. No original ROM, WAD, executable, extracted image/audio, checkpoint, dictionary dump or private trace is included.

## Related work

- !82 retains the original X-COM/TFTD methodology and cross-context state work; the source extension here does not overwrite that branch.
- !89's reference-backed scene-guard methodology remains applicable.
- The WAD media decoder is to be reviewed as a separate stacked contribution, with raw preservation and decoded media distinct from semantic scene recovery.
- MIDI-to-WAV pre-rendering is a separately identified rendering/provider question, not implied by converting MUS event data into a MIDI score.

All publication commits use `[skip ci]`. No merge, tag, release, runner-setting change, credential change, or Mac-mirror synchronization was performed.
