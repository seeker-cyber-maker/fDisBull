# Bounded OVH CI recovery

`recovery-run.py --config /private/path/config.json` drives one explicitly
selected incident to a terminal receipt. It is not a scheduled service. The
existing GitLab runner executes one job at a time; the controller additionally
holds the shared host executor lease. Healthy waiting uses no model calls.

The initial qualification is deliberately limited to `ci-recovery-rehearsal`.
That API-only job is excluded from ordinary/native release qualification, and
excludes those jobs when selected. It first fails for a missing CI-owned input,
then exposes a deliberately incomplete predicate in `recovery_probe_logic.py`.
The worker may repair only that file. Original failures remain failed.

Dispatch uses validated pipeline inputs, with harmless defaults for ordinary
pipelines. It does not require or enable pipeline-variable overrides. The
action hash is bound to the provider's pipeline name for canonical readback.

The finite controller retains and verifies each completed job's export before
classification. It permits one known input repair and one source worker, with
fresh production-health checks before dispatch. Unknown evidence, conflicting
identities, repeated failure, exceeded budgets, or unavailable health stop it.
It does not repair n8n, websites, authentication or account restrictions.

Source repair uses the already authenticated local Codex CLI once, with a
five-minute deadline and bounded logs. The parent verifies the unchanged
reproducer, the allowed diff, real process completion and successful replay;
then commits the fix and synchronizes the selected branch to local Git and
GitLab. A changed candidate receives a new pipeline. No force-push is allowed.

All mutations have durable intent records. After an uncertain response, the
controller reads canonical provider state; it never repeats the original POST
merely because observation failed. Ambiguity requires attention. The source
worker is not automatically relaunched after an uncertain result.

The existing repository-wide provider reservation retains its five-minute
cooldown and persistent access/rate-limit stop. Configuration must name its
current owner; this command has no takeover, reset or force switch.
An immediately resulting retry/dispatch can complete in the same reserved
observation batch; the next status observation still waits for a new interval.

Failure/recovery events go to the existing operations incident journal with a
stable incident key. An accepted journal write proves neither notification
delivery nor execution. Those outcomes require separate observed receipts.

The GUI provider adapter also reserves execution time inside the existing
five-minute provider batch: 180 seconds for its at-most-two GET attempts,
75 seconds for a single action-bound GitHub POST, and 110 seconds for GitLab's
principal check followed by its single POST. A nearly expired batch waits for
normal renewal; it is not reset early. Waiting checks the executor lease,
source pins and production health, and is bounded by the caller's deadline.
This does not authorize replaying a POST or repeating a source-worker launch.

When the first canonical observation is unavailable, the controller can emit
an attention notice without asserting that the CI job failed. The producer
requires the actual private manifest and stopped state, with no observations,
evidence, repairs or actions, and saves an immutable snapshot and hash binding.
The existing five-field journal request and seven-field context are unchanged.
The reserved key `controller-attention:<incident-id>` accepts only attention
with reason `ci_executor_unavailable` and the matching snapshot path. Normal
job Down/Recovered transitions keep their existing rules. Reentry reuses the
same event identity; an uncertain local append acknowledgement permits one
identical journal lookup/append, not another CI action or message send.

`operations/ci_incident.py` and `operations/notification_journal.py` retain the
native journal protocol sources for review and deployment. The producer owns
private-file verification; the unprivileged journal validates the context and
path binding, without opening the private snapshot. These sources do not
install a receiver or notification service. Record each deployed component's
commit and hash separately from the workflow-control SHA when recovering an
older run; do not relabel that run as using a newer workflow.

Some pytest 9 reports count passing subreports in the suite total while reusing
their parent testcase nodes. An ordinary report with that count mismatch needs
its closed-inventory `tests.log`: one complete terminal summary must reconcile
every parent, directly skipped case, skipped node and passing subtest exactly.
Missing or ambiguous captures fail verification. Native reports and the 26
required contracts retain their strict checks.

A verifier correction does not rewrite a controller's earlier terminal
attention state. Revalidate the original closed export and canonical provider
capture, then retain a separate immutable operator-assisted closure certificate
under the incident's `reconciliation/` directory. Bind the original state,
manifest and actions, successful job evidence, corrected verifier commit and
component hashes, and record `automatic_controller_complete: false`. The
existing incident journal can record `recovered/ci_requalified` for the actual
verified job; journal acceptance, delivery and automatic controller recovery
remain separate claims.

Configuration contains source/state paths, a retained credential-free CI
transport helper, the selected branch and full initial SHA, runner/project
identities, the existing SSH argv, a pinned boot ID, expected marker bytes/hash,
owner ID, and a finite deadline. It contains no credential material. Keep it,
worker logs, runtime outputs and incident evidence outside the checkout.

This rehearsal does not qualify an application release, a backend migration,
an offline package, arbitrary source repair, or unattended recovery of every
CI failure. Extending the allowlist requires a concrete failure and reproducer.
