"""Boundary checks for private macOS arena builds."""
import pytest

from fdisbull.shadowrun_macos import build_macos_assisted_arena


def test_macos_builder_rejects_unknown_preset_before_reading_inputs(tmp_path):
    with pytest.raises(ValueError, match='preset'):
        build_macos_assisted_arena(tmp_path/'missing', rom_path=tmp_path/'rom',
                                  capture=tmp_path/'capture', output=tmp_path/'app', preset='invented')
    assert not (tmp_path/'app').exists()


def test_macos_builder_rejects_git_output_and_symlink_manifest(tmp_path):
    checkout=tmp_path/'checkout';checkout.mkdir();(checkout/'.git').mkdir()
    with pytest.raises(ValueError, match='outside Git'):
        build_macos_assisted_arena(tmp_path/'missing', rom_path=tmp_path/'rom',
                                  capture=tmp_path/'capture', output=checkout/'app')
    source=tmp_path/'real.json';source.write_text('{}')
    selected=tmp_path/'manifest.json';selected.symlink_to(source)
    with pytest.raises(ValueError, match='manifest'):
        build_macos_assisted_arena(selected, rom_path=tmp_path/'rom',
                                  capture=tmp_path/'capture', output=tmp_path/'private')
    assert not (tmp_path/'private').exists()
