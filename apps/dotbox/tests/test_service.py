"""Real sockets/client processes with a fake game boundary, not GUI acceptance."""

import json
import socket
import subprocess
import sys
import threading
import time

import pytest

from dotbox.client import Client, ClientError
from dotbox.service import MAX_REQUEST, PROTOCOL, PlayService, encoded, receive_line

from dotbox.local_auth import LocalCredential


class Game:
    def __init__(self):
        self.thread = threading.get_ident()
        self.run_id = "one-live-game"
        self.state = "stopped"
        self.reason = "startup"
        self.owner = "agent"
        self.generation = 0
        self.inputs = []
        self.closed = False
        self.calls = []
        self.drift_after_transfer = False
        self.failed = False

    def check(self, op):
        assert threading.get_ident() == self.thread
        self.calls.append(op)
        if self.failed:
            raise ConnectionError("game transport closed")

    def status(self):
        self.check("status")
        if self.drift_after_transfer and self.generation == 1:
            self.generation = 2
        return {"run_id": self.run_id, "state": self.state, "stop_reason": {"kind": self.reason},
                "native_control": {"owner": self.owner, "generation": self.generation}}

    def transfer(self, owner, expected_generation):
        self.check("transfer")
        assert self.generation == expected_generation
        self.owner = owner
        self.generation += 1
        self.inputs.clear()  # Native cleanup is separately verified by native tests.
        return {"owner": owner, "generation": self.generation}

    def play(self):
        self.check("play")
        self.state = "running"
        return {"state": "running"}

    def resume_after_handoff(self, owner, generation):
        assert self.owner == owner and self.generation == generation
        if self.state == "stopped" and self.reason in ("startup", "pause"):
            return self.play()
        return self.status()

    def pause(self):
        self.check("pause")
        self.state, self.reason = "stopped", "pause"
        return {"state": "stopped", "stop_reason": {"kind": "pause"}}

    def key(self, params, generation):
        self.check("key")
        if params.get("key") not in ("left", "right"):
            raise ValueError("unsupported key")
        assert self.owner == "agent" and generation == self.generation
        self.inputs.append(params["key"])
        return {"accepted": True, "delivery": "queued"}

    def frame(self):
        self.check("frame")
        return {"format": "png", "frame_id": 12}

    def close(self):
        assert threading.get_ident() == self.thread
        self.closed = True


@pytest.fixture
def running(tmp_path):
    ready = threading.Event()
    failures = []
    games = []

    def factory():
        game = Game()
        games.append(game)
        return game

    service = PlayService(factory, tmp_path / "session", manual_control=True,
                          client_timeout=0.15,
                          credential_factory=lambda: LocalCredential("dotbox-test-"))

    def serve():
        try:
            service.run(on_ready=lambda _: ready.set())
        except BaseException as error:
            failures.append(error)
            ready.set()

    thread = threading.Thread(target=serve)
    thread.start()
    assert ready.wait(3)
    assert not failures, failures
    client = Client(tmp_path / "session/session.json", timeout=3)
    yield service, client, games[0], tmp_path / "session/session.json"
    service.request_stop()
    thread.join(3)
    assert not thread.is_alive()
    assert not failures, failures
    assert games[0].closed


def status(client):
    reply = client.request("status")
    assert reply["ok"], reply
    return reply["result"]


def test_two_client_processes_reconnect_to_the_same_running_game(running):
    _, client, game, descriptor = running
    lease = status(client)
    transferred = client.request("control", {"owner": "agent", "resume": True}, lease=lease)
    assert transferred["ok"] and transferred["session"]["state"] == "running"
    code = "from dotbox.client import Client; import json,sys; print(json.dumps(Client(sys.argv[1]).request('status')))"
    replies = [json.loads(subprocess.check_output([sys.executable, "-c", code, str(descriptor)], text=True)) for _ in range(2)]
    assert all(r["result"]["run_id"] == "one-live-game" for r in replies)
    assert all(r["result"]["instance_id"] == lease["instance_id"] for r in replies)
    assert status(client)["state"] == "running" and not game.closed


