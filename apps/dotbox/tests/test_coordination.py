"""Real no-backend receiver, sockets and CLI; callback witnesses are not desktop input."""

import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

import pytest

import dotbox
from dotbox.client import Client, ClientError, TurnInterrupted
from dotbox.coordination import CoordinationService
from dotbox.service import PROTOCOL, encoded, receive_line


VIEWER = "a" * 64


def raw_request(client, op, params=None, **overrides):
    request = {"protocol": PROTOCOL, "id": uuid.uuid4().hex, "token": client.token,
               "op": op, "params": {} if params is None else params,
               "instance_id": client.descriptor["instance_id"], **overrides}
    with socket.create_connection(("127.0.0.1", client.descriptor["port"]), timeout=1) as connection:
        connection.settimeout(1)
        connection.sendall(encoded(request))
        return receive_line(connection, 8192)


def publish(publisher, stream, owner="dot", mode="observe", connection="live"):
    response = publisher.request("bridge-challenge", {"stream_id": stream})
    assert response["ok"], response
    challenge = response["result"]
    event = {k: challenge[k] for k in ("stream_id", "challenge", "sequence")}
    event.update(owner=owner, viewer_mode=mode, connection=connection)
    response = publisher.request("bridge-observe", event)
    assert response["ok"], response
    return response["result"]


@pytest.fixture
def receiver(tmp_path):
    directory = tmp_path / "coordinator"
    service = CoordinationService(directory, VIEWER)
    ready = threading.Event()
    errors = []

    def run():
        try:
            service.run(on_ready=lambda _: ready.set())
        except BaseException as error:
            errors.append(error)
            ready.set()

    worker = threading.Thread(target=run)
    worker.start()
    assert ready.wait(3) and not errors
    client = Client(directory / "session.json", timeout=1)
    publisher = Client(directory / "ownership-publisher.json", timeout=1)
    credential_paths = [Path(c.descriptor["password_file"]) for c in (client, publisher)]
    opened = publisher.request("bridge-open", {"viewer_id": VIEWER})
    assert opened["ok"], opened
    yield service, client, publisher, opened["result"]["stream_id"]
    service.request_stop()
    worker.join(3)
    assert not worker.is_alive() and not errors
    assert service.backend is None
    assert not (directory / "session.json").exists()
    assert not (directory / "ownership-publisher.json").exists()
    assert not any(path.exists() for path in credential_paths)


def test_receiver_reports_its_actual_kind_without_invented_game_fields(receiver):
    service, client, _, _ = receiver
    reply = client.request("status")
    assert reply["ok"]
    assert set(reply["result"]) == {"instance_id", "kind", "platform_takeover"}
    assert reply["result"]["kind"] == "ownership-coordinator"
    assert reply["result"]["instance_id"] == service.instance_id
    assert reply["result"]["platform_takeover"]["owner"] == "unknown"
    assert service.backend is None


@pytest.mark.parametrize("op", ["frame", "control", "play", "pause", "key", "type",
                              "click", "close", "harness-list", "harness-save", "act"])
def test_game_operations_are_refused_without_a_native_backend_or_effect(receiver, op):
    service, client, _, _ = receiver
    reply = raw_request(client, op)
    assert reply["error"]["code"] == "unknown_operation"
    assert service.backend is None and not service.stop_requested.is_set()
    assert client.request("status")["result"]["kind"] == "ownership-coordinator"


def test_publisher_and_controller_capabilities_remain_separate(receiver):
    service, client, publisher, stream = receiver
    assert client.token != publisher.token
    for op in ("status", "turn-claim", "coordinator-close", "frame"):
        reply = raw_request(publisher, op)
        assert reply["error"]["code"] == "unauthorized" and "session" not in reply
        assert client.token not in json.dumps(reply) and publisher.token not in json.dumps(reply)
    assert client.request("bridge-open", {"viewer_id": VIEWER})["error"]["code"] == "unauthorized"
    assert not service.stop_requested.is_set()
    publish(publisher, stream)
    assert client.wait_for_turn("controller", timeout=0)["viewer_id"] == VIEWER


def test_status_turn_and_shutdown_require_current_instance(receiver):
    service, client, _, _ = receiver
    client.descriptor["instance_id"] = "f" * 32
    for op, params in (("status", {}), ("turn-claim", {"controller_id": "controller"}),
                       ("coordinator-close", {})):
        assert client.request(op, params)["error"]["code"] == "stale_instance"
    assert not service.stop_requested.is_set()


@pytest.mark.parametrize(("op", "params"), [
    ("status", {"extra": True}), ("coordinator-close", {"extra": True}),
    ("turn-claim", {}), ("turn-check", {}), ("turn-release", {}),
])
def test_strict_parameters_do_not_close_or_grant(receiver, op, params):
    service, client, _, _ = receiver
    assert client.request(op, params)["error"]["code"] == "invalid_params"
    assert not service.stop_requested.is_set()


