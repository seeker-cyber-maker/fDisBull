import io
import json
import subprocess
import sys
from pathlib import Path
from fdisbull.cli import main
from test_zmachine import image


def test_story_content_and_il_primitives_from_cli(tmp_path,capsys):
    story=tmp_path/'renamed';story.write_bytes(image())
    assert main(['story-info',str(story)])==0
    assert json.loads(capsys.readouterr().out)['format']=='z-machine'
    program={'format':'fdisbull-il-1','role':'udl','variables':{'$money':{'type':'u16','initial':0}},
             'resources':{},'body':[{'id':'reward','op':'add','var':'$money','value':200}]}
    path=tmp_path/'program.json';path.write_text(json.dumps(program))
    assert main(['il-run',str(path)])==0
    assert json.loads(capsys.readouterr().out)['state']=={'$money':200}


def test_fair_play_startup_flag_overrides_private_host_configuration(tmp_path,monkeypatch,capsys):
    import fdisbull.text_host as host
    path=tmp_path/'config.json';path.write_text(json.dumps({'fair_play':False}))
    seen=[]
    monkeypatch.setattr(host,'host',lambda config,**kwargs:seen.append(config) or {'status':'test'})
    assert main(['text-host',str(path),'--fair-play'])==0
    assert seen==[{'fair_play':True,'spatial_mode':'physical'}]


def test_zork_command_autosaves_and_resumes_through_cli(tmp_path,monkeypatch,capsys):
    story=tmp_path/'story';story.write_bytes(image());state=tmp_path/'private.json'
    original=subprocess.Popen
    def launch(args,**kwargs):
        args[2]=str(Path(__file__).with_name('zork_worker_fixture.py'))
        return original(args,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',launch)
    monkeypatch.setattr(sys,'stdin',io.StringIO('{"op":"command","text":"look"}\n'))
    assert main(['zork',str(story),'--python',sys.executable,'--checkpoint',str(state)])==0
    lines=list(map(json.loads,capsys.readouterr().out.splitlines()))
    assert lines[0]['status']=='ready' and lines[1]['checkpoint']['outcome']=='saved'
    monkeypatch.setattr(sys,'stdin',io.StringIO('{"op":"observe"}\n'))
    assert main(['zork',str(story),'--python',sys.executable,'--resume',str(state)])==0
    lines=list(map(json.loads,capsys.readouterr().out.splitlines()))
    assert lines[0]['observation']=='look' and lines[1]['observation']=='look'


def test_cli_incomplete_or_unknown_request_stops(tmp_path,monkeypatch,capsys):
    story=tmp_path/'story';story.write_bytes(image())
    original=subprocess.Popen
    def launch(args,**kwargs):
        args[2]=str(Path(__file__).with_name('zork_worker_fixture.py'))
        return original(args,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',launch)
    monkeypatch.setattr(sys,'stdin',io.StringIO('{"op":"command","text":"look","ignored":true}\n'))
    assert main(['zork',str(story),'--python',sys.executable])==1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['status']=='stopped'
