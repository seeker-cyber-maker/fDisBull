import pytest
from fdisbull.agi_layout import logic_layout


def resource(code): return len(code).to_bytes(2,'little')+code


def test_position_only_at_condition_boundary():
    # A matching byte pattern in an action's operands is not a condition.
    layout=logic_layout(resource(bytes.fromhex('510b000a0b14ff0b000a0b1415ff000000')))
    assert 3 not in layout['conditions']
    assert layout['conditions'][9]=={'opcode':11,'end':15,'negated':False}


@pytest.mark.parametrize('code',[
    bytes.fromhex('ff0b000a0b1415ffffff00'), # target enters an operand
    bytes.fromhex('ff0b000a0b14'),           # truncated condition
    bytes.fromhex('feff7f'),                 # invalid jump
    bytes.fromhex('ae00'),                   # version-specific action
    bytes.fromhex('fffdff0000'),             # dangling not
])
def test_invalid_layout_rejected(code):
    with pytest.raises(ValueError): logic_layout(resource(code))


def test_negated_position_is_identified_for_caller_to_refuse():
    layout=logic_layout(resource(bytes.fromhex('fffd0b000a0b1415ff000000')))
    assert layout['conditions'][4]['negated'] is True
