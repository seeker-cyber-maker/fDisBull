"""One read-only MCP projection of an explicitly bound ownership coordinator.

The optional SDK is imported only when building/launching the MCP server. Both
launch modes require a local HTTP bearer; a private tunnel supplies app access
control separately. Neither mode implements a user OAuth login.
"""

import argparse
from contextlib import contextmanager, nullcontext
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import sys
import time
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from . import __version__
from .client import Client, private_file
from .local_auth import LocalCredential


READ_SCOPE = "dotbox.ownership.read"
TOOL_NAME = "dotbox_ownership_status"
MAX_MCP_REQUEST = 8192


class OwnershipSnapshot(TypedDict):
    available: bool
    owner: Literal["dot", "human", "unknown"]
    source: Literal["codex-viewer-ui", "unavailable"]
    viewer_mode: Literal["observe", "control", "unknown"]
    connection: Literal["live", "disconnected", "unknown"]
    fresh: bool
    expires_in_ms: int
    epoch: int | None
    sequence: int | None


def unavailable() -> OwnershipSnapshot:
    return {"available": False, "owner": "unknown", "source": "unavailable",
            "viewer_mode": "unknown", "connection": "unknown", "fresh": False,
            "expires_in_ms": 0, "epoch": None, "sequence": None}


class OwnershipReader:
    """Pin one coordinator instance/viewer; never rebind or cache last success."""

    def __init__(self, descriptor, viewer_id, *, timeout=1.0):
        if not isinstance(viewer_id, str) or re.fullmatch(r"[0-9a-f]{64}", viewer_id) is None:
            raise ValueError("A lowercase viewer SHA-256 binding is required")
        if type(timeout) not in (int, float) or not 0.05 <= timeout <= 2:
            raise ValueError("Choose a bounded coordinator timeout")
        client = Client(descriptor, timeout=timeout)
        if (client.descriptor.get("kind") != "ownership-coordinator"
                or "role" in client.descriptor):
            raise ValueError("Use a current coordinator session descriptor, not a game or publisher")
        self._client = client
        self._instance_id = client.descriptor["instance_id"]
        self._viewer_id = viewer_id

    def read(self) -> OwnershipSnapshot:
        started = time.monotonic_ns()
        try:
            reply = self._client.request("status")
            elapsed = max(0, math.ceil((time.monotonic_ns() - started) / 1_000_000))
            if reply.get("ok") is not True:
                return unavailable()
            current = reply["result"]
            if (current["kind"] != "ownership-coordinator"
                    or current["instance_id"] != self._instance_id):
                return unavailable()
            raw = current["platform_takeover"]
            if (raw["viewer_id"] != self._viewer_id
                    or raw["owner"] not in ("dot", "human", "unknown")
                    or raw["source"] not in ("codex-viewer-ui", "unavailable")
                    or raw["viewer_mode"] not in ("observe", "control", "unknown")
                    or raw["connection"] not in ("live", "disconnected", "unknown")
                    or type(raw["fresh"]) is not bool
                    or (raw["fresh"] and raw["source"] != "codex-viewer-ui")
                    or any(type(raw[k]) is not int or raw[k] < 0
                           for k in ("epoch", "sequence", "expires_in_ms"))
                    or raw["expires_in_ms"] > 3000
                    or (raw["owner"] == "dot" and
                        (raw["viewer_mode"] != "observe" or raw["connection"] != "live"))):
                return unavailable()
            remaining = max(0, raw["expires_in_ms"] - elapsed)
            fresh = raw["fresh"] and remaining > 0
            return {"available": True,
                    "owner": raw["owner"] if fresh else "unknown",
                    "source": raw["source"],
                    "viewer_mode": raw["viewer_mode"] if fresh else "unknown",
                    "connection": raw["connection"] if fresh else "unknown",
                    "fresh": fresh, "expires_in_ms": remaining if fresh else 0,
                    "epoch": raw["epoch"], "sequence": raw["sequence"]}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            # Descriptors, tokens, IDs, raw replies and exception text stay local.
            # A response failure never returns the previous successful snapshot.
            return unavailable()


def _http_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
            or (parsed.scheme == "http" and parsed.hostname not in
                ("127.0.0.1", "localhost", "::1"))):
        raise ValueError("Use HTTPS URLs, or HTTP loopback for local testing")
    _ = parsed.port  # Reject malformed/out-of-range ports before SDK construction.
    return parsed


