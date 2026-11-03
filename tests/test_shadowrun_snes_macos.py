"""Public SNES build routing and private-input boundaries."""
import json

import pytest

from fdisbull.cli import main,respond
from fdisbull.shadowrun_snes_macos import build


def test_native_snes_output_stays_outside_git(tmp_path):
    root=tmp_path/'checkout';root.mkdir();(root/'.git').mkdir()
    with pytest.raises(ValueError,match='outside Git'):
        build(rom_path='missing',ram='missing',save_ram='missing',output=root/'app')
    assert not (root/'app').exists()


def test_unknown_profile_is_rejected_before_input_or_output(tmp_path):
    with pytest.raises(ValueError,match='profile'):
        build(rom_path='missing',ram='missing',save_ram='missing',output=tmp_path/'app',profile='unknown')
    assert not (tmp_path/'app').exists()


def test_native_snes_refuses_missing_input_without_creating_output(tmp_path):
    output=tmp_path/'app'
    with pytest.raises(ValueError,match='regular file'):
        build(rom_path=tmp_path/'missing',ram='missing',save_ram='missing',output=output)
    assert not output.exists()


@pytest.mark.parametrize('profile',['static-morgue','live-morgue','npc-intro','scripted-intro'])
def test_snes_build_cli_and_standalone_protocol(tmp_path,capsys,profile):
    params={'rom_path':str(tmp_path/'missing'),'ram':'missing','save_ram':'missing','output':str(tmp_path/'app'),'profile':profile}
    result=respond({'method':'shadowrun-snes-build','params':params},default_project='unrelated.fdb')
    assert not result['ok'] and 'regular file' in result['error']['message']
    code=main(['shadowrun-snes-build','--rom',params['rom_path'],'--ram','missing',
               '--save-ram','missing','--output',params['output'],'--profile',profile])
    output=json.loads(capsys.readouterr().out)
    assert code==1 and not output['ok'] and 'regular file' in output['error']['message']
