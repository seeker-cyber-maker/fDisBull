# CI triggers and status coordination

For the complete source-to-release sequence, ownership and identity requirements,
start with [the release process](RELEASE_PROCESS.md). The intended next release is
0.35.0; CI success alone does not establish release completion.

The user selected original GitHub [`seeker-cyber-maker/fDisBull`](https://github.com/seeker-cyber-maker/fDisBull), repository ID `1431097789`, as the preferred source/review platform. The connected `TiGa-RCE` account now has Write access. `TiGa-RCE/fdisbull` is a distinct partial import, not the restoration target.

The guarded mirror service preserves original GitHub, local-hub and GitLab refs. GitHub and GitLab use separate durable histories and one outer lock. GitLab pushes retain `ci.skip`; GitHub/local pushes do not receive that option. Historical tag identities remain immutable. See [the restoration contract](GITHUB_RESTORATION.md).

**CI owner: n8n. The manual GitHub → OVH bootstrap passed on 2026-11-13.** [Run 43512305780](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/43512305780), attempt 1, completed successfully on runner `fdisbull-ovh-ca-gh1`; its artifact was independently verified and [handed back to PR #84](https://github.com/seeker-cyber-maker/fDisBull/pull/84#issuecomment-6865708771). Actions is enabled, `ovh-bootstrap.yml` is manual-only, and legacy workflow IDs `394106283` and `394474280` remain disabled. Its finite worker shares the OVH executor lock with GitLab and relinquishes the lock after owned-process cleanup. Pushes, PRs and tags do not automatically dispatch this workflow. Only n8n dispatches/observes jobs; other workers consume dated receipts.

This establishes infrastructure and artifact handoff, not application/native qualification. The real qualification checker rejected missing ordinary/native receipts and emitted `release_ready=false`. Existing exact-candidate GitLab/local receipts retain their own scope. QEMU qualification, the full offline consumer kit and release publication remain separate gates.

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

## Legacy local/GitLab helper

Use the installed guarded three-way service for normal propagation. Push an ordinary source branch to `origin` or `local-hub`; the service preserves the other endpoints. The legacy `scripts/sync_mirrors.py` helper is only for reviewed local/GitLab operations. Do not use the old `dual` command or pass `ci.skip` to GitHub/local-hub. Manual GitLab pushes require `-o ci.skip`.


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

## Finite agent waits and controller handoffs

Reviewers must not remain active solely to wait for another CI chat. Read the
owner's existing receipt first. At most one bounded chat wait of up to 60 seconds
is appropriate for an imminent result; do not renew it merely because the owner
is active or its cursor changed. If the required result is unavailable, publish
the completed review, name the missing evidence and its owner, and end the turn
or continue independent authorized work. Resume review when concrete new evidence
is available. This rule does not stop an authorized finite worker or replace the
existing n8n service with a chat-based polling loop.

The CI owner maintains one durable current-state handoff in the existing control
records. Include the incident, run and attempt, exact application and workflow
commits, owner, current stage, last substantive progress time, stage deadline,
next action, blocker and paths to retained results. Repeated status reads and
additional passing test counts are not substantive progress by themselves.

Controller stages need finite deadlines and explicit success, failure or
attention outcomes. A timeout must retain the original action intent and evidence;
it must not authorize replay of an uncertain mutation. A completed job must not
leave an idle holder retaining the executor indefinitely. Before releasing or
transferring ownership, reconcile live workers and unresolved actions under the
existing executor protocol. Report controller attention through the existing
deduplicated notification route, including failures before job-evidence capture.

When a verifier rejects a completed export, preserve it and correct the verifier
against that real evidence without weakening failure detection. Reuse the export
where source identity and completeness remain valid; do not rebuild merely to
repair receipt interpretation. Record operator-assisted reconciliation separately
from automatic recovery. A fix, a successful rehearsal and a recovered production
incident are distinct outcomes. These are required behaviors, not a declaration
that the current deployment has passed them.
