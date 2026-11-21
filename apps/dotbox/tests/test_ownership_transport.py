"""Finite real stdio/mailbox exchanges; not SSH or cloud acceptance."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
import dotbox

from dotbox.client import ClientError
from dotbox.ownership_publisher import command_exchange, publish_once
from dotbox.ownership_source import atomic_json, exchange

VIEWER = "a" * 64
PROBE = {"stream_id": "b" * 64, "challenge": "c" * 64, "sequence": 1}
OBSERVATION = {"owner": "dot", "viewer_mode": "observe", "connection": "live"}


def answer(directory, event=None):
    deadline = time.monotonic() + 2
    while not (directory / "request.json").exists():
        assert time.monotonic() < deadline
        time.sleep(0.005)
    request = json.loads((directory / "request.json").read_text())
    atomic_json(directory / "response.json", {"request_id": request["request_id"],
                "event": {**request["probe"], **OBSERVATION, **(event or {})}})


def test_real_command_stdin_stdout_completes_probe_bound_mailbox(tmp_path):
    directory = tmp_path / "mailbox"
    directory.mkdir(mode=0o700)
    worker = threading.Thread(target=answer, args=(directory,))
    worker.start()
    # Child interpreters do not inherit pytest's sys.path. Use the exact
    # imported package location, whether source or an ordinary installed wheel.
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('dotbox.ownership_source',run_name='__main__')"
    result = command_exchange([sys.executable, "-c", bootstrap, str(Path(dotbox.__file__).parent.parent),
                              "--directory", str(directory), "--viewer-id", VIEWER], PROBE, timeout=2)
    worker.join(2)
    assert not worker.is_alive()
    assert result == {**PROBE, **OBSERVATION}
    assert (directory / "request.json").stat().st_mode & 0o777 == 0o600


def test_cached_reply_never_satisfies_a_new_source_probe(tmp_path):
    directory = tmp_path / "mailbox"
    directory.mkdir(mode=0o700)
    atomic_json(directory / "response.json", {"request_id": "old", "event": {**PROBE, **OBSERVATION}})
    with pytest.raises(TimeoutError):
        exchange(directory, VIEWER, PROBE, timeout=0.05)


def test_mismatched_probe_or_symlink_source_response_is_refused(tmp_path):
    directory = tmp_path / "mailbox"
    directory.mkdir(mode=0o700)
    worker = threading.Thread(target=answer, args=(directory, {"challenge": "d" * 64}))
    worker.start()
    with pytest.raises(ValueError, match="different probe"):
        exchange(directory, VIEWER, PROBE, timeout=2)
    worker.join(2)
    (directory / "response.json").unlink()
    (directory / "response.json").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(OSError):
        exchange(directory, VIEWER, PROBE, timeout=0.05)


@pytest.mark.parametrize("command", [[], "echo unsafe", [""], [42], ["a\0b"]])
def test_transport_never_shell_expands_a_command_string(command):
    with pytest.raises(ValueError):
        command_exchange(command, PROBE, timeout=0.1)


def test_source_command_failure_and_timeout_are_not_owner_grants():
    with pytest.raises(ClientError):
        command_exchange([sys.executable, "-c", "raise SystemExit(2)"], PROBE, timeout=1)
    with pytest.raises(subprocess.TimeoutExpired):
        command_exchange([sys.executable, "-c", "import time;time.sleep(2)"], PROBE, timeout=0.05)


def test_observation_exchange_is_completed_before_authenticated_ingest():
    events = []

    class Publisher:
        def request(self, op, params):
            events.append((op, params))
            if op == "bridge-challenge":
                return {"ok": True, "result": {**PROBE, "expires_in_ms": 3000}}
            assert op == "bridge-observe" and params == {**PROBE, **OBSERVATION}
            return {"ok": True, "result": {"owner": "dot"}}

    def source(probe, ttl):
        events.append(("source", probe))
        assert probe == PROBE and ttl == 3
        return {**probe, **OBSERVATION}

    assert publish_once(Publisher(), PROBE["stream_id"], source) == {"owner": "dot"}
    assert [x[0] for x in events] == ["bridge-challenge", "source", "bridge-observe"]


def test_timeout_cleans_up_source_descendants(tmp_path):
    marker = tmp_path / "late-effect"
    child = "import time,pathlib;time.sleep(0.25);pathlib.Path(" + repr(str(marker)) + ").write_text('bad')"
    parent = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c'," + repr(child) + "]);time.sleep(2)"
    with pytest.raises(subprocess.TimeoutExpired):
        command_exchange([sys.executable, "-c", parent], PROBE, timeout=0.05)
    time.sleep(0.3)
    assert not marker.exists()


def test_source_output_is_bounded_before_process_exit():
    code = "import sys,time;sys.stdout.write('x'*100000);sys.stdout.flush();time.sleep(2)"
    started = time.monotonic()
    with pytest.raises(ClientError, match="byte limit"):
        command_exchange([sys.executable, "-c", code], PROBE, timeout=1)
    assert time.monotonic() - started < 1


def test_fifo_mailbox_response_cannot_bypass_exchange_deadline(tmp_path):
    directory = tmp_path / "mailbox"
    directory.mkdir(mode=0o700)
    os.mkfifo(directory / "response.json", 0o600)
    started = time.monotonic()
    with pytest.raises(ClientError, match="private file"):
        exchange(directory, VIEWER, PROBE, timeout=0.05)
    assert time.monotonic() - started < 0.2
