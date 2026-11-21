# Codex viewer code and ownership

> Follow-up: [the optional ownership bridge](OWNERSHIP_BRIDGE.md) now implements
> bounded UI observation and cooperating turn coordination. This investigation
> remains the earlier artifact and input-path evidence, not a cloud deployment.

16 November 2026. This combines shipped-artifact analysis, an offline replay of
actual extracted client code, and a separately scoped live web-viewer check.
Sound and gameplay work remain deferred. No installed app was modified.

## What the app already implements

The inspected macOS app is **26.1111.21308, build 27194**. Its WebRTC client is
explicitly labelled `NekoClient` by its own logs. It has an empty-label RTC data
channel carrying both binary input and JSON control messages; this is different
from current upstream Neko's WebSocket control plane.

| Question | Source-backed result |
| --- | --- |
| Can the viewer observe an owner? | With shared takeover enabled, `system/init.control_host` and `control/host` normalize boolean `has_host` to `controlowner`: human metadata or Dot. This is independent of the local viewer's input mode. |
| How does Take over work? | The existing button's `onToggle` starts a request, calls `setMode("control", requestId)` and sends `control/request`. Shared requests carry a correlation ID and `shared_dot_takeover:true`. An acknowledged `control/locked` changes local mode; the React wrapper then attaches input listeners. |
| Is correlation strict? | Wrong peers and stale/invalid supplied IDs are refused. A lock acknowledgement without a request ID remains accepted for compatibility. Requesting control is not itself a grant. |
| How does Return control work? | The wrapper detaches input sources and calls `setMode("observe")`, sending `control/release`. The transport does not invent immediate server acknowledgement. |
| What inputs are sent? | Binary input requires mode `control` and an open channel. Pointer packets contain absolute video x/y; display scaling accounts for contained/letterboxed video. Keys/buttons have separate down/up packets. |
| What happens on lifecycle changes? | Peer replacement emits owner-null and returns to observe. Explicit disconnect resets local mode but does not itself emit owner-null. A bridge must invalidate owner state on disconnect/error rather than trust retained metadata. |
| Can a guest DotBox process subscribe? | Not established. The inspected owner callback updates private React state and the existing controls UI. Selected preload members expose generic bridges, without an identified desktop-owner subscription. |

`sharedDotTakeover` is conditional; the Dot panel's `isShared` input defaults
false. Therefore the shared owner event must not be assumed present in every
ordinary/private viewer. Local `observe/control`, global/shared owner metadata,
and current connection validity are three different facts.

## Source trace

All offsets below are zero-based UTF-8 bytes, end-exclusive where ranges appear.
Exact member hashes are in the [machine-readable report](evidence/codex-viewer-2026-11-16.json).

- `423400.5f97d1f55f.js`: client/helper range 8903–22964; input gate/encoding
  11548–12435; owner normalization 18586–18756; request 21594–22003; release
  22003–22139. Its existing Take over/Return control button uses `control.onToggle`
  around 36000–37500.
- `393618.4045ff333c.js`: owner listener 11680, owner-state update 35819,
  `control` render object 33466, toggle 33562, acknowledged controlling-state
  callback 37035, and render handoff 38485.
- `146838.87652f10ab.js`: Dot panel export 27656; factory forwarding 32155;
  conditional shared flag 41050; existing controls wrappers 41829 and 43340.
- The generic `remoteControl/status/changed` path in the inspected main-process
  consumer updates local installation/environment identity. It is not evidence
  of a Neko desktop-owner subscription.

REA 6.7.0 CLI analyzed the two core viewer members as inert text. Evidence ID:
`ev_b38973a428c7de00a12b3b007ff8c1a67c3a6e9c04c5e040f268fdb8e06d0a40`.
The complete evidence stays private. Source selection leaves 11,076 inventoried
files unanalysed by that graph; additional named chunks were inspected manually.
There is no whole-app absence proof. Seven unselected unpacked native companions
contradicted their declared ASAR integrity; analysis retained those unknowns with
`record-and-continue`. The three selected core JS members match their declared
integrity hashes. No native companion was executed or altered.

## Offline checks versus live evidence

