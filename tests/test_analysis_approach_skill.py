"""The investigation decision guide is discoverable without opening a project."""
import json

from fdisbull.cli import invoke, main, respond

REFERENCE = 'references/analysis-approach.md'


def test_approach_reference_is_indexed_and_selectively_available(capsys):
    index = invoke('agent-skill', {'index': True})
    item = next(row for row in index['guides'] if row['reference'] == REFERENCE)
    assert item['purpose']
    result = respond({'method': 'agent-skill', 'params': {'reference': REFERENCE}},
                     default_project='/not-a-project')
    assert result['ok'] and set(result['result']['files']) == {REFERENCE}
    content = result['result']['files'][REFERENCE]
    assert 'Pac-Man-like' in content and 'Shadowrun-style field encounter' in content
    assert main(['agent-skill', '--reference', REFERENCE]) == 0
    assert json.loads(capsys.readouterr().out)['result']['files'][REFERENCE] == content


def test_entrypoint_routes_to_approach_without_fetching_all_references():
    result = invoke('agent-skill', {'reference': 'SKILL.md'})
    assert set(result['files']) == {'SKILL.md'}
    assert f']({REFERENCE})' in result['files']['SKILL.md']
