"""Standalone input/auth helpers retain bounded validation without fDisBull."""

import stat

import pytest

from dotbox.keyboard_input import validate_keyboard
from dotbox.local_auth import LocalCredential


@pytest.mark.parametrize("key", ["left", "f12", "enter", "esc", "'", "\\", "`", "kp5"])
def test_supported_physical_keys_remain_available(key):
    validate_keyboard(key=key)


@pytest.mark.parametrize("params", [
    {"key": "LEFT"}, {"key": "f13"}, {"key": None},
    {"key": "left", "hold_ms": True}, {"key": "left", "gap_ms": 1001},
    {"key": "left", "modifiers": ["ctrl", "ctrl"]},
    {"key": "ctrl", "modifiers": ["ctrl"]},
    {"key": "left", "modifiers": "ctrl"},
    {"key": "left", "modifiers": [["ctrl"]]},
    {"text": ""}, {"text": "x" * 65}, {"text": "\0"}, {"text": "\u2603"},
    {"text": "yes", "key": "enter"}, {"text": "yes", "modifiers": ["shift"]},
])
def test_invalid_keyboard_input_is_rejected_before_delivery(params):
    with pytest.raises(ValueError):
        validate_keyboard(**params)


def test_us_layout_text_accepts_printable_ascii_enter_and_tab():
    validate_keyboard(text="Hello, world!\r\n\t", hold_ms=1, gap_ms=1000)


def test_private_credential_roundtrip_cleanup_and_invalid_unicode():
    with LocalCredential("dotbox-test-") as credential:
        path = credential.path
        token = path.read_text(encoding="ascii").strip()
        assert len(token) == 64 and credential.check(token)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert not credential.check(None)
        assert not credential.check("a" * 63)
        assert not credential.check("\u2603" * 64)
        assert not credential.check("g" * 64)
    assert not path.exists() and not path.parent.exists()
    credential.close()
