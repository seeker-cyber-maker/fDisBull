"""Local authenticated connector checks; no native backend or live desktop input."""

import asyncio
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from dotbox.client import Client
import dotbox.connector as connector
from dotbox.connector import (
    LocalTestVerifier, OwnershipReader, READ_SCOPE, TOOL_NAME, create_server,
    local_transport_security, unavailable,
)
from dotbox.coordination import CoordinationService
from dotbox.local_auth import LocalCredential
from dotbox.ownership import OwnershipState


VIEWER = "a" * 64
FIELDS = {"available", "owner", "source", "viewer_mode", "connection", "fresh",
          "expires_in_ms", "epoch", "sequence"}


class Receiver:
    """An actual serialized receiver/socket with a deterministic evidence clock."""

    def __init__(self, directory):
        self.directory = directory
        self.now = [100.0]
        self.service = CoordinationService(directory, VIEWER)
        self.service.ownership = OwnershipState(VIEWER, clock=lambda: self.now[0])
        ready = threading.Event()
        self.errors = []

        def run():
            try:
                self.service.run(on_ready=lambda _: ready.set())
            except BaseException as error:
                self.errors.append(error)
                ready.set()

        self.worker = threading.Thread(target=run)
        self.worker.start()
        assert ready.wait(3) and not self.errors
        self.descriptor = directory / "session.json"
        self.client = Client(self.descriptor, timeout=1)
        self.publisher = Client(directory / "ownership-publisher.json", timeout=1)
        self.stream = self.open()

    def open(self):
        reply = self.publisher.request("bridge-open", {"viewer_id": VIEWER})
        assert reply["ok"], reply
        self.stream = reply["result"]["stream_id"]
        return self.stream

    def publish(self, owner="dot", mode="observe", connection="live"):
        reply = self.publisher.request("bridge-challenge", {"stream_id": self.stream})
        assert reply["ok"], reply
        event = {k: reply["result"][k] for k in ("stream_id", "challenge", "sequence")}
        event.update(owner=owner, viewer_mode=mode, connection=connection)
        reply = self.publisher.request("bridge-observe", event)
        assert reply["ok"], reply
        return reply["result"]

    def stop(self):
        self.service.request_stop()
        self.worker.join(3)
        assert not self.worker.is_alive() and not self.errors
        assert self.service.backend is None


@pytest.fixture
def receiver(tmp_path):
    running = Receiver(tmp_path / "coordinator")
    try:
        yield running
    finally:
        running.stop()


class ClaimVariants:
    """Exercise resource middleware independently of a verifier's claim policy."""

    def __init__(self, normal, resource):
        self.normal, self.resource = normal, resource

    async def verify_token(self, token):
        from mcp.server.auth.provider import AccessToken
        if token in ("without-scope", "wrong-audience", "expired"):
            return AccessToken(token=token, client_id="negative-test",
                               scopes=[] if token == "without-scope" else [READ_SCOPE],
                               resource=(self.resource + "/other" if token == "wrong-audience"
                                         else self.resource),
                               expires_at=int(time.time()) + (-10 if token == "expired" else 60))
        return await self.normal.verify_token(token)


