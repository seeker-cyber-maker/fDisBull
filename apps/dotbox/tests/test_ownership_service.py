"""Real authenticated sockets; the reused Game boundary is not cloud acceptance."""

import threading

import pytest

from dotbox.client import Client, ClientError, TurnInterrupted
from dotbox.ownership import OwnershipState
from dotbox.service import PlayService
from test_service import Game

VIEWER = "a" * 64


@pytest.fixture
def bridged(tmp_path):
    ready = threading.Event()
    errors, games = [], []
    clock = [100.0]

    def factory():
        games.append(Game())
        return games[-1]

    service = PlayService(factory, tmp_path / "session", ownership_viewer=VIEWER)
    service.ownership = OwnershipState(VIEWER, clock=lambda: clock[0])

    def run():
        try:
            service.run(on_ready=lambda _: ready.set())
        except BaseException as error:
            errors.append(error)
            ready.set()

    worker = threading.Thread(target=run)
    worker.start()
    assert ready.wait(3) and not errors
    client = Client(tmp_path / "session/session.json")
    publisher = Client(tmp_path / "session/ownership-publisher.json")
    opened = publisher.request("bridge-open", {"viewer_id": VIEWER})
    assert opened["ok"], opened
    stream = opened["result"]["stream_id"]

    def publish(owner="dot", mode="observe", connection="live"):
        challenge = publisher.request("bridge-challenge", {"stream_id": stream})["result"]
        event = {k: challenge[k] for k in ("stream_id", "challenge", "sequence")}
        event.update(owner=owner, viewer_mode=mode, connection=connection)
        reply = publisher.request("bridge-observe", event)
        assert reply["ok"], reply
        return event

    yield service, client, publisher, stream, publish, games[0], clock
    service.request_stop()
    worker.join(3)
    assert not worker.is_alive() and not errors
    assert games[0].closed
    assert not (tmp_path / "session/ownership-publisher.json").exists()


def test_bridge_preserves_native_desktop_ownership_and_separates_credentials(bridged):
    _, client, publisher, _, publish, game, _ = bridged
    initial = client.request("status")["result"]
    assert (initial["owner"], initial["native_owner"], initial["generation"]) == ("harness", "host", 1)
    assert not client.request("turn-claim", {"controller_id": "dot"})["ok"]
    publish()
    current = client.request("status")["result"]
    assert current["platform_takeover"]["owner"] == "dot"
    assert (current["owner"], current["native_owner"], current["generation"]) == ("harness", "host", 1)
    assert game.calls.count("transfer") == 1
    for op in ("status", "close", "pause", "turn-claim"):
        denied = publisher.request(op, {"controller_id": "dot"} if op == "turn-claim" else {}, lease=current)
        assert denied["error"]["code"] == "unauthorized" and "session" not in denied
    denied = client.request("bridge-open", {"viewer_id": VIEWER})
    assert denied["error"]["code"] == "unauthorized"
    assert not game.closed
    assert client.request("key", {"key": "left"}, lease=current)["error"]["code"] == "harness_controls_input"


def test_human_transition_fences_next_step_without_replaying_completed_effect(bridged):
    _, client, _, _, publish, game, _ = bridged
    publish()
    lease = client.wait_for_turn("dot", timeout=0)
    effects = []

    def first_step():
        effects.append("delivered-once")
        publish("human", "control")
        return {"delivered": True}

    with pytest.raises(TurnInterrupted) as interrupted:
        client.run_turn_step(lease, first_step)
    assert interrupted.value.result == {"delivered": True}
    with pytest.raises(TurnInterrupted):
        client.run_turn_step(lease, lambda: effects.append("must-not-run"))
    assert effects == ["delivered-once"]
    assert client.request("frame")["ok"]  # Human play is not paused.
    assert game.state == "running" and game.owner == "host" and game.generation == 1
    publish()
    fresh = client.wait_for_turn("dot", timeout=0)
    assert fresh["epoch"] > lease["epoch"]
    client.run_turn_step(fresh, lambda: effects.append("next-turn"))
    assert effects == ["delivered-once", "next-turn"]


def test_source_expiry_and_reconnect_never_revive_an_old_turn(bridged):
    _, client, publisher, stream, publish, _, clock = bridged
    publish()
    old = client.wait_for_turn("dot", timeout=0)
    clock[0] += 3
    expired = client.request("status")["result"]["platform_takeover"]
    assert expired["owner"] == "unknown" and not expired["fresh"]
    with pytest.raises(ClientError):
        client.wait_for_turn("dot", timeout=0)
    publish()
    assert not client.request("turn-check", {"lease": old})["ok"]
    next_lease = client.wait_for_turn("dot", timeout=0)
    replacement = publisher.request("bridge-open", {"viewer_id": VIEWER})["result"]
    assert replacement["stream_id"] != stream
    assert not client.request("turn-check", {"lease": next_lease})["ok"]
    assert not publisher.request("bridge-challenge", {"stream_id": stream})["ok"]


def test_current_publisher_reordered_event_fails_closed(bridged):
    _, client, publisher, _, publish, _, _ = bridged
    event = publish()
    lease = client.wait_for_turn("dot", timeout=0)
    rejected = publisher.request("bridge-observe", event)
    assert rejected["error"]["code"] == "ownership_rejected"
    assert client.request("status")["result"]["platform_takeover"]["owner"] == "unknown"
    assert not client.request("turn-check", {"lease": lease})["ok"]


