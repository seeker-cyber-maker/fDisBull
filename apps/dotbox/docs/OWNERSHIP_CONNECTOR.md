# Ownership status connector

This optional MCP adapter exposes one zero-argument tool,
`dotbox_ownership_status`, around the existing ownership coordinator. It reads
sampled viewer state. A response is neither an input grant nor a turn lease.
Dot's existing desktop tools remain responsible for keyboard and mouse actions.

## Local use

From the source checkout, install the optional test and connector dependencies:

```sh
python -m pip install '.[test,connector]'
dotbox-ownership-connector --session '<private-directory>/session.json' \
  --viewer-id '<lowercase-viewer-sha256>' --port 8787 --local-test
```

Use a current coordinator descriptor with `kind="ownership-coordinator"`.
An older unmarked coordinator needs a deliberate stop/restart through its normal
controls. Never manually add this marker to an old or game session. The reader
pins the descriptor's receiver instance and the supplied viewer binding; it
refuses game/publisher descriptors and does not follow a replacement receiver.
See [the ownership bridge](OWNERSHIP_BRIDGE.md) for coordinator preparation.

The launcher binds only `127.0.0.1` and serves `/mcp`. It generates a separate
local Bearer credential with a 600-second lifetime. Startup prints its private
token-file path, resource URL, scope and expiry, never the token. The token file
is removed when the credential context closes; stop the launcher when finished.
Its required scope is `dotbox.ownership.read`. This fixture has no functioning
OAuth authorization server and cannot provide ChatGPT login.

For an authenticated local SDK call, read the token privately from the printed
file and pass it as an HTTP header:

```python
from pathlib import Path
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

token = Path("<printed-token-file>").read_text().strip()
async with httpx2.AsyncClient(
    headers={"Authorization": f"Bearer {token}"},
    trust_env=False, timeout=5.0,
) as http:
    transport = streamable_http_client("http://127.0.0.1:8787/mcp", http_client=http)
    async with Client(transport, cache=None) as client:
        result = await client.call_tool("dotbox_ownership_status", {})
        assert not result.is_error
        print(result.structured_content)
```

Run this inside an async function. Do not print or share the credential.

## Data and limits

The response contains exactly nine fields: `available`, `owner`, `source`,
`viewer_mode`, `connection`, `fresh`, `expires_in_ms`, `epoch` and `sequence`.
This reveals coarse human/Dot presence and the sampled state of one selected
viewer. It excludes credentials, identifiers, file paths, frames and raw errors.
Every call reads the local coordinator again without retaining a last-good
snapshot. Remaining freshness subtracts the coordinator round trip; it does not
include later MCP network delay. Check the result's freshness and unknown states;
even a fresh Dot observation does not authorize input.

The remote surface offers no turn operations, shutdown, publishing, input,
frames, file access, shell or SSH. The connector process holds the normal local
coordinator credential, which also permits turn operations and coordinator
shutdown. The fixed tool prevents remote operation selection; it does not
protect that credential from a compromised connector process.

## Connection review

[The permissions proposal](../connectors/ownership/permissions.review.json)
records the selected private-tunnel route and its verification state. The user
authorized connection setup on 16 November 2026. No public endpoint, domain,
DNS change or OAuth provider is needed for that route.

### Private Secure MCP Tunnel

The explicit private-tunnel launcher keeps the same local HTTP bearer checks:

```sh
dotbox-ownership-connector --session '<private-directory>/session.json' \
  --viewer-id '<lowercase-viewer-sha256>' --port 8787 --private-tunnel \
  --tunnel-header-file '<owned-0700-directory>/mcp-authorization'
```

The header file must be new. It contains the full local Bearer header, stays
0600 and is distinct from the coordinator, publisher and tunnel runtime keys.
The local credential lasts for the connector process; authenticated request
claims expire after at most 60 seconds. Restarting the connector creates a new
local credential, so restart its tunnel client too. Shutdown removes the owned
header. Concurrent replacements are restored where possible or preserved in a
private `.dotbox-tunnel-cleanup-*` directory without overwriting a newer entry.
The private-directory mechanism does not isolate malicious processes sharing
the user's OS identity.

Install the supported client with `brew install openai/tools/tunnel-client` on
macOS. Pin and record the actually installed version; this setup uses 0.0.21.
Use the supplied existing tunnel, a runtime key restricted to **Tunnels Read +
Use**, and a private profile containing only references:

```yaml
config_version: 1
control_plane:
  tunnel_id: <existing-private-tunnel-id>
  api_key: file:/private/operator/runtime-key
  poll_channels: [main]
mcp:
  server_urls:
    - channel: main
      url: http://127.0.0.1:8787/mcp
  extra_headers:
    Authorization: file:/private/operator/mcp-authorization
  oauth_discovery: disabled
health:
  listen_addr: 127.0.0.1:0
  url_file: /private/operator/tunnel-health-url
```

The client initiates outbound HTTPS to OpenAI. Keep admin UI/health on loopback;
enable only `main`, without Harpoon or arbitrary HTTP targets. Inspect the
selected tunnel's organization/workspace access and actual readiness before
connecting the private app. Do not infer readiness from a running process.
Run `tunnel-client doctor --profile-file '<private-profile>' --explain`, then
`tunnel-client run --profile-file '<private-profile>'` in an owned foreground
session. This setup does not claim login/startup persistence. The inspected
0.0.21 `runtimes connect` writer replaces its profile rather than preserving
extra headers/discovery/channel settings, so it was not used for this profile.

In ChatGPT's custom MCP form, select **Tunnel** and **No authentication**. Here
that setting means no separate user OAuth flow: OpenAI's tunnel access controls
protect the private app, and the tunnel client supplies the distinct local
Bearer header. The tool therefore advertises `noauth` in this mode. Direct
unauthenticated HTTP and in-memory tool reads remain denied. Check doctor,
runtime health and an actual Dot tool call before claiming a connection.

See the official [tunnel setup](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
and [restricted-key guidance](https://github.com/openai/tunnel-client/blob/v0.0.21/docs/permissions.md).

### Separate public OAuth route

`create_server` accepts an external token verifier and issuer/resource URLs for
later integration; it neither selects nor implements an authorization provider.
A public OAuth deployment still requires endpoint and owner/client bindings, HTTPS,
OAuth 2.1 authorization code with PKCE, resource/audience validation,
issuer/signature/expiry/scope checks and DNS-rebinding protection.
[ChatGPT's authentication requirements](https://developers.openai.com/plugins/build/auth)
do not support a custom static Bearer API key as a substitute for this flow.

Local regression checks use real authenticated MCP HTTP and a synthetic ownership
publisher. The separate [live receipt](evidence/ownership-connector-live-2026-11-16.json)
matches actual Dot tool replies to the selected viewer and receiver. Its three
foreground observation windows establish Dot, human after Take over, and Dot
after Return control. A fourth Dot read and an independent connector read both
return unknown after the source stops.

Fresh ownership requires the bounded observer to run inside an active CUA call.
Unawaited background attempts produced no AX observations and were rejected as
unknown; they are excluded from the live proof. No unattended sampler is
delivered. Keep the coordinator, connector and tunnel sessions running for tool
access; paused sampling correctly remains unknown. Actual desktop input, an
atomic capture lock, sound and gameplay remain deferred.
