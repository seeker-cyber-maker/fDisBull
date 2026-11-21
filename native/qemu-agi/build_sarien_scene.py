"""Build the small host scene library once, without rebuilding QEMU.

The output is a new private directory containing the library and its receipt.
No download, installation, runtime discovery, or provider CI is performed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def build(output):
    if not sys.platform.startswith('linux'):
        raise RuntimeError('This build recipe is qualified for Linux only')
    source = Path(__file__).resolve().parent
    output = Path(output).expanduser().resolve()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Output must be a new directory under an existing parent')
    if shutil.disk_usage(output.parent).free < 40 * 1024**3 + 4 * 1024**2:
        raise RuntimeError('The 40 GiB free-space reserve is unavailable')
    compiler = shutil.which('cc')
    if compiler is None:
        raise RuntimeError('An existing C compiler is required')
    inputs = {name: sha256((source / name).read_bytes()).hexdigest()
              for name in ('sarien_scene.c', 'sarien_scene.h', 'COPYING.sarien.txt')}
    output.mkdir()
    library = output / 'libagi-scene.so'
    command = [compiler, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fPIC', '-shared', str(source / 'sarien_scene.c'), '-o', str(library)]
    receipt = {'schema': 'fdisbull-agi-scene-library-build-1', 'status': 'running',
               'command': command, 'input_sha256': inputs, 'timeout_seconds': 30,
               'compiler': subprocess.check_output([compiler, '--version'], text=True,
                                                   timeout=5).splitlines()[0]}
    started = time.monotonic()
    try:
        with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
                raise RuntimeError('Scene library compilation exceeded its deadline')
        receipt['exit_code'] = code
        if code != 0:
            raise RuntimeError('Scene library compilation failed; see retained stderr.log')
        if library.stat().st_size > 4 * 1024**2:
            raise RuntimeError('Scene library exceeded its output budget')
        if any(sha256((source / name).read_bytes()).hexdigest() != digest
               for name, digest in inputs.items()):
            raise RuntimeError('Native inputs changed during compilation')
        receipt.update(status='built', library=str(library), bytes=library.stat().st_size,
                       library_sha256=sha256(library.read_bytes()).hexdigest(),
                       source_inputs_unchanged=True)
    except BaseException as error:
        receipt.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        receipt['elapsed_seconds'] = round(time.monotonic() - started, 6)
        receipt['free_bytes_after'] = shutil.disk_usage(output).free
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
