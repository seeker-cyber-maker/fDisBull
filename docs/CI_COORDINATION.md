# CI triggers and status coordination

fDisBull maintains **equal repository state** across local Git (`/Volumes/CODEX/Codex_Projects/fDisBull` and `local-hub` at `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git`) and GitLab (`gitlab` at `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project ID `88349936`) during the 30-day GitLab evaluation trial. **GitHub (`origin` / `seeker-cyber-maker/fDisBull`) is permanently retired and obsolete** (`remote.origin.pushurl` is locked to `RETIRED_GITHUB_DO_NOT_PUSH`, and `scripts/ci_status.py` blocks live refreshes against `seeker-cyber-maker/fDisBull`).

Agents are required to update **both** local Git and GitLab when landing or syncing branches and tags, while strictly preventing duplicate or unthrottled CI pipeline runs that could trigger provider abuse filters.

## Workflow routing (`.gitlab-ci.yml` and portable `.github/workflows/*`)

This table describes admission by the GitLab YAML. A skipped push, a commit
message containing `[skip ci]` / `[ci skip]`, or `FDISBULL_DISABLE_CI=1` can
still prevent those jobs from being created. In particular, the current mirror
helper suppresses **main and tag pushes as well as topic pushes by default**;
see the synchronization section below. An admitted pipeline is not evidence
that a job ran or that native qualification passed.

| Event | `test-and-package` (fast Python/package gate) | `native-debugger-*` (45-min C++ emulator build) |
| --- | --- | --- |
| Feature, agent, or archive branch push (`codex/*`, `pr/*`, `archive/*`) | **No automatic run** (`when: never`) | **No automatic run** (`when: never`) |
| Draft Merge Request (`Draft:` / `[Draft]`) opened or updated | **No automatic run** unless `FDISBULL_RUN_DRAFT_CI=1` | No job unless the draft pipeline is admitted; then manual / `FDISBULL_RUN_NATIVE_CI=1` |
| Ready (non-Draft) Merge Request opened or updated | **Run** (interruptible, serialized per ref) | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Default branch (`main`) push | **Run** | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Version tag push matching `vX.Y.Z` | **Run** | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Explicit web / API / manual trigger | **Run** | **Run** when manually played or `FDISBULL_RUN_NATIVE_CI=1` |

### Why heavy native jobs are manual-only on GitLab

Compiling `dosbox-x` from source downloads system packages and runs a 30–45 minute C++ build. Explicit native qualification limits repeated builds and quota use. The configuration alone does not establish the cause of any provider account restriction. In `.gitlab-ci.yml`:

1. Routine pushes to topic branches do not admit jobs. GitLab can retain a skipped pipeline record with no jobs.
2. Bulk branch mirroring via `python scripts/sync_mirrors.py` always passes `-o ci.skip` on topic branches.
3. `Draft:` Merge Requests do not start automatic pipelines until marked Ready (or explicitly dispatched with `FDISBULL_RUN_DRAFT_CI=1`).
4. Jobs use `interruptible: true`, `retry: 0`, and per-ref `resource_group` values. These permit cancellation of superseded interruptible work and serialize jobs sharing a resource group; they do not guarantee immediate cancellation or an empty queue. Different refs can still run concurrently.
5. `native-debugger-stable` and `native-debugger-layers` are `when: manual` by default on admitted pipelines. Release qualification requires deliberately running the required jobs on the candidate SHA before tagging; the YAML does not restrict manual play to releases.

The default manual native jobs have `allow_failure: true`. A successful pipeline
can therefore contain native jobs that were never played; a failed optional
native job also does not make the whole pipeline fail. The current GitLab
native path uses shorter test selections than the preserved GitHub workflow,
does not pass `--require-native`, and does not include the downstream installed
wheel PE64/DOS/QEMU/boot or offline-kit qualification. Its green status must not
be described as the full former native gate. The
[migration handoff](CI_MIGRATION_HANDOFF.md) defines the remaining work.

The variable opt-ins in the table also depend on project permissions. If
`ci_pipeline_variables_minimum_override_role` is `no_one_allowed`, callers cannot
supply these overrides as pipeline variables through the web/API/trigger routes.
That restriction does not disable variables already defined in YAML, project
settings or group settings. Verify the intended admission route before starting
a qualification; changing project permissions is a separate authorized action.

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

`sync_mirrors.py` currently defaults to `ci_on_main=False` and includes tags
unless `--no-tags` is supplied. Thus its default main **and tag** push commands
carry `-o ci.skip`. `--ci-on-main` removes that option from both main and tag
pushes; topic/archive pushes remain suppressed. This flag does not rerun an
already synchronized ref, and an up-to-date push is not a CI trigger. It also
does not make native jobs mandatory. Do not resynchronize every ref or push an
empty commit to obtain checks: select the intended candidate and coordinate
one bounded qualification with the CI owner.

GitLab's `ci.skip` push option does not suppress a separate merge-request
pipeline. Draft-MR rules are what keep a draft handoff from admitting jobs.
MR pipelines use the source branch's YAML, so an old branch without
`.gitlab-ci.yml` does not inherit the target's configuration merely by opening
an MR. See GitLab's [skip behavior](https://docs.gitlab.com/ci/pipelines/#skip-a-pipeline),
[manual job semantics](https://docs.gitlab.com/ci/jobs/job_control/#types-of-manual-jobs),
[pipeline-variable permissions](https://docs.gitlab.com/ci/variables/#restrict-pipeline-variables)
and [MR pipeline contract](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/).

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
