"""Optional full-service acceptance against an actual owned DOSBox-X process."""

import base64
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import threading
import time
import struct

import pytest

from dotbox.backend import FDisBullBackend
from dotbox.client import Client
from dotbox.service import PlayService


def test_real_game_survives_clients_and_native_ownership_changes(tmp_path):
    executable = os.environ.get("DOTBOX_DOSBOX_EXECUTABLE")
    if not executable:
        pytest.skip("DOTBOX_DOSBOX_EXECUTABLE required for full native play-service acceptance")
    Image = pytest.importorskip("PIL.Image")
    source = Path(__file__).resolve().parents[1] / "examples/input_playground.py"
    spec = importlib.util.spec_from_file_location("dotbox_playground_fixture", source)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    program = game_dir / "PLAY.COM"
    program.write_bytes(fixture.program())
    backend_objects, native_processes, failures = [], [], []

    def backend_factory():
        backend = FDisBullBackend({"project": tmp_path / "play.fdb", "program": program,
                                  "game_dir": game_dir, "executable": executable, "image": "com"})
        backend_objects.append(backend)
        native_processes.append(backend._session.rpc.process)
        return backend

    service = PlayService(backend_factory, tmp_path / "session", manual_control=True)
    ready = threading.Event()

    def serve():
        try:
            service.run(on_ready=lambda _: ready.set())
        except BaseException as error:
            failures.append(error)
            ready.set()

    worker = threading.Thread(target=serve)
    worker.start()
    descriptor = tmp_path / "session/session.json"

    def square(client, expected_x):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            reply = client.request("frame")
            if reply["ok"]:
                image = Image.open(BytesIO(base64.b64decode(reply["result"]["png_base64"]))).convert("RGB")
                pixels = image.load()
                positions = [(x, y) for y in range(image.height) for x in range(image.width)
                             if pixels[x, y][1] > 200 and pixels[x, y][0] < 120 and pixels[x, y][2] < 120]
                if positions:
                    left = min(x for x, _ in positions)
                    top = min(y for _, y in positions)
                    if (left, top) == (expected_x, 100):
                        return reply["session"]
            time.sleep(0.02)
        raise AssertionError("Original game did not reach the expected visible position")

    try:
        assert ready.wait(10) and not failures, failures
        first = Client(descriptor)
        initial = first.request("status")["result"]
        agent = first.request("control", {"owner": "agent", "resume": True}, lease=initial)
        assert agent["ok"] and agent["session"]["state"] == "running"
        square(first, 160)
        assert first.request("key", {"key": "right"}, lease=agent["session"])["ok"]
        square(first, 168)
        another_client = Client(descriptor)
        current = another_client.request("status")["result"]
        assert current["run_id"] == initial["run_id"] and current["instance_id"] == initial["instance_id"]
        human = another_client.request("control", {"owner": "human"}, lease=current)
        assert human["ok"] and human["session"]["state"] == "running"
        assert first.request("key", {"key": "right"}, lease=agent["session"])["error"]["code"] == "stale_generation"
        assert another_client.request("key", {"key": "right"}, lease=human["session"])["error"]["code"] == "human_has_control"
        returned = another_client.request("control", {"owner": "agent"}, lease=human["session"])
        assert returned["ok"]
        assert first.request("key", {"key": "left"}, lease=returned["session"])["ok"]
        last = square(first, 160)
        assert last["run_id"] == initial["run_id"]
        assert another_client.request("close", lease=last)["ok"]
    finally:
        service.request_stop()
        worker.join(10)
    assert not worker.is_alive() and not failures, failures
    assert not descriptor.exists()
    assert native_processes and all(process.poll() is not None for process in native_processes)


def test_default_native_desktop_path_blocks_direct_agent_input(tmp_path):
    executable = os.environ.get("DOTBOX_DOSBOX_EXECUTABLE")
    if not executable:
        pytest.skip("DOTBOX_DOSBOX_EXECUTABLE required for native harness-input acceptance")
    from dotbox.backend import DOSBoxBackend
    program = tmp_path / "INPUT.COM"
    program.write_bytes(bytes.fromhex("b81300cd10ebfe"))
    backends, errors = [], []
    ready = threading.Event()

    def factory():
        backend = DOSBoxBackend({"project": tmp_path / "controls.db", "program": program,
                                 "game_dir": tmp_path, "executable": executable})
        backends.append(backend)
        return backend

    service = PlayService(factory, tmp_path / "session")

    def serve():
        try:
            service.run(on_ready=lambda _: ready.set())
        except BaseException as error:
            errors.append(error)
            ready.set()

    worker = threading.Thread(target=serve)
    worker.start()
    try:
        assert ready.wait(10) and not errors, errors
        client = Client(tmp_path / "session/session.json")
        lease = client.request("status")["result"]
        assert lease["owner"] == "harness" and lease["native_owner"] == "host"
        assert lease["state"] == "running"
        assert lease["platform_takeover"]["owner"] == "unknown"
        assert client.request("key", {"key": "right"}, lease=lease)["error"]["code"] == "harness_controls_input"
        assert client.request("control", {"owner": "agent"}, lease=lease)["error"]["code"] == "takeover_unavailable"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            frame = client.request("frame")
            if frame["ok"] and frame["result"]["width"] == 320:
                assert frame["result"]["height"] == 200
                break
            time.sleep(0.02)
        else:
            raise AssertionError("No original graphics frame in desktop-input mode")
        assert client.request("close", lease=lease)["ok"]
    finally:
        service.request_stop()
        worker.join(10)
    assert not worker.is_alive() and not errors, errors
    assert not (tmp_path / "session/session.json").exists()
    assert backends[0]._session.rpc.process.poll() is not None


def test_original_mz_entry_and_relocation_with_standalone_runtime(tmp_path):
    executable = os.environ.get("DOTBOX_DOSBOX_EXECUTABLE")
    if not executable:
        pytest.skip("DOTBOX_DOSBOX_EXECUTABLE required for original MZ acceptance")
    from dotbox.native_session import NativeSession
    # Authored MZ: VGA initialization, infinite loop, one unused relocated word.
    code = bytes.fromhex("b81300cd10ebfe0000")
    header = struct.pack("<14H", 0x5A4D, 32 + len(code), 1, 1, 2,
                         16, 0xFFFF, 0, 256, 0, 0, 0, 28, 0)
    program = tmp_path / "TEST.EXE"
    program.write_bytes(header + struct.pack("<HH", 7, 0) + code)
    session = NativeSession(executable, tmp_path, program, window=False)
    try:
        assert session.metadata["image_format"] == "MZ"
        assert session.metadata["entry_bytes_verified"] == len(code)
        assert session.call("session.status")["state"] == "stopped"
        session.call("execution.continue")
    finally:
        session.close()
    assert session.close_receipt["closed"] is True
    assert session.rpc.process.poll() == 0
