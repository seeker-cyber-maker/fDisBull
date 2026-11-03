# CI triggers and status coordination

fDisBull maintains **equal repository state** across local Git (`/Volumes/CODEX/Codex_Projects/fDisBull` and `local-hub` at `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git`) and GitLab (`gitlab` at `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project ID `88349936`) during the 30-day GitLab evaluation trial. **GitHub (`origin` / `seeker-cyber-maker/fDisBull`) is permanently retired and obsolete** (`remote.origin.pushurl` is locked to `RETIRED_GITHUB_DO_NOT_PUSH`, and `scripts/ci_status.py` blocks live refreshes against `seeker-cyber-maker/fDisBull`).

Agents are required to update **both** local Git and GitLab when landing or syncing branches and tags, while strictly preventing duplicate or unthrottled CI pipeline runs that could trigger provider abuse filters.

## Workflow routing (`.gitlab-ci.yml` and portable `.github/workflows/*`)

This table describes admission by the GitLab YAML. A skipped push, a commit
message containing `[skip ci]` / `[ci skip]`, or `FDISBULL_DISABLE_CI=1` can
still prevent jobs from being created. An admitted pipeline is not evidence
that a job ran or that native qualification passed.

| Event | `test-and-package` (fast Python/package gate) | `native-debugger-*` (45-min C++ emulator build) |
| --- | --- | --- |
| Feature, agent, or archive branch push (`codex/*`, `pr/*`, `archive/*`) | **No automatic run** (`when: never`) | **No automatic run** (`when: never`) |
| Draft Merge Request (`Draft:` / `[Draft]`) opened or updated | **No automatic run**; use an explicit API/web pipeline for qualification | No native jobs |
| Ready (non-Draft) Merge Request opened or updated | **Run** (superseded MR work is interruptible) | No native jobs |
| Default branch (`main`) push | **Run** | No native jobs |
| Explicit version tag push matching `vX.Y.Z` | **Run** | No native jobs |
| Explicit web / API pipeline | **Run** | Wait for blocking manual `native-qualification`; then run stable, layers, unified and final qualification |
| Trigger-token pipeline | **Run** | No native jobs |

### Why heavy native jobs are manual-only on GitLab

Compiling `dosbox-x` from source downloads system packages and runs a 30–45 minute C++ build. Explicit native qualification limits repeated builds and quota use. The configuration alone does not establish the cause of any provider account restriction. In `.gitlab-ci.yml`:

1. Routine pushes to topic branches do not admit jobs. GitLab can retain a skipped pipeline record with no jobs.
2. Bulk branch mirroring via `python scripts/sync_mirrors.py` always passes `-o ci.skip` on topic branches.
3. `Draft:` Merge Requests do not start automatic pipelines until marked Ready. An API/web pipeline is a separate explicit request and does not need a pipeline-variable override.
4. Jobs use `retry: 0`. Only superseded MR fast checks are interruptible; main, tag and explicit qualification work is retained. Fast checks use a per-ref resource group. These controls do not guarantee an empty queue or prohibit different refs from running concurrently.
5. API/web pipelines expose one blocking manual `native-qualification` job. Playing it once starts both complete DOSBox legs, then installed-wheel PE64/DOS/QEMU/boot acceptance and the `qualify-candidate` job. Native jobs are absent from routine push/MR pipelines, so routine fast checks do not wait for an unplayed native gate.

Native qualification is blocking and requires all declared jobs to succeed.
The DOSBox legs use explicit Python 3.12/3.13.5, source/patch/backend identities,
the full preserved suites and `--require-native`. Selected native tests may not
skip: missing prerequisites fail qualification. Layers verifies the offline kit
with genuine dependencies and Z3. Unified acceptance installs the ordinary
job's exact core wheel, and the kit carries its exact core/player wheels.
Docker-in-Docker support is a required runner capability for the unified leg;
an unavailable daemon fails that leg.

This route works when pipeline-variable overrides are prohibited by
`ci_pipeline_variables_minimum_override_role=no_one_allowed`. The old
`FDISBULL_RUN_NATIVE_CI` / `FDISBULL_RUN_DRAFT_CI` overrides are unnecessary and
no longer start native jobs. No project permission needs to be weakened.

## Dual synchronization between Local Git and GitLab

Whenever an agent updates `main`, a topic branch, or release tags, both the local Git repository and GitLab must be kept in sync:

```sh
# Dry-run planned sync commands across local-hub and gitlab:
python scripts/sync_mirrors.py --dry-run

# Sync a specific branch to both local-hub and gitlab (automatically passes -o ci.skip on GitLab):
python scripts/sync_mirrors.py --branch codex/my-feature --no-tags

# Or push directly to the configured dual remote with ci.skip:
git push -o ci.skip dual refs/heads/codex/my-feature:refs/heads/codex/my-feature
```

`sync_mirrors.py` admits fast checks for main by default and omits tags unless
requested. Topic/archive pushes always carry `-o ci.skip`. `--tag vX.Y.Z`
selects an explicit local version tag and admits its fast checks; `--tags`
mirrors all tags as archives with CI suppressed, avoiding a pipeline for every
old version. `--skip-ci` explicitly suppresses main/selected-tag checks for an
archival sync. `--no-tags` and `--ci-on-main` remain compatible options.
An up-to-date push is not a CI trigger. Do not resynchronize every ref or push
an empty commit to obtain checks: select the candidate and coordinate one
bounded API/web qualification with the CI owner. No version tag is needed.

GitLab's `ci.skip` push option does not suppress a separate merge-request
pipeline. Draft-MR rules are what keep a draft handoff from admitting jobs.
MR pipelines use the source branch's YAML, so an old branch without
`.gitlab-ci.yml` does not inherit the target's configuration merely by opening
an MR. See GitLab's [skip behavior](https://docs.gitlab.com/ci/pipelines/#skip-a-pipeline),
[manual job semantics](https://docs.gitlab.com/ci/jobs/job_control/#types-of-manual-jobs),
[pipeline-variable permissions](https://docs.gitlab.com/ci/variables/#restrict-pipeline-variables)
and [MR pipeline contract](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/).

## Candidate and package acceptance

The ordinary job derives a payload inventory from tracked runtime, player,
test and support files, then compares bytes in the wheel, player wheel, sdist
and tool ZIP. Newly added resources cannot disappear unnoticed because their
extension was absent from an older selector. Privacy/archive checks still run
separately. Built-wheel skills and isolated core/player/sdist/tool installations
are checked outside the source tree. Failure logs are retained. CI pins a
hash-verified Node 22.23.4 toolchain and checks real Web Crypto/WebAssembly
availability before the suite; a distro's older Node must not silently replace
the runtime used by the former workflow.

`qualify-candidate` depends on every required job. It rechecks receipt source,
pipeline and job identities, interpreters, JUnit coverage and artifact hashes.
Missing, skipped, canceled, failed or wrong-source evidence cannot produce
`qualification.json`. Fast-only pipeline success is not release qualification.

Before packaging a release for publication, obtain the successful
`qualify-candidate` artifact for the exact source commit. Preserve the package
hashes; do not silently rebuild or substitute a local wheel. The artifact
includes the raw receipts/JUnit and tested payloads so the offline validator can
be rerun from its extracted root:

```sh
python scripts/check_ci_qualification.py --root /external/qualified-candidate \
  --source-commit FULL_COMMIT_SHA --pipeline-id PIPELINE_ID \
  --output /external/rechecked-qualification.json
```

This validates the evidence, not permission to publish. Provider completion and
the exact pipeline/job IDs remain part of the release review. Tagging,
publication and installation require their separate user authorization. Keep
the historical [migration comparison](CI_MIGRATION_HANDOFF.md) as the rationale
for these gates.

## One owner and a finite status command

Name one CI owner per repository before observing hosted checks. The owner
publishes the exact head, run IDs, observation time, terminal conclusions and
next permitted refresh time. Other agents consume that receipt and continue
independent work. They do not each refresh GitLab or GitHub.

From a source checkout, any agent can read the local receipt without network
access:

```sh
python scripts/ci_status.py --host gitlab.com --repo brewster-jennings-group/fdisbull --sha "$(git rev-parse HEAD)"
```

Only the named owner requests one refresh:

```sh
python scripts/ci_status.py --host gitlab.com --repo brewster-jennings-group/fdisbull --sha "$(git rev-parse HEAD)" --refresh --owner YOUR_CHAT_ID
```

The helper performs at most one bounded provider API request (`glab api` for GitLab or `gh api` for portable GitHub fallback) per invocation and has no watch, force or automatic retry mode. A repository-wide five-minute cooldown is reserved before network access, including failed requests. Cached results are separated by exact host, repository and full commit SHA. A different SHA does not bypass the repository cooldown. Receipts preserve their observation time; cached success is not a new live observation or a qualification verdict.

The resolved Git common directory shares the owner, lock, cooldown and cache across sibling local worktrees. `--state-dir` supports an explicitly selected shared directory or isolated verification.

## Failures and recovery

Missing runs, incomplete pages, mismatched SHAs, stale data and provider errors remain explicit. Inspect failed job logs once after a terminal failure; do not poll each matrix job while it runs. Do not combine this command with separate connector loops, `glab ci trace`, or `gh run watch`.

Authentication/access failures, rate limits, CI quota exhaustion and confirmed account restrictions stop refreshes through a persisted `provider_stop`. Do not repeatedly retry, change accounts/repositories, weaken checks or push empty commits to evade the condition. Resolve normal provider access first.

Do not start watchers, scheduled checks or monitoring services without a separate user request. Source fixes, CI qualification, review readiness, merging and releasing remain separate gates.
