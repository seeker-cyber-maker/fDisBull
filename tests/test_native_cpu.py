import pytest

from fdisbull.native_cpu import FORMAT, inspect_native_cpu


def schema(targets=('x86_64',)):
    return [
        # QEMU's live schema uses numeric type IDs, not stable type names.
        {'name': '531', 'meta-type': 'enum', 'members': [{'name': v} for v in targets]},
        {'name': '205', 'meta-type': 'object',
         'members': [{'name': 'arch', 'type': '531'}]},
        {'name': 'CpuInfoFastBase', 'meta-type': 'object',
         'members': [{'name': 'qom-path', 'type': 'str'},
                     {'name': 'target', 'type': '531'}]},
        {'name': 'CpuInfoFast', 'meta-type': 'object', 'base': 'CpuInfoFastBase',
         'variants': [{'case': 's390x', 'type': 'CpuInfoS390'}]},
        {'name': 'CpuInfoFastList', 'meta-type': 'array', 'element-type': 'CpuInfoFast'},
        {'name': 'CpuInfoS390', 'meta-type': 'object', 'members': []},
        {'name': 'ObjectPropertyInfo', 'meta-type': 'object',
         'members': [{'name': 'name', 'type': 'str'}, {'name': 'type', 'type': 'str'}]},
        {'name': 'ObjectPropertyInfoList', 'meta-type': 'array',
         'element-type': 'ObjectPropertyInfo'},
        {'name': 'StatusInfo', 'meta-type': 'object',
         'members': [{'name': 'status', 'type': 'str'}]},
        {'name': 'query-target', 'meta-type': 'command', 'ret-type': '205'},
        {'name': 'query-cpus-fast', 'meta-type': 'command', 'ret-type': 'CpuInfoFastList'},
        {'name': 'qom-list', 'meta-type': 'command', 'ret-type': 'ObjectPropertyInfoList'},
        {'name': 'query-status', 'meta-type': 'command', 'ret-type': 'StatusInfo'},
    ]


class QMP:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def call(self, command, arguments=None, *, timeout_ms, max_reply_bytes=8 * 1024 * 1024):
        self.calls.append((command, arguments, timeout_ms, max_reply_bytes))
        value = self.replies[command]
        if callable(value):
            return value(arguments)
        if isinstance(value, BaseException):
            raise value
        return value


def qmp_replies(schema_rows, **overrides):
    result = {
        'query-qmp-schema': schema_rows,
        'query-target': {'arch': 'x86_64'},
        'query-cpus-fast': [{'cpu-index': 0, 'qom-path': '/machine/unattached/device[0]',
                             'thread-id': 1234, 'target': 'x86_64'}],
        'query-status': {'running': False, 'status': 'paused'},
        'qom-list': [],
    }
    result.update(overrides)
    return result


def test_supported_target_uses_raw_standard_qmp_fields():
    target = {'arch': 'x86_64'}
    cpus = [{'cpu-index': 0, 'qom-path': '/machine/unattached/device[0]',
             'thread-id': 1234, 'target': 'x86_64'}]
    status = {'running': False, 'status': 'paused'}
    qmp = QMP(qmp_replies(schema(), **{'query-target': target,
                                      'query-cpus-fast': cpus,
                                      'query-status': status}))

    result = inspect_native_cpu(qmp, expected_target='x86_64', timeout_ms=500)

    assert result == {
        'format': FORMAT, 'expected_target': 'x86_64',
        'expected_target_source': 'caller-declared', 'expected_cpu_type': None,
        'target': target, 'target_source': 'qmp', 'cpus': cpus,
        'cpu_paths': ['/machine/unattached/device[0]'],
        'cpu_source': 'query-cpus-fast', 'qom_cpu_children': [],
        'status': status, 'status_source': 'qmp',
    }
    assert [call[0] for call in qmp.calls] == [
        'query-qmp-schema', 'query-target', 'query-cpus-fast', 'query-status']
    assert qmp.calls[0][3] == 4 * 1024 * 1024
    assert all(1 <= call[2] <= 500 for call in qmp.calls)
    assert 'pc' not in result['cpus'][0]
    assert 'registers' not in result['cpus'][0]


