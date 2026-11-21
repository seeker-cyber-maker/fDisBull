"""Short-lived authenticated clients; never retry a game effect automatically."""

import asyncio
import inspect
import json
import os
from pathlib import Path
import re
import socket
import stat
import uuid
import time

from .service import BRIDGE_OPS, TURN_OPS, MAX_REQUEST, MAX_RESPONSE, MUTATIONS, PROTOCOL, encoded, receive_line


class ClientError(ValueError):
    pass


class TurnInterrupted(ClientError):
    """An effect may have completed; callers must inspect rather than replay."""

    def __init__(self, message, *, result=None):
        super().__init__(message)
        self.result = result


def private_file(path, *, limit=4096):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > limit:
            raise ClientError("Expected a small private file owned by this user.")
        return source.read(limit + 1)


class Client:
    def __init__(self, descriptor, *, timeout=10):
        self.descriptor = json.loads(private_file(descriptor))
        d = self.descriptor
        if (not isinstance(d, dict) or d.get("protocol") != PROTOCOL or d.get("host") != "127.0.0.1"
                or type(d.get("port")) is not int or not 1 <= d["port"] <= 65535
                or not isinstance(d.get("instance_id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", d["instance_id"])):
            raise ClientError("Invalid local session descriptor.")
        self.token = private_file(d["password_file"]).decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{64}", self.token):
            raise ClientError("Invalid session credential.")
        self.timeout = timeout

    def request(self, op, params=None, *, lease=None):
        request = {"protocol": PROTOCOL, "id": uuid.uuid4().hex, "token": self.token,
                   "op": op, "params": params or {}}
        if op in MUTATIONS:
            if lease is None:
                raise ClientError("Mutating requests require a previously observed session lease.")
            request.update(instance_id=lease["instance_id"], expected_generation=lease["generation"])
        elif op in TURN_OPS | BRIDGE_OPS | {"status", "coordinator-close"}:
            request["instance_id"] = self.descriptor["instance_id"]
        payload = encoded(request)
        if len(payload) > MAX_REQUEST:
            raise ClientError("Request exceeds byte limit.")
        with socket.create_connection(("127.0.0.1", self.descriptor["port"]), timeout=self.timeout) as connection:
            connection.settimeout(self.timeout)
            connection.sendall(payload)
            response = receive_line(connection, MAX_RESPONSE)
        if (not isinstance(response, dict) or response.get("protocol") != PROTOCOL
                or response.get("id") != request["id"] or type(response.get("ok")) is not bool):
            raise ClientError("Invalid response; request outcome is unknown. Do not replay automatically.")
        return response

    def wait_for_turn(self, controller_id, *, timeout=10, interval=0.1):
        """Wait locally; never block the sole service listener receiving updates."""
        if not 0 <= timeout <= 3600 or not 0.01 <= interval <= 5:
            raise ValueError("Invalid turn wait duration")
        deadline = time.monotonic() + timeout
        while True:
            reply = self.request("turn-claim", {"controller_id": controller_id})
            if reply["ok"]:
                return reply["result"]
            if reply["error"]["code"] != "turn_unavailable" or time.monotonic() >= deadline:
                raise ClientError(reply["error"]["message"])
            time.sleep(min(interval, max(0, deadline - time.monotonic())))

    def run_turn_step(self, lease, action):
        """Fence one cooperating desktop action; never retry an unknown effect.

        The outer harness remains responsible for capture and in-flight input.
        This is a decision fence, not an atomic lock around an external tool.
        Actions must return completed synchronous results, not awaitables.
        """
        before = self.request("turn-check", {"lease": lease})
        if not before["ok"]:
            raise TurnInterrupted(before["error"]["message"])
        try:
            result = action()
        except Exception as error:
            raise TurnInterrupted("Desktop action failed; effects are unknown, inspect before continuing") from error
        if inspect.isawaitable(result):
            message = ("Desktop callback returned an awaitable; a completed synchronous result is required. "
                       "Effects may have occurred; inspect before continuing")
            # Only an unstarted native coroutine can be closed without running
            # its body/finalizers. Other awaitables remain entirely caller-owned.
            if inspect.iscoroutine(result) and inspect.getcoroutinestate(result) == inspect.CORO_CREATED:
                try:
                    result.close()
                except Exception as error:
                    raise TurnInterrupted(message) from error
            raise TurnInterrupted(message)
        try:
            after = self.request("turn-check", {"lease": lease})
        except (OSError, ValueError) as error:
            raise TurnInterrupted("Action outcome requires inspection; coordination check failed", result=result) from error
        if not after["ok"]:
            raise TurnInterrupted("Ownership changed during the action; inspect before continuing", result=result)
        return result

    async def run_turn_step_async(self, lease, action):
        """Await one cooperating action between checks of the same turn receipt.

        The zero-argument callback must return a fresh, unstarted native
        coroutine. Run input and its observation in that coroutine on their
        supported executor. Tasks and arbitrary awaitables cannot establish
        when their effects started and are not accepted or cancelled here.
        Await steps sequentially; sharing a controller lease is not an action
        mutex for concurrent callers.

        Only read-only coordination requests run in worker threads, bounded by
        this client's socket timeout. Cancellation does not stop such a thread;
        it propagates with an inspection note and a ``result`` attribute holding
        the completed outcome, if any. No action is retried, no receipt renewed,
        and the outer harness still owns capture and input already in flight.
        """
        # Valid receipts have only scalar fields. Capture before the first await
        # so a caller cannot replace the postcheck receipt during the action.
        receipt = dict(lease)
        phase = "before action"
        result = None
        try:
            try:
                before = await asyncio.to_thread(self.request, "turn-check", {"lease": receipt})
            except (OSError, ValueError) as error:
                raise TurnInterrupted("No action was started; coordination check failed") from error
            if not before["ok"]:
                raise TurnInterrupted(before["error"]["message"])

            phase = "during action"
            try:
                pending = action()
            except Exception as error:
                raise TurnInterrupted("Desktop action failed; effects are unknown, inspect before continuing") from error
            if not (inspect.iscoroutine(pending)
                    and inspect.getcoroutinestate(pending) == inspect.CORO_CREATED):
                raise TurnInterrupted(
                    "Desktop callback must return a fresh unstarted native coroutine; "
                    "effects may have occurred, inspect before continuing")
            try:
                result = await pending
            except Exception as error:
                raise TurnInterrupted("Desktop action failed; effects are unknown, inspect before continuing") from error
            if inspect.isawaitable(result):
                message = ("Desktop action returned another awaitable; a completed result is required. "
                           "Effects may have occurred; inspect before continuing")
                if inspect.iscoroutine(result) and inspect.getcoroutinestate(result) == inspect.CORO_CREATED:
                    try:
                        result.close()
                    except Exception as error:
                        raise TurnInterrupted(message) from error
                raise TurnInterrupted(message)

            phase = "after action"
            try:
                after = await asyncio.to_thread(self.request, "turn-check", {"lease": receipt})
            except (OSError, ValueError) as error:
                raise TurnInterrupted("Action outcome requires inspection; coordination check failed", result=result) from error
            if not after["ok"]:
                raise TurnInterrupted("Ownership changed during the action; inspect before continuing", result=result)
            return result
        except asyncio.CancelledError as error:
            error.result = result if phase == "after action" else None
            error.add_note(
                f"DotBox turn cancelled {phase}; inspect current state before continuing. "
                "Effects are not replayed or rolled back. A pending read-only coordination "
                "request may finish within the client's socket timeout.")
            raise
