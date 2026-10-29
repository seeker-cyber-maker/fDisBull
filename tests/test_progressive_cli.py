"""The ordinary agent protocol and the independent player entry point agree."""
from fdisbull.cli import METHODS, main, parser
from fdisbull.debug_script import validate_script


def test_public_agent_operation_names_and_saved_script_validation():
    assert {'debug-save-workflow','debug-workflow-info','debug-workflow-receipts',
            'debug-save-text-projection','debug-text-projection-info','debug-assisted-travel',
            'debug-text-observe','debug-text-act','debug-workflow-observe','debug-workflow-act'} <= METHODS.keys()
    validate_script({'format':'fdisbull-script-1','steps':[
        {'op':'workflow-observe','workflow':'pinned','resource_root':'private','research_context':'room'},
        {'op':'text-observe','projection':'pinned','resource_root':'private'},
        {'op':'text-act','projection':'pinned','resource_root':'private','request':{'verb':'go','target':'opaque','item':None,'context_token':'opaque'}},
    ]})


def test_text_host_cli_loads_bounded_configuration(monkeypatch,tmp_path,capsys):
    import json
    import fdisbull.text_host
    path=tmp_path/'config.json';path.write_text('{"format":"fdisbull-text-host-1"}')
    called=[]
    def host(config,*,on_listen):
        called.append(config);on_listen({'host':'127.0.0.1','port':7});return {'status':'disconnected'}
    monkeypatch.setattr(fdisbull.text_host,'host',host)
    assert parser().parse_args(['text-host',str(path)]).configuration==str(path)
    assert main(['text-host',str(path)])==0
    lines=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]['text_player_endpoint']['port']==7 and lines[1]['status']=='disconnected'
    assert called==[{'format':'fdisbull-text-host-1'}]
