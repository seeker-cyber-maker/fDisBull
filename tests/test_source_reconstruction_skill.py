"""Source-reconstruction guidance stays available through selective skill reads.

These are documentation/discovery checks, not reconstruction or compiler tests.
No external repository, game input, network or toolchain is used.
"""

import re

import pytest

from fdisbull.cli import invoke


REFERENCE = 'references/recovery-research.md'
CIVD_PIN = 'c425f7ba45411111c7c71d926e1ce8d4fa641571'


def read_reference(reference):
    result = invoke('agent-skill', {'reference': reference})
    assert result['name'] == 'fdisbull-investigate'
    assert set(result['files']) == {reference}
    return result['files'][reference]


def test_entrypoint_routes_source_reconstruction_to_existing_reference():
    text = read_reference('SKILL.md')
    assert 'source-reconstruction reuse' in text
    assert text.count(f']({REFERENCE})') == 1
    assert 'independent recovery arm' in text
    index = invoke('agent-skill', {'index': True})
    assert REFERENCE in {row['reference'] for row in index['guides']}


@pytest.mark.parametrize('heading', [
    '## Reuse reconstructed source',
    '### Discover and classify',
    '### Establish correspondence without laundering claims',
    '### Turn results into executable definitions',
    '### Keep three reuse modes measurable',
])
def test_reconstruction_workflow_is_selectively_retrievable(heading):
    text = read_reference(REFERENCE)
    assert heading in text
    assert len(text.encode('utf-8')) < 65536


def test_workflow_retains_evidence_and_import_boundaries():
    text = ' '.join(read_reference(REFERENCE).split())
    for phrase in (
        'upstream-reported', 'input-matched', 'locally-rebuilt',
        'source-bound', 'semantically-qualified',
        'raw linker output and post-link edits separate',
        'not a general importer for arbitrary reconstructed C',
        'source/backing, backing/UIL and UIL/target relationships separately',
    ):
        assert phrase in text
    for mode in ('Independent recovery', 'Notes-assisted recovery', 'Results-derived definitions'):
        assert mode in text


def test_civd_example_is_edition_pinned_and_attributed():
    text = read_reference(REFERENCE)
    links = re.findall(r'\]\((https://github\.com/sjmelia/civd/[^)]+)\)', text)
    assert len(links) == 4
    assert all(CIVD_PIN in link for link in links)
    assert 'release/474.01' in text and '474.05' in text
    assert 'OpenCiv1' in text and 'attributed upstream reports' in text
