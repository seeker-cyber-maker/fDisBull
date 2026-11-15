import pytest
from fdisbull.agent_friction import FrictionError, triage, validate_report, promotion_gate


def report(**overrides):
    p={'format':'fdisbull-agent-friction-1','reporter':'cold-agent-A',
       'task':'Castles II offline intake', 'tool_version':'0.34.1',
       'command':'fdisbull preflight --help',
       'expected':'Command advertised by AGENTS.md should be available',
       'observed':'CLI rejects preflight as an invalid command',
       'classification':'discoverability',
       'reproduce':['install 0.34.1 offline kit','run fdisbull preflight --help'],
       'evidence':['cli-help-0.34.1','AGENTS.md:29-31'],
       'manual_steps':1,'tool_calls':1,'scope_expansion':False,
       'salty_note':'I spent a tool call trying a documented command.'}
    p.update(overrides);return p


def test_real_documentation_friction_is_not_fake_missing_feature():
    r=report(); assert validate_report(r)['observed']==r['observed']
    assert triage(r,capability_status='unknown')['action']=='check_capability_catalog_and_reproduce'
    assert triage(r,capability_status='available')['action']=='repair_skill_discoverability'


def test_missing_reusable_module_requires_scope_decision():
    r=report(scope_expansion=True,classification='missing_capability',command='decoder sci',
             observed='No registered SCI decoder')
    assert triage(r,capability_status='missing')['requires_human_decision']
    assert triage(r,capability_status='missing',human_decision='go_with_it')['action']=='implement_on_review_branch'
    assert triage(r,capability_status='missing',human_decision='do_your_best')['action']=='continue_with_existing_tools'
    assert triage(r,capability_status='missing',human_decision='stop_here')['action']=='park_affected_task'


def test_qa_cannot_self_certify():
    qa={'reviewer':'cold-agent-A','reproduced':True,'regressions_passed':True,
        'original_task_resumed':True,'evidence':['independent-run-1'],'notes':'Fixed'}
    with pytest.raises(FrictionError,match='Independent'):promotion_gate(report(),qa)
    qa['reviewer']='qa-agent-B'
    assert promotion_gate(report(),qa)['promotion_ready_for_review']
    qa['original_task_resumed']=False
    assert not promotion_gate(report(),qa)['promotion_ready_for_review']


def test_reports_refuse_unsupported_or_unbounded_inputs():
    for p in (report(manual_steps=-1),report(evidence=[]),report(unexpected='x'),
              report(scope_expansion='yes')):
        with pytest.raises(FrictionError):validate_report(p)
