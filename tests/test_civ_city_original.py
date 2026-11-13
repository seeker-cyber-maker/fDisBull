"""Private original-code gate; no game bytes are distributed with tests."""
import os
from pathlib import Path

import pytest

from examples.civ.civ_city_original import OriginalCity
from examples.civ.civ_city_uil import _primitive_program
from fdisbull.interaction_il import execute_il


def test_original_disorder_preserves_existing_storage_and_reset_is_separate():
    path = os.environ.get("FDISBULL_CIV_UNPACKED")
    if not path or not Path(path).is_file():
        pytest.skip("supply the private pinned original via FDISBULL_CIV_UNPACKED")
    pytest.importorskip("unicorn")
    original = OriginalCity(path)
    for stock in (-32768,-1,0,5,999,1000,32767):
        for delta in (-32768,-1,0,3,32767):
            for disorder in (False,True):
                observed = original.observe(stock,delta,disorder,city=127,frame=0x8800,maintenance=7)
                state = {"$shield_box":observed["sanitized_stock"],"$shield_delta":delta,
                         "$disorder":disorder,"$sanitized":True}
                result = execute_il(_primitive_program(),state=state)
                assert result["status"]=="complete"
                assert result["state"]["$shield_box"]==observed["result"]
    assert original.observe(5,3,True)["result"]==5
    assert original.observe(1000,3,True)["result"]==0
