# DotBox ownership connector

Approved scope: user request of 16 November 2026. Build the smallest connector
around the existing coordinator, verify read-only ownership locally, prepare
connection permissions for review and update draft PR #2. The user subsequently
authorized connecting Dot through the existing infrastructure and verifying live
ownership changes. The selected route uses an existing OpenAI Secure MCP Tunnel
on Studio, with no public DotBox endpoint or new network grant.

## Purpose and interaction

Dot needs fresh ownership information in her original chat without switching
computers. The existing coordinator and viewer observer already provide those
facts. One zero-argument MCP tool, `dotbox_ownership_status`, reads the explicitly
bound coordinator and returns a filtered snapshot. No new view is needed.
Dot's existing keyboard/mouse harness remains authoritative.

The response is observational only. It is not an input grant or a turn lease;
freshness describes the coordinator snapshot and is not renewed by the connector.
Every invocation reads again. Unknown, expired and unavailable states must stay
visible. No last-good result is retained after a failure.

## Implementation boundaries

- Reuse `CoordinationService`, `Client` and their authenticated loopback transport.
- Add a coordinator descriptor kind marker and refuse ordinary game/publisher
  descriptors before making a backend request. Verify the response kind and
  instance as well. Old unmarked coordinators need a deliberate restart.
- Expose only owner, source, viewer mode, connection, freshness, remaining time,
  epoch and sequence. Do not disclose session/stream/viewer IDs, paths, tokens,
  frames, game state or raw backend errors.
- The local MCP prototype uses the pinned official Python SDK (`mcp==2.3.0`)
  as an optional extra. The existing Python engine keeps its normal dependencies.
- Authenticate real Streamable HTTP requests, enforce the read scope and exact
  resource audience, and bind the local test launcher to IPv4 loopback only.
- Keep the local MCP bearer token separate from coordinator, publisher and tunnel
  runtime credentials. Local-test mode remains a ten-minute fixture. Explicit
  private-tunnel mode uses a process-lifetime local credential and bounded
  per-request claims; neither implements a user OAuth login.
- Provide a resource-server factory accepting an operator-supplied token verifier
  and issuer/resource configuration for later OAuth integration. No issuer,
  public hostname or callback is selected for that separate route.
- For the selected private tunnel, retain loopback HTTP bearer/scope/resource
  checks while advertising no separate user OAuth flow. Export the full local
  header only into a new 0600 file in an owned 0700 directory. Preserve concurrent
  replacements during cleanup; no overwrite or automatic deletion of foreign data.
- Enable only the tunnel's main MCP channel. Keep key material and all selected
  identities outside Git. Verify actual readiness and original-Dot tool results.

## Permissions for review

Exactly one read-only tool and one scope: `dotbox.ownership.read`. No turn
claim/check/release, publishing, shutdown, shell, file selection, keyboard/mouse,
native operations, sound or gameplay. The server's coordinator credential stays
local to its process; the remote caller receives no coordinator capability.
That local credential currently also authorizes coordinator turn/shutdown calls;
the adapter's fixed operation prevents callers selecting them, but does not
isolate a compromised server process from its local credential.

The separate public OAuth route needs HTTPS, an approved OAuth 2.1 authorization
server, authorization code + PKCE, resource-bound access tokens, expiry/scope
verification and an explicitly reviewed user/session binding. Static bearer/API
keys alone are not a user OAuth flow. Those are prerequisites for that route,
not delivered authentication-provider functionality. The selected private app
instead relies on OpenAI tunnel organization access and a separate authenticated
loopback upstream. Its runtime key is restricted to Tunnels Read + Use.

## Acceptance evidence

Use a real no-backend coordinator, its actual publisher and authenticated MCP
HTTP requests through the SDK client. Demonstrate Dot, human, expiry,
invalidation, receiver failure/replacement, no cached fallback, exact tool/data
surface and rejected unauthenticated/wrong-scope/wrong-resource/extra-argument
requests. Refuse game and publisher descriptors before sending a request.
Keep native/backend operations untouched. Run source regression and isolated
installed-package checks; preserve a sanitized local receipt.

Live qualification additionally requires Dot's actual tool replies to match the
receiver's epoch/sequence and corresponding viewer evidence for Dot, human after
Take over, and Dot after Return control. Paused sampling must return unknown,
with no cached success. The existing observer runs in bounded foreground CUA
sessions; no unattended sampler or atomic input lock is claimed. These checks
do not qualify keyboard/mouse execution, sound or gameplay.
