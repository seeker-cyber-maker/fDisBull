"""One authored endpoint batch; no assets, native library or guest execution."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native/qemu-agi"))
from scene_packet_preview import _endpoint
from sarien_scene import SceneInputError


def _authored_endpoints():
    """Endpoint-only projections; source/reset/journal validation is separate."""
    return_code = bytes([70, 0, 0])  # stop.cycling(0), authored return
    returned = {
        "execution_endpoint": {"kind": "authored_return", "fragment_pc": 2,
                               "bytes": [0], "original_source_address": None,
                               "retired": True, "committed": True},
        "draw_request": None,
    }
    return_state = {"guest": {"status": "return", "pc": 3,
                              "pending_effect": None, "fault": None}}

    pending_code = bytes([35, 0, 0])  # draw(0), unexecuted authored return
    pose = {"id": 0, "x": 20, "y": 50, "prev_x": 20, "prev_y": 50,
            "view_bound": True, "view": 1, "loop": 0, "cel": 0,
            "width": 2, "height": 2, "animated": True, "update": True,
            "cycling": True, "ignore_horizon": False, "update_pos": False,
            "view_replaced": True, "motion": "normal", "cycle": "normal",
            "direction": 0}
    source = {"sha256": sha256(pending_code).hexdigest(), "size": 3}
    descriptor = {"kind": "draw", "reason": "draw_requires_host", "pc": 0,
                  "opcode": 35, "bytes": [35, 0], "actor": 0,
                  "retired": False, "committed": False,
                  "completion_available": False}
    site = {"fragment_pc": 0, "code_pc": 0, "payload_offset": 2,
            "opcode": 35, "bytes": [35, 0]}
    pending = {
        "sites": [deepcopy(site)], "selected_actors": [0],
        "execution_endpoint": {"kind": "pending_draw", **deepcopy(site),
                               "retired": False, "committed": False},
        "draw_request": {
            "native_descriptor": deepcopy(descriptor), "source": deepcopy(source),
            "site": deepcopy(site), "committed_pose": deepcopy(pose),
            "position_repair_completed": False, "sprite_buffers_updated": False,
            "presentation_established": False,
            "unresolved": ["position_repair", "collision_and_priority_effects",
                           "sprite_composition", "presentation"],
        },
    }
    pending_state = {"source": source,
                     "guest": {"status": "effect", "pc": 0, "fault": None,
                               "pending_effect": descriptor, "actors": [pose]}}
    return (returned, return_state, return_code), (pending, pending_state, pending_code)


def test_endpoint_declaration_batch(record_property):
    returned, pending = _authored_endpoints()
    budget_pending = deepcopy(pending)
    budget_pending[1]["guest"].update(status="budget", pending_effect=None)
    budget_return = deepcopy(returned)
    budget_return[1]["guest"].update(status="budget", pc=2)
    false_completion = deepcopy(pending)
    false_completion[0]["draw_request"]["presentation_established"] = True

    cases = [
        ("authored-return", returned, "authored_return", None),
        ("pending-draw", pending, "pending_draw", None),
        ("budget-mislabeled-pending", budget_pending, None,
         "Packet did not stop at its declared pending draw"),
        ("budget-mislabeled-return", budget_return, None,
         "Packet did not complete its authored return"),
        ("contradictory-completion", false_completion, None,
         "Packet endpoint or draw request contradicts native state"),
    ]
    record_property("endpoint_cases", ",".join(case[0] for case in cases))
    record_property("endpoint_case_count", len(cases))
    for name, inputs, expected, error in cases:
        before = deepcopy(inputs)
        if error is None:
            assert _endpoint(*inputs) == expected, name
        else:
            with pytest.raises(SceneInputError, match=error):
                _endpoint(*inputs)
        assert inputs == before, f"{name}: endpoint validation changed its inputs"
