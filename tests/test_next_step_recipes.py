"""Run the published novice recipes, including their deliberate wrong turns."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pytest

from fdisbull.cli import invoke

GUIDE = Path(__file__).parents[1] / 'src/fdisbull/skills/fdisbull-investigate/references/next-steps.md'


def run_blocks(tmp_path, heading):
    text = GUIDE.read_text().split(heading, 1)[1].split('\n## ', 1)[0]
    blocks = re.findall(r'```sh\n(.*?)\n```', text, re.S)
    assert len(blocks) == 2
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    launcher = bindir / 'fdisbull'
    launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable)
                        + " -c 'from fdisbull.cli import main; raise SystemExit(main())' \"$@\"\n")
    launcher.chmod(0o755)
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
               PYTHONPATH=str(GUIDE.parents[4]))
    results = [subprocess.run(['bash', '-e', '-c', block], cwd=tmp_path,
                             env=env, text=True, capture_output=True, timeout=45)
               for block in blocks]
    assert results[0].returncode == 0, results[0].stdout + results[0].stderr
    return results


def test_static_recipe_and_wrong_address_recovery(tmp_path):
    run_blocks(tmp_path, '## Recipe 1:')
    p = str(tmp_path / 'entry.fdb')
    status = invoke('status', {'project': p})
    assert status['entry'] == '0x1000'
    assert status['loader_metadata']['file_mappings'][0]['virtual_address'] == 0x1000
    right = invoke('disasm', {'project': p, 'address': '0x1000', 'lines': 4})
    wrong = invoke('disasm', {'project': p, 'address': '0', 'lines': 4})
    assert wrong != right
    text = json.dumps(right).lower()
    assert 'mov' in text and 'add' in text and 'ret' in text
    assert (tmp_path / 'entry.bin').read_bytes() == bytes.fromhex('b80500000083c007c3')


def test_file_recipe_and_wrong_binding_recovery(tmp_path):
    run_blocks(tmp_path, '## Recipe 2:')
    p = str(tmp_path / 'records.fdb')
    data = invoke('file-data', {'project': p, 'file': 'records.dat', 'offset': 0, 'max_items': 16})
    assert [leaf['value'] for leaf in data['items']] == [3, 2, 7, 4]
    with pytest.raises(ValueError):
        invoke('file-data', {'project': p, 'file': 'records.dat', 'offset': 1, 'max_items': 16})
    assert (tmp_path / 'records.dat').read_bytes() == bytes.fromhex('0300020007000400')


def test_new_guides_are_selectively_retrievable():
    for reference in ('references/next-steps.md', 'references/analysis-types.md'):
        result = invoke('agent-skill', {'skill': 'fdisbull-investigate', 'reference': reference})
        assert set(result['files']) == {reference}
    writing = invoke('agent-skill', {'skill': 'write-gamefaqs-guide', 'reference': 'SKILL.md'})
    assert 'name: write-gamefaqs-guide' in writing['files']['SKILL.md']
