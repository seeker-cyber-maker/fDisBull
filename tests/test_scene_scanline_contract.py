"""Authored checks for scanline guards and existing popup dispatch.

No original game images, emulator, model calls, or new runtime API are used.
The dispatch tests supply explicit synthetic observations; they do not qualify
native frame freshness, controls, or a game's dialogue behavior.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull.scenes import SceneError, SceneHandle, SceneSessionMixin, _evaluate, predicate


def scanline(y, bits):
    """Author a bounded row using the existing point-list predicate."""
    return {"pixels": {"samples": [
        {"x": x, "y": y, "rgb": [240, 240, 240] if bit else [16, 16, 16]}
        for x, bit in enumerate(bits)
    ], "tolerance": 0, "min_matches": len(bits)}}


def observed(*rows):
    return {(p["x"], p["y"]): p["rgb"]
            for row in rows for p in row["pixels"]["samples"]}


def matches(spec, pixels):
    predicate(spec, 320, 200)
    return _evaluate(spec, None, pixels, [], None)


@pytest.mark.parametrize("family,ys,prefix_bits,a_bits,b_bits", [
    ("item-notification", (20, 40), [1, 0, 1, 1, 0, 0, 1, 0],
     [1, 0, 0, 1, 1, 0, 0, 1], [1, 1, 0, 1, 1, 0, 0, 1]),
    ("document-status", (70, 90), [0, 1, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1],
     [0, 1, 1, 0, 0, 0, 0, 1, 1, 0, 1, 0], [0, 1, 1, 1, 0, 0, 0, 1, 1, 0, 1, 0]),
])
def test_shared_prefix_collides_but_required_identity_row_separates(family, ys, prefix_bits, a_bits, b_bits):
    # These names describe authored families, not semantic OCR results.
    prefix = scanline(ys[0], prefix_bits)
    names = [scanline(ys[1], a_bits), scanline(ys[1], b_bits)]
    assert all(matches(prefix, observed(prefix, name)) for name in names)
    for wanted, name in enumerate(names):
        guard = {"all": [prefix, name]}
        for actual, other in enumerate(names):
            assert matches(guard, observed(prefix, other)) == (wanted == actual), family


def test_prefix_matches_cannot_outvote_the_required_identity_row():
    prefix = scanline(20, [1] * 64)
    identity = scanline(40, [1, 0, 0, 1])
    wrong = scanline(40, [1, 0, 0, 0])
    frame = observed(prefix, wrong)
    pooled = {"pixels": {
        "samples": prefix["pixels"]["samples"] + identity["pixels"]["samples"],
        "min_matches": 67, "tolerance": 0}}
    assert matches(pooled, frame)  # Explicitly demonstrate the unsafe threshold.
    assert not matches({"all": [prefix, identity]}, frame)


def test_same_glyph_cross_section_needs_another_row():
    first = scanline(20, [1, 1, 0, 0, 1, 1])
    second_a = scanline(21, [1, 0, 1, 0, 1, 0])
    second_b = scanline(21, [0, 1, 0, 1, 0, 1])
    assert matches(first, observed(first, second_b))
    assert not matches({"all": [first, second_a]}, observed(first, second_b))


class ProbeSession(SceneSessionMixin):
    """Synthetic transport around the unchanged production frame_probe method."""
    def __init__(self, pixels, screenshot_payload=False):
        self.rpc = SimpleNamespace(capabilities={"video": {"pixel_probe": True}})
        self.pixels = pixels
        self.calls = []
        self.screenshot_payload = screenshot_payload

    def call(self, method, params):
        assert method == "video.probe"
        self.calls.append((method, deepcopy(params)))
        result = {"format": "rgb-samples", "frame_id": 1, "mode_id": 19,
                  "samples": [{"x": x, "y": y, "rgb": self.pixels[(x, y)]}
                              for x, y in params["points"]]}
        if self.screenshot_payload:
            result["png_base64"] = "forbidden-authored-sentinel"
        return result

    def _event(self, *args):
        pass


def test_two_native_width_rows_use_one_sparse_request():
    a, b = scanline(20, [1, 0] * 160), scanline(40, [0, 1] * 160)
    pixels = observed(a, b)
    session = ProbeSession(pixels)
    result = session.frame_probe([list(p) for p in sorted(pixels)])
    assert len(session.calls) == 1
    assert len(result["samples"]) == 640
    assert "png_base64" not in result
    assert matches({"all": [a, b]},
                   {(p["x"], p["y"]): p["rgb"] for p in result["samples"]})


def test_sparse_transport_refuses_screenshot_payload():
    row = scanline(20, [1, 0])
    session = ProbeSession(observed(row), screenshot_payload=True)
    with pytest.raises(ValueError, match="screenshot"):
        session.frame_probe([[0, 20], [1, 20]])


class DispatchHarness(SceneHandle):
    """Exercise production act() with scripted observations, not live pixels."""
    def __init__(self, observations):
        self.revision = "authored-scene-revision"
        self.trace = []
        self.observations = iter(observations)
        self.info = {"definition": {
            "objects": [{"id": "target", "name": "continue", "aliases": [],
                         "point": [10, 10], "action": {"kind": "click", "tag": "requested"},
                         "outcome": {"constant": False}, "timeout_ms": 5000, "guest_ms": 5000}],
            "handlers": [{"name": "known_notice", "point": [20, 20],
                          "action": {"kind": "click", "tag": "acknowledge"},
                          "outcome": {"constant": True}}]}}
        project = SimpleNamespace(debug_scene_info=lambda *a, **kw: self.info)
        self.session = SimpleNamespace(project=project, run_id="authored-run", version={"id": 1})

    def _observe(self, target=None, **kwargs):
        status = next(self.observations)
        self.trace.append(("observe", status))
        return {"status": status, "complete": status == "matched", "initial_outcome": False,
                "handlers": ["known_notice"] if status == "blocked" else [],
                "frame": {"frame_id": len(self.trace), "mode_id": 19}}

    def _store(self, value, **kwargs):
        return dict(value, observation="authored-observation")

    def _input(self, action, point, frame):
        self.trace.append(("input", action["tag"]))
        return {"queued": True}

    def _wait_outcome(self, spec, **kwargs):
        self.trace.append(("postcondition", "checked"))
        return {"status": "matched", "complete": True, "guest_elapsed_ms": 1}


@pytest.mark.parametrize("status", ["mismatch", "unavailable", "ambiguous"])
def test_unqualified_precondition_never_dispatches_input(status):
    harness = DispatchHarness([status])
    with pytest.raises(SceneError):
        harness.act("continue", handle_popups=True)
    assert not any(event[0] == "input" for event in harness.trace)


def test_known_popup_requires_explicit_policy():
    harness = DispatchHarness(["blocked"])
    with pytest.raises(SceneError):
        harness.act("continue")
    assert not any(event[0] == "input" for event in harness.trace)


def test_acknowledgement_is_followed_by_fresh_original_target_check():
    harness = DispatchHarness(["blocked", "matched"])
    assert harness.act("continue", handle_popups=True)["complete"]
    assert harness.trace == [
        ("observe", "blocked"), ("input", "acknowledge"), ("postcondition", "checked"),
        ("observe", "matched"), ("input", "requested"), ("postcondition", "checked")]


def test_changed_context_after_acknowledgement_blocks_original_click():
    harness = DispatchHarness(["blocked", "mismatch"])
    with pytest.raises(SceneError):
        harness.act("continue", handle_popups=True)
    assert [event for event in harness.trace if event[0] == "input"] == [("input", "acknowledge")]


def test_repeated_popup_stops_at_existing_bound():
    harness = DispatchHarness(["blocked"] * 5)
    with pytest.raises(SceneError) as error:
        harness.act("continue", handle_popups=True)
    assert error.value.result["status"] == "handler-limit"
    assert all(tag == "acknowledge" for kind, tag in harness.trace if kind == "input")
    assert sum(kind == "input" for kind, _ in harness.trace) == 5
