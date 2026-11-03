import pytest
from fdisbull.mario_minus_world import identify, warp_result


def test_control_changes_lookup_not_a_signed_world():
    assert warp_result(1,0x28)=={'table_index':4,'table_value':36,'world_index':35,'display_tile':36}
    assert warp_result(4,0x28)=={'table_index':0,'table_value':4,'world_index':3,'display_tile':4}
    assert warp_result(0,0x28) is None
    assert warp_result(1,0x60)['world_index']==4
    assert warp_result(1,0xa0)['world_index']==35
    assert warp_result(3,0x28)['world_index'] is None


def test_wrong_or_invalid_identity_is_refused():
    with pytest.raises(ValueError):identify(bytes(81936))
    for args in ((-1,0),(0,256),(True,0)):
        with pytest.raises(ValueError):warp_result(*args)
