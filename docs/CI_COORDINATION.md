# CI triggers and status coordination

fDisBull maintains **equal repository state** across local Git (`/Volumes/CODEX/Codex_Projects/fDisBull` and `local-hub` at `/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git`) and GitLab (`gitlab` at `https://gitlab.com/brewster-jennings-group/fdisbull.git`, project ID `88349936`) during the 30-day GitLab evaluation trial. **GitHub (`origin` / `seeker-cyber-maker/fDisBull`) is permanently retired and obsolete** (`remote.origin.pushurl` is locked to `RETIRED_GITHUB_DO_NOT_PUSH`, and `scripts/ci_status.py` blocks live refreshes against `seeker-cyber-maker/fDisBull`).

Agents are required to update **both** local Git and GitLab when landing or syncing branches and tags, while strictly preventing duplicate or unthrottled CI pipeline runs that could trigger provider abuse filters.

## Workflow routing (`.gitlab-ci.yml` and portable `.github/workflows/*`)

| Event | `test-and-package` (fast Python/package gate) | `native-debugger-*` (45-min C++ emulator build) |
| --- | --- | --- |
| Feature, agent, or archive branch push (`codex/*`, `pr/*`, `archive/*`) | **No automatic run** (`when: never`) | **No automatic run** (`when: never`) |
| Draft Merge Request (`Draft:` / `[Draft]`) opened or updated | **No automatic run** unless `FDISBULL_RUN_DRAFT_CI=1` | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Ready (non-Draft) Merge Request opened or updated | **Run** (interruptible, serialized per ref) | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Default branch (`main`) push | **Run** | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Version tag push matching `vX.Y.Z` | **Run** | Manual / `FDISBULL_RUN_NATIVE_CI=1` only |
| Explicit web / API / manual trigger | **Run** | **Run** when manually played or `FDISBULL_RUN_NATIVE_CI=1` |

### Why heavy native jobs are manual-only on GitLab

Compiling `dosbox-x` from source downloads system packages and runs a 30–45 minute C++ build. Running multi-job C++ compilations automatically on every agent push or Draft MR was a primary trigger for automated provider spam/abuse flags. In `.gitlab-ci.yml`:

1. Routine pushes to topic branches **never** create pipelines.
2. Bulk branch mirroring via `python scripts/sync_mirrors.py` always passes `-o ci.skip` on topic branches.
3. `Draft:` Merge Requests do not start automatic pipelines until marked Ready (or explicitly dispatched with `FDISBULL_RUN_DRAFT_CI=1`).
4. Every job sets `interruptible: true`, `retry: 0`, and a per-ref `resource_group` so superseded runs cancel immediately and concurrent jobs never pile up.
5. `native-debugger-stable` and `native-debugger-layers` are `when: manual` by default and are triggered explicitly only when qualifying a release candidate SHA before tagging.

## Dual synchronization between Local Git and GitLab

Whenever an agent updates `main`, a topic branch, or release tags, both the local Git repository and GitLab must be kept in sync:

```sh
# Dry-run planned sync commands across local-hub and gitlab:
python scripts/sync_mirrors.py --dry-run

# Sync a specific branch to both local-hub and gitlab (automatically passes -o ci.skip on GitLab):
python scripts/sync_mirrors.py --branch codex/my-feature

# Or push directly to the configured dual remote with ci.skip:
git push -o ci.skip dual refs/heads/codex/my-feature:refs/heads/codex/my-feature
```

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
