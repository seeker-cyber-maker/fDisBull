import base64
import hashlib
import json

import pytest

from dotbox import cli
from dotbox.backend import BackendUnavailable
from dotbox.client import Client, ClientError


def test_probe_options_reach_the_standalone_probe(tmp_path):
    output = tmp_path / "probe.json"
    assert cli.main(["probe", "--context", "local", "--label", "cli", "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["label"] == "cli" and report["context"]["requested"] == "local"
    assert report["takeover"]["owner"] == "unknown"
    assert output.stat().st_mode & 0o077 == 0


def test_unavailable_native_backend_is_a_clear_cli_error(tmp_path, monkeypatch, capsys):
    def unavailable(config):
        raise BackendUnavailable("Backend lacks cooperative input control")

    monkeypatch.setattr("dotbox.backend.DOSBoxBackend", unavailable)
    args = ["serve", "--directory", str(tmp_path / "session"), "--project", "game.fdb",
            "--game-dir", "game", "--executable", "dosbox"]
    assert cli.main(args) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False and "cooperative" in error["error"]
    assert not (tmp_path / "session/session.json").exists()


@pytest.mark.parametrize("window_scale", [None, 2, 3, 4, 5])
def test_serve_passes_only_explicit_window_scale_to_backend(tmp_path, monkeypatch, capsys, window_scale):
    configurations = []

    def capture_config(config):
        configurations.append(dict(config))
        raise BackendUnavailable("Stopped at tested native launch boundary")

    monkeypatch.setattr("dotbox.backend.DOSBoxBackend", capture_config)
    args = ["serve", "--directory", str(tmp_path / "session"), "--project", "game.fdb",
            "--program", "GAME.EXE", "--game-dir", "game", "--executable", "dosbox", "--image", "mz"]
    expected = {"project": "game.fdb", "program": "GAME.EXE", "game_dir": "game",
                "executable": "dosbox", "image": "mz"}
    if window_scale is not None:
        args.extend(["--window-scale", str(window_scale)])
        expected["window_scale"] = window_scale
    assert cli.main(args) == 1
    assert configurations == [expected]
    assert json.loads(capsys.readouterr().err)["error"] == "Stopped at tested native launch boundary"


@pytest.mark.parametrize("window_scale", ["1", "6", "true", "3.0", "large"])
def test_serve_rejects_invalid_window_scale_before_backend(tmp_path, monkeypatch, capsys, window_scale):
    monkeypatch.setattr("dotbox.backend.DOSBoxBackend",
                        lambda *_: pytest.fail("Invalid display scale reached the backend"))
    args = ["serve", "--directory", str(tmp_path / "session"), "--project", "game.fdb",
            "--game-dir", "game", "--executable", "dosbox", "--window-scale", window_scale]
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert "--window-scale" in capsys.readouterr().err
    assert not (tmp_path / "session").exists()


def test_client_rejects_nonobject_descriptor(tmp_path):
    descriptor = tmp_path / "session.json"
    descriptor.write_text("[]")
    descriptor.chmod(0o600)
    with pytest.raises(ClientError, match="descriptor"):
        Client(descriptor)


def test_frame_command_writes_only_verified_bytes_and_preserves_existing_file(tmp_path, monkeypatch, capsys):
    png = b"owned-test-image-bytes"

    class FrameClient:
        def __init__(self, descriptor):
            assert descriptor == "session.json"

        def request(self, op, params=None, *, lease=None):
            assert op == "frame" and lease is None
            return {"ok": True, "result": {"png_base64": base64.b64encode(png).decode(),
                                             "sha256": hashlib.sha256(png).hexdigest()}}

    monkeypatch.setattr(cli, "Client", FrameClient)
    destination = tmp_path / "frame.png"
    args = ["frame", "--session", "session.json", "--output", str(destination)]
    assert cli.main(args) == 0
    reply = json.loads(capsys.readouterr().out)
    assert "png_base64" not in reply["result"]
    assert destination.read_bytes() == png
    assert cli.main(args) == 1
    assert destination.read_bytes() == png


@pytest.mark.parametrize(("arguments", "operation", "params"), [
    (["harness-list"], "harness-list", {}),
    (["harness-info", "revision-id"], "harness-info", {"revision": "revision-id"}),
])
def test_harness_read_commands_need_no_lease(arguments, operation, params, monkeypatch, capsys):
    class ReadClient:
        def __init__(self, descriptor):
            assert descriptor == "session.json"

        def request(self, op, request_params=None, *, lease=None):
            assert (op, request_params, lease) == (operation, params, None)
            return {"ok": True, "result": {"stored": "revision-id"}}

    monkeypatch.setattr(cli, "Client", ReadClient)
    assert cli.main([*arguments, "--session", "session.json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == {"stored": "revision-id"}


@pytest.mark.parametrize("parent", [None, "previous-revision"])
def test_harness_save_sends_definition_and_observed_lease(tmp_path, parent, monkeypatch, capsys):
    definition = {"format": "fdisbull-macro-set-1", "name": "play", "macros": {}}
    source = tmp_path / "controls.json"
    source.write_text(json.dumps(definition))
    observed = {"instance_id": "observed-instance", "generation": 7}
    lease = tmp_path / "status.json"
    lease.write_text(json.dumps({"ok": True, "session": observed}))
    expected = {"definition": definition}
    if parent is not None:
        expected["parent"] = parent

    class SaveClient:
        def __init__(self, descriptor):
            assert descriptor == "session.json"

        def request(self, op, params=None, *, lease=None):
            assert op == "harness-save" and params == expected and lease == observed
            return {"ok": True, "result": {"revision": "new-revision"}}

    monkeypatch.setattr(cli, "Client", SaveClient)
    arguments = ["harness-save", "--definition", str(source), "--session", "session.json", "--lease", str(lease)]
    if parent is not None:
        arguments += ["--parent", parent]
    assert cli.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["result"]["revision"] == "new-revision"


@pytest.mark.parametrize("ok", [True, False])
def test_act_sends_pinned_revision_and_returns_failure_on_interruption(tmp_path, ok, monkeypatch, capsys):
    observed = {"instance_id": "observed-instance", "generation": 4}
    lease = tmp_path / "lease.json"
    lease.write_text(json.dumps(observed))
    response = {"ok": ok, "result": {"completed_steps": 1}}
    if not ok:
        response["error"] = {"code": "action_interrupted", "message": "Ownership changed."}

    class ActionClient:
        def __init__(self, descriptor):
            assert descriptor == "session.json"

        def request(self, op, params=None, *, lease=None):
            assert op == "act"
            assert params == {"revision": "pinned-revision", "name": "move_left"}
            assert lease == observed
            return response

    monkeypatch.setattr(cli, "Client", ActionClient)
    assert cli.main(["act", "pinned-revision", "move_left", "--session", "session.json",
                     "--lease", str(lease)]) == (0 if ok else 1)
    assert json.loads(capsys.readouterr().out) == response


@pytest.mark.parametrize("contents", [b"{", b"[]", b'{"value":NaN}', b" " * (48 * 1024 + 1)])
def test_invalid_harness_file_fails_before_client_access(tmp_path, contents, monkeypatch, capsys):
    source = tmp_path / "invalid.json"
    source.write_bytes(contents)
    monkeypatch.setattr(cli, "Client", lambda *_: pytest.fail("Invalid definition reached Client"))
    assert cli.main(["harness-save", "--definition", str(source), "--session", "unused.json",
                     "--lease", "unused-lease.json"]) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_harness_definition_accepts_the_documented_size_boundary(tmp_path):
    source = tmp_path / "boundary.json"
    source.write_bytes(b"{}" + b" " * (48 * 1024 - 2))
    assert cli.read_definition(source) == {}


def test_nonregular_harness_file_is_rejected_without_reading(tmp_path, monkeypatch, capsys):
    import os
    source = tmp_path / "definition-pipe"
    os.mkfifo(source)
    monkeypatch.setattr(cli, "Client", lambda *_: pytest.fail("Special file reached Client"))
    assert cli.main(["harness-save", "--definition", str(source), "--session", "unused.json",
                     "--lease", "unused-lease.json"]) == 1
    assert "regular JSON file" in json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize("arguments", [["harness-save", "--definition", "controls.json"],
                                       ["act", "revision", "move_left"]])
def test_harness_mutations_require_a_lease(arguments):
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args([*arguments, "--session", "session.json"])
    assert error.value.code == 2
