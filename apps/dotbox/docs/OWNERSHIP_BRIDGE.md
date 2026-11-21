# Viewer ownership bridge

The bridge coordinates cooperating desktop callers from sampled observations of
the existing viewer UI. It is a decision fence around an action, not an atomic
tool-capture lock or a server ownership lease. A takeover and return occurring
entirely between samples can be missed. The outer harness continues to own input
capture and any input already in flight.

The bridge is **off by default**. Without `--ownership-viewer`, session status
retains exactly `{"owner":"unknown","source":"unavailable"}` for
`platform_takeover`. Enabling it preserves session `owner="harness"`,
`native_owner="host"` and the desktop input path. Direct native agent input stays
disabled; `--manual-control` cannot be combined with the bridge.

For an ownership receiver that does not need an emulator, use:

```sh
dotbox coordinate --directory '<private-directory>' --ownership-viewer '<viewer-sha256>'
dotbox status --session '<private-directory>/session.json'
dotbox coordinator-close --session '<private-directory>/session.json'
```

This uses the same authenticated transport, separate publisher capability and
turn leases as `serve`. Its status contains only `instance_id`,
`kind="ownership-coordinator"` and `platform_takeover`. It launches no backend
and refuses game, frame, native input and native handoff operations. Shutdown
also accepts SIGINT/SIGTERM and removes its descriptors and credentials. Keep
the normal descriptor local to the cooperating caller; publisher possession
does not authorize status, turn claims or shutdown.

## Enable and bind one viewer

Add `--ownership-viewer <viewer-sha256>` to the existing verified `dotbox serve`
invocation. The binding is lowercase SHA-256 of the **complete URL string** in
the selected browser tab's fresh CUA snapshot header. The observer also requires
the header URL and root AX web-area URL to agree. A Dot name or hostname alone
does not bind a viewer. Keep the URL and all connection/chat identifiers private.

The service creates two private descriptors in its existing session directory:

| Descriptor | Capability |
| --- | --- |
| `session.json` | Normal session client and cooperating turn operations. |
| `ownership-publisher.json` | Publish ownership evidence only. Its separate credential cannot inspect frames, claim turns, inject input, pause or close the game. |

Descriptors refer to private credential files; they contain no inline token.
Do not copy provider credentials or put credentials in command arguments. Session
directories require mode 0700; descriptor, credential and mailbox files remain
private regular files. Stopping the service removes its published descriptors.

Inspect the actual interfaces before configuring a route:

```sh
dotbox serve --help
dotbox turn-claim --help
dotbox turn-check --help
dotbox turn-release --help
python -m dotbox.ownership_publisher --help
python -m dotbox.ownership_source --help
```

## Publish fresh evidence

The data-only `OwnershipState(viewer_id, ttl=3.0)` exposes `open`, `challenge`,
`observe`, `invalidate`, `status`, `claim`, `check` and `release`. It performs no
authentication or native input. `PlayService` supplies the authenticated,
serialized interface and session binding.

The receiver uses its own monotonic clock. The default observation TTL is three
seconds, beginning when it issues a challenge, **not** when an event arrives.
No remote wall clock can extend it.

1. An authenticated `bridge-open` binds `viewer_id`, creates a random stream ID
   and invalidates earlier leases.
2. `bridge-challenge` issues a one-use random challenge and next sequence.
3. The source observes the selected UI after receiving that probe and returns
   exactly `stream_id`, `challenge`, `sequence`, `owner`, `viewer_mode` and
   `connection`.
4. `bridge-observe` consumes the challenge. Dot eligibility requires `owner=dot`,
   `viewer_mode=observe` and `connection=live`. Human, partial, contradictory,
   unknown or expired evidence cannot authorize an agent turn.

Old streams and reordered/replayed probes are rejected. Publisher replacement,
invalidation and expired evidence invalidate turn leases; current-stream
malformed observations also revoke the grant. Changes to the native
run/session/control identity invalidate
coordination. A fresh heartbeat never extends an already issued lease's original
deadline or revives its token after invalidation.

The finite publisher accepts a private JSON **argument-list** file for an
already authorized transport, such as an existing SSH route. It invokes that
command without a local shell, sends one JSON probe on stdin, and accepts one
bounded JSON event on stdout. It adds no network listener, tunnel or account.
Timeout/error cleanup terminates the invocation's owned process group; publisher
exit explicitly invalidates its stream, with receiver expiry as fallback.

```sh
python -m dotbox.ownership_publisher \
  --publisher '<session-directory>/ownership-publisher.json' \
  --viewer-id '<viewer-sha256>' \
  --source-command '<private-command-arguments.json>' \
  --duration 30 --interval 0.1
```

