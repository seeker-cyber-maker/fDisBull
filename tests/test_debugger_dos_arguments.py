"""Host checks for safe argv parsing at the DOSBox-X launch boundary."""
from __future__ import annotations

import pytest

from fdisbull.debugger import _parse_dosbox_arguments
from fdisbull.project import Project
from support.dos_process_fixture import mz_exit


def test_dosbox_arguments_default_to_no_arguments():
    assert _parse_dosbox_arguments(None) == []


def test_dosbox_arguments_share_the_126_byte_dos_tail_limit():
    assert _parse_dosbox_arguments("x" * 126) == ["x" * 126]
    with pytest.raises(ValueError, match="126-byte"):
        _parse_dosbox_arguments("x" * 127)


def test_dosbox_arguments_are_parsed_without_shell_expansion():
    assert _parse_dosbox_arguments('-warp 1 1 -config "D:\\DOOM CFG\\BASE.CFG"') == [
        "-warp", "1", "1", "-config", "D:\\DOOM CFG\\BASE.CFG"
    ]


@pytest.mark.parametrize("argument_string", [
    "-warp 1 1 -config DEFAULT.CFG",
    None,
])
def test_project_debugger_passes_dosbox_argument_vector(tmp_path, monkeypatch, argument_string):
    game = tmp_path / "game"
    game.mkdir()
    executable = game / "DOOM.EXE"
    executable.write_bytes(mz_exit()[0])
    captured = {}

    def fake_debug_session(project, binary, game_dir, **options):
        captured.update(options)
        return object()

    monkeypatch.setattr("fdisbull.debugger.DebugSession", fake_debug_session)
    with Project.create(tmp_path / "project.fdb", executable, image="mz") as project:
        if argument_string is None:
            project.debugger("/bin/true", game, backend="dosbox")
            expected = []
        else:
            project.debugger("/bin/true", game, backend="dosbox",
                             dos_arguments=argument_string)
            expected = ["-warp", "1", "1", "-config", "DEFAULT.CFG"]
    assert captured["dos_arguments"] == expected


@pytest.mark.parametrize("value", ["-config 'unterminated", "-warp 1\n1", "-warp 1\x001",
                                    "-warp " + "x" * 130, "-name 😀"])
def test_dosbox_arguments_reject_malformed_or_multiline_input(value):
    with pytest.raises(ValueError, match="dos_arguments"):
        _parse_dosbox_arguments(value)
