from types import SimpleNamespace
import pytest

from fdisbull import qemu_paged_le_trace_replay as module
from fdisbull.qemu_paged_le_trace_replay import analyze_trace


def setup_case(monkeypatch):
    binding = dict(
        binding_id='b',
        run='r',
        capture_epoch='r:process:1',
        source_sha256='a' * 64,
        version=1,
        version_sha256='c' * 64,
    )
    metadata = dict(
        backend='qemu-dos',
        source_sha256='a' * 64,
        version_sha256='c' * 64,
        machine_configuration=dict(memory_mib=16),
        runtime_inputs={},
    )
    import json

    trace = dict(id='t', run='r', version=1, sha256='d' * 64, run_metadata=json.dumps(metadata))
    bound = dict(
        id='b',
        run='r',
        version=1,
        kind='dos-source-binding',
        sha256='e' * 64,
        size=10,
        name='bind',
        metadata='{}',
    )
    q = dict(
        qualified=True,
        reason=None,
        instruction_size=1,
        execution_bytes='90',
        source_instruction_sha256='f' * 64,
        source_location={'object_offset': 0},
        context={},
    )
    witness = dict(
        cpu={'ip': 0}, context={}, reads=[dict(space='physical', address=0x1000, length=1, hex='90')]
    )
    event = dict(
        sequence=1, registers={}, qualification=q, mapping_identity={'selector': 8}, witness=witness
    )
    doc = dict(
        format='fdisbull-paged-le-trace-1',
        binding=binding,
        binding_artifact=dict(
            artifact='b',
            run='r',
            version=1,
            kind='dos-source-binding',
            sha256='e' * 64,
            size=10,
            name='bind',
            metadata={},
        ),
        events=[event],
        producer={'p': 'v'},
        native_inputs={},
        outcome='count',
    )
    bdoc = dict(format='fdisbull-paged-le-tracking-binding-1', recipe=binding)
    monkeypatch.setattr(
        module, '_artifact', lambda p, key, kind: (trace, doc) if key == 't' else (bound, bdoc)
    )
    monkeypatch.setattr(module, '_capture_sequence', lambda p, row: 1 if row['id'] == 'b' else 2)
    monkeypatch.setattr(module, '_paged_producer', lambda: {'p': 'v'})
    monkeypatch.setattr(
        module,
        '_source',
        lambda *a: (b'source', {k: binding[k] for k in ('source_sha256', 'version', 'version_sha256')}),
    )
    monkeypatch.setattr(module, '_cpu', lambda *a: {'ip': 0})
    monkeypatch.setattr(
        module,
        'replay',
        lambda *a: dict(qualification=q, mapping_identity={'selector': 8}, witness=witness),
    )
    import fdisbull.le

    monkeypatch.setattr(fdisbull.le, 'load_runtime_le_carrier', lambda _: object())
    project = SimpleNamespace(
        meta={'source_sha256': 'a' * 64}, version=lambda _: {'id': 1, 'sha256': 'c' * 64}
    )
    return project, trace, bound, doc, event


def test_replay_requires_matching_witness_and_owned_binding(monkeypatch):
    project, trace, bound, doc, event = setup_case(monkeypatch)
    assert analyze_trace(project, 't')['events'][0]['qualification']['qualified']
    event['mapping_identity'] = {'selector': 16}
    with pytest.raises(ValueError, match='replay differs'):
        analyze_trace(project, 't')
    event['mapping_identity'] = {'selector': 8}
    bound['run'] = 'restored-run'
    with pytest.raises(ValueError, match='identity or binding'):
        analyze_trace(project, 't')


def test_replay_rejects_unbounded_and_fabricated_unknown(monkeypatch):
    project, _, _, doc, event = setup_case(monkeypatch)
    event['witness']['reads'][0]['length'] = 2**31
    with pytest.raises(ValueError, match='witness row'):
        analyze_trace(project, 't')
    event['qualification'] = dict(
        qualified=False,
        reason='outside',
        instruction_size=None,
        execution_bytes='',
        source_instruction_sha256=None,
        source_location={'object_offset': 0},
        context=None,
    )
    event['mapping_identity'] = event['witness'] = None
    with pytest.raises(ValueError, match='Unknown event'):
        analyze_trace(project, 't')


def test_binding_receipt_is_exact_and_empty_error_is_explicit(monkeypatch):
    project, _, _, doc, _ = setup_case(monkeypatch)
    doc['binding_artifact']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='artifact reference'):
        analyze_trace(project, 't')
    doc['binding_artifact']['sha256'] = 'e' * 64
    doc['events'] = []
    with pytest.raises(ValueError, match='no recorded error'):
        analyze_trace(project, 't')
    doc['error'] = 'read failed'
    result = analyze_trace(project, 't')
    assert result['events'] == [] and result['error'] == 'read failed'
