"""Public structural verifier controls use authored resources only."""
from copy import deepcopy
import json
from pathlib import Path
import os
import subprocess
import sys

import pytest

from scripts.verify_agi_compact_graph import verify
from tests.test_agi_control import loaded, lift


def fixture(tmp_path):
    program=loaded(tmp_path,{0:bytes.fromhex('ff010100ff02001e021e0300')})
    projection=lift(program,{'$agi_v1':0},control_flow='compact',allow_opaque=True)
    path=tmp_path/'projection.json';path.write_text(json.dumps(projection))
    return projection,path


def test_verifier_matches_source_graph_and_writes_sanitized_receipt(tmp_path):
    projection,path=fixture(tmp_path)
    receipt=verify(tmp_path/'LOGDIR',tmp_path,0,'2.917',path)
    assert receipt['counts']['source_nodes']==4 and receipt['counts']['source_edges']==4
    assert receipt['counts']['source_structural_paths']==2
    assert receipt['counts']['opaque_actions']==2
    assert receipt['execution_check']=={'status':'refused','events':0,'visited':0}
    assert receipt['source_inputs_unchanged']
    encoded=json.dumps(receipt)
    assert str(tmp_path) not in encoded and '"instruction_bytes":' not in encoded
    assert 'initial_state' not in encoded and 'continuations": {' not in encoded
    root=Path(__file__).resolve().parents[1]
    output=tmp_path/'receipt.json'
    argv=[sys.executable,str(root/'scripts/verify_agi_compact_graph.py'),
          '--logdir',str(tmp_path/'LOGDIR'),'--volume-dir',str(tmp_path),'--logic','0',
          '--projection',str(path),'--output',str(output)]
    result=subprocess.run(argv,capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    assert result.returncode==0,result.stderr
    assert json.loads(output.read_text())==receipt
    original=(tmp_path/'LOGDIR').read_bytes()
    bad=subprocess.run(argv[:-1]+[str(tmp_path/'LOGDIR')],capture_output=True,text=True)
    assert bad.returncode!=0 and (tmp_path/'LOGDIR').read_bytes()==original


@pytest.mark.parametrize('mutation',['swap-branches','duplicate-opaque','move-opaque','alter-evidence'])
def test_verifier_rejects_corrupt_control_and_provenance(tmp_path,mutation):
    projection,path=fixture(tmp_path);broken=deepcopy(projection)
    if mutation=='swap-branches':
        branch=broken['uil']['continuations'][broken['uil']['entry']]['transfer']
        branch['then'],branch['else']=branch['else'],branch['then']
    elif mutation=='duplicate-opaque':
        broken['opaque_operations'][1]=deepcopy(broken['opaque_operations'][0])
    elif mutation=='move-opaque':
        body=broken['uil']['continuations']['agi_0007']['body']
        broken['uil']['continuations']['agi_0009']['body'].append(body.pop())
    else:
        broken['uil']['evidence']['agi_0007']['instruction_bytes']='00'
    path.write_text(json.dumps(broken))
    with pytest.raises(ValueError):verify(tmp_path/'LOGDIR',tmp_path,0,'2.917',path)