def test_takeover_rejects_old_lease_and_all_agent_input_during_human_control(running):
    _, client, game, _ = running
    initial = status(client)
    agent = client.request("control", {"owner": "agent", "resume": True}, lease=initial)["session"]
    assert client.request("key", {"key": "right"}, lease=agent)["ok"]
    human = client.request("control", {"owner": "human"}, lease=agent)["session"]
    assert human["owner"] == "human" and human["generation"] == agent["generation"] + 1
    assert client.request("key", {"key": "right"}, lease=agent)["error"]["code"] == "stale_generation"
    assert client.request("key", {"key": "right"}, lease=human)["error"]["code"] == "human_has_control"
    assert not game.inputs and game.state == "running"
    back = client.request("control", {"owner": "agent"}, lease=human)["session"]
    assert client.request("key", {"key": "left"}, lease=back)["ok"]
    assert game.inputs == ["left"]
    assert back["platform_takeover"] == {"owner": "unknown", "source": "unavailable"}


def test_wrong_instance_and_missing_lease_do_not_mutate(running):
    _, client, game, _ = running
    lease = status(client)
    with pytest.raises(ClientError, match="previously observed"):
        client.request("play")
    result = client.request("control", {"owner": "human"}, lease={**lease, "instance_id": "old-instance"})
    assert result["error"]["code"] == "stale_instance"
    assert game.generation == 0 and not game.inputs


def test_duplicate_service_refused_before_opening_another_game(running):
    service, client, game, _ = running
    opened = []

    def another_game():
        opened.append(True)
        return Game()

    duplicate = PlayService(another_game, service.directory,
                            credential_factory=lambda: LocalCredential("dotbox-duplicate-"))
    with pytest.raises(RuntimeError, match="already owns"):
        duplicate.run()
    assert not opened and not game.closed
    assert status(client)["run_id"] == game.run_id


def test_invalid_input_leaves_the_running_session_usable_without_replay(running):
    _, client, game, _ = running
    lease = client.request("control", {"owner": "agent", "resume": True}, lease=status(client))["session"]
    result = client.request("key", {"key": "invalid"}, lease=lease)
    assert not result["ok"] and result["error"]["code"] == "backend_error"
    assert not game.closed and game.state == "running" and not game.inputs
    assert client.request("key", {"key": "right"}, lease=lease)["ok"]
    assert game.inputs == ["right"]


def test_interrupted_named_action_preserves_progress_without_client_replay(running):
    from dotbox.harness import ActionInterrupted
    _, client, game, _ = running
    lease = client.request("control", {"owner": "agent", "resume": True}, lease=status(client))["session"]
    attempts = []

    def interrupted(params, generation):
        game.check("act")
        attempts.append((params, generation))
        raise ActionInterrupted(params["revision"], params["name"], [
            {"index": 0, "op": "key", "result": {"accepted": True, "delivery": "queued"}}
        ], 1, RuntimeError("Observed breakpoint"))

    game.act = interrupted
    reply = client.request("act", {"revision": "a" * 64, "name": "move"}, lease=lease)
    assert reply["ok"] is False
    assert reply["error"]["code"] == "action_interrupted"
    assert reply["error"]["active_step"] == 1
    assert len(reply["error"]["completed_steps"]) == 1
    assert reply["session"]["instance_id"] == lease["instance_id"]
    assert len(attempts) == 1
    assert status(client)["state"] == "running" and not game.closed
    assert len(attempts) == 1


def test_handoff_does_not_resume_a_breakpoint_or_unknown_stop(running):
    _, client, game, _ = running
    for reason in ("breakpoint", "exception", "unknown"):
        game.state, game.reason = "stopped", reason
        reply = client.request("control", {"owner": "human", "resume": True}, lease=status(client))
        assert reply["ok"] and reply["session"]["state"] == "stopped"
        assert "play" not in game.calls


def test_generation_drift_during_transfer_never_resumes(running):
    _, client, game, _ = running
    game.drift_after_transfer = True
    result = client.request("control", {"owner": "human", "resume": True}, lease=status(client))
    assert not result["ok"] and result["error"]["code"] == "ownership_conflict"
    assert result["session"]["owner"] == "unclaimed" and "play" not in game.calls


def test_no_platform_feed_requires_explicit_manual_testing_mode(running):
    service, client, game, _ = running
    service.manual_control = False
    reply = client.request("control", {"owner": "human"}, lease=status(client))
    assert reply["error"]["code"] == "takeover_unavailable"
    assert game.generation == 0


