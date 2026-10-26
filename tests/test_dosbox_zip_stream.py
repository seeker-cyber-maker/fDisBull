"""Native ZIP regression: use the real patched upstream adapter and minizip."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_native_zip_empty_writes_preserve_crc_and_corruption_is_rejected(tmp_path, request):
    location = os.environ.get('FDISBULL_DOSBOX_SOURCE')
    if not location:
        if request.config.getoption('--require-native', default=False):
            pytest.fail('Native ZIP acceptance requires FDISBULL_DOSBOX_SOURCE')
        pytest.skip('Set FDISBULL_DOSBOX_SOURCE to the patched upstream checkout')
    source = Path(location).resolve(strict=True)
    compiler = shutil.which('c++')
    c_compiler = shutil.which('cc')
    assert compiler and c_compiler, 'Native ZIP acceptance requires C and C++ compilers'
    includes = ['-I' + str(source / 'include')]
    objects = []
    for name in ('zip', 'unzip', 'ioapi'):
        output = tmp_path / (name + '.o')
        subprocess.run([c_compiler, '-O2', *includes, '-c',
                        str(source / 'vs/zlib/contrib/minizip' / (name + '.c')),
                        '-o', str(output)], check=True, capture_output=True, text=True)
        objects.append(str(output))
    executable = tmp_path / 'zip-empty-write'
    regression = Path(__file__).with_name('dosbox_zip_empty_write.cpp')
    subprocess.run([compiler, '-std=c++11', '-O2', *includes, str(regression),
                    *objects, '-lz', '-o', str(executable)], check=True,
                   capture_output=True, text=True)
    result = subprocess.run([str(executable), str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'corrupt payload rejected' in result.stdout
