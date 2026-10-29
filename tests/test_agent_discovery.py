"""Cheap discovery must remain usable before opening a project or a guide."""
import json
from fdisbull.cli import invoke, main, respond


def test_index_routes_to_real_bundled_guides_with_compact_output(capsys):
    index=invoke('agent-skill',{'index':True})
    full=invoke('agent-skill',{})
    assert index['format']=='fdisbull-skill-index-1'
    names={guide['reference'] for guide in index['guides']}
    assert names==set(full['files'])
    assert index['entrypoint'] in names
    assert all(guide['purpose'].strip() for guide in index['guides'])
    assert 'files' not in index
    assert len(json.dumps(index)) < len(json.dumps(full))/4
    assert main(['agent-skill','--index'])==0
    assert json.loads(capsys.readouterr().out)['result']==index
    assert respond({'method':'agent-skill','params':{'index':True}},default_project='/nonexistent')['result']==index


def test_index_rejects_ambiguous_requests_and_non_boolean_flags():
    for value in (1,'yes',[],None):
        assert not respond({'method':'agent-skill','params':{'index':value}})['ok']
    assert not respond({'method':'agent-skill','params':{'index':True,'reference':'SKILL.md'}})['ok']
    assert not respond({'method':'agent-skill','params':{'index':True,'unknown':True}})['ok']
    assert invoke('agent-skill',{'index':False,'reference':'SKILL.md'})==invoke('agent-skill',{'reference':'SKILL.md'})
