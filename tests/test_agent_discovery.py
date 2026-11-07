"""Cheap discovery must remain usable before opening a project or a guide."""
import json
import pytest
from fdisbull.cli import invoke, main, respond


@pytest.mark.parametrize('skill',[None,'fdisbull-investigate','write-gamefaqs-guide'])
def test_index_routes_to_real_bundled_guides_with_compact_output(capsys,skill):
    selection={} if skill is None else {'skill':skill}
    index=invoke('agent-skill',dict(selection,index=True))
    full=invoke('agent-skill',selection)
    assert index['format']=='fdisbull-skill-index-1'
    assert index['name']==(skill or 'fdisbull-investigate')
    names={guide['reference'] for guide in index['guides']}
    assert names==set(full['files'])
    assert index['entrypoint'] in names
    assert all(guide['purpose'].strip() for guide in index['guides'])
    assert 'files' not in index
    assert len(json.dumps(index)) < len(json.dumps(full))/4
    command=['agent-skill']+([] if skill is None else ['--skill',skill])
    assert main(command+['--index'])==0
    assert json.loads(capsys.readouterr().out)['result']==index
    assert respond({'method':'agent-skill','params':dict(selection,index=True)},default_project='/nonexistent')['result']==index
    for reference in names:
        result=respond({'method':'agent-skill','params':dict(selection,reference=reference)},default_project='/nonexistent')
        assert result['ok'] and result['result']=={'name':index['name'],'files':{reference:full['files'][reference]}}
        assert len(json.dumps(result).encode())<64*1024
    assert main(command+['--reference','SKILL.md'])==0
    assert json.loads(capsys.readouterr().out)['result']['files']=={'SKILL.md':full['files']['SKILL.md']}


def test_catalogue_is_compact_and_default_selection_is_backward_compatible(capsys):
    catalogue=invoke('agent-skill',{'list':True})
    assert catalogue['format']=='fdisbull-skill-catalog-1'
    assert catalogue['default_skill']=='fdisbull-investigate'
    assert {item['name'] for item in catalogue['skills']}=={'fdisbull','fdisbull-investigate','write-gamefaqs-guide'}
    assert all(set(item)=={'name','purpose','entrypoint'} and item['purpose'].strip()
               and item['entrypoint']=='SKILL.md' for item in catalogue['skills'])
    assert len(json.dumps(catalogue).encode())<2048
    assert main(['agent-skill','--list'])==0
    assert json.loads(capsys.readouterr().out)['result']==catalogue
    assert respond({'method':'agent-skill','params':{'list':True}},default_project='/nonexistent')['result']==catalogue
    assert invoke('agent-skill',{})==invoke('agent-skill',{'skill':'fdisbull-investigate'})


def test_index_rejects_ambiguous_requests_and_non_boolean_flags():
    for value in (1,'yes',[],None):
        assert not respond({'method':'agent-skill','params':{'index':value}})['ok']
        assert not respond({'method':'agent-skill','params':{'list':value}})['ok']
    assert not respond({'method':'agent-skill','params':{'index':True,'reference':'SKILL.md'}})['ok']
    assert not respond({'method':'agent-skill','params':{'index':True,'unknown':True}})['ok']
    assert invoke('agent-skill',{'index':False,'reference':'SKILL.md'})==invoke('agent-skill',{'reference':'SKILL.md'})


@pytest.mark.parametrize('params',[
    {'skill':None},{'skill':True},{'skill':1},{'skill':[]},{'skill':{}},
    {'skill':'unknown'},{'skill':'../fdisbull-investigate'},
    {'skill':'/fdisbull-investigate'},{'skill':'fdisbull-investigate/../write-gamefaqs-guide'},
    {'reference':True},{'reference':[]},{'reference':'../SKILL.md'},
    {'reference':'/etc/passwd'},{'reference':'references/../SKILL.md'},
    {'skill':'write-gamefaqs-guide','reference':'references/scenes.md'},
    {'skill':'fdisbull-investigate','reference':'references/technical-mechanics.md'},
    {'list':True,'index':True},{'list':True,'reference':'SKILL.md'},
    {'list':True,'skill':'fdisbull-investigate'},
    {'skill':'write-gamefaqs-guide','index':True,'reference':'SKILL.md'},
    {'list':True,'unknown':True},
])
def test_skill_selection_rejects_bad_types_paths_names_and_combinations(params):
    assert not respond({'method':'agent-skill','params':params})['ok']


def test_cli_rejects_cross_skill_paths_and_incompatible_catalogue_flags(capsys):
    assert main(['agent-skill','--skill','write-gamefaqs-guide','--reference','references/scenes.md'])==1
    assert not json.loads(capsys.readouterr().out)['ok']
    assert main(['agent-skill','--list','--skill','write-gamefaqs-guide'])==1
    assert not json.loads(capsys.readouterr().out)['ok']
    with pytest.raises(SystemExit) as error:
        main(['agent-skill','--list','--index'])
    assert error.value.code==2