def test_chip8_missing_target_enum_uses_one_level_qom_without_qapi_union_calls():
    properties = [
        {'name': 'device[0]', 'type': 'child<chip8-cpu>'},
        {'name': 'memory', 'type': 'link<memory-region>'},
        {'name': 'device[1]', 'type': 'child<virtio-device>'},
    ]
    qmp = QMP(qmp_replies(schema(), **{
        'query-qmp-schema': schema(('x86_64',)),
        'query-target': AssertionError('unsafe query-target must not be issued'),
        'query-cpus-fast': AssertionError('unsafe query-cpus-fast must not be issued'),
        'qom-list': properties,
        'query-status': {'running': False, 'status': 'paused'},
    }))

    result = inspect_native_cpu(qmp, expected_target='chip8',
                                expected_cpu_type='chip8-cpu')

    assert result['expected_target'] == 'chip8'
    assert result['expected_target_source'] == 'caller-declared'
    assert result['target'] is None and result['target_source'] is None
    assert result['cpus'] is None and result['cpu_source'] == 'qom-list'
    assert result['qom_cpu_children'] == [{
        'qom_path': '/machine/unattached/device[0]', 'property': properties[0]}]
    assert result['cpu_paths'] == ['/machine/unattached/device[0]']
    assert result['status'] == {'running': False, 'status': 'paused'}
    names = [call[0] for call in qmp.calls]
    assert names == ['query-qmp-schema', 'qom-list', 'query-status']
    assert qmp.calls[1][1] == {'path': '/machine/unattached'}


def test_expected_cpu_type_filters_qom_children_without_synthetic_cpu_fields():
    properties = [{'name': 'device[0]', 'type': 'child<other-cpu>'},
                  {'name': 'device[1]', 'type': 'child<chip8-cpu>'}]
    qmp = QMP(qmp_replies(schema(), **{
        'query-qmp-schema': schema(('x86_64',)),
        'qom-list': properties,
    }))
    result = inspect_native_cpu(qmp, expected_target='chip8',
                                expected_cpu_type='chip8-cpu')
    assert result['expected_cpu_type'] == 'chip8-cpu'
    assert result['qom_cpu_children'] == [{
        'qom_path': '/machine/unattached/device[1]', 'property': properties[1]}]
    assert result['cpu_paths'] == ['/machine/unattached/device[1]']
    assert not any(key in result['qom_cpu_children'][0] for key in ('pc', 'registers', 'cpu-index'))


def test_standard_cpu_query_requires_target_enum_in_its_own_return_graph():
    rows = [row for row in schema(('x86_64',))
            if row['name'] not in ('SysEmuTarget', 'TargetInfo', 'CpuInfoFastBase')]
    rows = [dict(row) for row in rows]
    rows = [row for row in rows if row['name'] not in ('query-target', 'query-cpus-fast')]
    rows.extend([
        {'name': 'TargetInfo', 'meta-type': 'object', 'members': []},
        {'name': 'CpuInfoFastBase', 'meta-type': 'object',
         'members': [{'name': 'qom-path', 'type': 'str'}]},
        {'name': 'query-target', 'meta-type': 'command', 'ret-type': 'TargetInfo'},
        {'name': 'query-cpus-fast', 'meta-type': 'command', 'ret-type': 'CpuInfoFastList'},
    ])
    qmp = QMP(qmp_replies(rows, **{
        'query-qmp-schema': rows,
        'query-target': AssertionError('missing target enum is not proof of safety'),
        'query-cpus-fast': AssertionError('missing target enum is not proof of safety'),
    }))

    result = inspect_native_cpu(qmp, expected_target='x86_64')

    assert result['target'] is None
    assert result['cpus'] is None and result['cpu_source'] == 'qom-list'
    assert [call[0] for call in qmp.calls] == ['query-qmp-schema', 'qom-list', 'query-status']


def test_agi_schema_enum_allows_standard_native_qmp_inspection():
    target = {'arch': 'agi'}
    cpus = [{'cpu-index': 0, 'qom-path': '/machine/unattached/device[0]',
             'thread-id': 99, 'target': 'agi'}]
    qmp = QMP(qmp_replies(schema(('agi',)), **{
        'query-target': target, 'query-cpus-fast': cpus,
    }))
    result = inspect_native_cpu(qmp, expected_target='agi', expected_cpu_type='agi-cpu')
    assert result['target'] == target and result['target_source'] == 'qmp'
    assert result['cpus'] == cpus and result['cpu_source'] == 'query-cpus-fast'
    assert [call[0] for call in qmp.calls] == [
        'query-qmp-schema', 'query-target', 'query-cpus-fast', 'query-status']


