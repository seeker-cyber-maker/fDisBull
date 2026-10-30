"""The standalone player is a separate, source-complete distribution."""
from pathlib import Path
import runpy
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(str(ROOT/'scripts/check_dist.py'))['check_archive']
RELEASE_FILES = runpy.run_path(str(ROOT/'scripts/build_release.py'))['release_files']
MODULES = ('__init__.py','__main__.py','player.py','runtime.py','live.py','word16.py',
           'game_intents.py','intent_runtime.py')


def player_wheel(path, *, omit=None, extra=None, metadata_name='fdisbull-player'):
    with zipfile.ZipFile(path,'w') as archive:
        for module in MODULES:
            if module != omit: archive.writestr('fdisbull_player/'+module,'')
        archive.writestr('fdisbull_player-1.0.dist-info/METADATA',f'Metadata-Version: 2.1\nName: {metadata_name}\nVersion: 1.0\n')
        if extra: archive.writestr(extra,'local data')


def test_player_wheel_has_distinct_metadata_and_complete_modules(tmp_path):
    wheel=tmp_path/'fdisbull_player-1.0-py3-none-any.whl'
    player_wheel(wheel)
    assert CHECK(wheel)==len(MODULES)+1
    player_wheel(wheel,omit='runtime.py')
    with pytest.raises(ValueError,match='runtime[.]py'): CHECK(wheel)
    player_wheel(wheel,metadata_name='fdisbull')
    with pytest.raises(ValueError,match='wrong Name'): CHECK(wheel)


@pytest.mark.parametrize('extra', ['fdisbull/__init__.py','other/__init__.py','fdisbull_player/GAME.EXE',
                                    'fdisbull_player/state.db','fdisbull_player/extra.py'])
def test_player_wheel_rejects_other_packages_and_local_data(tmp_path,extra):
    wheel=tmp_path/'fdisbull_player-1.0-py3-none-any.whl'
    player_wheel(wheel,extra=extra)
    with pytest.raises(ValueError): CHECK(wheel)


def test_tool_zip_selection_includes_only_player_python_and_manifest(tmp_path):
    # Use the real tree for required root inputs, then inspect the selected scope.
    selected={p.relative_to(ROOT).as_posix() for p in RELEASE_FILES(ROOT)}
    assert {'player/pyproject.toml'} | {'player/fdisbull_player/'+x for x in MODULES} <= selected
    assert not any(p.startswith('player/') and p not in {'player/pyproject.toml'} | {'player/fdisbull_player/'+x for x in MODULES} for p in selected)
