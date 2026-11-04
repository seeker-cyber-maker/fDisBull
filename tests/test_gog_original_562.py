"""Optional source-bound GOG Inno 5.6.2 regression acceptance.

Not run in public CI: set FDISBULL_PRIVATE_GOG_INSTALLERS to an owner-controlled
folder with the three purchased GOG installers. No original bytes are retained
in the repo, test log, or source distribution.
"""
import hashlib
import os
from pathlib import Path

import pytest
from fdisbull.gog_unpack import list_gog, unpack_gog
from fdisbull.native_inno import NativeInno

PRIVATE = os.environ.get('FDISBULL_PRIVATE_GOG_INSTALLERS')
CASES = {
 'setup_castles_1.03_dlc_(92359).exe': (190,'CASTLES1.EXE','228bda66bed005eabeafbace2bed2afca987f4cef4ba076c28c275c3c935edad'),
 'setup_castles_2_1.0_(28043).exe': (259,'C2CDTOOL.EXE','512efad4a4d771f6c975702cad9a688aeef10f8d81798b8c7260e37c74e87d43'),
 'setup_alone_in_the_dark_1.0_cs_(28043).exe': (218,'INDARK/FITD.exe','277ecfb71c9443df5fda7c4c7c6ffae3fdeb7b2e55d0f75f66c305c9b468f70b')
}

@pytest.mark.skipif(not PRIVATE,reason='private GOG source is not mounted')
@pytest.mark.parametrize('filename,case',CASES.items())
def test_private_original_inventory_and_executable(tmp_path,filename,case):
    src=Path(PRIVATE)/filename
    if not src.is_file():pytest.skip('private installer absent')
    count,exe,want=case
    reader=NativeInno.open(src)
    assert len(reader.inventory)==count
    assert len(list_gog(src)['files'])==count
    receipt=unpack_gog(src,tmp_path/'extracted',include=[exe])
    assert len(receipt['files'])==1
    assert receipt['files'][0]['sha256']==want
    assert (tmp_path/'extracted'/exe).is_file()

@pytest.mark.skipif(not PRIVATE,reason='private GOG source is not mounted')
def test_large_castles_ii_multipart_checksum(tmp_path):
    src=Path(PRIVATE)/'setup_castles_2_1.0_(28043).exe'
    if not src.is_file():pytest.skip('private installer absent')
    receipt=unpack_gog(src,tmp_path/'extracted',include=['C2CD.gog'],timeout=300)
    assert receipt['files'][0]['size']==748686288
    assert receipt['files'][0]['sha256']=='7bf4c0d9fee03245132cc1010e71f7760f3aad6cddaf16ef3b77f20af1e7302e'