def test_schema_gate_checks_nested_return_types():
    rows = schema(('x86_64',))
    rows.append({'name': 'Wrapper', 'meta-type': 'object',
                 'members': [{'name': 'nested', 'type': 'TargetInfo'}]})
    rows.append({'name': 'query-nested', 'meta-type': 'command', 'ret-type': 'Wrapper'})
    qmp = QMP(qmp_replies(rows, **{
        'query-qmp-schema': rows,
        'query-nested': {},
    }))
    result = inspect_native_cpu(qmp, expected_target='chip8')
    assert [call[0] for call in qmp.calls] == [
        'query-qmp-schema', 'qom-list', 'query-status']


def test_cpu_target_field_must_reference_same_numeric_enum_as_query_target():
    rows = schema(('x86_64',))
    rows.append({'name': '999', 'meta-type': 'enum', 'members': [{'name': 'x86_64'}]})
    base = next(row for row in rows if row['name'] == 'CpuInfoFastBase')
    base['members'][1]['type'] = '999'
    qmp = QMP(qmp_replies(rows, **{
        'query-qmp-schema': rows,
        'query-cpus-fast': AssertionError('different enum identity must fail closed'),
    }))
    result = inspect_native_cpu(qmp, expected_target='x86_64')
    assert result['target_source'] == 'qmp'
    assert result['cpus'] is None and result['cpu_source'] == 'qom-list'
    assert [call[0] for call in qmp.calls] == [
        'query-qmp-schema', 'query-target', 'qom-list', 'query-status']


def test_unrelated_false_friend_enum_cannot_enable_unknown_target():
    rows = schema(('x86_64',))
    rows.append({'name': '999', 'meta-type': 'enum', 'members': [{'name': 'chip8'}]})
    rows.append({'name': 'Unrelated', 'meta-type': 'object',
                 'members': [{'name': 'mode', 'type': '999'}]})
    qmp = QMP(qmp_replies(rows, **{
        'query-qmp-schema': rows,
        'query-target': AssertionError('false-friend enum is not target schema'),
        'query-cpus-fast': AssertionError('false-friend enum is not CPU schema'),
    }))
    result = inspect_native_cpu(qmp, expected_target='chip8')
    assert result['target'] is None and result['cpus'] is None
    assert result['cpu_source'] == 'qom-list'
    assert [call[0] for call in qmp.calls] == [
        'query-qmp-schema', 'qom-list', 'query-status']


def test_malformed_schema_and_qom_data_fail_closed():
    with pytest.raises(ValueError):
        inspect_native_cpu(QMP(qmp_replies([{}])), expected_target='chip8')
    qmp = QMP(qmp_replies(schema(), **{
        'query-qmp-schema': schema(('x86_64',)), 'qom-list': [None],
    }))
    with pytest.raises(ValueError, match='qom-list'):
        inspect_native_cpu(qmp, expected_target='chip8')


def test_all_qmp_calls_share_one_absolute_deadline(monkeypatch):
    import fdisbull.native_cpu as native_cpu

    now = [0.0]
    monkeypatch.setattr(native_cpu.time, 'monotonic', lambda: now[0])

    class AdvancingQMP(QMP):
        def call(self, command, arguments=None, *, timeout_ms, max_reply_bytes=8 * 1024 * 1024):
            result = super().call(command, arguments, timeout_ms=timeout_ms,
                                  max_reply_bytes=max_reply_bytes)
            now[0] += 0.1
            return result

    qmp = AdvancingQMP(qmp_replies(schema()))
    inspect_native_cpu(qmp, expected_target='x86_64', timeout_ms=500)
    budgets = [call[2] for call in qmp.calls]
    assert budgets[:3] == [500, 400, 300]
    assert 199 <= budgets[3] <= 200


@pytest.mark.parametrize('kwargs', [
    {'expected_target': ''},
    {'expected_target': 4},
    {'expected_target': 'x86_64', 'expected_cpu_type': ''},
    {'expected_target': 'x86_64', 'timeout_ms': 0},
])
def test_invalid_inspection_identity_or_timeout_is_rejected(kwargs):
    with pytest.raises(ValueError):
        inspect_native_cpu(QMP({}), **kwargs)
