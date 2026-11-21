"""One native owner thread, reconnectable clients, explicit ownership leases."""

import json
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
import re
import socket
import stat
import threading
import time
import uuid

PROTOCOL = "dotbox-1"
MAX_REQUEST = 65536
MAX_RESPONSE = 12 * 1024 * 1024
MUTATIONS = {"control", "play", "pause", "key", "type", "click", "close", "harness-save", "act"}
READS = {"status", "frame", "harness-list", "harness-info"}
BRIDGE_OPS = {"bridge-open", "bridge-challenge", "bridge-observe", "bridge-invalidate"}
TURN_OPS = {"turn-claim", "turn-check", "turn-release"}


class ProtocolError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encoded(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode() + b"\n"


def receive_line(connection, limit):
    data = bytearray()
    timeout = connection.gettimeout()
    deadline = time.monotonic() + (timeout if timeout is not None else 5)
    while b"\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Message deadline expired.")
        connection.settimeout(remaining)
        chunk = connection.recv(min(4096, limit + 1 - len(data)))
        if not chunk:
            raise ProtocolError("incomplete_request", "Connection ended before a complete message.")
        data.extend(chunk)
        if len(data) > limit:
            raise ProtocolError("message_too_large", "Message exceeds the byte limit.")
    if data.find(b"\n") != len(data) - 1:
        raise ProtocolError("multiple_messages", "Send one message per connection.")
    try:
        return json.loads(data)
    except RecursionError as error:
        raise ProtocolError("invalid_json", "Message nesting exceeds the parser limit.") from error


def private_directory(path):
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise ValueError("Session directory must not be a symlink.")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Choose an owned session directory with permissions 0700.")
    return path


def authorized(request, credential):
    if credential is None:
        return False
    token = request.get("token") if isinstance(request, dict) else None
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{64}", token) is None:
        return False
    try:
        return credential.check(token)
    except (TypeError, ValueError):
        return False


@contextmanager
def session_lock(directory):
    """Acquire ownership before opening a project or launching another guest."""
    import fcntl
    fd = os.open(directory / "owner.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Expected a private owner lock.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another service already owns this session directory.") from error
        yield
    finally:
        # Keep the empty lock inode: unlinking it could allow a new owner to
        # lock a replacement while another process still holds the old inode.
        os.close(fd)


