# Production CI recovery

This is the control-plane contract, not a release qualification. Installed
source, provider results, closed exports, native health receipts and the
operational acceptance record determine which deployment is live. Fixture
tests alone do not establish activation, notification delivery or recovery of
a naturally occurring failure.

## Execution and ownership

The existing n8n operations timer reads the fixed native `status` command. Its
reply contains only `schema_version` and `pending_work`; the read performs no
provider request, model call or queue mutation. A pending result lets the
existing authenticated bridge start `fdisbull-ci-production.service`. There is
no second schedule or model polling loop.

One native service holds the existing OVH executor flock for its complete
incident. Durable intake and action records precede any non-idempotent action.
The original repository's manual GitHub workflow runs the actual ordinary
`test-and-package.sh`, using separate pinned control and candidate checkouts.
GitLab retains its deliberate web/API admission and blocking manual native
gate. Provider credentials stay on the already authenticated Mac; fixed
Tailscale SSH commands carry bounded structured requests, not credentials.

The service owns finite job, patch, request, output and incident budgets. Its
managed stop drains current work rather than killing a lease owner while
daemon-owned containers may survive. Unknown cleanup retains the lease in an
explicit attention hold. A durable blocker prevents subsequent controlled
provider operations. Only exact owned container identities may be stopped;
there is no pruning or deletion of unrelated workers or preserved results.

## Supported decisions

| Provider/job | Recognized failure | Allowed action |
| --- | --- | --- |
| GitHub ordinary | Closed, source-bound missing qualification-policy diagnostic | Restore that exact derived CI input from its retained hash-bound canonical bytes; retry the same source once |
| GitHub ordinary | One supported failed pytest node with a reproduced baseline | One bounded source worker, dedicated candidate branch, dual-provider ref readback, then a new exact-source workflow |
| GitLab ordinary | The same supported source-failure class | One bounded source worker and a new exact-source ordinary pipeline; its native gate remains manual |
| GitLab native | Canonical failed job and preserved export | Retain evidence and report attention; an existing retry adapter is not permission to invent a repair or bypass the manual gate |
| Any other, incomplete or ambiguous case | Unknown or unsupported | Preserve it as unknown/attention; do not infer success, retry indefinitely or weaken checks |

This matrix describes the implemented policy. Each route still needs its own
operational evidence before being called qualified. An induced infrastructure
failure must remain labeled induced. A successful job rerun qualifies that job
and candidate; it does not qualify a complete release or every backend.

## Source-worker boundary

The source selector accepts one non-parameterized failed test from an ordinary
JUnit report whose bytes are bound to a closed canonical job export. It maps
the test and up to three direct first-party source imports against the exact
Git commit. Protected test and verifier hashes, a clean isolated worktree and
an actually failing baseline are mandatory.

The existing Mac Python environment is explicitly pinned. Its reproducer is a
Mac-local observation, not Linux parity. The worker may change only the chosen
source files, within a 64 KiB diff, 300-second wall-time and bounded output.
The installed CLI has no hard token-budget flag; recorded token usage is an
audit value, not an enforced cap. Tests, CI configuration and protected
verifiers cannot be edited to make the result green.

Only a new, single-parent candidate commit with a passing reproducer may be
pushed to its dedicated `codex/ci-repair-*` ref. Both named provider identities
and both exact remote refs are verified. GitLab publication uses `ci.skip`;
qualification is a separate deliberate dispatch. Unknown publication is
readback-only: it does not repeat a push. Source repair never merges main,
moves tags, publishes a package or changes an installed application.

## Evidence and terminal results

Failure evidence is retained before classification: canonical provider
metadata, original bounded private log, source postcheck and a closed byte-hash
inventory. Source selection transfers bounded verified JUnit evidence;
provider logs never become model instructions or notification content.

GitHub binds actual numeric run, attempt, job and runner identities to the
control SHA and independently verified candidate checkout. The listener also
checks for other active runs before starting; its local lease cannot exclude
an unauthorized external actor racing at the provider. GitLab's ref-only API
likewise requires immediate ref readback and rejects a resulting SHA mismatch;
it is not an atomic compare-and-dispatch operation.

Recovery requires the correct candidate's canonical terminal success, clean
closed export, required real package/test artifacts and a durable healthy host
decision. A successful API response or artifact upload alone is insufficient.
Incident phases enter the existing notification journal. Journal acceptance,
delivery acceptance and a human seeing a phone notification are separate facts.

## Installation and publication gates

The native CLI checks the exact installed module set and entrypoint hash before
importing mutable control code. Provider action state is on the verified CODEX
volume with a separate small history anchor; missing mount, marker or history
fails closed instead of creating an empty replacement. Source selection and
publication require their own explicit private activation manifest.

An original no-network kit acceptance remains immutable. New source requires a
distinct private candidate and new consumer evidence. Every future large
download also needs its own scoped serving policy, HEAD-before-range checks,
exact first/middle/tail bytes, a complete download hash and an actually
interrupted `Range`/`If-Range` resumed hash. The successful existing archive's
CDN check is not a blanket qualification for future URLs. Release, tag and
system-wide application installation remain separate human-authorized steps.
