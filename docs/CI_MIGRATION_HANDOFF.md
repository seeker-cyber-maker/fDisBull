# GitLab release qualification: implementation handoff

This records the reviewed migration baseline and implementation plan. The
follow-up implementation is described in [the coordination guide](CI_COORDINATION.md):
manual native admission, complete suites, package inventories and dependent
qualification receipts. Neither the plan nor the source implementation is a
passing hosted result. Read the exact candidate's pipeline and qualification
receipt before making that claim. No provider setting or job should be changed
merely by reading this document.

## Source identities and comparison

Use `3dc5c50d35f310a3ba39b1cf0cf82a20b8df69f7` as the reviewed GitLab
configuration baseline. Compare it with the preserved GitHub workflow at
`v0.29.0`, peeled commit `09a820952ad3f54d0d0707db0515a8010f7eceb1`.
These are source contracts, not proof that a historical hosted run succeeded.
No live request to the retired GitHub account is needed.

| Contract | Preserved GitHub workflow | GitLab baseline | Required follow-up |
| --- | --- | --- | --- |
| Routine checks | Python 3.12 full suite, core/player packages, installed-wheel skills and isolated player smoke | Substantially the same fast gate | Preserve it and obtain a successful result on the selected candidate SHA |
| Main/tag admission | Workflow admits main and version tags | YAML admits them, but mirror helper defaults to `ci.skip` for both | Reconcile deliberate archive mirroring with candidate qualification; test both explicit choices |
| Native Python versions | Stable 3.12; layers 3.13.5 | Ubuntu system Python for both jobs | Restore explicit, reported versions or document and qualify a deliberate replacement |
| DOSBox identity | Pinned upstream, patch and patched-source hashes, explicit build features, backend identity receipt | Baseline/patch/source hashes retained; build flags differ and no backend identity artifact | Preserve identity verification and confirm the actual SDL2/heavy-debug/agent features |
| Native test scope | Broad stable/layers suites; `--require-native` | Two abbreviated selections, without that option | Port the full applicable contract and make absent native prerequisites fail |
| Offline kit | Layers backend, genuine dependencies including Z3, source companion and installation checks | No equivalent gate | Restore hash-bound kit construction and acceptance |
| Unified runtime | Installed-wheel PE64, DOS-in-QEMU and boot checks after both DOSBox legs | No downstream equivalent | Restore dependent jobs and strict runtime requirements |
| Release status | Repository policy requires ordinary and native success on the exact SHA | Default manual native jobs are optional | Make a qualification receipt require all mandatory jobs, irrespective of overall pipeline color |
| Evidence | Backend identity, logs/JUnit, failure evidence and success artifacts | Fast packages and skill receipts; no native artifacts | Retain readable failure evidence and hash-bound successful outputs |

Source entry points: [GitLab YAML](../.gitlab-ci.yml),
[mirror helper](../scripts/sync_mirrors.py),
[portable native workflow](../.github/workflows/native-debugger.yml),
[native prerequisite guard](../tests/conftest.py),
[offline-kit builder](../scripts/build_offline_kit.py),
[offline-kit verifier](../scripts/verify_offline_kit.py) and
[coordination policy](CI_COORDINATION.md).

The GitLab configure command omits the former explicit `--enable-sdl2` and
`--enable-dosbox_agent` options. Establish the pinned configure defaults and
inspect the resulting build features before diagnosing this as a disabled
backend; a different command alone does not prove the binary unusable.

## Ordered implementation slices

1. **Settle push intent.** Choose and document whether the mirror helper should
   default to suppression for archive synchronization or admission for main/tag
   qualification. Keep an explicit way to do each, and preserve topic/archive
   suppression. Extend `tests/test_sync_mirrors.py` to cover main, version tags,
   topics, non-GitLab remotes, dry runs and already-synchronized refs. No bulk
   mirror or empty commit should be needed to request one candidate's checks.
2. **Make admission usable.** Read the current pipeline-variable restriction
   once. Select a supported explicit route for native and draft qualification.
   Do not loosen account permissions or create credentials as an implementation
   shortcut. Validate the YAML with the provider's normal lint mechanism and
   prove that a routine topic push and a draft MR do not launch native builds.
3. **Restore native scope and identity.** Port the applicable stable/layers test
   lists and shared suite additions from the preserved workflow to the current
   tree; review renamed/new tests rather than blindly copying stale paths.
   Require an executable backend with `--require-native`, explicit Python
   versions, manifest checks, intended build features, source SHA and backend
   hash. Preserve bounded build concurrency and useful failure artifacts.
4. **Restore downstream acceptance.** Build and verify the offline kit with Z3
   and its DOSBox source companion. Test the installed wheel, PE64, DOS/QEMU and
   boot paths after the required DOSBox legs. Carry the old strict runtime flags
   (`FDISBULL_REQUIRE_PE`, `FDISBULL_REQUIRE_MACHINE`,
   `FDISBULL_REQUIRE_DOS_QEMU`) forward where their current fixtures support them.
5. **Define the release decision.** Enumerate required jobs in the qualification
   receipt. A manual, skipped, canceled, missing, failed or wrong-SHA required
   job leaves qualification incomplete. Keep main/tag/manual candidate runs
   from being silently replaced by unrelated work; cancellation behavior should
   be an explicit choice, distinct from superseded MR checks.
6. **Apply provider protections separately.** A maintainer can decide whether to
   require passing pipelines for merging and how to handle skipped pipelines.
   A general passing-pipeline rule alone cannot require optional native jobs.
   Record the exact settings and acceptance test after any authorized change.

## Acceptance and efficient execution

Start with command-construction and CI contract tests, YAML validation and one
selected ready-MR fast gate. Proceed to one coordinated native qualification on
that exact commit. Do not launch native jobs on every edit. Before local builds,
apply the storage admission rules and stop on a rejected estimate. Assign one
CI owner; use the finite status receipt described in the coordination policy.

The qualification should demonstrate that:

- An absent or non-executable DOSBox fails required-native admission instead of
  turning a native suite into optional skips.
- Both declared Python/backend legs run their complete selected suites and
  retain exact source, interpreter and backend identities.
- The offline kit installs and passes its real acceptance checks with the
  packaged dependencies, including Z3, and the backend source companion.
- Installed-wheel PE64, DOS/QEMU and boot acceptance runs with strict fixture
  requirements and reports unavailable prerequisites as incomplete or failed.
- A deliberately missing or failed required job cannot produce a successful
  qualification receipt, even if GitLab paints the overall pipeline green.
- Logs/artifacts are sufficient to investigate a failure without repeating the
  original action or creating duplicate pipelines.

Keep game/story files, emulator states, project databases, private runtime
captures and credentials outside source and CI artifacts. Authored synthetic
fixtures and sanitized receipts should follow the existing distribution guards.
Passing this CI plan does not authorize a merge, tag, release or installation.

## Existing KQ1 work

The bounded controller/alignment/frame-state changes at
`a16e80ff51fe106f43f8251b67706ba38e190232` are ancestors of the baseline main
commit above. Preserve that integration; do not reopen the closed stacked
MR !39 or reapply its patch. Its
[sanitized native evidence](evidence/native-alignment-coherence-2026-11-01/README.md)
records the bounded original-game verification and its limits. In particular,
the frame brackets declare `atomic:false` and do not claim exact image/CPU
equivalence. Those prior local/native results remain distinct from a new
Linux qualification of the current main tree.
