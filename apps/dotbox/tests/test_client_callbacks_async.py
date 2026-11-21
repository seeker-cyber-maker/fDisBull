"""Awaited callback fencing through an authenticated local coordinator."""

import asyncio
import inspect
import threading

import pytest

from dotbox.client import Client, TurnInterrupted
from dotbox.coordination import CoordinationService
from dotbox.ownership import OwnershipState


VIEWER = "a" * 64


@pytest.fixture
def turn(tmp_path):
    directory = tmp_path / "coordinator"
    service = CoordinationService(directory, VIEWER)
    clock = [100.0]
    service.ownership = OwnershipState(VIEWER, clock=lambda: clock[0])
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
    lease = client.wait_for_turn("async-callback-controller", timeout=0)
    yield client, lease, publish, service, clock
    service.request_stop()
    worker.join(3)
    assert not worker.is_alive() and not failures
    assert service.backend is None
    assert not (directory / "session.json").exists()
    assert not (directory / "ownership-publisher.json").exists()


def test_awaited_action_completes_once_and_returns_its_exact_result(turn):
    client, lease, _, _, _ = turn
    result = {"observed": object()}
    effects = []

    async def action():
        effects.append("started")
        await asyncio.sleep(0)
        effects.append("observed")
        return result

    assert asyncio.run(client.run_turn_step_async(lease, action)) is result
    assert effects == ["started", "observed"]


def test_denied_precheck_never_invokes_the_factory(turn):
    client, lease, publish, _, _ = turn
    publish("human", "control")
    calls = []
    with pytest.raises(TurnInterrupted):
        asyncio.run(client.run_turn_step_async(lease, lambda: calls.append("must-not-run")))
    assert calls == []


@pytest.mark.parametrize("failure", [OSError("connection lost"), ValueError("invalid response")])
def test_failed_precheck_preserves_cause_without_invoking_factory(turn, monkeypatch, failure):
    client, lease, _, _, _ = turn
    calls = []

    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(client, "request", unavailable)
    with pytest.raises(TurnInterrupted) as interrupted:
        asyncio.run(client.run_turn_step_async(lease, lambda: calls.append("must-not-run")))
    assert interrupted.value.__cause__ is failure
    assert interrupted.value.result is None
    assert calls == []


def test_takeover_while_awaiting_preserves_completed_result_without_replay(turn):
    client, lease, publish, _, _ = turn
    result = {"observed": object()}
    effects = []

    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()

        async def action():
            effects.append("effect-once")
            started.set()
            await finish.wait()
            return result

        task = asyncio.create_task(client.run_turn_step_async(lease, action))
        try:
            await asyncio.wait_for(started.wait(), 1)
            await asyncio.to_thread(publish, "human", "control")
        finally:
            finish.set()
        with pytest.raises(TurnInterrupted) as interrupted:
            await task
        assert interrupted.value.result is result

    asyncio.run(scenario())
    assert effects == ["effect-once"]


def test_callback_cannot_substitute_a_new_receipt_after_takeover(turn):
    client, lease, publish, _, _ = turn
    original = dict(lease)
    result = {"completed": True}
    effects = []

    async def action():
        effects.append("effect-once")
        await asyncio.to_thread(publish, "human", "control")
        await asyncio.to_thread(publish)
        replacement = await asyncio.to_thread(client.wait_for_turn, "async-callback-controller", timeout=0)
        lease.clear()
        lease.update(replacement)
        return result

    with pytest.raises(TurnInterrupted) as interrupted:
        asyncio.run(client.run_turn_step_async(lease, action))
    assert interrupted.value.result is result
    assert effects == ["effect-once"]
    assert lease["lease_id"] != original["lease_id"]
    assert client.request("turn-check", {"lease": lease})["ok"]
    assert not client.request("turn-check", {"lease": original})["ok"]


def test_fresh_heartbeat_does_not_extend_the_original_lease(turn):
    client, lease, publish, _, clock = turn
    result = {"completed": True}

    async def action():
        clock[0] = 102.0
        await asyncio.to_thread(publish)  # Evidence now lasts to 105; lease still expires at 103.
        clock[0] = 104.0
        return result

    with pytest.raises(TurnInterrupted) as interrupted:
        asyncio.run(client.run_turn_step_async(lease, action))
    assert interrupted.value.result is result
    status = client.request("status")["result"]["platform_takeover"]
    assert status["fresh"] and status["owner"] == "dot"
    assert not client.request("turn-check", {"lease": lease})["ok"]


