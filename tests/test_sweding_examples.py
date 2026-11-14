"""Exercise the authored guide's scalar example, without claiming game parity."""

import json
import re
import shutil
import subprocess

import pytest

from fdisbull.cli import invoke


def test_sweding_reference_is_selectively_discoverable_and_js_rows_match_domain():
    reference = 'references/sweding.md'
    index = invoke('agent-skill', {'index': True})
    assert reference in {guide['reference'] for guide in index['guides']}
    selected = invoke('agent-skill', {'reference': reference})
    assert set(selected['files']) == {reference}
    source, = re.findall(r'```js\n(.*?)\n```', selected['files'][reference], re.S)
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required only to execute the authored JavaScript illustration')
    check = source + '''
const functions = [rowArithmetic, rowBranches, rowLookup];
console.log(JSON.stringify(functions.map(fn =>
    Array.from({length: 9}, (_, cell) => fn(cell)))));
'''
    result = subprocess.run([node, '-e', check], capture_output=True,
                            text=True, timeout=10, check=True)
    assert json.loads(result.stdout) == [[0, 0, 0, 1, 1, 1, 2, 2, 2]] * 3
    assert result.stderr == ''