def create_server(reader, *, token_verifier, issuer_url, resource_url, private_tunnel=False):
    """Build a protected MCP resource server; any OAuth issuer is external.

    A production verifier must validate issuer/signature/audience/expiry/scope.
    Private-tunnel metadata advertises no user OAuth while preserving local
    bearer checks. This factory never configures the tunnel or its access rules.
    """
    from mcp.server import MCPServer
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.server.auth.settings import AuthSettings
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp_types import ToolAnnotations
    from pydantic import AnyHttpUrl

    if not isinstance(reader, OwnershipReader) or token_verifier is None:
        raise ValueError("A bound ownership reader and token verifier are required")
    issuer = _http_url(issuer_url)
    resource = _http_url(resource_url)
    if type(private_tunnel) is not bool:
        raise ValueError("private_tunnel must be boolean")
    if private_tunnel and (issuer.hostname != "127.0.0.1" or resource.hostname != "127.0.0.1"):
        raise ValueError("Private tunnel upstream URLs must use IPv4 loopback")
    if resource.path != "/mcp":
        raise ValueError("The resource URL must identify the exact /mcp endpoint")
    class ReadOnlyServer(MCPServer):
        # The pinned SDK normally ignores extra function arguments. Enforce the
        # closed public schema before its argument conversion drops those keys.
        async def list_tools(self):
            tools = await super().list_tools()
            return [tool.model_copy(update={"input_schema": {
                "type": "object", "properties": {}, "additionalProperties": False}})
                    for tool in tools if tool.name == TOOL_NAME]

        async def call_tool(self, name, arguments, context=None):
            if name != TOOL_NAME or arguments != {}:
                raise ToolError("This connector exposes only dotbox_ownership_status with no arguments")
            return await super().call_tool(name, arguments, context)

    server = ReadOnlyServer(
        "DotBox ownership", version=__version__, log_level="WARNING",
        instructions=("Read-only sampled viewer ownership. Every result is a snapshot, "
                      "not permission to inject input and not a turn lease. "
                      "It may be stale when received. Existing desktop tools own input."),
        token_verifier=token_verifier,
        auth=AuthSettings(issuer_url=AnyHttpUrl(issuer_url),
                          resource_server_url=AnyHttpUrl(resource_url),
                          required_scopes=[READ_SCOPE], validate_token_resource=True),
        subscriptions=False,
    )

    @server.tool(name=TOOL_NAME,
                 description="Read the bound coordinator's ownership snapshot; never authorizes input.",
                 annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                             idempotent_hint=True, open_world_hint=False),
                 meta={"securitySchemes": ([{"type": "noauth"}] if private_tunnel else
                                            [{"type": "oauth2", "scopes": [READ_SCOPE]}])})
    def ownership_status() -> OwnershipSnapshot:
        # The SDK's in-memory and stdio transports bypass HTTP authentication.
        # Refuse ownership data there as well as after a token expires in queue.
        token = get_access_token()
        if (token is None or READ_SCOPE not in token.scopes or token.resource != resource_url
                or token.expires_at is None or time.time() >= token.expires_at):
            raise ToolError("An authenticated, unexpired ownership-read HTTP token is required")
        return reader.read()

    return server


class LocalTestVerifier:
    """A separate local HTTP credential, never a user OAuth or tunnel API key."""

    def __init__(self, credential, resource_url, *, expires_at):
        self._credential = credential
        self._resource = resource_url
        self._expires_at = expires_at

    async def verify_token(self, token):
        from mcp.server.auth.provider import AccessToken
        if ((self._expires_at is not None and time.time() >= self._expires_at)
                or not self._credential.check(token)):
            return None
        # A private-tunnel credential lives with this process. Its per-request
        # claims remain short-lived so the handler still rejects expired queues.
        deadline = int(time.time()) + 60 if self._expires_at is None else int(self._expires_at)
        return AccessToken(token=token, client_id="dotbox-local-test", scopes=[READ_SCOPE],
                           expires_at=deadline, resource=self._resource)