@pytest.mark.parametrize("phase", ["factory", "awaited"])
def test_action_exception_preserves_cause_without_retry(turn, phase):
    client, lease, _, _, _ = turn
    failure = RuntimeError("action failed after an effect")
    calls = []

    async def action():
        calls.append("effect-once")
        await asyncio.sleep(0)
        raise failure

    def factory():
        calls.append("factory-once")
        if phase == "factory":
            raise failure
        return action()

    with pytest.raises(TurnInterrupted) as interrupted:
        asyncio.run(client.run_turn_step_async(lease, factory))
    assert interrupted.value.__cause__ is failure
    assert interrupted.value.result is None
    assert calls == (["factory-once"] if phase == "factory" else ["factory-once", "effect-once"])


@pytest.mark.parametrize("failure", [OSError("connection lost"), ValueError("invalid response")])
def test_postcheck_transport_failure_retains_completed_outcome(turn, monkeypatch, failure):
    client, lease, _, _, _ = turn
    request = client.request
    operations = []
    result = {"observed": object()}
    calls = []

    def lose_second_check(op, *args, **kwargs):
        operations.append(op)
        if len(operations) == 2:
            raise failure
        return request(op, *args, **kwargs)

    async def action():
        calls.append("effect-once")
        await asyncio.sleep(0)
        return result

    monkeypatch.setattr(client, "request", lose_second_check)
    with pytest.raises(TurnInterrupted) as interrupted:
        asyncio.run(client.run_turn_step_async(lease, action))
    assert interrupted.value.__cause__ is failure
    assert interrupted.value.result is result
    assert operations == ["turn-check", "turn-check"]
    assert calls == ["effect-once"]


def test_blocked_coordination_request_allows_loop_and_publisher_progress(turn, monkeypatch):
    client, lease, publish, _, _ = turn
    request = client.request
    release = threading.Event()
    result = {"completed": True}
    checks = []

    async def scenario():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        progressed = []

        def delayed_check(op, *args, **kwargs):
            checks.append(op)
            if len(checks) == 1:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(2), "The coordinator call blocked event-loop progress"
            return request(op, *args, **kwargs)

        async def update_from_loop():
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.to_thread(publish)
            progressed.append("published-while-check-blocked")
            release.set()

        async def action():
            assert progressed == ["published-while-check-blocked"]
            return result

        monkeypatch.setattr(client, "request", delayed_check)
        publisher = asyncio.create_task(update_from_loop())
        try:
            assert await client.run_turn_step_async(lease, action) is result
        finally:
            release.set()
            await publisher

    asyncio.run(scenario())
    assert checks == ["turn-check", "turn-check"]


@pytest.mark.parametrize("phase", ["precheck", "postcheck"])
def test_cancellation_during_coordination_does_not_replay_or_release(turn, monkeypatch, phase):
    client, lease, _, _, _ = turn
    request = client.request
    release = threading.Event()
    operations, effects = [], []
    result = {"observed": object()}

    async def scenario():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        target_check = 1 if phase == "precheck" else 2

        def delayed_check(op, *args, **kwargs):
            operations.append(op)
            response = request(op, *args, **kwargs)
            if len(operations) == target_check:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(2), "Test did not release its read-only request"
            return response

        async def action():
            effects.append("effect-once")
            return result

        monkeypatch.setattr(client, "request", delayed_check)
        task = asyncio.create_task(client.run_turn_step_async(lease, action))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel("test cancellation")
            with pytest.raises(asyncio.CancelledError) as cancelled:
                await task
            assert cancelled.value.args == ("test cancellation",)
            assert cancelled.value.result is (None if phase == "precheck" else result)
            assert any("inspect" in note.lower() for note in cancelled.value.__notes__)
        finally:
            release.set()

    asyncio.run(scenario())
    assert operations == ["turn-check"] * (1 if phase == "precheck" else 2)
    assert effects == ([] if phase == "precheck" else ["effect-once"])
    assert request("turn-check", {"lease": lease})["ok"]  # No automatic release or renewal.


