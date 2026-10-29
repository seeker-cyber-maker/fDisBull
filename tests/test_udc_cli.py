import json
from pathlib import Path

from fdisbull.cli import main
from fdisbull.project import Project


def call(monkeypatch,capsys,*args):
    monkeypatch.setattr('sys.argv',['fdisbull',*map(str,args)])
    code=main();return code,json.loads(capsys.readouterr().out)


def test_private_compilation_and_compact_replies(tmp_path,monkeypatch,capsys):
    binary=tmp_path/'GAME.COM';binary.write_bytes(bytes.fromhex('b8004ccd21'))
    db=tmp_path/'private.fdb'
    with Project.create(db,binary,image='com'):pass
    code,captured=call(monkeypatch,capsys,'udc-capture',db,'original')
    assert code==0 and captured['artifact_count']==1 and 'artifacts' not in captured
    ident=captured['id']
    code,info=call(monkeypatch,capsys,'udc-info',db,ident)
    assert code==0 and 'document' not in info
    code,full=call(monkeypatch,capsys,'udc-info',db,ident,'--full')
    assert code==0 and full['document']['artifacts'][0]['blocks']
    programfile=tmp_path/'programs.json'
    code,exported=call(monkeypatch,capsys,'udc-programs',db,ident,'--output',programfile)
    assert code==0 and exported['program_count']==0 and json.loads(programfile.read_text())=={}
    code,result=call(monkeypatch,capsys,'udc-compile',db,ident,tmp_path/'output','--programs',programfile)
    assert code==0 and result['artifact_count']==1 and 'proofs' not in result['qualification']
    assert Path(result['manifest']).is_file()
    assert (tmp_path/'output/GAME.COM').read_bytes()==binary.read_bytes()
    code,result=call(monkeypatch,capsys,'udc-compile',db,ident,tmp_path/'output')
    assert code==1 and result['status']=='refused'


def test_cli_lift_writes_file_and_preserves_it_on_refused_overwrite(tmp_path,monkeypatch,capsys):
    source=tmp_path/'block.asm-bytes';source.write_bytes(b'\x40')
    bindings=tmp_path/'bindings.json';bindings.write_text('{"ax":"$score"}')
    output=tmp_path/'lift.json'
    code,result=call(monkeypatch,capsys,'udl-lift-asm',source,'--bindings',bindings,'--input','ax','--output-register','ax','--output',output)
    assert code==0 and result['status']=='lifted' and 'source' not in result
    original=output.read_bytes();assert json.loads(original)['source']=='40'
    code,result=call(monkeypatch,capsys,'udl-lift-asm',source,'--bindings',bindings,'--input','ax','--output-register','ax','--output',output)
    assert code==1 and output.read_bytes()==original


def test_cli_proof_reply_is_compact_but_saved_spec_is_complete(tmp_path,monkeypatch,capsys):
    from fdisbull.udl_blocks import lift_asm_block
    lift=lift_asm_block(b'\x40',{'ax':'$score'},inputs=['ax'],outputs=['ax'])
    source=tmp_path/'lift.json';source.write_text(json.dumps(lift))
    program=tmp_path/'uil.json';program.write_text(json.dumps(lift['uil']))
    proof=tmp_path/'proof.json'
    code,result=call(monkeypatch,capsys,'udl-verify',source,program,'--output',proof)
    assert code in (0,1)
    assert result['status'] in ('equivalent_under_assumptions','unavailable')
    assert 'spec' not in result['outputs']['ax']
    assert json.loads(proof.read_text())['outputs']['ax']['spec']['variables']=={'ax':16}


def test_duplicate_recipe_json_is_refused_without_traceback(tmp_path,monkeypatch,capsys):
    source=tmp_path/'block';source.write_bytes(b'\x40')
    binding=tmp_path/'bindings';binding.write_text('{"ax":"$a","ax":"$b"}')
    output=tmp_path/'lift.json'
    code,result=call(monkeypatch,capsys,'udl-lift-asm',source,'--bindings',binding,'--input','ax','--output-register','ax','--output',output)
    assert code==1 and result['status']=='refused' and 'duplicate' in result['error']
    assert not output.exists()
