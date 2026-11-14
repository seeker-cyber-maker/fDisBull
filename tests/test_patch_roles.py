"""An observed API role is useful context, never an intent verdict."""
from copy import deepcopy

import pytest

from fdisbull.behavior_diff import compare_trace_topology
from fdisbull.debug_semantics import PE_TRACE_SEMANTICS
from fdisbull.patch_roles import compare_divergent_import_roles, observed_pe_import_roles
from fdisbull.project import Project as FDBProject
from test_platform_review import _pe_caller


class Project:
    arch = 'x86'
    bits = 64

    def __init__(self, name='ReadFile', source='a' * 64, version_hash='b' * 64):
        self.meta = {'format': 'PE', 'source_sha256': source}
        self.version_hash = version_hash
        self.code = {'0x101': 'e800000000'}
        self.analysis = {
            'state': 'done', 'stale': False, 'version': 1, 'context': 'x86:64:little',
            'address': '0x100', 'result': {
                'version': 1, 'context': 'x86:64:little', 'budget_exhausted': False,
                'import_calls': [{
                    'source_address': '0x101', 'source_context': 'x86:64:little',
                    'slot': '0x1000', 'stub': None, 'module': 'KERNEL32.dll', 'name': name,
                    'identity_basis': 'declared_import_metadata',
                    'binding_unchanged_under_static_state': True,
                    'evidence': 'declared import binding and native call target',
                }],
            },
        }

    def version(self, version):
        assert version == 1
        return {'sha256': self.version_hash}

    def function_analysis(self, address, version):
        assert address == 0x100 and version == 1
        return self.analysis

    def disassembly(self, address, lines, version):
        assert lines == 1 and version == 1
        return {'instructions': [{'address': hex(address), 'bytes': self.code[hex(address)],
                                  'context': 'x86:64:little'}] if hex(address) in self.code else []}


def trace(project, site='0x101', code='e800000000'):
    return {'mapping': {'backend': 'wine-qemu', 'bits': project.bits,
                        'source_sha256': project.meta['source_sha256'],
                        'version_sha256': project.version_hash},
            'version': 1, 'semantics': PE_TRACE_SEMANTICS,
            'events': [{'address': site, 'project_address': site, 'bytes': code,
                        'identity': {'source_version': 1, 'context': 'flat',
                                     'project_address': site, 'runtime_address': site}}]}


def test_observed_call_role_is_bound_to_owning_project_and_remains_conditional():
    project = Project()
    result = observed_pe_import_roles(project, 0x100, trace(project))
    assert result['roles'][0]['status'] == 'candidate'
    assert result['roles'][0]['api'] == {'module': 'KERNEL32.dll', 'name': 'ReadFile'}
    assert result['roles'][0]['observed_call_instruction'] is True
    assert result['semantic_equivalence'] is None
    assert 'arguments and effects unverified' in result['roles'][0]['scope']

    other = Project(source='c' * 64)
    with pytest.raises(ValueError, match='owning PE project'):
        observed_pe_import_roles(other, 0x100, trace(project))
    other = Project(version_hash='c' * 64)
    with pytest.raises(ValueError, match='code version'):
        observed_pe_import_roles(other, 0x100, trace(project))


def test_changed_code_ambiguous_binding_noncall_and_stale_analysis_do_not_resolve():
    project = Project()
    changed = trace(project)
    changed['events'][0].update(execution_bytes='e800000000', ram_bytes='e801000000')
    assert observed_pe_import_roles(project, 0x100, changed)['roles'][0]['status'] == 'unresolved'
    project.analysis['result']['import_calls'].append(deepcopy(project.analysis['result']['import_calls'][0]))
    assert observed_pe_import_roles(project, 0x100, trace(project))['roles'][0]['binding_count'] == 2
    assert observed_pe_import_roles(project, 0x100, trace(project))['roles'][0]['status'] == 'unresolved'
    project.analysis['result']['import_calls'].pop()
    assert observed_pe_import_roles(project, 0x100, trace(project, code='90'))['roles'][0]['status'] == 'unresolved'
    assert observed_pe_import_roles(project, 0x100, trace(project, code='e801000000'))['roles'][0]['status'] == 'unresolved'
    project.analysis['stale'] = True
    with pytest.raises(ValueError, match='non-stale'):
        observed_pe_import_roles(project, 0x100, trace(project))


