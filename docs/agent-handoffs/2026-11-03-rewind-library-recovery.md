# Rewind, KQ1 and Library recovery handoff — 2026-11-03

This handoff resumes the interrupted automatic-frame-delta and Library intake
work. It records a bounded source and preservation review, fresh local checks,
the completed !42 independent review, crash-replay usefulness and the next
integration decision. It is not a new native benchmark, a
repository-wide review, or merge/release authorization.

Origin: `chat:01a18dd3-8f60-7560-9a0f-422f44c91d2a/task:rewind-library-recovery-20261103`.
The publishing owner is the originating Codex chat; do not run a second
publisher or CI/status loop for this handoff.

## Start from the current repository

The observed local and GitLab `main` head is
`3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`. Its package source version is
`0.30.0`; this does not verify an installed prefix or establish release readiness.
The handoff branch is `codex/rewind-library-handoff-20261103`, based on that exact
main head. Its changes are documentation only.

Project `88349936`,
[brewster-jennings-group/fdisbull](https://gitlab.com/brewster-jennings-group/fdisbull),
is currently **public**, according to a fresh project metadata read. Older notes
calling it private are historical. This handoff adds authored text and sanitized
repository facts only. Private game inputs, RAM reads, FDBs, native states,
captures, raw logs and original archives remain outside this contribution.
Historical attachment availability and access controls were not re-audited.

The local `scripts/gitlab_handoff.py` publisher intentionally requires a private
project. Its offline preview remains useful, but a public-project handoff must
not be called a successful private-helper publication. Do not weaken that guard,
change project visibility, credentials or account settings to make it pass.
For this explicitly requested documentation MR, use the existing GitLab
connector and verify its source head, target, draft state and returned URL.

## Current MR state supersedes the November 1 snapshot

The following state was read from GitLab on November 3. No MR state, target,
approval or auto-merge setting was changed during this recovery.

| MR | Observed state | Source head | Meaning for the next owner |
| --- | --- | --- | --- |
| [!14](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/14) | Merged November 2 | `be073ce677f72cda4f6aef6da3ba2de806a1fb2b` | Already integrated; do not describe it as an open draft |
| [!16](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/16) | Closed; no merge recorded for this MR | `6225da7643d91258b9406cf2b7f0aeff1090e680` | Its source tip is an ancestor of current main; do not reopen it merely to resume work |
| [!30](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/30) | Closed; no merge recorded for this MR | `865542a26b5406b2bc81e0e3bc7c542a287eec25` | Its source tip is an ancestor of current main; the automatic timeline is present |
| [!36](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/36) | Merged November 2 | `4be05579bc623aa65bfe554a9ecd62dc4b90bd0e` | Zork recovery is no longer only an unmerged branch |
| [!37](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/37) | Merged November 2 | `7e5b13acb1bed91faebba6e558acb627c3d1bc5d` | All 41 KQ1 research files still match current main exactly |
| [!41](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/41) | Merged November 2 | `7426576807e91b795b04f463a4b98f41c3832dac` | Delta timeline implementation and its dated benchmark report are integrated |
| [!42](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/42) | Open, draft, targeting main | `0d4f7f4c3cc307e9c2084b942aa9924eaea3a360` | Reviewed Library intake updated from main; 69 selected text files remain absent from current main |

Auto-merge was off in all seven responses. The !14/!16/!30/!36/!37/!41 merge and
closure changes predate this recovery and were not performed by its owner.
The later !42 source synchronization and independent review were completed in
this chat and are recorded below. Preserve the existing history and MR targets;
no new MR merge, release, installation or reversal is authorized here.

## Delta capability and qualification boundary

No unfinished delta implementation edit was found. Full timeline storage remains
the default. `timeline_start(storage_mode="delta", keyframe_interval=8)` retains
lossless XOR/zlib differences between complete serialized native checkpoints,
with periodic full keyframes and full fallback. A pinned Anchor Stone reconstructs
the complete original native checkpoint. Native capture still saves a full state
for every point; this is not native dirty-page recording.

Read [the codec contract](../FRAME_STATE_DELTAS.md) and
[the automatic timeline contract](../FRAME_INPUT_TIMELINE.md) before new runtime
work. The codec, timeline and script implementations on current main match the
measured November 1 versions. The CLI has received later integration changes;
the fresh interface checks below exercise those changes without launching a guest.

RNG preservation is explicit. The default preserved overlay is mixed and frozen
until trusted recovery. An intentional policy can set
`allow_partial_resume: true`; that grants experimental partial execution and
retains mixed-state provenance, not whole-machine determinism. The November 1
raw-observation supplement tested the default frozen path. Do not generalize its
native result to every opt-in policy or to a new successful rat/bag route.

The [November 1 benchmark report](../verification/frame-timeline-deltas-20261101/REPORT.md)
and [numeric companion](../verification/frame-timeline-deltas-20261101/metrics.json)
remain bound to production source
`762f6e72021f3f558844d332472c1f19280a0015`, not current main. All 19 referenced
receipt files were rehashed locally during recovery and still match their
recorded sizes and SHA-256 values. This verifies preservation, not a fresh run.

That prepared real-KQ1 experiment reported 24.07–25.59% fewer complete logical
cache bytes, 26.32–27.97% fewer checkpoint payload bytes, and 7.26–9.08% slower
forward loops for delta storage. It did not establish lower process RAM/RSS.
Keep its image-coverage and discarded-observation limits intact. JPC-RR used
different scene/settings, frame boundaries, DS selection and retry input plans;
its reference times are not a normalized cross-engine speed ratio.

## Local recovery checks and the completed !42 review

The earlier recovery checks below ran on the source at main
`3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`, in an isolated worktree with private
external temporary output. No production code was changed.

| Check | Fresh result | Scope |
| --- | --- | --- |
| Codec, timeline, timeline deltas, interfaces, CPU deltas, Anchor rewind and handoff helper | 282 passed | Existing local tests; no native guest |
| Wine delta contracts, preservation policies/interfaces/review, mouse timeline and benchmark protocol | 109 passed | Existing stopped-RPC/offline collaborators; not Wine execution |
| Current CLI method discovery and delta/explicit-partial-resume script validation | Passed | Imports verified to come from the selected checkout |
| Original Library utility, earlier recovery | 16 tests passed | Original source at `2323b2b`; superseded for new operations by the reviewed derivative |

The two pytest selections are disjoint: 391 passed in total. They are not a full
repository suite. No macOS native guest, KQ1/JPC-RR replay, Wine runtime, Linux CI,
hosted check, package build or installed-prefix check was rerun in this recovery.
The earlier 2,826-pass/142-skip/26-deselection record and 3-failure/23-error
unrestricted result belong to their older source/environment; they are not
assertions about the entire current main suite.

For an explicitly requested repeat, select the intended source/Python environment,
re-admit storage, and set `FD_RUN` to a fresh approved private external output
directory. From the repository root, the exact pytest selections were:

```sh
TMPDIR="$FD_RUN/tmp" PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q \
  tests/test_frame_state_codec.py tests/test_debug_timeline.py \
  tests/test_debug_timeline_deltas.py tests/test_timeline_interfaces.py \
  tests/test_cpu_deltas.py tests/test_debug_rewind.py tests/test_gitlab_handoff.py \
  -p no:cacheprovider --basetemp="$FD_RUN/tmp/focused-pytest"

TMPDIR="$FD_RUN/tmp" PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -q \
  tests/test_wine_deltas.py tests/test_delta_policies.py \
  tests/test_delta_policy_interfaces.py tests/test_delta_policy_review.py \
  tests/test_frame_timeline_mouse.py tests/test_frame_timeline_benchmark.py \
  -p no:cacheprovider --basetemp="$FD_RUN/tmp/policy-pytest"
```

## Completed independent review of MR !42

MR !42 now has source head `0d4f7f4c3cc307e9c2084b942aa9924eaea3a360`.
Its merge parents are original intake `2323b2b4715a98b4bad44b576685f0a9330d6eb0`
and main `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`. That source-branch update
did not merge the MR into main. Both !42 and !74 remain draft and unmerged.

Two independent read-only reviews found and checked the following fixes:

- A failed exclusive ZIP creation/write could delete a competing or replacement
  output file. The maintained derivative removes automatic output unlink;
  failed partial output remains for explicit review and existing paths are refused.
- Delta verification accepted a reused parent ID when checksums were recomputed.
  Verification now enforces the same distinct-child-ID rule as generation.
- Thirteen wrapper READMEs now qualify old privacy/MR/install statements as dated
  records and route the six intentionally unresolved original links.

All 28 manifest-bound original imports remain byte-for-byte unchanged. The old
utility and its tests remain historical source; live commands select the
maintained derivative. Source and test identities are bound separately in its
[derivation record](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/0d4f7f4c3cc307e9c2084b942aa9924eaea3a360/research/library-handoffs/2026-11-01/tools/derivation.json).

The !42 review phase recorded **36 utility tests with 16 subtests** and **22
repository handoff/mirror contract tests**, all passing. Four new regression
methods first failed against the copied original for their intended reasons,
including both empty/changed checksum-consistent forged-ID subcases. The checked
CLI also verified the actual retained F001 bundle (323 payload files,
6,614,252 bytes) and D001 delta (two additions, zero modifications/deletions,
323 unchanged entries). These checks are distinct from the earlier 391 recovery
checks and the older native benchmarks; they are not native/game execution.

See [the completed review](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/0d4f7f4c3cc307e9c2084b942aa9924eaea3a360/research/library-handoffs/2026-11-01/REVIEW_2026-11-03.md)
and [the maintained utility and repeat commands](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/0d4f7f4c3cc307e9c2084b942aa9924eaea3a360/research/library-handoffs/2026-11-01/tools/README.md).

## Fresh checks for this handoff update

The documentation update reran the 13 recovery selectors above plus
`tests/test_sync_mirrors.py`: **395 tests passed** on the unchanged product source
from main `3dc5c50`. The two !42 utility suites were also rerun from the separate
`0d4f7f4` worktree: **36 tests and 16 subtests passed**. These fresh runs cover
existing failure/cleanup, pin/image, invalidation, policy, delivery and mirror
contracts; no new native crash experiment is implied.

Both updated documents passed local-link and bounded privacy checks. A larger
128 MiB validation allocation was refused because the normal 40 GB storage
target was unmet; that bulk phase was not performed. Only ordinary documentation
edits, small control receipts and the lightweight existing checks were used.
Their retained task output was under 2 MiB when measured after the test runs.

## Library intake still awaiting integration

MR !42 preserves 69 selected UTF-8 text files, 2,828,499 bytes. All 69
paths are absent from current main, and none of their exact Git blob identities
appears elsewhere in that tree. This is still unique preserved work.

The completed intake review parsed all 33 JSON documents and six Python sources and
verified all 28 selected import hashes. All 15 identified Library deliveries
have matching local copies; the inventory does not claim to enumerate the whole
Library. Previously recorded upload readback copies also still match locally.
No new download was made, so present remote attachment availability is unknown.

Use [the MR !42 intake wrapper](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/0d4f7f4c3cc307e9c2084b942aa9924eaea3a360/research/library-handoffs/2026-11-01/README.md)
and its inventory. The updated wrappers distinguish the historical November 1
records from the completed November 3 review. Six `scene/*` links in the byte-preserved original
`full-f001/original/00_START_HERE.md` do not resolve in the sanitized selection;
do not rewrite that original to manufacture a complete archive. Use the selected
[semantic-map material](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/0d4f7f4c3cc307e9c2084b942aa9924eaea3a360/research/library-handoffs/2026-11-01/full-f001/semantic-map)
and the working wrapper links. Historical raw archive links are not approval
to redistribute their contents under current publication rules.

The KQ1 preservation subtree has a different status: all 41 tracked files from
MR !37 already match current main. Its 31 selected import hashes, 13 Python
sources and four movie hashes passed fresh local preservation/parse checks.
There is no need to reacquire the Library ZIP to recover those authored files.
This does not constitute a new movie replay or full-game qualification.

## Crash diagnosis usefulness

Read [crash replay and evidence survival](../CRASH_REPLAY.md) before treating
rewind as crash recovery. The automatic frame cache is useful for controlled
reproduction/narrowing while its live session remains valid. Normal unrecorded
execution or instrumentation changes can invalidate it, and failure-triggered
close clears it. Pin verified Anchor Stones before risky execution and export a
stored image separately if needed. Instruction rewind/CPU-delta operations also
create recovery artifacts; their existence is distinct from a valid live cursor.
No native crash-survival experiment or automatic durable crash recorder is
qualified by this handoff.

## Next bounded action and stop conditions

1. Re-read main, MR !42, project visibility and the intended contribution target
   before any new action. Use one CI owner and no background polling. Keep
   GitHub retired and retain Local Git/GitLab parity for the contribution branch.
2. Inspect the completed !42 review at `0d4f7f4` and its maintained utility.
   The independent review/fixes are complete; the remaining decision is
   integration. Preserve both drafts and their targets until separately directed.
   Keep imported originals, native evidence and raw archives out of new changes.
3. Only if a new native behavior or performance question requires a replay,
   re-admit storage, verify the exact source/backend/preparation identities, use
   one guest owner and a fresh private output directory. Preserve the old sealed
   receipts. Test ordinary restoration and any explicit partial-resume policy
   separately; declare which one ran.
4. Publish only the requested authored handoff and sanitized evidence. Retain
   private runtime inputs and logs locally. Do not run Linux/hosted CI, merge,
   release, tag, change visibility or activate an installation as a side effect.

The recovery is complete when the handoff branch is present in both Local Git
and GitLab, its draft MR has been read back at the exact source head/base, and
the originating chat receives that URL with the fresh checks and open boundary
for MR !42. This checklist creates no continuing automation.
