"""Receiver-clock ownership evidence and cooperative turn leases, without a guest."""

import pytest

from dotbox.ownership import OwnershipState


VIEWER = "ab" * 32


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def opened():
    clock = Clock()
    state = OwnershipState(VIEWER, clock=clock)
    state.open(VIEWER)
    return state, clock


def observation(state, *, owner="dot", viewer_mode="observe", connection="live"):
    stream = state.status()["stream_id"]
    challenge = state.challenge(stream)
    return {"stream_id": stream, "challenge": challenge["challenge"],
            "sequence": challenge["sequence"], "owner": owner,
            "viewer_mode": viewer_mode, "connection": connection}


def publish(state, **kwargs):
    return state.observe(observation(state, **kwargs))


def test_initial_status_never_grants_an_unobserved_turn():
    state = OwnershipState(VIEWER, clock=Clock())
    assert state.status() == {
        "owner": "unknown", "source": "unavailable", "viewer_id": VIEWER,
        "epoch": 0, "stream_id": None, "sequence": 0, "fresh": False,
        "expires_in_ms": 0, "viewer_mode": "unknown", "connection": "unknown",
    }
    with pytest.raises(ValueError):
        state.claim("agent-A")


@pytest.mark.parametrize("viewer", [None, "a" * 63, "g" * 64, "A" * 64, b"a" * 64])
def test_viewer_binding_is_exact_lowercase_sha256(viewer):
    with pytest.raises(ValueError):
        OwnershipState(viewer)


@pytest.mark.parametrize("ttl", [True, 0, -1, float("nan"), float("inf"), "3", 10**1000])
def test_ttl_must_be_positive_finite_receiver_duration(ttl):
    with pytest.raises(ValueError):
        OwnershipState(VIEWER, ttl=ttl)


def test_open_replaces_stream_and_invalidates_preexisting_lease(opened):
    state, _ = opened
    publish(state)
    lease = state.claim("agent-A")
    old = state.status()
    with pytest.raises(ValueError):
        state.open("cd" * 32)
    assert state.status() == old
    current = state.open(VIEWER)
    assert current["stream_id"] != old["stream_id"]
    assert current["epoch"] > old["epoch"]
    assert current["sequence"] == 0 and current["owner"] == "unknown"
    assert current["source"] == "codex-viewer-ui"
    with pytest.raises(ValueError):
        state.check(lease)


def test_observation_deadline_begins_at_challenge_not_delivery(opened):
    state, clock = opened
    event = observation(state)
    clock.advance(2.5)
    current = state.observe(event)
    assert current["fresh"] and 499 <= current["expires_in_ms"] <= 500
    lease = state.claim("agent-A")
    assert 499 <= lease["expires_in_ms"] <= 500
    clock.advance(0.5)
    expired = state.status()
    assert expired["owner"] == "unknown" and not expired["fresh"]
    assert expired["expires_in_ms"] == 0
    assert state.status()["epoch"] == expired["epoch"]
    with pytest.raises(ValueError):
        state.check(lease)


def test_challenge_is_one_use_and_cannot_be_replayed_to_extend_freshness(opened):
    state, clock = opened
    event = observation(state)
    state.observe(event)
    clock.advance(1)
    before = state.status()
    with pytest.raises(ValueError):
        state.observe(event)
    assert state.status() == before


def test_replacing_challenge_refuses_older_delivery(opened):
    state, _ = opened
    first = observation(state)
    second = observation(state)
    assert first["sequence"] == second["sequence"] == 1
    assert first["challenge"] != second["challenge"]
    with pytest.raises(ValueError):
        state.observe(first)
    assert state.observe(second)["sequence"] == 1


def test_expired_challenge_and_old_stream_are_refused(opened):
    state, clock = opened
    event = observation(state)
    clock.advance(3)
    with pytest.raises(ValueError):
        state.observe(event)
    state.open(VIEWER)
    with pytest.raises(ValueError):
        state.challenge(event["stream_id"])
    with pytest.raises(ValueError):
        state.observe(event)


@pytest.mark.parametrize("change", [
    {"observed_at": 10**20}, {"sequence": True}, {"sequence": 99},
    {"owner": []}, {"viewer_mode": "ready"}, {"connection": "ready"},
    {"challenge": "\u00e9" * 64},
])
def test_strict_events_cannot_invent_fields_or_advance_sequence(opened, change):
    state, _ = opened
    event = observation(state)
    with pytest.raises(ValueError):
        state.observe({**event, **change})
    assert state.status()["sequence"] == 0
    assert state.observe(event)["sequence"] == 1