Replace the placeholders with private operator-selected values. The configured
source command can run `python -m dotbox.ownership_source` using its documented
`--directory`, `--viewer-id` and `--timeout` arguments. It forwards the probe into
an existing private source-host mailbox, correlates the response with another
random request nonce, and returns the event on stdout. An old response cannot
satisfy a new request. The source exchange opens no listener.

## Run the bounded viewer observer

[The authored observer](../scripts/observe_ownership.mjs) exports
`pumpMailbox(tab, dotName, options)` for the supported CUA browser context:

```js
await pumpMailbox(tab, dotName, {
  directory: mailboxDirectory,
  viewerId,
  ownerUid,
  durationMs: 30000,
  onObservation: recordSample,
});
```

Use the already selected browser `tab`, the expected Dot name and the same full
URL hash as the receiver. Supply `ownerUid` from trusted host configuration;
CUA forbids `node:process`, so the observer deliberately does not discover it
through that module or trust a mailbox's claimed owner. The mailbox must already
exist with mode 0700 and that UID. The pump validates small 0600 regular files,
directory identity and unchanged probes before atomically writing responses.

Each new probe requests a full AX snapshot through `tab.getAXState`. The parser
requires the selected computer panel, matching owner text and checkbox, and the
expected live-viewer structure. Here `connection=live` describes that UI, not
an independent server liveness check. A stalled UI may retain labels. Missing,
ambiguous, disconnected, mismatched or
failed observations yield unknown. Raw AX text and URLs are not returned by the
pump. Its optional callback receives a compact sample and hashes before response
delivery; that callback and the pump's processed count are not receiver
acknowledgements. Runs are finite, with a maximum pump duration of 60 seconds.

## Gate cooperating actions

The ordinary client supports:

```python
lease = client.wait_for_turn(controller_id, timeout=10, interval=0.1)
result = client.run_turn_step(lease, action)
```

`action` is one already authorized, zero-argument desktop callback.
It must return a completed synchronous result. An awaitable result raises
`TurnInterrupted`; the helper never awaits it or returns it as a successful
fenced action. Only an unstarted native coroutine is closed. Other awaitables
stay caller-owned and are not cancelled or resumed. A callback can have effects
before returning an awaitable, so rejection still requires inspection.

For a supported Python executor that already has both the coordinator client
and an authorized asynchronous action, use the separate awaited helper:

```python
result = await client.run_turn_step_async(lease, authorized_action_and_observation)
```

The zero-argument callback must return a fresh, unstarted native coroutine,
normally from an `async def` function. Put input and its effect observation
inside that coroutine when checking both. The helper copies the original flat
receipt before its first await, checks it, awaits the action once to completion,
then checks the same captured receipt. It never renews or substitutes a lease,
even if the caller changes its original dictionary or newer evidence arrives.
Read-only socket checks run in worker threads so the event loop can continue
receiving observations. An event-loop caller can also use
`await asyncio.to_thread(client.wait_for_turn, controller_id, timeout=10)` to
avoid blocking while claiming its initial lease.

Tasks, Futures, started coroutines, other custom awaitables and synchronous
results are refused by this asynchronous API. Rejection does not cancel, close
or resume caller-owned work. A coroutine that returns another awaitable is also
refused; only a fresh native coroutine returned this way is closed. The helper
does not recursively await work or describe a deferred result as completed.

`TurnInterrupted.result` preserves a completed outcome if the postcheck fails.
`asyncio.CancelledError` propagates with an inspection note and a `result`
attribute containing the completed outcome when cancellation occurs during
the postcheck, otherwise `None`. Cancellation does not replay input, renew or
release a turn, or undo effects. A socket check already running in its worker
thread can finish within the client's existing timeout. The callback must
cooperate with cancellation and must not launch detached effects.
Await steps sequentially. A controller lease identifies the cooperating caller;
it does not serialize overlapping callbacks that share the same receipt.

This Python helper does not make model-level CUA tools callable from Python or
add turn operations to the status-only MCP connector. Actual CUA input still
needs a supported path on its original executor, with coordinator access and
an observed effect. Separate model-level before/tool/after calls only establish
a bounded check if the same unchanged lease is still valid afterward; they are
not an atomic tool lock.

The [17 November continuation receipt](evidence/async-turn-fence-2026-11-17.json)
records real-coordinator async regressions, cancellation checks and isolated
wheel verification. Its callbacks are harmless data operations; they do not
qualify desktop-tool input.