The [replay script](../scripts/replay_viewer_contract.mjs) reads the exact
hash-pinned extracted member and executes its helpers/client class with fake
keyboard, channel and DOM geometry. **19 checks pass**, covering owner events,
requests/acknowledgements, cancellation, absolute input samples, peer replacement
and disconnect. The stubbed fetch/peer/socket/timer entrypoints were not invoked.
This does execute extracted class code offline; it does not connect the installed
app, test its bootstrap, exercise real capture, or establish server behavior.

The actual web viewer separately passed two Take over / Return control cycles.
The coordinator used the existing checkbox through browser automation, observed
`You have control`, clicked the remote Chromium address bar and sent desktop key
events spelling `dotbox`, without Enter. After Return control, Dot reported using
her own desktop click/key tools to type `dotbox-agent-b-20261116`. The coordinator
independently observed that marker in the same remote address bar while the
viewer showed Dot had control. A second takeover and mouse click created one
empty second tab, a distinct visible pointer effect. Only that test tab was
closed; two Escapes restored the original empty address bar. Final capture shows
one original tab and Dot control / unchecked Take over.

Thus the outer viewer's ownership label/checkbox are programmatically readable
and its existing buttons are triggerable through the allowed browser interface.
Dot reported no owner field/event in her offered tools. Her accepted input after
return is verified; automatic pausing, refusal during human control, an exclusive
whole-computer lease and unattended turn switching were not tested. This used an
automated viewer-side coordinator, not a person typing. Observation timestamps
include coordination gaps and do not measure transition latency.

The current web bundle was not bound to the installed macOS artifact digest;
the live browser test does not qualify native macOS capture or a DotBox cloud
installation. Raw screenshots and chat/connection IDs remain private. The
[live-check protocol and completed-run record](DOT_HARNESS_LIVE_CHECK.md)
distinguish the narrower executed sequence from the full proposed protocol.

## Reuse decision

Keep the existing viewer for ordinary keyboard/mouse input. A new client-side
input transport is unnecessary for that route. Programmatic ownership-aware
coordination would need a small authorized bridge from the existing viewer's
owner/mode/lifecycle events, or a server-supported equivalent. No such guest
bridge is claimed here, and no private API was called. Do not replace this gap
with focus inference, a new desktop, an upstream Neko endpoint assumption or a
second full remote-control client.

A browser-side coordinator can use the verified UI route for explicit handoffs
now. A guest-only agent still needs an authorized observation/control bridge
before automatic turn switching can rely on ownership. Such a bridge must retain
owner, acknowledged input mode and connection validity separately, invalidate
stale state on lifecycle changes, and coordinate the sole live controller.

Useful public precedents were inspected before this artifact pass:

| Prior art | Relevance and limit |
| --- | --- |
| [Neko client](https://github.com/m1k1o/neko/blob/4d0bb35b03759fce6497eb9a1a294f85501c2135/client/core/README.md) | Published owner/control events and shared desktop input. Its control transport differs; it is not a drop-in Dot client. |
| [Neko agent](https://github.com/G-structure/neko_agent/blob/b08d5f7f142aeaaf865d1e95f918f5656a491d36/src/neko_comms/webrtc_client.py) | Actual Python video/input agent for its own Neko server, not a qualified hosted Dot integration. |
| [GrokDeck viewer](https://github.com/Gamedesigner/grokdeck/blob/ddf60ea9008cedc44973d321c7a5c823fbce1b1f/src/ComputerViewer.tsx) | Concrete hosted Grok viewer integration using noVNC/RFB. Its `shared:true`/`viewOnly` switch does not establish exclusive agent/human ownership. |
| [BotHub Dot client](https://github.com/qybaihe/bothub/blob/9ef03a17d823c9f10769428de1398c3889e314f7/src/main/dot/dotClient.ts) | Real Dot messaging/realtime integration; inspected source does not establish a computer-owner feed. |

Public [Codex issue 49802](https://github.com/openai/codex/issues/49802) and a
[November 11 takeover report](https://community.openai.com/t/dots-takeover-issue-across-all-platforms/1405548/3)
show why the current account/frontend must be tested rather than inheriting a
prior client result. These are user reports, not independently reproduced bugs.
