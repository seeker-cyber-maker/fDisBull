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

Configuration contains source/state paths, a retained credential-free CI
transport helper, the selected branch and full initial SHA, runner/project
identities, the existing SSH argv, a pinned boot ID, expected marker bytes/hash,
owner ID, and a finite deadline. It contains no credential material. Keep it,
worker logs, runtime outputs and incident evidence outside the checkout.

This rehearsal does not qualify an application release, a backend migration,
an offline package, arbitrary source repair, or unattended recovery of every
CI failure. Extending the allowlist requires a concrete failure and reproducer.