`wait_for_turn` waits locally while the service continues accepting source
updates; fresh Dot evidence after human return can admit the next turn.
`run_turn_step` checks the lease before and after the callback. It refuses to
start on stale evidence and raises `TurnInterrupted` if the action fails, the
post-check fails or ownership changes. Its `result`, when present, preserves the
completed callback outcome. Inspect the current desktop before deciding what to
do next; no game effect is automatically replayed or rolled back.

Only one cooperating controller holds a turn lease. Treat its JSON receipt as
opaque and unchanged: it binds viewer, stream, epoch, sequence, controller and a
random lease ID. Its expiry value describes issuance, not a renewal. Release a
completed turn with `client.request("turn-release", {"lease": lease})`.
CLI `turn-claim`, `turn-check` and `turn-release` expose the same operations; keep
saved claim receipts private. These turn leases are separate from the existing
native generation leases. Arbitrary desktop tools that bypass this wrapper are
not fenced by it.

## Historical verification boundary — 16 November 2026

At this checkpoint the source suite passed 369 checks with no skips. An ordinary Mac
wheel installation passed 107 selected checks, including existing real native
checks. One source-tree-only static audit is excluded from that external test
directory and covered by the full source suite. All 21 runtime modules match
source, wheel and installation; fDisBull is unavailable there. The observer
passes 41 checks, including atomic request replacement/deletion, unsafe
replacements and in-place mutation. Retired request reads are discarded without
stopping the pump; response-file validation remains strict.

The same 21 module identities match an ordinary wheel built and installed in the
approved managed headless environment under Python 3.12.14. Its 64 selected
isolated installed checks use real authenticated sockets and synthetic ownership.
Those checks qualify cloud loopback operation separately from live delivery.
Ten callback regressions reproduce and fix the prior helper's acceptance of
awaitable results as synchronous successes. The earlier live data-only runs
below used the previous package; their original receipts remain unchanged.

The saved environment now starts and checks out the intended private repository
after the existing GitHub connection was refreshed. Both account connections
remain present; the old failed task remains unusable. A separate network failure
was traced to the intentional source allowlist. With the user's approval, one
rule added only this runtime's access to the source host on TCP 22. Applied-filter
readback preserves every earlier rule and the compiled SSH identity policy.
The existing primary pinned SSH route then passed. No credentials, enrollment
or source-environment settings changed. See [environment repair](CLOUD_ENVIRONMENT_REPAIR.md).

A local real authenticated coordinator accepted 126 exactly joined viewer samples:
121 Dot and five human. Three harmless data callbacks cover initial permission,
automatic return and reopening. A separate live cloud run accepted 56 exactly
joined samples over the existing SSH route: 51 Dot and five human. A cooperating
waiter resumed only after fresh Dot evidence following Return control. Its
4.228-second wait includes the human-controlled interval; this is not a measured
handoff detection latency. The original lease remained rejected in 52 recorded
checks, although its release/expiry prevents attributing every rejection solely
to takeover. Startup-gap recovery labels in that run are not admitted as proof
of the later deliberate interruption.

A separate strict cloud source-gap run accepts 23 exactly joined samples. After
the opening callback, the observer is deliberately stopped and the source-host
phase flag is armed. Two failures at the source-exchange callsite directly deny
new claims and refuse the prior callback. A lease was still valid immediately
before invalidation. Fresh observations after the gap authorize a callback
under a distinct stream and lease; the old lease stays rejected. Assertions/API
failures are fatal in this witness, and mandatory completion, exit status,
empty stderr and descriptor/credential cleanup are verified independently.
The flag proves it was armed when checked, rather than the exact instant a
failed exchange began.

These are sampled coordination checks with harmless headless data callbacks.
Actual desktop input through `run_turn_step`, an atomic capture lock, server
ownership events and a guarantee against missed between-poll transitions remain
unqualified. The outer harness still owns keyboard/mouse capture and in-flight
input. Native checks use the previously prepared executable; no native rebuild,
portable-library or release installation qualification is added.

The [current sanitized receipt](evidence/ownership-coordinator-2026-11-16.json)
records exact package identities, live joins and remaining limits. The
[earlier report](evidence/ownership-bridge-2026-11-16.json) remains a historical
snapshot. Raw observations, screenshots, routes, credentials, account aliases
and environment/chat identifiers stay outside Git. Sound and gameplay remain
deferred.

