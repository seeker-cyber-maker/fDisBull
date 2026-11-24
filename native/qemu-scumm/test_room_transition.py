"""Synthetic tests for the SCUMM v2 room transition contract."""
from copy import deepcopy
from hashlib import sha256
import unittest
import room_transition as rt

SOURCE = {"version": 2, "profile": "amiga-v2-isolated"}

def room(room_id, exit_span=None, entry_span=None):
    data = f"room-{room_id}".encode()
    return {"source": SOURCE, "room": {"id": room_id, "sha256": sha256(data).hexdigest()},
        "room_scripts": {"exit": exit_span, "entry": entry_span},
        "object_directory": {"count": 2}, "walkboxes": {"admitted": True},
        "dimensions_pixels": {"width": 320, "height": 144},
        "qualification": {"whole_resource_identity_checked": True}}

class TransitionTests(unittest.TestCase):
    def plan(self, old=None, new=None, global5=True):
        new = new or room(2, entry_span={"offset": 90, "size": 8})
        return rt.plan_room_transition(current_room=old, target_room=new,
            target_resource_sha256=new["room"]["sha256"], source=SOURCE,
            global_script_5_available=global5)
    def receipt(self, plan, phase):
        return {"index": phase["index"], "phase": phase["phase"], "status": "committed",
            "plan_sha256": plan["plan_sha256"], "evidence": deepcopy(phase["evidence_contract"])}
    def test_initial_room_has_no_old_room_exit(self):
        p = self.plan()
        self.assertFalse(p["phases"][0]["required"])
        self.assertTrue(p["semantics"]["movement_is_not_implied"])
        self.assertFalse(p["semantics"]["native_execution_performed"])
    def test_exit_entry_and_global5_are_separate_phases(self):
        p = self.plan(old=room(1, exit_span={"offset": 80, "size": 10}))
        names = [x["phase"] for x in p["phases"] if x["required"]]
        self.assertEqual(names[:4], ["run_old_room_exit", "stop_room_owned_scripts",
            "release_room_owned_resources", "admit_target_room"])
        self.assertIn("run_target_entry_script", names)
        self.assertEqual(names[-2:], ["run_global_script_5", "complete"])
    def test_no_entry_or_global5_is_not_invented(self):
        p = self.plan(new=room(2), global5=False)
        optional = {x["phase"]: x["required"] for x in p["phases"]}
        self.assertFalse(optional["run_target_entry_script"])
        self.assertFalse(optional["run_global_script_5"])
    def test_receipts_must_be_ordered_and_source_bound(self):
        p = self.plan(); required = [x for x in p["phases"] if x["required"]]
        good = [self.receipt(p, x) for x in required[:3]]
        self.assertEqual(rt.validate_phase_receipts(p, good)["next_required_phase"], required[3]["phase"])
        bad = deepcopy(good); bad[1]["plan_sha256"] = "0" * 64
        with self.assertRaises(rt.TransitionError): rt.validate_phase_receipts(p, bad)
        with self.assertRaises(rt.TransitionError): rt.validate_phase_receipts(p, [good[1]])
    def test_missing_phase_is_never_treated_as_complete(self):
        p = self.plan(); receipts = [self.receipt(p, x) for x in p["phases"] if x["required"]]
        result = rt.validate_phase_receipts(p, receipts[:-1])
        self.assertFalse(result["complete"])
        self.assertEqual(result["next_required_phase"], "complete")
    def test_target_hash_and_profile_mismatch_are_rejected(self):
        new = room(2)
        with self.assertRaises(rt.TransitionError):
            rt.plan_room_transition(current_room=None, target_room=new, target_resource_sha256="0"*64,
                source=SOURCE, global_script_5_available=False)
        with self.assertRaises(rt.TransitionError):
            rt.plan_room_transition(current_room=None, target_room=new,
                target_resource_sha256=new["room"]["sha256"],
                source={"version": 1, "profile": "amiga-v2-isolated"}, global_script_5_available=False)
    def test_tampered_plan_definition_is_rejected(self):
        p = self.plan()
        p["phases"][3]["evidence_contract"]["room_id"] = 99
        with self.assertRaises(rt.TransitionError): rt.validate_phase_receipts(p, [])
    def test_old_room_must_share_version_profile(self):
        old = room(1); old["source"] = {"version": 1, "profile": "amiga-v2-isolated"}
        with self.assertRaises(rt.TransitionError): self.plan(old=old)

if __name__ == "__main__": unittest.main()