@pytest.mark.parametrize("token", ["wrong", "\u00e9", {}, None, "a" * 64])
def test_wrong_authentication_never_discloses_session_or_token(running, token):
    _, client, game, _ = running
    with socket.create_connection(("127.0.0.1", client.descriptor["port"])) as connection:
        connection.settimeout(1)
        connection.sendall(encoded({"protocol": PROTOCOL, "id": "bad", "op": "status", "token": token}))
        reply = receive_line(connection, 4096)
    assert reply["error"]["code"] == "unauthorized"
    assert "session" not in reply and client.token not in json.dumps(reply)
    assert "transfer" not in game.calls


def test_dribbling_client_has_an_absolute_deadline(running):
    _, client, game, _ = running
    with socket.create_connection(("127.0.0.1", client.descriptor["port"])) as connection:
        connection.settimeout(1)
        connection.sendall(b'{"')
        time.sleep(0.08)
        connection.sendall(b'o')
        time.sleep(0.11)
        assert connection.recv(1) == b""
    assert status(client)["run_id"] == game.run_id


def test_descriptor_does_not_contain_token_and_close_invalidates_discovery(running):
    _, client, game, descriptor = running
    assert client.token not in descriptor.read_text()
    assert descriptor.stat().st_mode & 0o077 == 0
    reply = client.request("close", lease=status(client))
    assert reply["ok"]
    deadline = time.monotonic() + 2
    while descriptor.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not descriptor.exists() and game.closed


def test_oversized_client_message_is_closed_without_effect(running):
    _, client, game, _ = running
    with socket.create_connection(("127.0.0.1", client.descriptor["port"])) as connection:
        connection.settimeout(1)
        try:
            connection.sendall(b"x" * (MAX_REQUEST + 1))
            assert connection.recv(1) == b""
        except ConnectionResetError:
            pass
    assert status(client)["generation"] == 0 and not game.inputs


def test_excessively_nested_json_does_not_end_the_game(running):
    _, client, game, _ = running
    with socket.create_connection(("127.0.0.1", client.descriptor["port"])) as connection:
        connection.settimeout(1)
        connection.sendall(b"[" * 20000 + b"0" + b"]" * 20000 + b"\n")
        assert connection.recv(1) == b""
    assert status(client)["generation"] == 0 and not game.closed


def test_private_descriptor_and_credential_reading_refuse_symlinks(running, tmp_path):
    _, _, _, descriptor = running
    link = tmp_path / "linked.json"
    link.symlink_to(descriptor)
    with pytest.raises(OSError):
        Client(link)


def test_default_input_stays_with_desktop_harness_without_claiming_its_owner(tmp_path):
    game = Game()
    service = PlayService(lambda: game, tmp_path / "session")
    service.backend = game
    game.inputs.append("queued-before-transfer")
    service._start_harness_input()
    current = service.snapshot()
    assert game.owner == "host" and game.state == "running" and not game.inputs
    assert current["owner"] == "harness" and current["generation"] == 1
    assert current["platform_takeover"] == {"owner": "unknown", "source": "unavailable"}
    with LocalCredential("dotbox-harness-mode-test-") as credential:
        for op in ("key", "type", "click", "act", "play", "pause"):
            reply = service.handle({"protocol": PROTOCOL, "id": op,
                                    "token": credential.path.read_text().strip(),
                                    "op": op, "params": {},
                                    "instance_id": current["instance_id"],
                                    "expected_generation": current["generation"]}, credential)
            assert reply["error"]["code"] == "harness_controls_input"
    assert game.state == "running" and not game.inputs


def test_harness_start_preserves_foreign_stop_and_rejects_ownership_race(tmp_path):
    game = Game()
    game.reason = "breakpoint"
    service = PlayService(lambda: game, tmp_path / "session")
    service.backend = game
    service._start_harness_input()
    assert game.state == "stopped" and "play" not in game.calls
    game = Game()
    game.drift_after_transfer = True
    service = PlayService(lambda: game, tmp_path / "other-session")
    service.backend = game
    with pytest.raises(RuntimeError, match="ownership changed"):
        service._start_harness_input()
    assert "play" not in game.calls
