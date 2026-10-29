"""Synthetic object-table and refusal tests; no retail story embedded."""
import pytest
import fdisbull.zork_recovery as recipe


def memory():
    data = bytearray(4096); data[0] = 3
    def word(at, value): data[at:at+2] = value.to_bytes(2, 'big')
    word(10, 64); word(12, 1800)
    mailbox = 64 + 62 + 159 * 9; child = mailbox + 9
    data[mailbox + 1] |= 0x10  # attribute 11
    data[mailbox + 2] |= 0x10  # attribute 19
    data[mailbox + 6] = 161
    word(mailbox + 7, 2500); word(child + 7, 2600)
    data[2500:2507] = bytes([3, 0x80, 0, 0, 0, 0, 0])
    data[2600:2607] = bytes([3, 0x80, 0, 0, 0, 0, 1])
    data[2507:2510] = bytes([10, 12, 0])
    data[2607] = 0
    word(1800 + 2 * (0x86 - 0x10), 160)
    return bytes(data)


def test_extracts_witness_from_real_v3_object_layout():
    state = recipe.state_from_ram(memory())
    assert state['$opened'] is True and state['$seen'] is False
    assert state['$container'] is True and state['$transparent'] is False
    assert (state['$object'], state['$child'], state['$sibling']) == (160, 161, 0)
    assert state['$property10'] == 12 and state['$property14'] == 0
    assert state['$mailbox_name'] != state['$child_name']


def test_property_default_and_bad_pointers():
    data = bytearray(memory()); data[2507] = 0; data[64 + 18:64 + 20] = b'\x01\x23'
    assert recipe.state_from_ram(bytes(data))['$property10'] == 0x123
    data[64 + 62 + 159 * 9 + 7:64 + 62 + 159 * 9 + 9] = b'\xff\xff'
    with pytest.raises(ValueError): recipe.state_from_ram(bytes(data))


def test_recovery_refuses_wrong_identity(monkeypatch, tmp_path):
    story = tmp_path / 'other'; story.write_bytes(b'not a story')
    monkeypatch.setattr(recipe, 'inspect_story', lambda path: {'sha256':'0' * 64})
    with pytest.raises(ValueError, match='identity'): recipe.recover_mailbox(story)
