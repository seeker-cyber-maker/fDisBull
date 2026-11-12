"""The whole-export runner binds evidence and never upgrades finite observations."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def setup_campaign(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('function_campaign_test', scripts / 'verify_bla_functions.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root, babel = tmp_path / 'target', tmp_path / 'babel'
    root.mkdir(); babel.mkdir()
    pins = {}
    for name in ('template', 'L1', 'L2', 'L3'):
        raw = ('// authored test ' + name).encode()
        relative = name + '.cjs'
        (root / relative).write_bytes(raw)
        pins[name] = (relative, module.digest(raw))
    commitment = {'keySha256': '1' * 64, 'flagSha256': '2' * 64,
                  'artifactSha256': {name: pins[name][1] for name in ('L1', 'L2', 'L3')}}
    raw = json.dumps(commitment).encode()
    (root / 'commitment.json').write_bytes(raw)
    pins['commitment'] = ('commitment.json', module.digest(raw))
    for name in ('parser', 'traverse', 'generator'):
        package = babel / '@babel' / name
        package.mkdir(parents=True)
        (package / 'package.json').write_text(json.dumps({'version': '0.0-authored', 'main': 'index.js'}))
        (package / 'index.js').write_text('// authored analyzer receipt only')
    monkeypatch.setattr(module, 'PINS', pins)
    monkeypatch.setattr(module, 'git', lambda root, *args:
        module.SUPPORTED_COMMIT if args[0] == 'rev-parse' else
        'https://github.com/qybaihe/bla.git' if args[0] == 'config' else '')
    monkeypatch.setattr(module.shutil, 'which', lambda _: '/authored/node')
    calls = []

    def node(command, **kwargs):
        config = json.loads(kwargs['input'])
        calls.append((command, kwargs, config))
        observation = {'node': 'authored-test-driver', 'tiers': [
            {'tier': tier, 'source_sha256': pins[tier][1], 'caller_observations_equal': True,
             'private_heap_effects_equal_to_clean': False, 'actual_crypto_cases': 3,
             'modeled_call_cases': 2, 'static': {'status': 'structural_correspondence_under_assumptions',
                 'mutation_summary': {'mutator_source_sha256': '3' * 64,
                     'totality_assumption': None,
                     'discharged_obligations': ['shadow_heap_shape_preservation', 'shadow_heap_termination'],
                     'noninterference': {'status': 'proved', 'source': {'sha256': pins[tier][1]},
                                         'heap_certificate_sha256': '4' * 64, 'certificate_sha256': '5' * 64},
                     'proof': {'status': 'proved', 'certificate_sha256': '4' * 64,
                               'source': {'sha256': pins[tier][1], 'mutator_sha256': '3' * 64,
                                                          'ast_identity_verified': True},
                               'invariant': {'initialized': True, 'preserved': True},
                               'termination': {'proved': True}}},
                 'whole_function_equivalence': {'status': 'equivalent_under_contract',
                    'noninterference_certificate_sha256': '5' * 64,
                    'functions': [{'role': role} for role in ('sha256Hex','deriveFlagMask','decodeFlagCipher','tryUnlock')],
                    'source': {'target_sha256': pins[tier][1], 'template_sha256': pins['template'][1]}}}}
            for tier in ('L1', 'L2', 'L3')]}
        return subprocess.CompletedProcess(command, 0, module.encoded(observation), b'')

    monkeypatch.setattr(module.subprocess, 'run', node)
    return module, root, babel, calls


def test_report_preserves_claim_ceiling_and_binds_targets_analyzers_and_limits(setup_campaign, monkeypatch):
    runner, root, babel, calls = setup_campaign
    monkeypatch.setenv('NODE_OPTIONS', '--require=unapproved-preload')
    monkeypatch.setenv('NODE_PATH', '/unapproved/modules')
    report = runner.campaign(root, babel)
    command, kwargs, config = calls[0]
    assert command[1] == '--max-old-space-size=256' and kwargs['timeout'] == 60
    assert 'NODE_OPTIONS' not in kwargs['env'] and 'NODE_PATH' not in kwargs['env']
    assert config['commitment'] == {'keySha256': '1' * 64, 'flagSha256': '2' * 64}
    assert report['full_state_equivalence'] is False
    assert report['shadow_heap_obligations']['shape_preservation'] == 'proved'
    assert report['shadow_heap_obligations']['termination'] == 'proved'
    assert 'bla_shadow_heap_proof.cjs' in report['tool_sha256']
    assert 'unrestricted JavaScript contextual equivalence unproved' in report['claim_ceiling']
    assert report['shadow_heap_obligations']['noninterference'] == 'proved'
    assert len(report['observations']['tiers']) == 3
    assert set(report['analyzer_packages']) == {'@babel/parser', '@babel/traverse', '@babel/generator'}
    assert report['report_sha256'] == runner.digest(runner.encoded({
        key: value for key, value in report.items() if key != 'report_sha256'}))


def test_changed_target_is_rejected_before_any_execution(setup_campaign):
    runner, root, babel, calls = setup_campaign
    (root / runner.PINS['L2'][0]).write_text('// changed authored target')
    with pytest.raises(ValueError, match='hash differs'):
        runner.campaign(root, babel)
    assert not calls


def test_changed_commit_is_rejected(setup_campaign, monkeypatch):
    runner, root, babel, calls = setup_campaign
    monkeypatch.setattr(runner, 'git', lambda *_: '0' * 40)
    with pytest.raises(ValueError, match='revision'):
        runner.campaign(root, babel)
    assert not calls


def test_dirty_selected_sources_are_rejected_before_execution(setup_campaign, monkeypatch):
    runner, root, babel, calls = setup_campaign
    original = runner.git
    monkeypatch.setattr(runner, 'git', lambda root, *args:
        ' M L2.cjs' if args[0] == 'status' else original(root, *args))
    with pytest.raises(ValueError, match='Selected source differs'):
        runner.campaign(root, babel)
    assert not calls


@pytest.mark.parametrize('mode', ['missing_tier', 'wrong_source', 'heap_ignored', 'unqualified_static',
                                 'missing_heap_proof', 'proof_wrong_source', 'proof_wrong_mutator', 'assumption_not_discharged',
                                 'unproved_induction', 'unproved_termination', 'unbound_ast',
                                 'missing_noninterference', 'wrong_noninterference_heap', 'unknown_whole_function',
                                 'wrong_whole_function_target', 'wrong_whole_function_template',
                                 'whole_wrong_noninterference', 'partial_function_coverage'])
def test_incomplete_or_inconsistent_driver_evidence_is_rejected(setup_campaign, monkeypatch, mode):
    runner, root, babel, calls = setup_campaign
    original = runner.subprocess.run

    def inconsistent(*args, **kwargs):
        p = original(*args, **kwargs)
        result = json.loads(p.stdout)
        if mode == 'missing_tier':
            result['tiers'].pop()
        elif mode == 'wrong_source':
            result['tiers'][0]['source_sha256'] = '0' * 64
        elif mode == 'heap_ignored':
            result['tiers'][0]['private_heap_effects_equal_to_clean'] = True
        elif mode == 'unqualified_static':
            result['tiers'][0]['static']['status'] = 'unknown'
        else:
            mutation = result['tiers'][0]['static']['mutation_summary']
            if mode == 'missing_heap_proof':
                mutation.pop('proof')
            elif mode == 'proof_wrong_source':
                mutation['proof']['source']['sha256'] = '0' * 64
            elif mode == 'proof_wrong_mutator':
                mutation['proof']['source']['mutator_sha256'] = '0' * 64
            elif mode == 'unproved_induction':
                mutation['proof']['invariant']['preserved'] = False
            elif mode == 'unproved_termination':
                mutation['proof']['termination']['proved'] = False
            elif mode == 'unbound_ast':
                mutation['proof']['source']['ast_identity_verified'] = False
            elif mode == 'missing_noninterference':
                mutation.pop('noninterference')
            elif mode == 'wrong_noninterference_heap':
                mutation['noninterference']['heap_certificate_sha256'] = '0' * 64
            elif mode.startswith('wrong_whole_function_'):
                which = 'target_sha256' if mode.endswith('target') else 'template_sha256'
                result['tiers'][0]['static']['whole_function_equivalence']['source'][which] = '0' * 64
            elif mode == 'unknown_whole_function':
                result['tiers'][0]['static']['whole_function_equivalence']['status'] = 'unknown'
            elif mode == 'whole_wrong_noninterference':
                result['tiers'][0]['static']['whole_function_equivalence']['noninterference_certificate_sha256'] = '0' * 64
            elif mode == 'partial_function_coverage':
                result['tiers'][0]['static']['whole_function_equivalence']['functions'].pop()
            else:
                mutation['totality_assumption'] = 'still assumed'
        p.stdout = runner.encoded(result)
        return p

    monkeypatch.setattr(runner.subprocess, 'run', inconsistent)
    with pytest.raises(ValueError):
        runner.campaign(root, babel)


def test_driver_failure_does_not_publish_stderr_as_a_verified_report(setup_campaign, monkeypatch):
    runner, root, babel, _ = setup_campaign
    monkeypatch.setattr(runner.subprocess, 'run', lambda command, **kwargs:
        subprocess.CompletedProcess(command, 2, b'', b'private diagnostic value'))
    with pytest.raises(ValueError, match='driver failed') as error:
        runner.campaign(root, babel)
    assert 'private diagnostic' not in str(error.value)