def test_same_bytes_different_api_and_different_bytes_same_api_stay_candidates():
    project = Project()
    second = deepcopy(project.analysis['result']['import_calls'][0])
    second['source_address'] = '0x105'
    project.analysis['result']['import_calls'].append(second)
    project.code['0x105'] = 'ff1500000000'
    left_trace = trace(project)
    right_trace = trace(project, site='0x105', code='ff1500000000')
    for data in (left_trace, right_trace):
        first, last = deepcopy(data['events'][0]), deepcopy(data['events'][0])
        for event, site in ((first, '0x100'), (last, '0x110')):
            event['address'] = event['project_address'] = site
            event['identity'] = {'source_version': 1, 'context': 'flat',
                                 'project_address': site, 'runtime_address': site}
            event['bytes'] = '90'
        data['events'] = [first, data['events'][0], last]
    topology = compare_trace_topology(left_trace, right_trace, same_source=True)
    assert topology['segments'][1]['kind'] == 'divergent'
    left_roles = observed_pe_import_roles(project, 0x100, left_trace)
    right_roles = observed_pe_import_roles(project, 0x100, right_trace)
    comparison = compare_divergent_import_roles(left_trace, right_trace, left_roles, right_roles,
                                                 same_source=True)
    assert comparison['segments'][0]['relation'] == 'shared_api_role_candidate'
    assert comparison['segments'][0]['semantic_equivalence'] is None
    assert comparison['segments'][0]['arguments'] == 'uncompared'
    assert comparison['segments'][0]['ordered_effects'] == 'uncompared'
    second['name'] = 'WriteFile'
    right_trace['events'][1]['bytes'] = 'e800000000'
    project.code['0x105'] = 'e800000000'
    right_roles = observed_pe_import_roles(project, 0x100, right_trace)
    assert compare_divergent_import_roles(left_trace, right_trace, left_roles, right_roles,
                                          same_source=True)['segments'][0]['relation'] == 'different_api_role'
    with pytest.raises(ValueError, match='cover'):
        compare_divergent_import_roles(left_trace, right_trace, left_roles,
            {**right_roles, 'coverage': {**right_roles['coverage'], 'trace_events': 2}},
            same_source=True)


def test_partial_alignment_cannot_promote_api_role_relation():
    project = Project()
    first = trace(project)
    role = observed_pe_import_roles(project, 0x100, first)
    with pytest.raises(ValueError, match='Complete topology'):
        compare_divergent_import_roles(first, first, role, role)
    altered = deepcopy(first)
    altered['events'][0]['bytes'] = '90'
    with pytest.raises(ValueError, match='exact supplied traces'):
        compare_divergent_import_roles(first, altered, role, role, same_source=True)


def test_role_projection_uses_real_project_analysis_and_stored_pe_instruction(tmp_path):
    source, entry, _, _ = _pe_caller(tmp_path)
    with FDBProject.create(tmp_path / 'conditional.fdb', source) as project:
        assert project.auto_analyze()['stable']
        call, = project.function_analysis(entry)['result']['import_calls']
        site = call['source_address']
        instruction, = project.disassembly(address=site, lines=1)['instructions']
        raw = {'mapping': {'backend': 'wine-qemu', 'bits': project.bits,
                           'source_sha256': project.meta['source_sha256'],
                           'version_sha256': project.version(1)['sha256']},
               'version': 1, 'semantics': PE_TRACE_SEMANTICS,
               'events': [{'address': site, 'project_address': site,
                           'bytes': instruction['bytes'],
                           'identity': {'source_version': 1, 'context': 'flat',
                                        'project_address': site, 'runtime_address': site}}]}
        role, = observed_pe_import_roles(project, entry, raw)['roles']
        assert role['status'] == 'candidate'
        assert role['execution_matches_analyzed_code'] is True
        assert role['api'] == {'module': 'KERNEL32.dll', 'name': 'memset'}
