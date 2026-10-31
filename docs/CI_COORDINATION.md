# CI triggers and status coordination

Feature work receives automatic checks through pull requests. A push to the
feature branch does not start a second copy of the same workflows. Required
test bodies and check names remain unchanged. Main and version tags retain
their own qualification runs, and both workflows remain manually dispatchable.

## Workflow routing

| Event | Tests and tool packages | Native debugger acceptance |
| --- | --- | --- |
| Feature branch push | No automatic run | No automatic run |
| PR opened, reopened or synchronized, including draft PRs | Run | Run when native-relevant paths change |
| Main push, including documentation changes | Run | Run |
| Version tag push matching `v*` | Run | Run |
| Explicit manual dispatch | Run the selected workflow | Run the selected workflow |

Native PR paths include workflow definitions, source, tests, player code,
native backend inputs and the existing offline-kit build/verification scripts.
Documentation-only PRs retain ordinary checks; their absent native checks do
not prove native qualification. Manually dispatch both workflows if the
selected branch needs complete qualification before a PR or release.

Superseded runs of the same workflow and PR share a concurrency group and can
be cancelled. Different PRs and different workflows remain independent. Main,
tag and manual runs use unique run IDs, so a new run cannot replace a pending
qualification for another commit. GitHub does not guarantee arrival order;
verify the current head and its terminal results before declaring readiness.

These check identities and their complete existing test/build steps remain:

- `test-and-package`
- `Native debugger (stable-backend)`
- `Native debugger (layers-backend)`
- `Unified DOS, boot and PE64 (installed wheel)`

Both native profiles, required native selectors, installed-wheel acceptance,
offline-kit/Z3 verification, package checks, bundled-skill gates and evidence
uploads remain required where applicable. PR integration checks can test a
merge context; do not relabel them as qualification of a different main or tag
commit. A release requires ordinary and required-native success on its exact
commit **before tagging**. Post-tag checks cannot satisfy that earlier gate.

## One owner and a finite status command

Name one CI owner per repository before observing hosted checks. The owner
publishes the exact head, run IDs, observation time, terminal conclusions and
next permitted refresh time. Other agents consume that receipt and continue
independent work. They do not each refresh GitHub.

From a source checkout, any agent can read the local receipt without network
access. The helper currently requires Linux/macOS file locking; unsupported
platforms return an explicit local error without contacting GitHub:

```sh
python scripts/ci_status.py --repo seeker-cyber-maker/fDisBull --sha "$(git rev-parse HEAD)"
```

Only the named owner requests one refresh:

```sh
python scripts/ci_status.py --repo seeker-cyber-maker/fDisBull --sha "$(git rev-parse HEAD)" --refresh --owner YOUR_CHAT_ID
```

The helper performs at most one bounded GitHub request per invocation and has
no watch, force or automatic retry mode. A repository-wide five-minute cooldown
is reserved before network access, including failed requests. Cached results
are separated by exact host, repository and full commit SHA. A different SHA
does not bypass the repository cooldown. Receipts preserve their observation
time; cached success is not a new live observation or a qualification verdict.

The resolved Git common directory shares the owner, lock, cooldown and cache
across sibling local worktrees. `--state-dir` supports an explicitly selected
shared directory or isolated verification. Independent cloud clones do not
share that filesystem: one named owner across those clones must publish the
receipt through the existing coordination channel. This helper is not an
account-wide rate limiter or a background coordination service.

## Failures and recovery

While GitHub access is disabled, continue source work and local checks through
the caller's selected local Git hub. Keep `origin` unchanged, publish only the
agent's own branch to the local transport, and record the base, head and local
verification receipt. Do not probe or dispatch hosted workflows in this mode.
Local test success does not replace the ordinary and required-native Linux
qualification gates after normal access returns.

Missing runs, incomplete pages, mismatched SHAs, stale data and provider errors
remain explicit. Inspect failed job logs once after a terminal failure; do not
poll each matrix job while it runs. Do not combine this command with separate
connector loops or `gh run watch`.

Authentication/access failures, rate limits and confirmed account restrictions
stop refreshes through a persisted provider stop. Do not repeatedly retry,
change accounts/repositories, weaken checks or push empty commits to evade the
condition. Resolve normal provider access first. For an intentional ownership
handoff or recovery after access is confirmed restored, the operator can
archive the old local state and select a new state directory; retain the old
receipt and record the handoff. This is an explicit local recovery operation,
not an automatic response to an error.

Do not start watchers, scheduled checks or monitoring services without a
separate user request. Source fixes, CI qualification, review readiness, merging
and releasing remain separate gates.
