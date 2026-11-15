"""Projectless public CLI/JSON scaffold round trips using authored stories."""
import json

from fdisbull.cli import invoke, respond
from fdisbull.output_limits import OutputPolicy, output_policy_context
from tests.test_dos_udc_cli import cli
from tests.test_zmachine_udc import story, edit


def test_zmachine_cli_capture_and_compile_expected_old_experiment(tmp_path):
    source = tmp_path / 'STORY'; source.write_bytes(story())
    run, capture = cli('zmachine-udc-capture', source)
    assert run.returncode == 0 and capture['ok'], capture
    definition = tmp_path / 'definition.json'
    definition.write_text(json.dumps(capture['result']))
    run, exact = cli('zmachine-udc-compile', definition)
    assert run.returncode == 0 and exact['ok'], exact
    assert bytes.fromhex(exact['result']['bytes']) == source.read_bytes()
    edits = tmp_path / 'edits.json'; edits.write_text(json.dumps([edit()]))
    assertions = tmp_path / 'assumptions.json'
    assertions.write_text(json.dumps({'no_code_data_alias': True, 'scalar_values_not_addresses': True}))
    run, changed = cli('zmachine-udc-compile', definition, '--mode', 'experiment',
                       '--edits', edits, '--assumptions', assertions)
    assert run.returncode == 0 and changed['ok'], changed
    result = changed['result']; raw = bytes.fromhex(result['bytes'])
    assert raw[900:904] == bytes.fromhex('14010310')
    assert result['qualification'] == 'unverified_experiment'
    assert not result['native_execution'] and not result['equivalence_proven']
    assert int.from_bytes(raw[28:30], 'big') == sum(raw[64:1024]) & 0xffff


def test_zmachine_json_is_projectless_and_rejects_unknown_or_ambiguous_arguments(tmp_path):
    path = tmp_path / 'input'; path.write_bytes(story())
    spec = invoke('zmachine-udc-capture', {'path': str(path)})
    result = invoke('zmachine-udc-compile', {'definition': spec})
    assert result['byte_identity']
    file = tmp_path / 'definition.json'; file.write_text(json.dumps(spec))
    for params in ({'definition': spec, 'definition_file': str(file)},
                   {'definition': spec, 'unknown': True}):
        reply = respond({'method': 'zmachine-udc-compile', 'params': params})
        assert reply['ok'] is False


def test_large_capture_spills_and_source_identity_is_retrievable_without_project(tmp_path):
    path = tmp_path / 'large-story'; path.write_bytes(story(padding=bytes(8192)))
    policy = OutputPolicy(4096, artifact_dir=tmp_path / 'outputs')
    with output_policy_context(policy):
        reply = respond({'method': 'zmachine-udc-capture', 'params': {'path': str(path)}},
                         default_project='/nonexistent')
        assert reply['ok'] and reply['result']['format'] == 'fdisbull-output-ref-1'
        assert not reply['result']['complete']
        ident = reply['result']['artifact']['id']
        selected = respond({'method': 'output-select', 'params': {
            'artifact': ident, 'pointer': '/result/source_sha256'}}, default_project='/nonexistent')
        assert selected['ok'] and selected['result']['complete']
        assert selected['result']['value'] == invoke('zmachine-udc-capture', {'path': str(path)})['source_sha256']
        assert len(policy.render(reply).encode()) + 1 <= 4096
