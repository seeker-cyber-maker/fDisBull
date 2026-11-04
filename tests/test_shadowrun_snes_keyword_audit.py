import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_shadowrun_snes_keywords.py'
spec = importlib.util.spec_from_file_location('shadowrun_keyword_audit', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_record_parser_distinguishes_selector_from_taught_keywords():
    # Selector 3 has a response but teaches only keyword 7; selector 0xFF
    # teaches keyword 36 and carries a child script.
    data = bytes([0, 0, 0, 0, 3, 5, 1, 7, 0x34, 0x12,
                  0xff, 7, 0x81, 36, 0x78, 0x56, 0xbc, 0x9a, 0xf8])
    entries, end = audit.dialogue_entries(data, 0, len(data))
    assert end == len(data)
    assert [(e['selector'], e['learns'], e['script']) for e in entries] == [
        (3, [7], None), (0xff, [36], 0x5678)]


@pytest.mark.parametrize('data', [
    bytes([0, 0, 0, 0, 3, 2, 0x80, 0xf8]),  # missing script/text
    bytes([0, 0, 0, 0, 3, 4, 0, 0, 0]),  # missing sentinel
    bytes([0, 0, 0, 0, 3, 4, 0, 0, 0, 3, 4, 0, 0, 0, 0xf8]),
    bytes([0, 0, 0, 0, 3, 5, 1, 64, 0, 0, 0xf8]),  # invalid keyword
])
def test_record_parser_refuses_malformed_or_ambiguous_catalogue(data):
    with pytest.raises(ValueError):
        audit.dialogue_entries(data, 0, len(data))


def test_script_cfg_includes_both_conditional_arms_and_constant_argument():
    data = bytes([0xc0, 0x44, 8, 0, 0x00, 7, 0x58, 0x71, 0x56])
    seen, incoming = audit.script_cfg(data, 0, len(data), {0xc0, 0x44, 0, 0x58, 0x56})
    assert set(seen) == {0, 1, 4, 6, 8}
    assert incoming[8] == {1, 6}
    assert audit.constant_learn_argument(data, 6, seen, incoming) == 7


def test_script_cfg_ignores_bytes_after_unconditional_end():
    data = bytes([0x56, 0, 36, 0x58, 0x71, 0x56])
    seen, _ = audit.script_cfg(data, 0, len(data), {0, 0x58, 0x56})
    assert set(seen) == {0}


def test_branch_into_native_learn_does_not_get_a_false_constant_proof():
    data = bytes([0xc0, 0x44, 6, 0, 0x00, 7, 0x58, 0x71, 0x56])
    seen, incoming = audit.script_cfg(data, 0, len(data), {0xc0, 0x44, 0, 0x58, 0x56})
    with pytest.raises(ValueError, match='exclusive immediate'):
        audit.constant_learn_argument(data, 6, seen, incoming)


@pytest.mark.parametrize('data,valid', [
    (bytes([0x44, 10, 0]), {0x44}),  # target beyond current root
    (bytes([0x00]), {0}),  # truncated immediate
    (bytes([0x54]), {0x56}),  # source illegal operation
    (bytes([0xc0, 0x44, 5, 0, 0, 0xc0, 0x56]), {0xc0, 0x44, 0, 0x56}),
])
def test_script_cfg_refuses_uncertain_or_overlapping_instruction_boundaries(data, valid):
    with pytest.raises(ValueError):
        audit.script_cfg(data, 0, len(data), valid)


def test_wrong_source_is_not_a_successful_unused_keyword_audit():
    with pytest.raises(ValueError, match='exact qualified'):
        audit.audit(bytes(1048576))