@contextmanager
def running_http(reader, *, private_tunnel=False):
    pytest.importorskip("mcp")
    uvicorn = pytest.importorskip("uvicorn")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    resource = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
    with LocalCredential("dotbox-connector-test-") as credential:
        token = credential.path.read_text().strip()
        normal = LocalTestVerifier(credential, resource, expires_at=time.time() + 60)
        server = create_server(reader, token_verifier=ClaimVariants(normal, resource),
                               issuer_url=resource.removesuffix("/mcp") + "/issuer",
                               resource_url=resource,
                               **({"private_tunnel": True} if private_tunnel else {}))
        app = server.streamable_http_app(json_response=True, stateless_http=True,
                                        max_request_body_size=8192,
                                        transport_security=local_transport_security())
        runner = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", loop="asyncio",
                                             lifespan="on", log_config=None,
                                             log_level="critical", access_log=False,
                                             timeout_graceful_shutdown=2))
        errors = []

        def run():
            try:
                runner.run(sockets=[listener])
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            deadline = time.monotonic() + 3
            while not runner.started:
                assert worker.is_alive() and not errors and time.monotonic() < deadline
                time.sleep(0.01)
            yield SimpleNamespace(url=resource, token=token, verifier=normal)
        finally:
            runner.should_exit = True
            worker.join(4)
            listener.close()
            assert not worker.is_alive() and not errors


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_real_mcp_client_lists_one_read_tool_projects_only_status_and_rejects_arguments(receiver, mode):
    mcp = pytest.importorskip("mcp")
    httpx2 = pytest.importorskip("httpx2")
    from mcp.client.streamable_http import streamable_http_client

    receiver.publish()
    lease = receiver.client.wait_for_turn("existing-controller", timeout=0)
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    with running_http(reader) as http:
        async def exercise():
            async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {http.token}"},
                                          trust_env=False) as transport:
                async with mcp.Client(streamable_http_client(http.url, http_client=transport),
                                      mode=mode, cache=None) as client:
                    tools = (await client.list_tools()).tools
                    assert [tool.name for tool in tools] == [TOOL_NAME]
                    tool = tools[0]
                    assert tool.input_schema.get("properties", {}) == {}
                    assert tool.input_schema.get("additionalProperties") is False
                    assert tool.annotations.read_only_hint is True
                    assert tool.annotations.destructive_hint is False
                    assert tool.annotations.idempotent_hint is True
                    assert tool.annotations.open_world_hint is False
                    assert tool.meta["securitySchemes"] == [{"type": "oauth2", "scopes": [READ_SCOPE]}]
                    first = await client.call_tool(TOOL_NAME)
                    assert first.is_error is False
                    state = first.structured_content
                    assert set(state) == FIELDS
                    assert state["available"] and state["fresh"] and state["owner"] == "dot"
                    serialized = json.dumps(first.model_dump(mode="json"))
                    for secret in (receiver.client.token, receiver.publisher.token, http.token,
                                   VIEWER, receiver.stream, receiver.service.instance_id,
                                   str(receiver.directory), "127.0.0.1", "password_file"):
                        assert secret not in serialized
                    rejected = await client.call_tool(TOOL_NAME, {"op": "coordinator-close"})
                    assert rejected.is_error is True
                    for name in ("turn-claim", "bridge-observe", "key", "coordinator-close"):
                        assert (await client.call_tool(name, {})).is_error
                    assert not receiver.service.stop_requested.is_set()
                    assert receiver.client.request("turn-check", {"lease": lease})["ok"]
                    receiver.publish("human", "control")
                    assert not receiver.client.request("turn-check", {"lease": lease})["ok"]
                    second = await client.call_tool(TOOL_NAME)
                    assert second.structured_content["owner"] == "human"
                    assert second.structured_content["epoch"] > state["epoch"]
                    receiver.now[0] += 4
                    expired = (await client.call_tool(TOOL_NAME)).structured_content
                    assert expired["available"] and not expired["fresh"]
                    assert expired["owner"] == "unknown" and expired["expires_in_ms"] == 0
                    receiver.stop()
                    failed = await client.call_tool(TOOL_NAME)
                    assert not failed.is_error and failed.structured_content == unavailable()

        asyncio.run(exercise())
    assert receiver.service.backend is None
    assert not receiver.worker.is_alive()


@pytest.mark.parametrize("private_tunnel", [False, True])
def test_in_memory_transport_does_not_bypass_ownership_tool_authentication(receiver, monkeypatch, private_tunnel):
    mcp = pytest.importorskip("mcp")
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    calls = []
    actual_read = reader.read

    def read():
        calls.append("status")
        return actual_read()

    monkeypatch.setattr(reader, "read", read)
    with LocalCredential("dotbox-connector-memory-test-") as credential:
        resource = "http://127.0.0.1:8787/mcp"
        server = create_server(reader, token_verifier=LocalTestVerifier(
            credential, resource, expires_at=int(time.time()) + 60),
            issuer_url="http://127.0.0.1:8787/local-test-issuer", resource_url=resource,
            **({"private_tunnel": True} if private_tunnel else {}))

        async def exercise():
            async with mcp.Client(server, cache=None) as client:
                result = await client.call_tool(TOOL_NAME)
                assert result.is_error and not result.structured_content

        asyncio.run(exercise())
    assert calls == []


