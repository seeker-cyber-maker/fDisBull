"""Sound receipt admission at the host boundary, without a guest interpreter."""
from copy import deepcopy
import pytest

from test_qemu_agi_runtime_pack import boundary, pack, runtime  # noqa: F401


def capture_source(boundary, runtime):
    source = deepcopy(boundary._state["source"])
    return {"schema": runtime.SOUND_SCHEMA, "source": source, "available": True,
            "capacity": 262144, "count": 3, "epoch": 1, "eligible": 3,
            "dropped": 0, "last_seq": 3, "native_epoch": 0,
            "columns": runtime.SOUND_COLUMNS,
            "events": [[1, 0, 1, 1, 1, 0, 12, 1],
                       [2, 0, 2, 2, 1, 0, 24, 1],
                       [3, 0, 3, 3, 1, 0, 0, 0]]}


def bind_capture(monkeypatch, boundary, record):
    original = boundary._json_property
    monkeypatch.setattr(boundary, "_json_property", lambda key:
                        deepcopy(record) if key == "agi-runtime-sound-json" else original(key))


def test_complete_capture_has_owner_identity_and_no_implicit_consumption(monkeypatch, boundary, runtime):
    record = capture_source(boundary, runtime)
    bind_capture(monkeypatch, boundary, record)
    first = boundary.sound_events()
    assert first == boundary.sound_events()
    assert first["context"] == boundary.context_id and first["events"] == record["events"]
    assert boundary.commands == []


def test_overflow_requires_explicit_incomplete_capture(monkeypatch, boundary, runtime):
    record = capture_source(boundary, runtime)
    record.update(eligible=5, dropped=2, last_seq=5)
    bind_capture(monkeypatch, boundary, record)
    with pytest.raises(runtime.HarnessError, match="dropped 2"):
        boundary.sound_events()
    assert boundary.sound_events(allow_dropped=True)["dropped"] == 2
    assert boundary.commands == []


@pytest.mark.parametrize("mutation", [
    lambda r: r["events"].reverse(),
    lambda r: r["events"][1].__setitem__(2, 1),
    lambda r: r["events"][1].__setitem__(5, 4),
    lambda r: r["events"][1].__setitem__(6, 12277),
    lambda r: r.__setitem__("count", 2),
    lambda r: r["source"].__setitem__("sha256", "0" * 64),
])
def test_corrupt_audio_receipts_are_rejected(monkeypatch, boundary, runtime, mutation):
    record = capture_source(boundary, runtime)
    mutation(record)
    bind_capture(monkeypatch, boundary, record)
    with pytest.raises(runtime.HarnessError):
        boundary.sound_events()


def test_clear_requires_current_exact_owner_receipt(monkeypatch, boundary, runtime):
    record = capture_source(boundary, runtime)
    bind_capture(monkeypatch, boundary, record)
    receipt = boundary.sound_events()
    sent = []
    monkeypatch.setattr(boundary, "_command", lambda command: sent.append(command))
    boundary.clear_sound_events(receipt)
    assert sent == [{"action": "sound-clear", "epoch": 1, "through": 3}]
    forged = deepcopy(receipt)
    forged["context"] = "another child"
    with pytest.raises(runtime.HarnessError, match="another owner"):
        boundary.clear_sound_events(forged)
    record["epoch"] = 2
    with pytest.raises(runtime.HarnessError, match="stale"):
        boundary.clear_sound_events(receipt)
    assert len(sent) == 1