class PlayService:
    """Create and use backend/SQLite objects only inside run()'s owner thread.

    Default input passes through the outer desktop harness. Direct RPC input
    is disabled there. Explicit native transfers require manual_control=True;
    they do not claim to observe the outer WebRTC owner.
    A socket disconnect never ends the game. The owner stops on an explicit
    close, a stop request, or an unrecoverable backend failure.
    """

    descriptor_kind = None

    def __init__(self, backend_factory, directory, *, manual_control=False,
                 client_timeout=1.0, credential_factory=None, ownership_viewer=None):
        if type(manual_control) is not bool:
            raise ValueError("manual_control must be boolean")
        if not 0.05 <= client_timeout <= 10:
            raise ValueError("client_timeout must be between 0.05 and 10 seconds")
        self.backend_factory = backend_factory
        self.directory = Path(directory)
        self.manual_control = manual_control
        self.client_timeout = client_timeout
        self.credential_factory = credential_factory
        self.instance_id = uuid.uuid4().hex
        self.stop_requested = threading.Event()
        self.owner = "unclaimed"
        self.generation = None
        self.backend = None
        self.failure = None
        self.ownership = None
        self.publisher_credential = None
        self._bridge_native_identity = None
        if ownership_viewer is not None:
            if manual_control:
                raise ValueError("The ownership bridge requires desktop-harness mode")
            from .ownership import OwnershipState
            self.ownership = OwnershipState(ownership_viewer)

    def request_stop(self):
        self.stop_requested.set()

    def snapshot(self):
        status = self.backend.status()
        control = status["native_control"]
        generation = control["generation"]
        if type(generation) is not int or generation < 0 or control["owner"] not in ("agent", "host"):
            raise RuntimeError("Backend returned an invalid ownership acknowledgement.")
        if self.generation is not None and generation != self.generation:
            self.owner = "unclaimed"
        self.generation = generation
        expected = {"agent": "agent", "human": "host", "harness": "host"}.get(self.owner)
        if expected is not None and control["owner"] != expected:
            self.owner = "unclaimed"
        if self.ownership is not None:
            identity = (status["run_id"], status.get("native_session_id"), generation, control["owner"])
            if self._bridge_native_identity is not None and identity != self._bridge_native_identity:
                stream = self.ownership.status()["stream_id"]
                if stream is not None:
                    self.ownership.invalidate(stream)
            self._bridge_native_identity = identity
        return {
            "instance_id": self.instance_id,
            "run_id": status["run_id"],
            "native_session_id": status.get("native_session_id"),
            "state": status["state"],
            "stop_reason": status.get("stop_reason"),
            "owner": self.owner,
            "generation": generation,
            "native_owner": control["owner"],
            "control_source": ("desktop-input-path" if self.owner == "harness" else
                               "manual" if self.owner in ("agent", "human") else "unavailable"),
            "platform_takeover": (self.ownership.status() if self.ownership is not None else
                                  {"owner": "unknown", "source": "unavailable"}),
            "manual_control_enabled": self.manual_control,
        }

    def _dispatch(self, request, credential):
        if not authorized(request, credential):
            raise ProtocolError("unauthorized", "Authentication required.")
        if set(request) - {"protocol", "id", "token", "op", "params", "instance_id", "expected_generation"}:
            raise ProtocolError("invalid_request", "Unknown request fields.")
        if request.get("protocol") != PROTOCOL:
            raise ProtocolError("protocol_mismatch", "Unsupported protocol.")
        op, params = request.get("op"), request.get("params", {})
        if not isinstance(op, str) or not isinstance(params, dict):
            raise ProtocolError("invalid_request", "Operation and object params are required.")
        if op not in MUTATIONS | READS | TURN_OPS:
            raise ProtocolError("unknown_operation", "Unknown operation.")
        current = self.snapshot()
        if op in TURN_OPS:
            if request.get("instance_id") != self.instance_id:
                raise ProtocolError("stale_instance", "Read this service's current instance before acting.")
            if self.ownership is None:
                raise ProtocolError("bridge_unavailable", "No ownership publisher is configured.")
            if current["owner"] != "harness" or current["native_owner"] != "host":
                raise ProtocolError("turn_unavailable", "The native desktop-harness boundary changed; inspect the session.")
            try:
                if op == "turn-claim" and set(params) == {"controller_id"}:
                    return self.ownership.claim(params["controller_id"])
                if op == "turn-check" and set(params) == {"lease"}:
                    return self.ownership.check(params["lease"])
                if op == "turn-release" and set(params) == {"lease"}:
                    return self.ownership.release(params["lease"])
                raise ValueError("Invalid turn parameters")
            except ValueError as error:
                raise ProtocolError("turn_unavailable", str(error)) from error
        if op in MUTATIONS:
            if request.get("instance_id") != self.instance_id:
                raise ProtocolError("stale_instance", "Read this service's current instance before acting.")
            expected = request.get("expected_generation")
            if type(expected) is not int or expected != self.generation:
                raise ProtocolError("stale_generation", "Ownership changed; observe again before acting.")
        if op in {"status", "frame", "harness-list", "play", "pause", "close"} and params:
            raise ProtocolError("invalid_params", "This operation accepts no params.")
        if op == "status":
            return current
        if op == "frame":
            return self.backend.frame()
        if op == "harness-list":
            return self.backend.harness_list()
        if op == "harness-info":
            return self.backend.harness_info(params)
        if op == "harness-save":
            return self.backend.harness_save(params)
        if op == "close":
            self.stop_requested.set()
            return {"status": "closing"}
        if not self.manual_control and op in {"play", "pause", "key", "type", "click", "act"}:
            raise ProtocolError("harness_controls_input", "Use the desktop harness input path; direct agent input/play/pause is disabled in harness-controlled mode.")
        if op == "pause":
            return self.backend.pause()
        if op == "control":
            if set(params) - {"owner", "resume"} or params.get("owner") not in ("agent", "human"):
                raise ProtocolError("invalid_params", "Choose owner agent or human.")
            resume = params.get("resume", False)
            if type(resume) is not bool:
                raise ProtocolError("invalid_params", "resume must be boolean.")
            if not self.manual_control:
                raise ProtocolError("takeover_unavailable", "Native handoff requires --manual-control; the outer desktop harness owns its own takeover flow.")
            native_owner = "host" if params["owner"] == "human" else "agent"
            previous = self.generation
            result = self.backend.transfer(native_owner, previous)
            if result.get("owner") != native_owner or result.get("generation") != previous + 1:
                self.owner = "unclaimed"
                raise RuntimeError("Backend did not acknowledge the requested ownership transfer.")
            self.owner, self.generation = params["owner"], result["generation"]
            after = self.snapshot()
            if (after["owner"] != params["owner"] or after["generation"] != previous + 1
                    or after["native_owner"] != native_owner):
                raise ProtocolError("ownership_conflict", "Ownership changed during handoff; observe again.")
            reason = after.get("stop_reason") or {}
            kind = reason.get("kind") if isinstance(reason, dict) else reason
            # A breakpoint/exit winning the race must remain visible. Explicit
            # play can continue later; a handoff must not silently erase it.
            if resume and after["state"] == "stopped" and kind in ("pause", "startup"):
                result = {**result, "execution": self.backend.resume_after_handoff(native_owner, self.generation)}
            return result
        if self.owner == "unclaimed":
            raise ProtocolError("ownership_unclaimed", "Establish ownership before playing.")
        if op == "play":
            return self.backend.play()
        if self.owner != "agent":
            raise ProtocolError("human_has_control", "Agent input is disabled during human control.")
        return getattr(self.backend, op)(params, self.generation)

    def _bridge_dispatch(self, request):
        # The publisher capability cannot close, pause or inject game input.
        if self.ownership is None or not authorized(request, self.publisher_credential):
            raise ProtocolError("unauthorized", "Publisher authentication required.")
        if (set(request) - {"protocol", "id", "token", "op", "params", "instance_id"}
                or request.get("protocol") != PROTOCOL):
            raise ProtocolError("invalid_request", "Invalid publisher request.")
        if request.get("instance_id") != self.instance_id:
            raise ProtocolError("stale_instance", "Publisher belongs to another service instance.")
        params = request.get("params", {})
        if not isinstance(params, dict):
            raise ProtocolError("invalid_params", "Object params are required.")
        try:
            op = request["op"]
            if op == "bridge-open" and set(params) == {"viewer_id"}:
                return self.ownership.open(params["viewer_id"])
            if op == "bridge-challenge" and set(params) == {"stream_id"}:
                return self.ownership.challenge(params["stream_id"])
            if op == "bridge-observe":
                return self.ownership.observe(params)
            if op == "bridge-invalidate" and set(params) == {"stream_id"}:
                return self.ownership.invalidate(params["stream_id"])
            raise ValueError("Invalid publisher parameters")
        except ValueError as error:
            # Malformed/reordered evidence from the current authenticated stream
            # is a gap, not permission to retain its last Dot grant.
            current_stream = self.ownership.status()["stream_id"]
            if (request.get("op") == "bridge-observe" and current_stream is not None
                    and params.get("stream_id") == current_stream):
                self.ownership.invalidate(current_stream)
            raise ProtocolError("ownership_rejected", str(error)) from error

    def handle(self, request, credential):
        from .harness import ActionInterrupted
        ident = request.get("id") if isinstance(request, dict) else None
        # Do not echo arbitrary client objects (which may contain credentials).
        if not isinstance(ident, (str, int)) or isinstance(ident, bool):
            ident = None
        reply = {"protocol": PROTOCOL, "id": ident}
        try:
            publisher = (isinstance(request, dict) and isinstance(request.get("op"), str)
                         and request["op"] in BRIDGE_OPS)
            result = self._bridge_dispatch(request) if publisher else self._dispatch(request, credential)
            reply.update(ok=True, result=result)
        except ProtocolError as error:
            reply.update(ok=False, error={"code": error.code, "message": str(error)})
        except ActionInterrupted as error:
            reply.update(ok=False, error={"code": "action_interrupted", "message": str(error),
                                          **error.progress})
        except Exception as error:
            reply.update(ok=False, error={"code": "backend_error", "message": str(error)[:1000],
                                         "effects": "not replayed; inspect current state"})
            try:
                self.snapshot()
            except Exception:
                self.owner = "unavailable"
                self.stop_requested.set()
        if authorized(request, credential):
            try:
                reply["session"] = self.snapshot()
            except Exception:
                reply["session"] = {"instance_id": self.instance_id, "owner": "unavailable"}
                self.stop_requested.set()
        return reply

    def run(self, *, on_ready=None):
        directory = private_directory(self.directory)
        with session_lock(directory):
            self._run_owned(directory, on_ready=on_ready)

    def _start_harness_input(self):
        """Admit ordinary desktop input without pretending to read its owner."""
        initial = self.snapshot()
        previous = initial["generation"]
        result = self.backend.transfer("host", previous)
        if result != {"owner": "host", "generation": previous + 1}:
            raise RuntimeError("Backend did not acknowledge desktop input ownership")
        self.owner, self.generation = "harness", result["generation"]
        after = self.snapshot()
        if after["owner"] != "harness" or after["native_owner"] != "host":
            raise RuntimeError("Desktop input ownership changed during startup")
        reason = after.get("stop_reason") or {}
        kind = reason.get("kind") if isinstance(reason, dict) else reason
        if after["state"] == "stopped" and kind in ("startup", "pause"):
            self.backend.resume_after_handoff("host", self.generation)

    def _run_owned(self, directory, *, on_ready=None):
        if self.credential_factory is None:
            from .local_auth import LocalCredential
            self.credential_factory = lambda: LocalCredential("dotbox-session-")
        descriptor_path = directory / "session.json"
        if descriptor_path.exists() or descriptor_path.is_symlink():
            raise RuntimeError("Session descriptor already exists; inspect its owner before starting another guest.")
        published = False
        try:
            self.backend = self.backend_factory()
            if not self.manual_control:
                self._start_harness_input()
            initial = self.snapshot()
            with ExitStack() as stack:
                credential = stack.enter_context(self.credential_factory())
                if self.ownership is not None:
                    from .local_auth import LocalCredential
                    self.publisher_credential = stack.enter_context(LocalCredential("dotbox-owner-publisher-"))
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                    listener.bind(("127.0.0.1", 0))
                    listener.listen(8)
                    listener.settimeout(0.2)
                    descriptor = {"protocol": PROTOCOL, "host": "127.0.0.1", "port": listener.getsockname()[1],
                                  "instance_id": self.instance_id, "password_file": str(credential.path)}
                    if self.descriptor_kind is not None:
                        descriptor["kind"] = self.descriptor_kind
                    fd = os.open(descriptor_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    published = True
                    with os.fdopen(fd, "wb") as output:
                        output.write(encoded(descriptor))
                        output.flush()
                        os.fsync(output.fileno())
                    publisher_path = directory / "ownership-publisher.json"
                    if self.ownership is not None:
                        publisher_descriptor = {**descriptor, "role": "ownership-publisher",
                                                "password_file": str(self.publisher_credential.path)}
                        publisher_fd = os.open(publisher_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(publisher_fd, "wb") as output:
                            output.write(encoded(publisher_descriptor))
                    if on_ready is not None:
                        on_ready({"descriptor": str(descriptor_path), "session": initial})
                    while not self.stop_requested.is_set():
                        try:
                            connection, _ = listener.accept()
                        except socket.timeout:
                            continue
                        with connection:
                            connection.settimeout(self.client_timeout)
                            try:
                                request = receive_line(connection, MAX_REQUEST)
                                response = encoded(self.handle(request, credential))
                                if len(response) > MAX_RESPONSE:
                                    raise ProtocolError("response_too_large", "Response exceeds byte limit.")
                                connection.sendall(response)
                            except (ValueError, UnicodeError, OSError, ProtocolError):
                                # An incomplete/departed client never owns the
                                # guest lifetime, nor causes an effect replay.
                                continue
        finally:
            try:
                if self.backend is not None:
                    self.backend.close()
            finally:
                if published:
                    if self.ownership is not None:
                        try:
                            publisher_path = directory / "ownership-publisher.json"
                            if json.loads(publisher_path.read_text()).get("instance_id") == self.instance_id:
                                publisher_path.unlink()
                        except (OSError, ValueError):
                            pass
                    try:
                        if json.loads(descriptor_path.read_text()).get("instance_id") == self.instance_id:
                            descriptor_path.unlink()
                    except (OSError, ValueError):
                        pass