@contextmanager
def _tunnel_header(path, credential):
    """Publish a new private header file; remove only the inode we created."""
    path = Path(path).expanduser().absolute()
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
    identity = None
    fd = None
    try:
        directory = os.fstat(parent)
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
                or stat.S_IMODE(directory.st_mode) != 0o700):
            raise ValueError("Tunnel header parent must be an owned private directory (0700)")
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb", closefd=False) as output:
            info = os.fstat(output.fileno())
            identity = (info.st_dev, info.st_ino)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise ValueError("Expected a new owned regular tunnel header file")
            os.fchmod(output.fileno(), 0o600)
            output.write(b"Bearer " + private_file(credential.path).strip() + b"\n")
            output.flush()
            os.fsync(output.fileno())
        yield path
    finally:
        try:
            if identity is not None:
                quarantine = ".dotbox-tunnel-cleanup-" + secrets.token_hex(16)
                os.mkdir(quarantine, 0o700, dir_fd=parent)
                captured = None
                try:
                    captured = os.open(quarantine, os.O_RDONLY | os.O_DIRECTORY |
                                       getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
                    # Isolate the public name atomically before inspecting it.
                    # This private random directory is not a trust boundary
                    # against malicious processes running under the same UID.
                    try:
                        os.rename(path.name, "header", src_dir_fd=parent, dst_dir_fd=captured)
                    except FileNotFoundError:
                        pass
                    else:
                        current = os.stat("header", dir_fd=captured, follow_symlinks=False)
                        if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity:
                            os.unlink("header", dir_fd=captured)
                        elif stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
                            try:
                                os.link("header", path.name, src_dir_fd=captured,
                                        dst_dir_fd=parent, follow_symlinks=False)
                            except OSError:
                                # A newer public entry or failed restoration
                                # leaves the foreign entry intact in quarantine.
                                pass
                            else:
                                os.unlink("header", dir_fd=captured)
                finally:
                    if captured is not None:
                        os.close(captured)
                    try:
                        os.rmdir(quarantine, dir_fd=parent)
                    except OSError:
                        pass  # Preserve every unresolved captured entry.
        finally:
            try:
                if fd is not None:
                    os.close(fd)  # Prevent inode reuse until cleanup is complete.
            finally:
                os.close(parent)


def local_transport_security():
    from mcp.server.transport_security import TransportSecuritySettings
    return TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                     allowed_hosts=["127.0.0.1:*"], allowed_origins=[])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="Private coordinator session.json")
    parser.add_argument("--viewer-id", required=True, help="Expected lowercase viewer SHA-256")
    parser.add_argument("--port", type=int, default=8787)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local-test", action="store_true",
                      help="Short-lived loopback bearer fixture, not ChatGPT OAuth")
    mode.add_argument("--private-tunnel", action="store_true",
                      help="Private tunnel controls app access; local HTTP bearer remains required")
    parser.add_argument("--tunnel-header-file", help="New full Bearer header file in an owned 0700 directory")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535 or args.private_tunnel != bool(args.tunnel_header_file):
        parser.error("Use an unprivileged port; --private-tunnel requires --tunnel-header-file exclusively")
    previous = {}
    try:
        if args.private_tunnel:
            def interrupted(*_):
                raise KeyboardInterrupt
            previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
        reader = OwnershipReader(args.session, args.viewer_id)
        resource = f"http://127.0.0.1:{args.port}/mcp"
        with LocalCredential("dotbox-mcp-local-") as credential:
            expires_at = None if args.private_tunnel else int(time.time()) + 600
            verifier = LocalTestVerifier(credential, resource, expires_at=expires_at)
            server = create_server(reader, token_verifier=verifier,
                                   issuer_url=f"http://127.0.0.1:{args.port}/local-test-issuer",
                                   resource_url=resource, private_tunnel=args.private_tunnel)
            header = _tunnel_header(args.tunnel_header_file, credential) if args.private_tunnel else nullcontext()
            with header as published:
                configuration = ({"private_tunnel_only": True, "resource": resource,
                                  "tunnel_header_file": str(published), "scope": READ_SCOPE,
                                  "credential_lifetime": "process"} if args.private_tunnel else
                                 {"local_test_only": True, "resource": resource,
                                  "token_file": str(credential.path), "scope": READ_SCOPE,
                                  "expires_at": expires_at})
                print(json.dumps(configuration), flush=True)
                server.run(transport="streamable-http", host="127.0.0.1", port=args.port,
                           json_response=True, stateless_http=True,
                           max_request_body_size=MAX_MCP_REQUEST,
                           transport_security=local_transport_security())
        return 0
    except KeyboardInterrupt:
        return 130
    except ImportError:
        print("Install the optional dotbox[connector] dependency for this command.", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("Connector configuration or local transport failed; inspect private operator state.",
              file=sys.stderr)
        return 2
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