def test_native_generation_fields_are_not_accepted_as_a_coordinator_lease(receiver):
    _, client, _, _ = receiver
    reply = raw_request(client, "coordinator-close", expected_generation=0)
    assert reply["error"]["code"] == "invalid_request"
    assert client.request("status")["ok"]


def test_real_client_wait_wakes_after_fresh_return_and_fences_callback_outcome(receiver):
    service, client, publisher, stream = receiver
    publish(publisher, stream, "human", "control")
    finished = threading.Event()
    leases, errors = [], []

    def wait():
        try:
            leases.append(client.wait_for_turn("controller", timeout=2, interval=0.01))
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    waiter = threading.Thread(target=wait)
    waiter.start()
    try:
        assert not finished.wait(0.05)
        publish(publisher, stream)
        assert finished.wait(2) and not errors
        lease = leases[0]
        effects = []
        assert client.run_turn_step(lease, lambda: effects.append("data-witness")) is None

        def interrupted():
            effects.append("completed-once")
            publish(publisher, stream, "human", "control")
            return {"witness": "completed-once"}

        with pytest.raises(TurnInterrupted) as result:
            client.run_turn_step(lease, interrupted)
        assert result.value.result == {"witness": "completed-once"}
        with pytest.raises(TurnInterrupted):
            client.run_turn_step(lease, lambda: effects.append("must-not-run"))
        assert effects == ["data-witness", "completed-once"]
        assert service.backend is None
    finally:
        waiter.join(3)
        assert not waiter.is_alive()


def test_real_receiver_expiry_invalidates_old_turn_after_new_observation(receiver):
    _, client, publisher, stream = receiver
    publish(publisher, stream)
    old = client.wait_for_turn("controller", timeout=0)
    time.sleep(old["expires_in_ms"] / 1000 + 0.03)
    assert not client.request("status")["result"]["platform_takeover"]["fresh"]
    with pytest.raises(ClientError):
        client.wait_for_turn("controller", timeout=0)
    publish(publisher, stream)
    assert not client.request("turn-check", {"lease": old})["ok"]
    assert client.wait_for_turn("controller", timeout=0)["lease_id"] != old["lease_id"]


def module_command(*arguments):
    # Use the exact imported package in source and installed-wheel test runs.
    package_root = str(Path(dotbox.__file__).resolve().parent.parent)
    bootstrap = f"import runpy,sys;sys.path.insert(0,{package_root!r});runpy.run_module('dotbox',run_name='__main__')"
    return [sys.executable, "-I", "-c", bootstrap, *arguments]


@pytest.mark.parametrize("shutdown", ["coordinator-close", "SIGINT", "SIGTERM"])
def test_real_cli_startup_and_shutdown_clean_descriptors_without_native_launch(tmp_path, shutdown):
    directory = tmp_path / "coordinator"
    process = subprocess.Popen(module_command("coordinate", "--directory", str(directory),
                               "--ownership-viewer", VIEWER), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 3
        descriptor = directory / "session.json"
        publisher_path = directory / "ownership-publisher.json"
        while not publisher_path.exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        client = Client(descriptor, timeout=1)
        publisher = Client(publisher_path, timeout=1)
        credentials = [Path(c.descriptor["password_file"]) for c in (client, publisher)]
        assert client.request("status")["result"]["kind"] == "ownership-coordinator"
        if shutdown == "coordinator-close":
            result = subprocess.run(module_command("coordinator-close", "--session", str(descriptor)),
                                    capture_output=True, text=True, timeout=3)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["result"] == {"status": "closing"}
        else:
            process.send_signal(getattr(signal, shutdown))
        stdout, stderr = process.communicate(timeout=3)
        assert process.returncode == 0, stderr
        assert json.loads(stdout)["session"]["kind"] == "ownership-coordinator"
        assert client.token not in stdout + stderr and publisher.token not in stdout + stderr
        assert not descriptor.exists() and not publisher_path.exists()
        assert not any(path.exists() for path in credentials)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)


def test_coordinate_cli_requires_binding_and_refuses_game_startup_arguments(tmp_path):
    directory = tmp_path / "coordinator"
    result = subprocess.run(module_command("coordinate", "--directory", str(directory),
                            "--ownership-viewer", VIEWER, "--project", "unused"),
                            capture_output=True, text=True, timeout=3)
    assert result.returncode == 2 and not directory.exists()
    result = subprocess.run(module_command("coordinate", "--directory", str(directory),
                            "--ownership-viewer", "invalid"),
                            capture_output=True, text=True, timeout=3)
    assert result.returncode == 1 and not directory.exists()
    assert json.loads(result.stderr)["ok"] is False
