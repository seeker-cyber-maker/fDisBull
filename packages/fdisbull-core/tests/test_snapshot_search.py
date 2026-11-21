"""Shared-kernel contracts using only authored bytes and the standard library."""
from copy import deepcopy

import pytest

from fdisbull_core.memory_search import (
    plan_edit, refine_search, search_results, snapshot_metadata, start_search,
)


def snapshot(data, capture_id, **context_changes):
    context = dict(source_sha256="ab" * 32, run_id="authored-run",
                   address_space="physical", region=dict(start=0x4000, length=len(data)),
                   task_id="machine", mapping_id="flat", version_id=1)
    context.update(context_changes)
    return snapshot_metadata(data, context=context, capture_id=capture_id)


def test_changed_value_narrows_without_discarding_ambiguity_or_writing():
    before, after = bytes([0, 9, 0, 8]), bytes([100, 9, 100, 7])
    a, b = snapshot(before, "before"), snapshot(after, "after")
    initial = start_search(before, a, mode="equal", value=0)
    narrowed = refine_search(initial, before, a, after, b, mode="delta", delta=100)
    result = search_results(narrowed, after, b)
    assert result["candidate_count"] == 2
    assert [(row["address"], row["value"]) for row in result["rows"]] == [
        ("0x4000", 100), ("0x4002", 100),
    ]
    original = deepcopy(narrowed)
    plan = plan_edit(narrowed, after, b, offset=2, value=101)
    assert plan["expected_hex"] == "64" and plan["replacement_hex"] == "65"
    assert plan["write_performed"] is False
    assert narrowed == original and after == bytes([100, 9, 100, 7])


def test_snapshot_context_change_and_payload_corruption_refuse():
    data = b"\x01\x02"
    original = snapshot(data, "before")
    state = start_search(data, original)
    with pytest.raises(ValueError, match="context"):
        refine_search(state, data, original, data,
                      snapshot(data, "after", run_id="different-run"), mode="unchanged")
    with pytest.raises(ValueError, match="snapshot"):
        start_search(b"\x01\x03", original)
