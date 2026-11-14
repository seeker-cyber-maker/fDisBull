"""Authored launch validation and protocol tests; native acceptance is separate."""
from copy import deepcopy
from pathlib import Path
import json

import pytest

from fdisbull.dos_launch_profile import prepare_launch_options, bind_start
from fdisbull.disc import inspect_disc_path
from test_iso9660 import image


def cd(tmp_path):
    (tmp_path/'data.bin').write_bytes(b''.join(image()))
    p=tmp_path/'GAME.INS';p.write_text('FILE "data.bin" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00\n')
    return p


def test_ins_alias_goes_through_cue_validator(tmp_path):
    p=cd(tmp_path);r=inspect_disc_path(p)
    assert r['format']=='CUE/BIN disc' and r['valid'] and r['complete']
    with pytest.raises(ValueError): inspect_disc_path(p,mode='MODE1/2048')


def test_ins_is_not_accepted_merely_by_extension(tmp_path):
    p=tmp_path/'bad.ins';p.write_text('not a CUE')
    assert not inspect_disc_path(p)['valid']
    with pytest.raises(ValueError): prepare_launch_options([],p)


def test_explicit_arguments_and_source_bound_cd(tmp_path):
    p=cd(tmp_path);r=prepare_launch_options(['-p'],p)
    assert r['arguments']==['-p'] and len(r['cd']['inputs'])==2
    assert r['cd']['mount_observed'] is False
    request={'target':{'command':'MAINMENU.EXE','arguments':[]},'mounts':[{'drive':'C','host_path':'/private'}]}
    original=deepcopy(request);bound=bind_start(request,r)
    assert bound['target']['arguments']==['-p'] and request==original
    (tmp_path/'data.bin').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'): bind_start(request,r)


@pytest.mark.parametrize('args',[True,(),[''],['two tokens'],['"quoted"'],['x&y'],['%PATH%'],['x\n'],['é'],['a'*126],['x']*33])
def test_unsafe_or_ambiguous_command_tail_refused(args):
    with pytest.raises(ValueError): prepare_launch_options(args)


def test_conflicting_arguments_are_not_silently_dropped():
    p=prepare_launch_options(['-p'])
    with pytest.raises(ValueError): bind_start({'target':{'arguments':['-other']}},p)


def test_plain_iso_and_cue_links_are_explicit(tmp_path):
    p=tmp_path/'data.iso';p.write_bytes(b''.join(image()))
    assert prepare_launch_options([],p)['cd']['drive']=='D'
    link=tmp_path/'link.iso';link.symlink_to(p)
    with pytest.raises(ValueError): prepare_launch_options([],link)
    c=tmp_path/'disc.cue';c.write_text('FILE "link.iso" BINARY\n TRACK 01 MODE1/2048\n INDEX 01 00:00:00\n')
    with pytest.raises(ValueError): prepare_launch_options([],c)


def test_cli_exposes_switch_values_without_stealing_them():
    from fdisbull.dos_tools import parser
    r=parser().parse_args(['debug','x.fdb','--executable','agent','--game-dir','game','--argument=-p','--cd-image','GAME.INS'])
    assert r.argument==['-p'] and r.cd_image=='GAME.INS'


@pytest.mark.parametrize('track,index', [('1','1'),('01','01'),('1','01'),('01','1')])
def test_real_gog_single_digit_cue_numbers(tmp_path,track,index):
    p=cd(tmp_path)
    p.write_text(f'FILE "data.bin" BINARY\n TRACK {track} MODE1/2048\n INDEX {index} 00:00:00\n')
    assert inspect_disc_path(p)['valid']
    assert prepare_launch_options(['-p'],p)['cd']['drive']=='D'