def test_action_cancellation_propagates_same_exception_with_inspection_guidance(turn):
    client, lease, _, _, _ = turn
    effects, received = [], []

    async def scenario():
        started, never_finish = asyncio.Event(), asyncio.Event()

        async def action():
            effects.append("partial-effect")
            started.set()
            try:
                await never_finish.wait()
            except asyncio.CancelledError as error:
                received.append(error)
                raise

        task = asyncio.create_task(client.run_turn_step_async(lease, action))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel("stop after partial effect")
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await task
        assert cancelled.value is received[0]
        assert cancelled.value.result is None
        assert any("inspect" in note.lower() for note in cancelled.value.__notes__)

    asyncio.run(scenario())
    assert effects == ["partial-effect"]


def test_prestarted_task_is_rejected_and_remains_caller_owned(turn):
    client, lease, _, _, _ = turn
    effects = []

    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()

        async def already_running():
            effects.append("caller-started")
            started.set()
            try:
                await finish.wait()
            finally:
                effects.append("caller-cleanup")

        pending = asyncio.create_task(already_running())
        await started.wait()
        try:
            with pytest.raises(TurnInterrupted):
                await client.run_turn_step_async(lease, lambda: pending)
            assert not pending.done() and not pending.cancelled()
            assert effects == ["caller-started"]
        finally:
            finish.set()
            await pending

    asyncio.run(scenario())
    assert effects == ["caller-started", "caller-cleanup"]


@pytest.mark.parametrize("completed", [False, True])
def test_future_is_rejected_without_consumption_or_cancellation(turn, completed):
    client, lease, _, _, _ = turn

    async def scenario():
        future = asyncio.get_running_loop().create_future()
        if completed:
            future.set_result("caller-completed")
        with pytest.raises(TurnInterrupted):
            await client.run_turn_step_async(lease, lambda: future)
        assert not future.cancelled()
        assert future.done() is completed

    asyncio.run(scenario())


def test_started_native_coroutine_is_rejected_without_running_cleanup(turn):
    client, lease, _, _, _ = turn
    effects = []

    class Pause:
        def __await__(self):
            yield

    async def started_action():
        try:
            effects.append("caller-started")
            await Pause()
        finally:
            effects.append("caller-cleanup")

    pending = started_action()
    pending.send(None)
    try:
        with pytest.raises(TurnInterrupted):
            asyncio.run(client.run_turn_step_async(lease, lambda: pending))
        assert effects == ["caller-started"]
        assert inspect.getcoroutinestate(pending) == inspect.CORO_SUSPENDED
    finally:
        pending.close()
    assert effects == ["caller-started", "caller-cleanup"]


@pytest.mark.parametrize("nested", [False, True])
def test_custom_awaitable_is_not_run_closed_or_cancelled(turn, nested):
    client, lease, _, _, _ = turn
    calls = []

    class CallerOwned:
        def __await__(self):
            calls.append("must-not-await")
            yield

        def close(self):
            calls.append("must-not-close")

        def cancel(self):
            calls.append("must-not-cancel")

    pending = CallerOwned()

    async def outer():
        calls.append("outer-effect")
        return pending

    def factory():
        calls.append("factory-once")
        return outer() if nested else pending

    with pytest.raises(TurnInterrupted):
        asyncio.run(client.run_turn_step_async(lease, factory))
    assert calls == (["factory-once", "outer-effect"] if nested else ["factory-once"])


def test_nested_unstarted_coroutine_is_closed_without_recursive_execution(turn):
    client, lease, _, _, _ = turn
    effects, returned = [], []

    async def nested():
        effects.append("must-not-run")

    async def action():
        effects.append("outer-effect-once")
        pending = nested()
        returned.append(pending)
        return pending

    with pytest.raises(TurnInterrupted) as interrupted:
        asyncio.run(client.run_turn_step_async(lease, action))
    assert interrupted.value.result is None
    assert effects == ["outer-effect-once"]
    assert inspect.getcoroutinestate(returned[0]) == inspect.CORO_CLOSED