def test_claim_fences_other_controllers_and_receivers(bridged):
    _, client, publisher, _, publish, _, _ = bridged
    publish()
    lease = client.wait_for_turn("dot", timeout=0)
    assert not client.request("turn-claim", {"controller_id": "other"})["ok"]
    client.descriptor["instance_id"] = "f" * 32
    assert client.request("turn-check", {"lease": lease})["error"]["code"] == "stale_instance"
    publisher.descriptor["instance_id"] = "f" * 32
    assert publisher.request("bridge-open", {"viewer_id": VIEWER})["error"]["code"] == "stale_instance"


def test_diagnostic_native_control_cannot_be_mixed_with_platform_bridge(tmp_path):
    with pytest.raises(ValueError, match="desktop-harness"):
        PlayService(Game, tmp_path, manual_control=True, ownership_viewer=VIEWER)


def test_guest_replacement_invalidates_turn_even_when_viewer_owner_stays_dot(bridged):
    _, client, _, _, publish, game, _ = bridged
    publish()
    lease = client.wait_for_turn("dot", timeout=0)
    game.run_id = "replacement-game"
    status = client.request("status")["result"]
    assert status["platform_takeover"]["owner"] == "unknown"
    assert not client.request("turn-check", {"lease": lease})["ok"]
    publish()
    assert client.wait_for_turn("dot", timeout=0)["epoch"] > lease["epoch"]


def test_restore_generation_fences_turn_while_ordinary_revisions_do_not(bridged, monkeypatch):
    """Socket-level receipt behavior; this does not execute a native restore."""
    _, client, _, _, publish, game, _ = bridged
    revision = [5]
    native_status = game.status

    def observed_status():
        return {**native_status(), "state_revision": revision[0]}

    monkeypatch.setattr(game, "status", observed_status)
    publish()
    lease = client.wait_for_turn("dot", timeout=0)
    effects = []
    revision[0] += 1  # Ordinary input or capture may change this revision.
    client.run_turn_step(lease, lambda: effects.append("ordinary-turn"))
    assert client.request("turn-check", {"lease": lease})["ok"]

    before = client.request("status")["result"]
    game.generation += 1  # Receipt of an admitted same-owner restore fence.
    with pytest.raises(TurnInterrupted):
        client.run_turn_step(lease, lambda: effects.append("stale-must-not-run"))
    after = client.request("status")["result"]
    assert effects == ["ordinary-turn"]
    assert before["run_id"] == after["run_id"]
    assert before["native_owner"] == after["native_owner"] == "host"
    assert after["generation"] == before["generation"] + 1
    assert after["owner"] == "unclaimed"
    assert after["platform_takeover"]["owner"] == "unknown"
    # New viewer evidence cannot silently repair a changed native boundary.
    publish()
    assert not client.request("turn-check", {"lease": lease})["ok"]
    assert not client.request("turn-claim", {"controller_id": "dot"})["ok"]
    assert game.calls.count("transfer") == 1


def test_native_harness_ownership_drift_disables_turns_without_repairing_it(bridged):
    _, client, _, _, publish, game, _ = bridged
    publish()
    lease = client.wait_for_turn("dot", timeout=0)
    game.owner, game.generation = "agent", game.generation + 1
    assert not client.request("turn-check", {"lease": lease})["ok"]
    publish()
    assert not client.request("turn-claim", {"controller_id": "dot"})["ok"]
    assert game.owner == "agent" and game.calls.count("transfer") == 1


def test_waiter_resumes_automatically_after_return_without_blocking_publisher(bridged):
    service, client, _, _, publish, _, _ = bridged
    publish("human", "control")
    waiting, finished = threading.Event(), threading.Event()
    replies, failures = [], []
    waiter = Client(service.directory / "session.json")
    original_request = waiter.request

    def observed_request(op, params=None, **kwargs):
        result = original_request(op, params, **kwargs)
        if op == "turn-claim" and not result["ok"]:
            waiting.set()
        return result

    waiter.request = observed_request

    def wait():
        try:
            replies.append(waiter.wait_for_turn("dot", timeout=2, interval=0.01))
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=wait)
    thread.start()
    assert waiting.wait(1) and not finished.is_set()
    publish()  # A single listener must still process the actual publisher.
    thread.join(2)
    assert finished.is_set() and not failures and len(replies) == 1
    assert client.request("turn-check", {"lease": replies[0]})["ok"]


def test_cli_turn_receipt_roundtrip_and_invalid_shape(bridged, tmp_path, capsys):
    from dotbox.cli import main
    service, _, _, _, publish, _, _ = bridged
    publish()
    session = str(service.directory / "session.json")
    assert main(["turn-claim", "--session", session, "--controller-id", "dot-cli"]) == 0
    claim = capsys.readouterr().out
    receipt = tmp_path / "turn.json"
    receipt.write_text(claim)
    receipt.chmod(0o600)
    for op in ("turn-check", "turn-release"):
        assert main([op, "--session", session, "--turn-lease", str(receipt)]) == 0
        capsys.readouterr()
    receipt.write_text("[]")
    assert main(["turn-check", "--session", session, "--turn-lease", str(receipt)]) == 1
    assert "object turn-claim receipt" in capsys.readouterr().err