def test_private_tunnel_metadata_does_not_remove_local_http_authentication(receiver):
    mcp = pytest.importorskip("mcp")
    httpx2 = pytest.importorskip("httpx2")
    from mcp.client.streamable_http import streamable_http_client

    receiver.publish()
    with running_http(OwnershipReader(receiver.descriptor, VIEWER), private_tunnel=True) as http:
        async def exercise():
            async with httpx2.AsyncClient(trust_env=False) as transport:
                for bearer, expected in ((None, 401), ("without-scope", 403), ("wrong-audience", 401)):
                    headers = {"Accept": "application/json, text/event-stream"}
                    if bearer is not None:
                        headers["Authorization"] = f"Bearer {bearer}"
                    denied = await transport.post(http.url, headers=headers,
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
                    assert denied.status_code == expected
                transport.headers["Authorization"] = f"Bearer {http.token}"
                async with mcp.Client(streamable_http_client(http.url, http_client=transport),
                                      cache=None) as client:
                    tools = (await client.list_tools()).tools
                    assert [tool.name for tool in tools] == [TOOL_NAME]
                    assert tools[0].meta["securitySchemes"] == [{"type": "noauth"}]
                    result = await client.call_tool(TOOL_NAME, {})
                    assert not result.is_error and result.structured_content["owner"] == "dot"
                    assert (await client.call_tool(TOOL_NAME, {"op": "turn-claim"})).is_error

        asyncio.run(exercise())


def test_reader_does_not_claim_release_renew_or_cache_and_expiry_stays_visible(receiver):
    initial = OwnershipReader(receiver.descriptor, VIEWER).read()
    assert initial["available"] and not initial["fresh"] and initial["owner"] == "unknown"
    receiver.publish()
    lease = receiver.client.wait_for_turn("existing-controller", timeout=0)
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    first = reader.read()
    assert first["fresh"] and first["owner"] == "dot"
    receiver.now[0] += 1
    second = reader.read()
    assert 0 < second["expires_in_ms"] <= 2000 < first["expires_in_ms"] <= 3000
    assert receiver.client.request("turn-check", {"lease": lease})["ok"]
    assert (second["epoch"], second["sequence"]) == (first["epoch"], first["sequence"])
    receiver.now[0] += 2
    expired = reader.read()
    assert expired["available"] and expired["owner"] == "unknown" and not expired["fresh"]
    assert expired["expires_in_ms"] == 0 and expired["epoch"] > first["epoch"]


def test_disconnection_invalidation_and_stopped_receiver_never_return_last_dot(receiver):
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    receiver.publish()
    assert reader.read()["owner"] == "dot"
    receiver.publish("unknown", "unknown", "disconnected")
    disconnected = reader.read()
    assert disconnected["available"] and disconnected["owner"] == "unknown"
    receiver.publish()
    assert reader.read()["fresh"]
    assert receiver.publisher.request("bridge-invalidate", {"stream_id": receiver.stream})["ok"]
    invalidated = reader.read()
    assert invalidated["available"] and not invalidated["fresh"]
    receiver.stop()
    assert reader.read() == unavailable()


def test_reader_does_not_rebind_to_replacement_receiver_at_same_descriptor(receiver):
    reader = OwnershipReader(receiver.descriptor, VIEWER, timeout=0.1)
    receiver.publish()
    assert reader.read()["owner"] == "dot"
    old_instance = receiver.service.instance_id
    receiver.stop()
    replacement = Receiver(receiver.directory)
    try:
        replacement.publish()
        assert replacement.service.instance_id != old_instance
        assert reader.read() == unavailable()
        assert OwnershipReader(replacement.descriptor, VIEWER).read()["owner"] == "dot"
    finally:
        replacement.stop()


@pytest.mark.parametrize("kind", ["unmarked-native", "wrong-kind", "publisher"])
def test_wrong_descriptor_identity_is_rejected_before_socket_transport(receiver, tmp_path, monkeypatch, kind):
    if kind == "publisher":
        descriptor = receiver.directory / "ownership-publisher.json"
    else:
        data = dict(receiver.client.descriptor)
        if kind == "unmarked-native":
            data.pop("kind")  # The format emitted by ordinary PlayService.
        else:
            data["kind"] = "game-service"
        descriptor = tmp_path / "wrong-session.json"
        descriptor.write_text(json.dumps(data))
        descriptor.chmod(0o600)

    def must_not_connect(*args, **kwargs):
        pytest.fail("A non-coordinator descriptor reached socket transport")

    monkeypatch.setattr(socket, "create_connection", must_not_connect)
    with pytest.raises(ValueError, match="coordinator session descriptor"):
        OwnershipReader(descriptor, VIEWER)


def test_wrong_viewer_binding_fails_closed_without_exposing_identity(receiver):
    receiver.publish()
    assert OwnershipReader(receiver.descriptor, "b" * 64).read() == unavailable()


@pytest.mark.parametrize("damage", ["wrong-instance", "wrong-kind", "boolean-epoch", "contradictory-dot",
                                  "fresh-unavailable-source"])
def test_malformed_authenticated_response_is_not_reported_as_dot(receiver, monkeypatch, damage):
    receiver.publish()
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    actual_request = reader._client.request

    def altered(*args, **kwargs):
        reply = deepcopy(actual_request(*args, **kwargs))
        if damage == "wrong-instance":
            reply["result"]["instance_id"] = "f" * 32
        elif damage == "wrong-kind":
            reply["result"]["kind"] = "game-service"
        elif damage == "boolean-epoch":
            reply["result"]["platform_takeover"]["epoch"] = True
        elif damage == "fresh-unavailable-source":
            reply["result"]["platform_takeover"]["source"] = "unavailable"
        else:
            reply["result"]["platform_takeover"]["viewer_mode"] = "control"
        return reply

    monkeypatch.setattr(reader._client, "request", altered)
    assert reader.read() == unavailable()


def test_full_round_trip_is_deducted_even_when_receiver_reply_says_fresh(receiver, monkeypatch):
    receiver.publish()
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    # Keep real authentication/socket/state, deterministically model a delayed delivery.
    ticks = iter((10_000_000, 3_011_000_000))
    monkeypatch.setattr(connector, "time", SimpleNamespace(monotonic_ns=lambda: next(ticks)))
    result = reader.read()
    assert result["available"] and result["source"] == "codex-viewer-ui"
    assert not result["fresh"] and result["owner"] == "unknown" and result["expires_in_ms"] == 0


def test_real_http_denies_missing_bad_expired_scope_and_audience_credentials(receiver):
    httpx2 = pytest.importorskip("httpx2")
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    with running_http(reader) as http:
        async def exercise():
            async with httpx2.AsyncClient(trust_env=False) as client:
                for token, expected in ((None, 401), ("invalid", 401), ("expired", 401),
                                        ("without-scope", 403), ("wrong-audience", 401)):
                    headers = {"Accept": "application/json, text/event-stream"}
                    if token is not None:
                        headers["Authorization"] = f"Bearer {token}"
                    reply = await client.post(http.url, headers=headers,
                                              json={"jsonrpc": "2.0", "id": 1,
                                                    "method": "tools/list", "params": {}})
                    assert reply.status_code == expected, (token, reply.status_code, reply.text)
                    assert receiver.client.token not in reply.text
                    assert receiver.publisher.token not in reply.text
            assert http.token not in (receiver.client.token, receiver.publisher.token)
            http.verifier._expires_at = time.time() - 1
            assert await http.verifier.verify_token(http.token) is None

        asyncio.run(exercise())


def test_real_http_rejects_untrusted_host_and_origin_before_tool_call(receiver, monkeypatch):
    httpx2 = pytest.importorskip("httpx2")
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    calls = []
    actual_read = reader.read

    def read():
        calls.append("status")
        return actual_read()

    monkeypatch.setattr(reader, "read", read)
    with running_http(reader) as http:
        async def exercise():
            async with httpx2.AsyncClient(trust_env=False) as client:
                for override in ({"Host": "untrusted.invalid"}, {"Origin": "https://untrusted.invalid"}):
                    headers = {"Authorization": f"Bearer {http.token}",
                               "Accept": "application/json, text/event-stream", **override}
                    reply = await client.post(http.url, headers=headers,
                                              json={"jsonrpc": "2.0", "id": 1,
                                                    "method": "tools/call",
                                                    "params": {"name": TOOL_NAME, "arguments": {}}})
                    assert reply.status_code in (400, 403, 421), reply.text

        asyncio.run(exercise())
    assert calls == []


@pytest.mark.parametrize(("private_tunnel", "stop_signal"), [
    (False, signal.SIGINT), (True, signal.SIGINT), (True, signal.SIGTERM),
])
def test_local_launcher_serves_authenticated_status_and_cleans_generated_credential(receiver, tmp_path,
                                                                                   private_tunnel, stop_signal):
    mcp = pytest.importorskip("mcp")
    httpx2 = pytest.importorskip("httpx2")
    from mcp.client.streamable_http import streamable_http_client

    receiver.publish()
    with socket.socket() as selection:
        selection.bind(("127.0.0.1", 0))
        port = selection.getsockname()[1]
    output = tmp_path / "launcher.out"
    errors = tmp_path / "launcher.err"
    task_env = os.environ.copy()
    task_env["TMPDIR"] = str(tmp_path)
    header_path = tmp_path / "tunnel-authorization"
    mode = (["--private-tunnel", "--tunnel-header-file", str(header_path)] if private_tunnel else
            ["--local-test"])
    with output.open("w") as stdout, errors.open("w") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "dotbox.connector", "--session", str(receiver.descriptor),
             "--viewer-id", VIEWER, "--port", str(port), *mode],
            cwd=tmp_path, env=task_env, stdout=stdout, stderr=stderr)
        try:
            deadline = time.monotonic() + 5
            configuration = None
            while configuration is None:
                assert process.poll() is None, "Connector exited before its launch configuration"
                lines = output.read_text().splitlines()
                if lines:
                    configuration = json.loads(lines[0])
                else:
                    assert time.monotonic() < deadline, "Connector did not print launch configuration"
                    time.sleep(0.02)
            if private_tunnel:
                assert configuration["private_tunnel_only"] is True
                assert configuration["credential_lifetime"] == "process"
                assert configuration["tunnel_header_file"] == str(header_path)
                assert "token_file" not in configuration and "expires_at" not in configuration
                header = header_path.read_text().strip()
                assert header.startswith("Bearer ")
                token = header.removeprefix("Bearer ")
                assert header_path.stat().st_mode & 0o777 == 0o600
                assert header_path.parent.stat().st_mode & 0o777 == 0o700
            else:
                token_path = Path(configuration["token_file"])
                token = token_path.read_text().strip()
                assert token_path.stat().st_mode & 0o777 == 0o600
                assert configuration["local_test_only"] is True
                assert 590 < configuration["expires_at"] - time.time() <= 600
            assert token not in (receiver.client.token, receiver.publisher.token)
            assert configuration["scope"] == READ_SCOPE

            async def exercise():
                async with httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {token}"}, trust_env=False,
                    timeout=1.0,
                ) as http:
                    # Launch output is configuration, not readiness. Observe actual HTTP.
                    while True:
                        try:
                            metadata = configuration["resource"].removesuffix("/mcp")
                            reply = await http.get(metadata + "/.well-known/oauth-protected-resource/mcp")
                            if reply.status_code == 200:
                                assert reply.json()["resource"] == configuration["resource"]
                                break
                        except httpx2.TransportError:
                            pass
                        assert process.poll() is None and time.monotonic() < deadline
                        await asyncio.sleep(0.02)
                    async with mcp.Client(streamable_http_client(
                        configuration["resource"], http_client=http), cache=None) as client:
                        tools = (await client.list_tools()).tools
                        expected = [{"type": "noauth"}] if private_tunnel else [
                            {"type": "oauth2", "scopes": [READ_SCOPE]}]
                        assert tools[0].meta["securitySchemes"] == expected
                        result = await client.call_tool(TOOL_NAME, {})
                        assert not result.is_error and result.structured_content["owner"] == "dot"
                        assert result.structured_content["fresh"]

            asyncio.run(exercise())
        finally:
            if process.poll() is None:
                process.send_signal(stop_signal)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                pytest.fail("Connector launcher did not stop on interruption")
    if private_tunnel:
        assert not header_path.exists()
        assert not list(tmp_path.glob("dotbox-mcp-local-*"))
    else:
        assert not token_path.exists() and not token_path.parent.exists()
    assert process.returncode == 130
    assert token not in output.read_text() and token not in errors.read_text()
    assert not receiver.service.stop_requested.is_set() and receiver.service.backend is None


