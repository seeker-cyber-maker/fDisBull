# Rewind, KQ1 and Library recovery handoff — 2026-11-03

This handoff resumes the interrupted automatic-frame-delta and Library intake
work. It records a bounded source and preservation review, fresh local checks,
and the next integration decision. It is not a new native benchmark, a
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
| [!42](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/42) | Open, draft, targeting main | `2323b2b4715a98b4bad44b576685f0a9330d6eb0` | Remaining Library intake; 64 selected text files are absent from current main |

Auto-merge was off in all seven responses. These are observations of changes
made before this recovery, not actions performed by the recovery owner. Preserve
the existing history and MR targets. The current request does not authorize a
new merge, release, installation or reversal of the recorded integrations.

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

## Fresh local checks on the current source

The following existing checks ran on the source at main
`3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7`, in an isolated worktree with private
external temporary output. No production code was changed.

| Check | Fresh result | Scope |
| --- | --- | --- |
| Codec, timeline, timeline deltas, interfaces, CPU deltas, Anchor rewind and handoff helper | 282 passed | Existing local tests; no native guest |
| Wine delta contracts, preservation policies/interfaces/review, mouse timeline and benchmark protocol | 109 passed | Existing stopped-RPC/offline collaborators; not Wine execution |
| Current CLI method discovery and delta/explicit-partial-resume script validation | Passed | Imports verified to come from the selected checkout |
| Library handoff utility from MR !42 | 16 tests passed | Standard-library utility; no target execution or installation |

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

## Library intake still awaiting integration

MR !42 preserves exactly 64 selected UTF-8 text files, 2,793,624 bytes. All 64
paths are absent from current main, and none of their exact Git blob identities
appears elsewhere in that tree. This is still unique preserved work.

Fresh local checks parsed all 32 JSON documents and four Python sources and
verified all 28 selected import hashes. All 15 identified Library deliveries
have matching local copies; the inventory does not claim to enumerate the whole
Library. Previously recorded upload readback copies also still match locally.
No new download was made, so present remote attachment availability is unknown.

Use [the MR !42 intake wrapper](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/2323b2b4715a98b4bad44b576685f0a9330d6eb0/research/library-handoffs/2026-11-01/README.md)
and its inventory. The wrapper's November 1 main/MR status is historical and is
superseded by this handoff. Six `scene/*` links in the byte-preserved original
`full-f001/original/00_START_HERE.md` do not resolve in the sanitized selection;
do not rewrite that original to manufacture a complete archive. Use the selected
[semantic-map material](https://gitlab.com/brewster-jennings-group/fdisbull/-/tree/2323b2b4715a98b4bad44b576685f0a9330d6eb0/research/library-handoffs/2026-11-01/full-f001/semantic-map)
and the working wrapper links. Historical raw archive links are not approval
to redistribute their contents under current publication rules.

The KQ1 preservation subtree has a different status: all 41 tracked files from
MR !37 already match current main. Its 31 selected import hashes, 13 Python
sources and four movie hashes passed fresh local preservation/parse checks.
There is no need to reacquire the Library ZIP to recover those authored files.
This does not constitute a new movie replay or full-game qualification.

## Next bounded action and stop conditions

1. Re-read main, MR !42, project visibility and the intended contribution target
   before any new action. Use one CI owner and no background polling. Keep
   GitHub retired and retain Local Git/GitLab parity for the contribution branch.
2. Review MR !42 against current main using its selected-text manifest. Preserve
   its authored utility, semantic documents, inventories and provenance without
   importing private game/state bytes or applying historical patches. Its fresh
   local checks are recorded above; merging it remains a separate decision.
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
