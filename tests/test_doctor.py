"""Doctor executes authored targets and retains evidence without private state."""
import json
import os
from pathlib import Path
import pytest

from fdisbull.doctor import doctor


def test_doctor_cli_starts_without_decoding_dependencies(tmp_path):
    import subprocess,sys
    environment={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    result=subprocess.run([sys.executable,'-S','-m','fdisbull','doctor','--backend','dosbox','--executable','missing'],
                          env=environment,text=True,capture_output=True)
    assert result.returncode==1
    report=json.loads(result.stdout)['result']
    assert report['status']=='failed' and report['checks'][0]['status']=='failed'
    assert all(report['dependencies'][name]['status']=='failed' for name in ('capstone','iced_x86','lief','PIL'))


def test_doctor_reports_missing_backend_without_claiming_a_pass(tmp_path):
    receipt=doctor(backend='dosbox',executable=str(tmp_path/'missing'),output=tmp_path/'evidence')
    assert receipt['status']=='failed'
    assert receipt['checks'][-1]['status']=='failed'
    assert json.loads((tmp_path/'evidence/receipt.json').read_text())==receipt
    with pytest.raises(FileExistsError):doctor(backend='dosbox',executable='missing',output=tmp_path/'evidence')
    assert {p.name for p in (tmp_path/'evidence').iterdir()}=={'receipt.json'}


def test_real_dos_runtime_doctor_exports_only_evidence(tmp_path):
    backend=os.environ.get('FDISBULL_DOSBOX')
    if not backend:pytest.skip('Set FDISBULL_DOSBOX for real doctor acceptance')
    receipt=doctor(backend='dosbox',executable=backend,output=tmp_path/'evidence')
    assert receipt['status']=='passed',receipt
    assert all(c['status']=='passed' for c in receipt['checks'])
    assert receipt['native_state_restored'] is True
    assert {'frame.png','click.png','trace.json','receipt.json'}<={p.name for p in (tmp_path/'evidence').iterdir()}
    assert not any(p.suffix in ('.exe','.fdb','.sav','.zip') for p in (tmp_path/'evidence').rglob('*'))
