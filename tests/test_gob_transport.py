"""Gob launch negotiation tests; fake peers exercise transport contracts only."""
import json
import textwrap

import pytest

from fdisbull.scummvm_rpc import ScummVMError, ScummVMRPC


def peer(tmp_path, **hello_changes):
    path = tmp_path / 'peer.py'
    hello = dict(engine='gob', protocol='fdisbull-scummvm-agent', protocol_version=1,
                 bridge_version=1, profile='gob-inter-v3', capabilities=['run','pause'],
                 virtual_clock=True, variant={'game_id':'lit','detected_language':'us','detected_platform':'pc','recognized_detection':True})
    hello.update(hello_changes)
    path.write_text(textwrap.dedent('''\
        #!/usr/bin/env python3
        import json, os, socket, sys
        sock=socket.socket(fileno=int(os.environ['FDISBULL_SCUMMVM_FD']))
        stream=sock.makefile('rwb',buffering=0)
        for line in stream:
            request=json.loads(line)
            reply={'id':request['id'],'ok':True}
            if request['op']=='hello':reply.update(HELLO)
            elif request['op']=='argv':reply['argv']=sys.argv[1:]
            stream.write((json.dumps(reply)+'\\n').encode())
            if request['op']=='quit':break
    ''').replace('HELLO', repr(hello)))
    path.chmod(0o700)
    game = tmp_path/'game'
    game.mkdir()
    return path,game


def test_gob_transport_passes_engine_language_platform_without_affecting_game_identity(tmp_path):
    executable,game=peer(tmp_path)
    with_rpc=ScummVMRPC(executable,game,engine='gob',game_id='gob:lit',language='us',
                       platform='dos',runtime_parent=tmp_path)
    try:
        argv=with_rpc.call('argv')['argv']
        assert argv[-1]=='gob:lit'
        assert '--language=us' in argv and '--platform=dos' in argv
        assert with_rpc.engine=='gob' and with_rpc.game_id=='lit'
        assert with_rpc.capabilities['virtual_time'] is True
    finally:
        with_rpc.close()


@pytest.mark.parametrize('changes', [dict(engine='agi'),dict(protocol_version=2),
    dict(bridge_version=2),dict(profile='gob-inter-v2'),dict(protocol='another-protocol'),
    dict(capabilities=[42]),dict(protocol_version=True)])
def test_gob_negotiation_fails_closed_and_reaps_peer(tmp_path,changes):
    executable,game=peer(tmp_path,**changes)
    processes=[]
    with pytest.raises(ScummVMError,match='protocol|profile'):
        ScummVMRPC(executable,game,engine='gob',game_id='lit',runtime_parent=tmp_path,
                   on_spawn=processes.append)
    assert len(processes)==1 and processes[0].poll() is not None


@pytest.mark.parametrize('options', [dict(engine='gob',game_id='agi:lit'),
    dict(engine='sci',game_id='lit'),dict(engine='gob',game_id='lit',language='en --debug'),
    dict(engine='gob',game_id='lit',platform='../../dos')])
def test_invalid_gob_launch_is_rejected_before_spawn(tmp_path,options):
    executable,game=peer(tmp_path)
    processes=[]
    with pytest.raises(ValueError):
        ScummVMRPC(executable,game,runtime_parent=tmp_path,on_spawn=processes.append,**options)
    assert processes==[]


@pytest.mark.parametrize('game_id',['woodruff','gob:woodruff','gob2','gob3'])
def test_other_gob_interpreter_families_are_rejected_before_spawn(tmp_path,game_id):
    executable,game=peer(tmp_path)
    processes=[]
    with pytest.raises(ValueError,match='only Lost in Time'):
        ScummVMRPC(executable,game,engine='gob',game_id=game_id,
                   runtime_parent=tmp_path,on_spawn=processes.append)
    assert processes==[]


@pytest.mark.parametrize('game_id',['lit1','lit2'])
def test_losttime_family_ids_keep_the_explicit_gob_profile(tmp_path,game_id):
    variant={'game_id':game_id,'detected_language':'us','detected_platform':'pc',
             'recognized_detection':True}
    executable,game=peer(tmp_path,variant=variant)
    rpc=ScummVMRPC(executable,game,engine='gob',game_id='gob:'+game_id,runtime_parent=tmp_path)
    try:
        assert rpc.call('argv')['argv'][-1]=='gob:'+game_id
    finally:
        rpc.close()


@pytest.mark.parametrize('variant,language,platform', [
    ({'game_id':'lit','detected_language':'unknown','detected_platform':'pc','recognized_detection':True},None,None),
    ({'game_id':'other','detected_language':'us','detected_platform':'pc','recognized_detection':True},None,None),
    ({'game_id':'lit','detected_language':'fr','detected_platform':'pc','recognized_detection':True},'us',None),
    ({'game_id':'lit','detected_language':'us','detected_platform':'amiga'},None,'dos'),
])
def test_gob_unknown_fallback_and_mismatched_variant_are_refused(tmp_path,variant,language,platform):
    executable,game=peer(tmp_path,variant=variant)
    processes=[]
    with pytest.raises(ScummVMError,match='variant|language|platform'):
        ScummVMRPC(executable,game,engine='gob',game_id='lit',language=language,platform=platform,
                   runtime_parent=tmp_path,on_spawn=processes.append)
    assert processes[0].poll() is not None
