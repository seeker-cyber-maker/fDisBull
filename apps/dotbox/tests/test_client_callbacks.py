"""Synchronous callback fencing through a real authenticated coordinator/socket."""

import asyncio
import inspect
import threading
import types

import pytest

from dotbox.client import Client, TurnInterrupted
from dotbox.coordination import CoordinationService


VIEWER = "a" * 64


@pytest.fixture
def turn(tmp_path):
    directory = tmp_path / "coordinator"
    service = CoordinationService(directory, VIEWER)
    ready = threading.Event()
    failures = []

    def serve():
        try:
            service.run(on_ready=lambda _: ready.set())
        except BaseException as error:
            failures.append(error)
            ready.set()

    worker = threading.Thread(target=serve)
    worker.start()
    assert ready.wait(3) and not failures
    client = Client(directory / "session.json", timeout=1)
    publisher = Client(directory / "ownership-publisher.json", timeout=1)
    response = publisher.request("bridge-open", {"viewer_id": VIEWER})
    assert response["ok"], response
    stream = response["result"]["stream_id"]

    def publish(owner="dot", mode="observe"):
        response = publisher.request("bridge-challenge", {"stream_id": stream})
        assert response["ok"], response
        event = {k: response["result"][k] for k in ("stream_id", "challenge", "sequence")}
        event.update(owner=owner, viewer_mode=mode, connection="live")
        response = publisher.request("bridge-observe", event)
        assert response["ok"], response

    publish()
    lease = client.wait_for_turn("callback-controller", timeout=0)
    yield client, lease, publish
    service.request_stop()
    worker.join(3)
    assert not worker.is_alive() and not failures
    assert service.backend is None
    assert not (directory / "session.json").exists()
    assert not (directory / "ownership-publisher.json").exists()


def test_async_coroutine_is_rejected_and_closed_without_running_its_body(turn):
    client, lease, _ = turn
    effects = []

    async def desktop_action():
        effects.append("must-not-run")
        return {"effect": "deferred"}

    deferred = desktop_action()
    try:
        with pytest.raises(TurnInterrupted, match="awaitable") as interrupted:
            client.run_turn_step(lease, lambda: deferred)
        assert interrupted.value.result is None
        assert effects == []
        assert inspect.getcoroutinestate(deferred) == inspect.CORO_CLOSED
    finally:
        deferred.close()


def test_custom_awaitable_is_neither_run_closed_cancelled_nor_returned_as_success(turn):
    client, lease, _ = turn
    calls = []

    class DeferredAction:
        def __await__(self):
            calls.append("await")
            yield

        def close(self):
            calls.append("close")

        def cancel(self):
            calls.append("cancel")

    deferred = DeferredAction()

    def action():
        calls.append("callback-once")
        return deferred

    with pytest.raises(TurnInterrupted, match="awaitable") as interrupted:
        client.run_turn_step(lease, action)
    assert interrupted.value.result is None
    assert calls == ["callback-once"]


@pytest.mark.parametrize("completed", [False, True])
def test_asyncio_future_is_rejected_without_running_loop_or_cancelling_it(turn, completed):
    client, lease, _ = turn
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        if completed:
            future.set_result("already-complete")
        with pytest.raises(TurnInterrupted, match="awaitable"):
            client.run_turn_step(lease, lambda: future)
        assert not future.cancelled()
        assert future.done() is completed
    finally:
        loop.close()


def test_generator_based_awaitable_is_rejected_without_execution_or_closing(turn):
    client, lease, _ = turn
    effects = []

    @types.coroutine
    def deferred_action():
        effects.append("must-not-run")
        yield

    deferred = deferred_action()
    try:
        with pytest.raises(TurnInterrupted, match="awaitable"):
            client.run_turn_step(lease, lambda: deferred)
        assert effects == []
        assert deferred.gi_frame is not None  # Caller still owns this arbitrary awaitable.
    finally:
        deferred.close()


def test_started_coroutine_is_rejected_without_running_its_finalizer(turn):
    client, lease, _ = turn
    effects = []

    class Pause:
        def __await__(self):
            yield

    async def desktop_action():
        try:
            effects.append("caller-started")
            await Pause()
        finally:
            effects.append("caller-cleanup")

    deferred = desktop_action()
    deferred.send(None)
    try:
        with pytest.raises(TurnInterrupted, match="awaitable"):
            client.run_turn_step(lease, lambda: deferred)
        assert effects == ["caller-started"]
        assert inspect.getcoroutinestate(deferred) == inspect.CORO_SUSPENDED
    finally:
        deferred.close()
    assert effects == ["caller-started", "caller-cleanup"]


def test_completed_synchronous_result_is_returned_unchanged_once(turn):
    client, lease, _ = turn
    result = {"completed": object()}
    calls = []

    def action():
        calls.append("once")
        return result

    assert client.run_turn_step(lease, action) is result
    assert calls == ["once"]


def test_completed_synchronous_outcome_survives_postcheck_rejection_without_replay(turn):
    client, lease, publish = turn
    result = {"completed": True}
    calls = []

    def action():
        calls.append("once")
        publish("human", "control")
        return result

    with pytest.raises(TurnInterrupted) as interrupted:
        client.run_turn_step(lease, action)
    assert interrupted.value.result is result
    assert calls == ["once"]


def test_synchronous_exception_retains_inspection_boundary_without_retry(turn):
    client, lease, _ = turn
    calls = []

    def action():
        calls.append("effect-before-error")
        raise RuntimeError("action failed")

    with pytest.raises(TurnInterrupted, match="effects are unknown") as interrupted:
        client.run_turn_step(lease, action)
    assert isinstance(interrupted.value.__cause__, RuntimeError)
    assert calls == ["effect-before-error"]


def test_failed_precheck_never_invokes_a_callback_factory(turn):
    client, lease, publish = turn
    publish("human", "control")
    calls = []
    with pytest.raises(TurnInterrupted):
        client.run_turn_step(lease, lambda: calls.append("must-not-run"))
    assert calls == []
