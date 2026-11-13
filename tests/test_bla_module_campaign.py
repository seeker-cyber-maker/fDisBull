"""A complete receipt retains counterexamples and cannot invent acceptance."""
import copy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def receipts(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location('module_campaign_test', scripts / 'verify_bla_modules.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    fingerprint = {'node': 'authored', 'openssl': 'authored', 'fips': 0,
                   'executable_sha256': '1' * 64}
    labels = ['missing', 'empty', 'short', 'min_length_wrong_key', 'max_length_wrong_key',
              'too_long', 'unicode_wrong_key', 'honeypot', 'ordinary_wrong_key']
    core = {'whole_function_equivalence': {'certificate_sha256': '2' * 64},
            'seed_invariant_proof': {'certificate_sha256': '3' * 64},
            'mutation_summary': {'proof': {'certificate_sha256': '4' * 64}}}
    functions = {'observations': {'provider_validation': {'runtime': fingerprint},
                 'tiers': [{'tier': tier, 'static': copy.deepcopy(core)} for tier in ('L1', 'L2', 'L3')]}}
    reference_hash, getter_hash = '5' * 64, '6' * 64

    def observation(source_hash, target=False):
        delta = [{'key': {'kind': 'string', 'name_sha256': getter_hash}, 'change': 'added',
                  'after': {'kind': 'accessor', 'enumerable': False, 'configurable': True,
                            'get': {'type': 'function'}}}] if target else []
        return {'module': {'exit_status': 0, 'stdout_bytes': 0, 'stderr_bytes': 0,
                    'observation': {'source_sha256': source_hash,
                        'initialization_global_descriptor_delta': delta,
                        'rows': [{'input_class': label, 'result_kind': 'return', 'result_type': 'null',
                                  'flag_commitment_matches': False} for label in labels]}},
                'cli': [{'input_class': label, 'exit_status': 1, 'flag_commitment_matches': False,
                         'native_cli_dispatch_returned': False, 'equal_to_reference': True} for label in labels],
                'rejection_paths_verified': True, 'real_valid_key_acceptance_verified': False}

    runtime = {'schema': 'bla-native-module-cli-v1',
               'status': 'verified_finite_rejections_real_acceptance_pending',
               'witness': {'status': 'missing', 'real_valid_key_verified': False},
               'runtime': fingerprint, 'reference_source_sha256': reference_hash,
               'loader_sha256': runner.digest((scripts / 'bla_module_runtime.cjs').read_bytes()),
               'provider_substitutions': False, 'function_bodies_rewritten': False,
               'target_observer_suffix': False, 'rejection_paths_verified': True,
               'all_cli_observations_equal': True, 'all_module_observations_equal': False,
               'cases_per_cli': len(labels), 'real_valid_key_acceptance_verified': False,
               'reference': observation(reference_hash), 'targets': []}
    modules = {'format': 'fdisbull-bla-module-driver-1', 'template_sha256': runner.PINS['template'][1],
               'reference_sha256': reference_hash, 'proofs': [], 'runtime': runtime}
    for tier in ('L1', 'L2', 'L3'):
        proof = {'status': 'different', 'certificate_sha256': '7' * 64,
                 'source': {'target_sha256': runner.PINS[tier][1], 'template_sha256': runner.PINS['template'][1]},
                 'selected_function_equivalence': {'certificate_sha256': '2' * 64},
                 'initialization': {'status': 'different', 'all_executed_initializers_classified': True,
                                    'global_effects': [{'property_name_sha256': getter_hash}]},
                 'cli': {'status': 'equivalent_under_contract',
                         'termination': {'post_dispatch_initializers_unreachable': True},
                         'initialization_prefix': {'seed_certificate_sha256': '3' * 64,
                                                   'heap_certificate_sha256': '4' * 64}}}
        modules['proofs'].append({'tier': tier, 'proof': proof})
        target = observation(runner.PINS[tier][1], True)
        target.update(tier=tier, source_sha256=runner.PINS[tier][1], function_results_equal=True,
                      cli_observations_equal=True, module_observations_equal=False,
                      initialization_global_effects_equal=False, export_reflection_equal=False)
        runtime['targets'].append(target)
    return runner, modules, functions


def test_complete_rejection_receipt_keeps_module_difference_and_missing_key(receipts):
    runner, modules, functions = receipts
    runner.validate_modules(modules, functions)
    assert modules['runtime']['witness']['status'] == 'missing'
    assert all(item['proof']['status'] == 'different' for item in modules['proofs'])


@pytest.mark.parametrize('defect', [
    'missing_tier', 'changed_source', 'unknown_init', 'promoted_module', 'stale_core',
    'stale_seed', 'reachable_tail', 'provider_substitution', 'runtime_mismatch',
    'false_acceptance', 'fake_verified_witness', 'missing_case', 'wrong_exit',
    'wrong_return', 'cli_mismatch', 'missing_getter', 'wrong_getter', 'global_erasure',
])
def test_incomplete_or_promoted_evidence_is_rejected(receipts, defect):
    runner, modules, functions = receipts
    proof = modules['proofs'][0]['proof']
    runtime, target = modules['runtime'], modules['runtime']['targets'][0]
    if defect == 'missing_tier': modules['proofs'].pop()
    elif defect == 'changed_source': proof['source']['target_sha256'] = '0' * 64
    elif defect == 'unknown_init': proof['initialization']['status'] = 'unknown'
    elif defect == 'promoted_module': proof['status'] = 'equivalent_under_contract'
    elif defect == 'stale_core': proof['selected_function_equivalence']['certificate_sha256'] = '0' * 64
    elif defect == 'stale_seed': proof['cli']['initialization_prefix']['seed_certificate_sha256'] = '0' * 64
    elif defect == 'reachable_tail': proof['cli']['termination']['post_dispatch_initializers_unreachable'] = False
    elif defect == 'provider_substitution': runtime['provider_substitutions'] = True
    elif defect == 'runtime_mismatch': runtime['runtime'] = {**runtime['runtime'], 'node': 'other'}
    elif defect == 'false_acceptance': runtime['real_valid_key_acceptance_verified'] = True
    elif defect == 'fake_verified_witness':
        runtime['witness'] = {'status': 'verified_against_real_native_implementations', 'real_valid_key_verified': True}
    elif defect == 'missing_case': target['cli'].pop()
    elif defect == 'wrong_exit': target['cli'][0]['exit_status'] = 0
    elif defect == 'wrong_return': target['module']['observation']['rows'][0]['result_type'] = 'string'
    elif defect == 'cli_mismatch': target['cli'][0]['equal_to_reference'] = False
    elif defect == 'missing_getter': target['module']['observation']['initialization_global_descriptor_delta'] = []
    elif defect == 'wrong_getter':
        target['module']['observation']['initialization_global_descriptor_delta'][0]['key']['name_sha256'] = '0' * 64
    elif defect == 'global_erasure': target['initialization_global_effects_equal'] = True
    with pytest.raises(ValueError):
        runner.validate_modules(modules, functions)
