import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("zork_adapter", Path(__file__).parents[1] / "examples/zork_text/adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def frame(line=">", row=24, col=1):
    bda = bytearray(60)
    bda[0] = 3
    bda[1:3] = (80).to_bytes(2, "little")
    bda[7:9] = bytes([col, row])
    bda[59] = 24
    screen = bytearray(b" \x07" * 2000)
    for i, ch in enumerate(line.encode("ascii")):
        screen[(row * 80 + i) * 2] = ch
    return bda, screen


def test_prompt_requires_cursor_and_bare_prompt():
    bda, screen = frame()
    assert adapter.decode_screen(bda, screen)["prompt_candidate"]
    bda[7] = 2
    assert not adapter.decode_screen(bda, screen)["prompt_candidate"]
    bda, screen = frame(">look", col=5)
    assert not adapter.decode_screen(bda, screen)["prompt_candidate"]


def test_wrong_mode_and_short_reads_fail_closed():
    bda, screen = frame()
    bda[0] = 4
    with pytest.raises(adapter.ObservationError, match="unsupported"):
        adapter.decode_screen(bda, screen)
    with pytest.raises(adapter.ObservationError, match="incomplete"):
        adapter.decode_screen(bda, screen[:-1])


def test_commands_require_fresh_prompt_and_invalidate_before_delivery():
    class Session:
        def keyboard_state(self):
            return {"keyboard": {"pending_events": 0, "owned_keys": 0}}
        def keyboard_type(self, text):
            raise RuntimeError("delivery uncertain")
    obj = adapter.ZorkScreenAdapter(Session())
    obj.observe = lambda: {"screen_sha256": "a", "prompt_candidate": True}
    with pytest.raises(adapter.ObservationError, match="no confirmed"):
        obj.command("look")
    obj.ready = {"screen_sha256": "a"}
    with pytest.raises(RuntimeError, match="uncertain"):
        obj.command("look")
    assert obj.ready is None


def test_wait_rejects_unchanged_screen_and_stops():
    class Session:
        def run(self, **kwargs):
            return {"outcome": "guest_time"}
        def keyboard_state(self):
            return {"keyboard": {"pending_events": 0, "owned_keys": 0}}
    obj = adapter.ZorkScreenAdapter(Session(), max_slices=2)
    obj.observe = lambda: {"screen_sha256": "same", "cursor": [24, 1], "prompt_candidate": True}
    obj.ready = {"screen_sha256": "old"}
    with pytest.raises(adapter.ObservationError, match="not confirmed"):
        obj.wait_prompt(changed_from="same")
    assert obj.ready is None


def test_rejected_keyboard_queue_is_not_treated_as_success():
    class Session:
        def keyboard_state(self):
            return {"keyboard": {"pending_events": 0, "owned_keys": 0}}
        def keyboard_type(self, text):
            return {"accepted": False, "delivery": "unknown"}
    obj = adapter.ZorkScreenAdapter(Session())
    obj.observe = lambda: {"screen_sha256": "a", "prompt_candidate": True}
    obj.ready = {"screen_sha256": "a"}
    with pytest.raises(adapter.ObservationError, match="delivery not confirmed"):
        obj.command("look")
    assert obj.ready is None
