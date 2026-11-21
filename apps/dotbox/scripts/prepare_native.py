#!/usr/bin/env python3
"""Prepare DotBox's pinned DOSBox-X source; see docs/STANDALONE_NATIVE.md."""
from pathlib import Path
import runpy


if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'native/prepare_source.py'),
                   run_name='__main__')
