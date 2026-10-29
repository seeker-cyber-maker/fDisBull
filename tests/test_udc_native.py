"""Guard the native verifier's private-input boundaries."""
import pytest
verify_native = pytest.importorskip('examples.udc.verify_native', reason='private verification example is not packaged')
verify_zork = verify_native.verify_zork
verify_dinopark = verify_native.verify_dinopark


def test_zork_native_refuses_overlapping_input_output(tmp_path):
    source=tmp_path/'game';source.mkdir()
    with pytest.raises(ValueError,match='distinct and disjoint'):
        verify_zork(source,source,tmp_path,source/'output')


def test_dinopark_native_refuses_unknown_original(tmp_path):
    original=tmp_path/'original';emitted=tmp_path/'emitted';original.mkdir();emitted.mkdir()
    (original/'DINOPARK.EXE').write_bytes(b'not the verified game')
    with pytest.raises(ValueError,match='Unqualified DinoPark'):
        verify_dinopark(original,emitted,tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_synthetic_game_assembles_without_relocations(tmp_path):
    import subprocess
    from pathlib import Path
    import os, shutil
    mc=shutil.which('llvm-mc');tool=Path(os.environ.get('FDISBULL_LLVM_DIR') or (Path(mc).parent if mc else '/opt/homebrew/opt/llvm/bin'))
    if not all((tool/name).is_file() for name in ('llvm-mc','llvm-objcopy','llvm-readobj')):
        pytest.skip('local LLVM assembler tools unavailable')
    source=Path(verify_native.__file__).with_name('synthetic_game.asm')
    obj=tmp_path/'fixture.o';binary=tmp_path/'GAME.COM'
    subprocess.run([str(tool/'llvm-mc'),'-triple=i386','-filetype=obj',str(source),'-o',str(obj)],check=True)
    reloc=subprocess.check_output([str(tool/'llvm-readobj'),'--relocations',str(obj)],text=True)
    assert 'Relocations [\n]' in reloc
    subprocess.run([str(tool/'llvm-objcopy'),'-O','binary','--only-section=.text',str(obj),str(binary)],check=True)
    assert binary.read_bytes()[0x10:0x14]==bytes.fromhex('05c80048')


def test_synthetic_game_native_acceptance(request):
    import os,shutil,tempfile
    from pathlib import Path
    backend=os.environ.get('FDISBULL_DOSBOX')
    mc=shutil.which('llvm-mc');llvm=Path(os.environ.get('FDISBULL_LLVM_DIR') or (Path(mc).parent if mc else '/opt/homebrew/opt/llvm/bin'))
    available=backend and Path(backend).is_file() and os.access(backend,os.X_OK) and all((llvm/name).is_file() and os.access(llvm/name,os.X_OK) for name in ('llvm-mc','llvm-objcopy','llvm-nm','llvm-readobj'))
    if not available:
        if request.config.getoption('--require-native'):pytest.fail('Native synthetic acceptance requires FDISBULL_DOSBOX and LLVM assembler tools')
        pytest.skip('Native synthetic acceptance requires FDISBULL_DOSBOX and LLVM assembler tools')
    with tempfile.TemporaryDirectory(prefix='fdisbull-udc-native-',dir='/tmp') as tmp:
        result=verify_native.verify_synthetic(backend,Path(tmp)/'result',llvm=llvm)
        assert result['qualification']['status']=='equivalent_under_assumptions'
        assert result['wrong_candidate']=='counterexample' and not result['wrong_output_created']
        assert result['stored_screenshot_reopen']
        assert result['c_view']['proof_status']=='equivalent_under_assumptions'
        for side in ('original','emitted','c_emitted'):
            assert result['native'][side]['input_ax']==10
            assert result['native'][side]['output_ax']==result['native'][side]['stored_u16']==209
            assert result['native'][side]['guest_completion'] and result['native'][side]['trace_complete']
            samples=result['native'][side]['assisted_boundary_samples']
            assert [v['input_ax'] for v in samples]==[0,1,65336,65337,65535]
            assert all(v['output_ax']==v['stored_u16']==v['model_u16']==(v['input_ax']+199)%65536 for v in samples)
