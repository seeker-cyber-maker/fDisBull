import struct

import pytest

from fdisbull.chimprec import CHIMPREC_COMMIT, recover_iat
from fdisbull.model import Region


def export(address, module="kernel32.dll", name="ExitProcess", ordinal=1, forwarder=None):
    return {"address": address, "module": module, "name": name, "ordinal": ordinal, "forwarder": forwarder}


def slots(values, start=0x2000, bits=64):
    width = bits // 8
    return Region("captured_iat", start, b"".join(value.to_bytes(width, "little") for value in values), False)


def test_x64_rip_reference_recovers_captured_runtime_iat():
    target = 0x7FFB12345000
    code = Region("code", 0x1000, b"\xff\x15" + struct.pack("<i", 0x2000 - 0x1006) + b"\xc3", True)
    result = recover_iat([code, slots([target, 0])], 64, [export(target)])
    entry = result["entries"][0]
    assert (entry["address"], entry["target"], entry["resolved"], entry["group"]) == (0x2000, target, True, "kernel32.dll")
    assert result["source"]["commit"] == CHIMPREC_COMMIT
    assert result["candidates_examined"] == 1
    assert result["entries"][1]["status"] == "padding"
    assert result["budget_exhausted"] is False


def test_x64_negative_rip_displacement_and_x86_absolute_slot():
    target = 0x71234567
    code64 = Region("code", 0x3000, b"\xff\x25" + struct.pack("<i", 0x2000 - 0x3006), True)
    assert recover_iat([code64, slots([target])], 64, [export(target)])["entries"][0]["address"] == 0x2000
    code32 = Region("code", 0x1000, b"\xff\x15" + struct.pack("<I", 0x2000), True)
    assert recover_iat([code32, slots([target], bits=32)], 32, [export(target)])["entries"][0]["target"] == target


def test_ordinal_only_import_is_resolved_without_inventing_name():
    result = recover_iat([slots([0x70001000])], 64, [export(0x70001000, name=None, ordinal=17)], [0x2000])
    entry = result["entries"][0]
    assert entry["resolved"] and not entry["ambiguous"]
    assert entry["alternatives"][0]["name"] is None
    assert entry["alternatives"][0]["ordinal"] == 17


def test_aliases_and_forwarders_are_preserved_without_arbitrary_choice():
    target = 0x70001000
    alternatives = [export(target, name="AliasA"), export(target, name="AliasB", forwarder="NTDLL.RealTarget")]
    result = recover_iat([slots([target])], 64, alternatives, [0x2000])
    entry = result["entries"][0]
    assert entry["resolved"] and entry["ambiguous"]
    assert {item["name"] for item in entry["alternatives"]} == {"AliasA", "AliasB"}
    assert any(item["forwarder"] == "NTDLL.RealTarget" for item in entry["alternatives"])
    assert entry["module"] == "kernel32.dll"
    assert "name" not in entry


def test_cross_module_alias_has_no_selected_module_group():
    target = 0x70001000
    result = recover_iat([slots([target])], 64,
                         [export(target, module="one.dll"), export(target, module="two.dll")], [0x2000])
    entry = result["entries"][0]
    assert entry["ambiguous"] and entry["module"] is None and entry["group"] is None
    assert result["groups"] == []


def test_padding_unresolved_and_module_group_boundaries():
    first, second, unknown = 0x70001000, 0x70002000, 0x55555555
    result = recover_iat([slots([first, 0, unknown, second, second])], 64,
                         [export(first), export(second, module="user32.dll", name="MessageBoxW")], [0x2000])
    assert [entry["status"] for entry in result["entries"]] == ["resolved", "padding", "unresolved", "resolved", "resolved"]
    unresolved = result["entries"][2]
    assert unresolved["alternatives"] == [] and unresolved["module"] is None
    assert [group["module"] for group in result["groups"]] == ["kernel32.dll", "user32.dll"]
    assert result["groups"][1]["addresses"] == [0x2018, 0x2020]


def test_gap_limit_stops_at_consecutive_unresolved_nonzero_slots():
    target = 0x70001000
    result = recover_iat([slots([target, 0x11, 0, 0x22, target])], 64, [export(target)], [0x2000], gap_limit=2)
    assert [entry["target"] for entry in result["entries"]] == [target, 0x11, 0, 0x22]
    assert result["budget_exhausted"] is False


def test_full_width_bounds_no_partial_slot_or_cross_region_expansion():
    target = 0x70001000
    first = Region("first", 0x2000, target.to_bytes(8, "little") + b"\x99" * 4, False)
    second = slots([target], start=0x200C)
    result = recover_iat([first, second], 64, [export(target)], [0x2000, 0x2008])
    assert [entry["address"] for entry in result["entries"]] == [0x2000]
    assert result["warnings"]


def test_budget_and_no_export_map_return_explicit_limits():
    target = 0x70001000
    region = slots([target] * 8)
    limited = recover_iat([region], 64, [export(target)], [0x2000], max_slots=2)
    assert len(limited["entries"]) == 2 and limited["budget_exhausted"]
    empty = recover_iat([region], 64, [], [0x2000])
    assert empty["entries"] == [] and empty["warnings"] and empty["candidates_examined"] == 0


def test_unmatched_candidates_do_not_become_fake_imports_and_input_validation():
    result = recover_iat([slots([0x1234])], 64, [export(0x70001000)], [0x2000])
    assert result["entries"] == [] and result["warnings"] and result["candidates_examined"] == 1
    with pytest.raises(ValueError, match="32 or 64"):
        recover_iat([], 16, [])
    with pytest.raises(ValueError, match="max_slots"):
        recover_iat([], 64, [], max_slots=0)


def test_automatic_discovery_rejects_truncated_pattern_and_unmapped_target():
    target = 0x70001000
    truncated = Region("code", 0x1000, b"\xff\x15\0", True)
    absent = recover_iat([truncated, slots([target])], 64, [export(target)])
    assert absent["entries"] == [] and absent["candidates_examined"] == 0
    unmapped = Region("code", 0x1000, b"\xff\x15" + struct.pack("<i", 0x9000 - 0x1006), True)
    missing = recover_iat([unmapped, slots([target])], 64, [export(target)])
    assert missing["entries"] == [] and missing["candidates_examined"] == 1 and missing["warnings"]
