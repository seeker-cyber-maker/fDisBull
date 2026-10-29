"""Automatic turn checkpoints and bounded external-agent story sessions."""
import json
import os
import selectors
import subprocess
import time

from .player import Player, public_observation


class LiveSession:
    def __init__(self, backend, max_actions=16):
        if type(max_actions) is not int or not 1 <= max_actions <= 256:
            raise ValueError("Invalid action limit")
        self.backend, self.player = backend, Player(backend)
        self.max_actions = max_actions
        self.started = False
        self.blocked = False

    def start(self):
        if self.started:
            return self.restore
        self.started = True
        try:
            result = self.backend.load("live")
        except (AttributeError, OSError, ValueError, EOFError) as exc:
            result = {"status": "incomplete", "complete": False, "error": str(exc)}
        if (not isinstance(result, dict) or result.get("status") not in ("missing", "restored")
                or result.get("complete") is not True):
            self.blocked = True
            result = {"status": "incomplete", "complete": False, "message": "Checkpoint could not be restored."}
        if not self.blocked:
            result = {"status": result["status"], "complete": True, "checkpoint": result.get("checkpoint", "live")}
        self.player.pending = None
        self.restore = result
        return result

    def observation(self):
        return public_observation(self.backend.observe())

    def run_turn(self, commands):
        if (not isinstance(commands, list) or len(commands) > self.max_actions
                or not all(isinstance(c, str) and len(c) <= 4096 for c in commands)):
            raise ValueError("Invalid or excessive turn commands")
        restore = self.start()
        result = {"restore": restore, "outcomes": [], "status": "complete", "checkpoint": {"status": "incomplete", "complete": False}}
        if self.blocked:
            result["status"] = "incomplete"
            return result
        try:
            for command in commands:
                outcome = self.player.execute_structured(command)
                result["outcomes"].append({"command": command, **outcome})
                if outcome["status"] == "incomplete":
                    result["status"] = "incomplete"
                    break
        except (OSError, ValueError, EOFError) as exc:
            result["status"] = "incomplete"
            result["error"] = "Turn interrupted: " + str(exc)
        finally:
            try:
                saved = self.backend.save("live")
                if (isinstance(saved, dict) and saved.get("status") == "saved"
                        and saved.get("complete") is True and isinstance(saved.get("checkpoint"), str)
                        and saved["checkpoint"]):
                    result["checkpoint"] = {"status": "saved", "complete": True, "checkpoint": saved["checkpoint"], "slot": "live"}
                else:
                    result["checkpoint"] = {"status": "incomplete", "complete": False, "message": "Checkpoint save failed."}
            except (AttributeError, OSError, ValueError, EOFError):
                result["checkpoint"] = {"status": "incomplete", "complete": False, "message": "Checkpoint save failed."}
        if result["checkpoint"]["status"] != "saved":
            result["status"] = "incomplete"
            self.blocked = True
        return result


class AgentProcess:
    """Persistent line protocol with a deadline even for an incomplete response."""
    def __init__(self, argv):
        if not argv:
            raise ValueError("Empty agent command")
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, shell=False, bufsize=0,
                                        start_new_session=os.name == 'posix')
        self.buffer = b""
        self.closed = False

    def request(self, payload, timeout):
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        if len(encoded) > 1024 * 1024:
            raise ValueError("Agent request too large")
        # A writer thread ensures even a non-reading child cannot block the deadline.
        import threading
        error = []
        def write():
            try:
                remaining = memoryview(encoded)
                while remaining:
                    count = self.process.stdin.write(remaining)
                    if not count:
                        raise OSError("Agent closed its input")
                    remaining = remaining[count:]
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                error.append(exc)
        deadline = time.monotonic() + timeout
        writer = threading.Thread(target=write, daemon=True)
        writer.start(); writer.join(max(0, deadline - time.monotonic()))
        if writer.is_alive():
            raise TimeoutError("Agent request timed out")
        if error:
            raise ValueError("Agent closed its input")
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("Agent response timed out")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise EOFError("Agent closed its output")
                self.buffer += chunk
                if len(self.buffer) > 1024 * 1024:
                    raise ValueError("Agent response too large")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def close(self, *, graceful=False):
        if self.closed:
            return
        self.closed = True
        try:
            if graceful and self.process.poll() is None:
                # A successful content service needs EOF to finalize native receipts.
                self.process.stdin.close()
                try: self.process.wait(timeout=3)
                except subprocess.TimeoutExpired: pass
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=1)
        finally:
            # A crashed worker can leave descendants holding its stdout pipe.
            # This group was created for this worker, never discovered by PID scan.
            if os.name == 'posix':
                import signal
                try: os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            self.process.stdin.close(); self.process.stdout.close()


def self_play(session, argv, max_turns=20, max_actions=16, wall_seconds=60, agent_timeout=10, emit=print):
    if (type(max_turns) is not int or not 1 <= max_turns <= 10000
            or type(max_actions) is not int or not 1 <= max_actions <= session.max_actions
            or not 0 < wall_seconds <= 86400 or not 0 < agent_timeout <= 3600):
        raise ValueError("Invalid self-play limits")
    start = time.monotonic()
    restore = session.start()
    transcript = {"restore": restore, "turns": [], "status": "incomplete"}
    if session.blocked:
        return transcript
    agent = AgentProcess(argv)
    try:
        last = []
        for index in range(max_turns):
            remaining = wall_seconds - (time.monotonic() - start)
            if remaining <= 0:
                transcript["status"] = "wall_limit"; break
            obs = session.observation()
            if obs is None:
                transcript["status"] = "incomplete_observation"; break
            remaining = wall_seconds - (time.monotonic() - start)
            if remaining <= 0:
                transcript["status"] = "wall_limit"; break
            response = agent.request({"turn": index, "observation": obs, "last_outcomes": last}, min(remaining, agent_timeout))
            if time.monotonic() - start >= wall_seconds:
                transcript["status"] = "wall_limit"; break
            if (not isinstance(response, dict) or not isinstance(response.get("commands"), list)
                    or len(response["commands"]) > max_actions
                    or not all(isinstance(c, str) and len(c) <= 4096 for c in response["commands"])
                    or not isinstance(response.get("narration"), str) or len(response["narration"]) > 65536
                    or type(response.get("done")) is not bool):
                raise ValueError("Invalid agent response")
            turn = session.run_turn(response["commands"])
            turn["narration"] = response["narration"]
            turn["done"] = response["done"]
            transcript["turns"].append(turn)
            emit(response["narration"])
            for outcome in turn["outcomes"]:
                emit("> " + outcome["command"] + "\n" + outcome["outcome"])
            last = turn["outcomes"]
            if turn["status"] == "incomplete":
                transcript["status"] = "checkpoint_or_turn_failure"; break
            if response["done"]:
                transcript["status"] = "agent_done"; break
        else:
            transcript["status"] = "turn_limit"
    except (OSError, ValueError, EOFError, TimeoutError) as exc:
        transcript["status"] = "agent_or_backend_error"
        transcript["error"] = str(exc)
    finally:
        agent.close()
    return transcript
