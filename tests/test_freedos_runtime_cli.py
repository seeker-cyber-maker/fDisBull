"""Runtime preparation/selection and workspace launch CLI routing."""
from fdisbull import cli, freedos_runtime


def test_runtime_info_and_prepare_reach_public_api(monkeypatch):
    calls=[]
    monkeypatch.setattr(freedos_runtime,'runtime_info',lambda path=None:dict(path=path))
    def prepare_runtime(boot_image,kernel_package,freecom_package,output,*,mtools_dir):
        calls.append((boot_image,kernel_package,freecom_package,output,mtools_dir))
        return dict(root=output)
    monkeypatch.setattr(freedos_runtime,'prepare_runtime',prepare_runtime)
    assert cli.invoke('freedos-runtime-info',dict(path='/runtime'))=={'path':'/runtime'}
    params=dict(boot_image='boot',kernel_package='kernel',freecom_package='shell',
                output='out',mtools_dir='tools')
    assert cli.invoke('freedos-runtime-prepare',params)=={'root':'out'}
    assert calls==[('boot','kernel','shell','out','tools')]


def test_cli_parses_runtime_and_workspace_launch_options():
    parser=cli.parser()
    info=parser.parse_args(['freedos-runtime-info','--path','/component'])
    assert info.path=='/component'
    prep=parser.parse_args(['freedos-runtime-prepare','boot','kernel','shell','out','--mtools-dir','tools'])
    assert (prep.boot_image,prep.kernel_package,prep.freecom_package,prep.output,prep.mtools_dir)==('boot','kernel','shell','out','tools')
    launch=parser.parse_args(['debug','db.fdb','--executable','qemu','--game-dir','games',
        '--backend','qemu-dos','--freedos-runtime','runtime','--dos-directory','workspace',
        '--dos-file-mode','checkpointed','--dos-generation','generation-id'])
    assert (launch.freedos_runtime,launch.dos_directory,launch.dos_file_mode,launch.dos_generation)==(
        'runtime','workspace','checkpointed','generation-id')
    assert 'debug-workspace-edit' in cli.METHODS
    automatic=parser.parse_args(['debug','db.fdb','--executable','qemu',
                                '--backend','qemu-dos','--freedos-runtime','runtime'])
    assert automatic.game_dir is None and automatic.backend == 'qemu-dos'