@pytest.mark.parametrize("case", ["existing", "symlink", "public-parent", "symlink-parent"])
def test_tunnel_header_refuses_unsafe_or_existing_paths_without_overwriting(tmp_path, case):
    parent = tmp_path / "headers"
    parent.mkdir(mode=0o700)
    header = parent / "authorization"
    target = tmp_path / "existing-private-value"
    target.write_text("preserve this value")
    target.chmod(0o600)
    if case == "existing":
        header.write_text("preserve existing header")
        header.chmod(0o600)
    elif case == "symlink":
        header.symlink_to(target)
    elif case == "public-parent":
        parent.chmod(0o755)
    else:
        alias = tmp_path / "header-directory-alias"
        alias.symlink_to(parent, target_is_directory=True)
        header = alias / "authorization"
    with LocalCredential("dotbox-header-negative-") as credential:
        with pytest.raises((OSError, ValueError)):
            with connector._tunnel_header(header, credential):
                pytest.fail("An unsafe header was published")
    assert target.read_text() == "preserve this value"
    if case == "existing":
        assert header.read_text() == "preserve existing header"
    elif case == "symlink":
        assert header.is_symlink()
    else:
        assert not header.exists()


@pytest.mark.parametrize("replacement_kind", ["regular", "symlink"])
def test_tunnel_header_cleanup_preserves_a_replacement_file(tmp_path, replacement_kind):
    header = tmp_path / "authorization"
    with LocalCredential("dotbox-header-replacement-") as credential:
        with connector._tunnel_header(header, credential):
            assert header.read_text() == "Bearer " + credential.path.read_text()
            header.unlink()
            if replacement_kind == "symlink":
                target = tmp_path / "operator-target"
                target.write_text("operator replacement")
                header.symlink_to(target)
            else:
                header.write_text("operator replacement")
                header.chmod(0o600)
        assert header.read_text() == "operator replacement"
        if replacement_kind == "symlink":
            assert header.is_symlink() and header.readlink() == target
        assert not list(tmp_path.glob(".dotbox-tunnel-cleanup-*"))


