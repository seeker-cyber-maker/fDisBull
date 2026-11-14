"""Public projectless interfaces for the authored parser/composition fixtures."""
import json
from pathlib import Path
import pytest
from fdisbull.cli import invoke, parser, respond
from test_structure_intents import fixture, trace, observation


@pytest.fixture
def files(tmp_path):
    result={}
    for name,doc in [('spec',fixture()),('trace',trace()),('macro',observation()),
                     ('report',{'format':'fdisbull-structure-discovery-pilot-1','findings':[]})]:
        p=tmp_path/(name+'.json');p.write_text(json.dumps(doc));result[name]=str(p)
    return result


@pytest.mark.parametrize('method,keys,status',[
    ('structure-compose',{'spec':'spec'},'validated_analysis_plan'),
    ('structure-trace',{'spec':'spec','trace':'trace'},'consistent-prefix'),
    ('structure-compare',{'expected':'macro','actual':'macro'},'matched-declared-observations'),
    ('structure-intents',{'report':'report'},'intent_candidates')])
def test_json_interfaces_are_projectless(files,method,keys,status):
    request={'id':'authored','method':method,'params':{k:files[v] for k,v in keys.items()}}
    result=respond(request,default_project='/does/not/exist.fdb')
    assert result['ok'] and result['result']['status']==status
    assert result['result']['execution_authorized'] is False if 'execution_authorized' in result['result'] else True


def test_console_budget_arguments():
    a=parser().parse_args(['structure-scan','game.zip','--output','out','--max-console-views','2','--max-file-bytes','4194304'])
    assert a.max_console_views==2 and a.max_file_bytes==4194304


def test_capabilities_advertise_bounded_parser():
    from fdisbull.capabilities import capabilities
    serialized=json.dumps(capabilities())
    assert 'analysis.structure-discovery' in serialized and 'cli:structure-compose' in serialized