The [earlier actual-input preflight](evidence/desktop-ownership-preflight-2026-11-16.json)
records the original managed-network attachment failure. The
[connection follow-up](evidence/studio-connection-repair-2026-11-16.json) clears
that failure in three strict attachments after changing only Studio's local
default from `danger-full-access` to `workspace-write`. Approval remains `never`,
the network proxy stays enabled, and all unrelated parsed settings are preserved.
No managed requirements, network grants or credentials changed. A private file
challenge, whose contents and expected digest were withheld from Dot, returned
exit 0 and the exact independently computed Studio digest. The sandboxed default
is retained. The attachment resolver did not expose its effective profile;
these successful attempts establish restored access, not a universal repair or
proof of every selected enforcement detail.

Actual desktop input through the bridge remains unverified. Selecting Studio
changed global CUA inventory to the Mac. A separate read-only retained-handle
test then found that CUA had reinitialized: the original cloud app variable was
undefined. This establishes lost handle state, rather than proving where a
surviving handle would route. Dot restored its original cloud environment after
each check; final inventory again identified the original Chromium window.
No keyboard/mouse input was issued. The checked tools still do not expose a
supported coordinator client in the original desktop executor, the retained
receiver in Dot's attachment list, or a private preview/cross-thread command
route. These are remaining capability gates, not immutable platform limits.

## Physical-controller comparison and original-executor route

The related [Claude Code/SNES demonstration](https://youtu.be/f2cLBiSWRyY?t=1346)
separates tool building from play. Its later
[cursor helper](https://youtu.be/f2cLBiSWRyY?t=2418) illustrates incremental
harness growth, without a measured speedup. The linked repository's pinned
[`step` command](https://github.com/dev-dull/questionable_commands/blob/48e8acd442d26c6d282a55875c21d57d8e71efef/cc/30102026-0x002-AI_plays_snes/bin/step#L37)
performs a local action, waits and captures locally. Its
[`gpio_lock`](https://github.com/dev-dull/questionable_commands/blob/48e8acd442d26c6d282a55875c21d57d8e71efef/cc/30102026-0x002-AI_plays_snes/lib/snespad.py#L120)
serializes processes; it does not observe human takeover. This is a useful
same-executor orchestration pattern, not a supplied Codex ownership integration.

The [follow-up receipt](evidence/controller-prior-art-2026-11-16.json) records a
separate read-only inventory on Dot's original cloud shell. SSH was present;
the Tailscale CLI, operations runbook and reviewed SSH helper were absent at the
checked locations. Absence of those files does not prove network isolation.
Dot then declined a bounded probe of the established managed-proxy/Studio SSH
route under its stated shell network policy. No connection was attempted: there
is no HTTP result, SSH banner or remote command from this executor. This is a
reported policy boundary, not a reproduced TCP refusal or an independently read
effective allowlist. The original cloud context stayed selected and no desktop
input was issued.

Keep the next acceptance check on that original executor. It needs a supported
way to query the coordinator alongside its existing desktop tools without
switching environments. Retain the three-second freshness contract and verify
the same lease around a completed input and its observed effect. A second
controller, a larger TTL or the headless runtime's successful data callbacks
would not establish this check. No third-party code was imported or executed;
sound and gameplay additions remain deferred.

### Original-computer network controls check

The [current controls receipt](evidence/original-computer-network-controls-2026-11-16.json)
records a further in-place grant investigation. Dot reports no
`cloud_environment.environment_status`, `cloud_environment.request_changes` or
equivalent running-machine network editor. Its checked shell has no
`/etc/codex/network-policy.json`; effective enforcement and VPN readiness remain
unknown. Its stated destination restriction is not independently read policy.

The coordinator inspected the current Pro account UI. **Work network access was
already on**. Cloud computer settings exposed cookies and website approvals;
the Codex Cloud list exposed saved configurations without establishing a
binding to the original Dot computer. No setting was changed. Official
[Work network guidance](https://learn.chatgpt.com/docs/enterprise/chatgpt-work-overview#network-access-and-external-destinations)
describes public internet access, while
[execution scope guidance](https://learn.chatgpt.com/docs/enterprise/agent-security#how-agent-security-applies-to-work-cloud)
distinguishes Dot computers from managed Codex environments. Neither establishes
a private TCP grant from this already-enabled preference. The inspected shipped
account-setting setter accepts a boolean; its separate existing-instance editor
requires the bound conversation, runtime and configuration identities.

The original Dot menu also offers Reboot. No original-runtime preservation or
network-policy refresh guarantee was established, so it was not used as a
network repair. No new access proposal, probe, environment switch, restart or
desktop input occurred. Network access remains unresolved; the actual input,
takeover and interruption-recovery gates were not executed. Resume those checks
after a supported grant/client is available in the original desktop executor;
do not substitute saved-config edits, another desktop or relaxed freshness.