def test_tunnel_header_public_name_race_cannot_delete_an_operator_replacement(tmp_path, monkeypatch):
    header = tmp_path / "authorization"
    actual_stat, actual_rename = os.stat, os.rename
    changed = []

    def replace():
        header.unlink()
        header.write_text("operator replacement at cleanup boundary")
        changed.append(True)

    def stat_at_old_boundary(path, *args, **kwargs):
        result = actual_stat(path, *args, **kwargs)
        if path == header.name and kwargs.get("dir_fd") is not None and not changed:
            replace()  # The former stat/unlink gap.
        return result

    def rename_at_capture(path, *args, **kwargs):
        if path == header.name and kwargs.get("src_dir_fd") is not None and not changed:
            replace()  # A replacement just before atomic capture must be preserved.
        return actual_rename(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", stat_at_old_boundary)
    monkeypatch.setattr(os, "rename", rename_at_capture)
    with LocalCredential("dotbox-header-public-race-") as credential:
        with connector._tunnel_header(header, credential):
            pass
    assert changed
    assert header.read_text() == "operator replacement at cleanup boundary"


@pytest.mark.parametrize("foreign_kind", ["regular", "symlink"])
def test_tunnel_header_preserves_captured_foreign_entry_when_new_public_name_exists(tmp_path,
                                                                                  monkeypatch, foreign_kind):
    header = tmp_path / "authorization"
    foreign = tmp_path / "operator-value"
    foreign.write_text("original operator value")
    actual_rename = os.rename

    def race_after_capture(path, *args, **kwargs):
        result = actual_rename(path, *args, **kwargs)
        if path == header.name and kwargs.get("src_dir_fd") is not None:
            header.write_text("newer operator public value")
        return result

    monkeypatch.setattr(os, "rename", race_after_capture)
    with LocalCredential("dotbox-header-restore-race-") as credential:
        with connector._tunnel_header(header, credential):
            header.unlink()
            if foreign_kind == "regular":
                header.write_text("captured operator value")
            else:
                header.symlink_to(foreign)
    assert header.read_text() == "newer operator public value"
    quarantines = list(tmp_path.glob(".dotbox-tunnel-cleanup-*"))
    assert len(quarantines) == 1
    assert quarantines[0].stat().st_mode & 0o777 == 0o700
    captured = list(quarantines[0].iterdir())
    assert len(captured) == 1
    if foreign_kind == "regular":
        assert captured[0].read_text() == "captured operator value"
    else:
        assert captured[0].is_symlink() and captured[0].readlink() == foreign
        assert foreign.read_text() == "original operator value"


def test_tunnel_header_keeps_original_inode_open_until_cleanup(tmp_path, monkeypatch):
    header = tmp_path / "authorization"
    actual_open = os.open
    created = []

    def remember_header_fd(path, flags, *args, **kwargs):
        fd = actual_open(path, flags, *args, **kwargs)
        if path == header.name and flags & os.O_CREAT:
            created.append(fd)
        return fd

    monkeypatch.setattr(os, "open", remember_header_fd)
    with LocalCredential("dotbox-header-inode-lifetime-") as credential:
        with connector._tunnel_header(header, credential):
            identity = header.stat()
            header.unlink()
            held = os.fstat(created[0])
            assert (held.st_dev, held.st_ino) == (identity.st_dev, identity.st_ino)
            assert held.st_nlink == 0
    with pytest.raises(OSError):
        os.fstat(created[0])


@pytest.mark.parametrize("arguments", [
    ["--private-tunnel"],
    ["--local-test", "--private-tunnel"],
    ["--local-test", "--tunnel-header-file", "unused-header"],
])
def test_private_tunnel_launcher_rejects_invalid_mode_flags_before_credentials(receiver, monkeypatch, arguments):
    def must_not_mint(*args, **kwargs):
        pytest.fail("Invalid flags reached credential creation")
    monkeypatch.setattr(connector, "LocalCredential", must_not_mint)
    with pytest.raises(SystemExit) as error:
        connector.main(["--session", str(receiver.descriptor), "--viewer-id", VIEWER, *arguments])
    assert error.value.code == 2


def test_private_tunnel_factory_rejects_a_public_resource(receiver):
    pytest.importorskip("mcp")
    reader = OwnershipReader(receiver.descriptor, VIEWER)
    with LocalCredential("dotbox-tunnel-public-negative-") as credential:
        resource = "https://public.example/mcp"
        with pytest.raises(ValueError, match="loopback"):
            create_server(reader, token_verifier=LocalTestVerifier(
                credential, resource, expires_at=None),
                issuer_url="http://127.0.0.1:8787/local-test-issuer",
                resource_url=resource, private_tunnel=True)


def test_process_lifetime_local_bearer_keeps_bounded_request_claims(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    now = [1000.0]
    monkeypatch.setattr(connector, "time", SimpleNamespace(time=lambda: now[0]))
    with LocalCredential("dotbox-tunnel-lifetime-") as credential:
        bearer = credential.path.read_text().strip()
        verifier = LocalTestVerifier(credential, "http://127.0.0.1:8787/mcp", expires_at=None)
        first = asyncio.run(verifier.verify_token(bearer))
        now[0] += 86400
        later = asyncio.run(verifier.verify_token(bearer))
        assert first.scopes == later.scopes == [READ_SCOPE]
        assert first.resource == later.resource == "http://127.0.0.1:8787/mcp"
        assert later.expires_at - first.expires_at == 86400
        assert 0 < later.expires_at - now[0] <= 60
        assert asyncio.run(verifier.verify_token("wrong-credential")) is None