@pytest.mark.parametrize("mode,connection", [
    ("control", "live"), ("unknown", "live"),
    ("observe", "unknown"), ("observe", "disconnected"),
])
def test_contradictory_dot_event_consumes_challenge_and_fails_closed(opened, mode, connection):
    state, _ = opened
    publish(state)
    lease = state.claim("agent-A")
    event = observation(state, viewer_mode=mode, connection=connection)
    with pytest.raises(ValueError):
        state.observe(event)
    current = state.status()
    assert current["owner"] == "unknown" and not current["fresh"]
    assert current["sequence"] == event["sequence"]
    with pytest.raises(ValueError):
        state.check(lease)
    with pytest.raises(ValueError):
        state.observe(event)


@pytest.mark.parametrize("owner,mode,connection", [
    ("human", "control", "live"), ("human", "observe", "live"),
    ("unknown", "unknown", "unknown"),
    ("unknown", "observe", "disconnected"),
])
def test_human_and_unknown_events_revoke_agent_lease(opened, owner, mode, connection):
    state, _ = opened
    publish(state)
    lease = state.claim("agent-A")
    current = publish(state, owner=owner, viewer_mode=mode, connection=connection)
    assert current["owner"] == owner and current["epoch"] > lease["epoch"]
    with pytest.raises(ValueError):
        state.claim("agent-A")
    with pytest.raises(ValueError):
        state.check(lease)
    publish(state)
    with pytest.raises(ValueError):
        state.check(lease)
    assert state.claim("agent-A")["lease_id"] != lease["lease_id"]


def test_heartbeat_does_not_extend_active_lease_and_expiry_invalidates_once(opened):
    state, clock = opened
    publish(state)
    lease = state.claim("agent-A")
    clock.advance(2)
    publish(state)
    assert state.check(lease)["fresh"]
    assert state.claim("agent-A") == lease
    clock.advance(1)
    current = state.status()
    assert current["owner"] == "dot" and current["fresh"]
    assert current["epoch"] > lease["epoch"]
    assert state.status()["epoch"] == current["epoch"]
    with pytest.raises(ValueError):
        state.check(lease)
    assert state.claim("agent-B")["lease_id"] != lease["lease_id"]


def test_only_one_controller_holds_lease_and_release_allows_next_controller(opened):
    state, _ = opened
    publish(state)
    lease = state.claim("agent-A")
    with pytest.raises(ValueError):
        state.claim("agent-B")
    released = state.release(lease)
    assert released["fresh"] and released["owner"] == "dot"
    with pytest.raises(ValueError):
        state.check(lease)
    replacement = state.claim("agent-B")
    assert replacement["controller_id"] == "agent-B"
    assert replacement["lease_id"] != lease["lease_id"]


def test_lease_is_opaque_and_caller_edits_never_change_receiver_deadline(opened):
    state, clock = opened
    publish(state)
    lease = state.claim("agent-A")
    for field, value in (("expires_in_ms", 10**20), ("controller_id", "agent-B"),
                         ("epoch", True), ("lease_id", "f" * 64)):
        with pytest.raises(ValueError):
            state.check({**lease, field: value})
    with pytest.raises(ValueError):
        state.check({**lease, "extra": True})
    state.status()["owner"] = "human"
    assert state.check(lease)["owner"] == "dot"
    clock.advance(3)
    with pytest.raises(ValueError):
        state.check(lease)


@pytest.mark.parametrize("controller", ["", " ", None, "a\nb", "a" * 129])
def test_controller_requires_bounded_stable_identifier(opened, controller):
    state, _ = opened
    publish(state)
    with pytest.raises(ValueError):
        state.claim(controller)


def test_new_source_evidence_after_gap_never_resurrects_lease(opened):
    state, clock = opened
    publish(state)
    lease = state.claim("agent-A")
    clock.advance(4)
    # No status poll was necessary to notice the lapse before this new event.
    current = publish(state)
    assert current["fresh"] and current["epoch"] > lease["epoch"]
    with pytest.raises(ValueError):
        state.check(lease)


def test_publisher_invalidation_rejects_foreign_stream_and_clears_pending_evidence(opened):
    state, _ = opened
    publish(state)
    lease = state.claim("agent-A")
    pending = observation(state)
    before = state.status()
    with pytest.raises(ValueError):
        state.invalidate("f" * 64)
    assert state.status() == before
    invalidated = state.invalidate(before["stream_id"])
    assert invalidated["owner"] == "unknown" and not invalidated["fresh"]
    assert invalidated["epoch"] > before["epoch"]
    with pytest.raises(ValueError):
        state.check(lease)
    with pytest.raises(ValueError):
        state.observe(pending)
    assert publish(state)["sequence"] == before["sequence"] + 1
