import importlib.util
import hashlib
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / 'examples' / 'recovery' / 'benchmark_asm_c_engines.py'
SPEC = importlib.util.spec_from_file_location('benchmark_asm_c_engines', SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def c_matching_source(lift):
    raw = bytes.fromhex(lift['source'])
    if raw.startswith(bytes.fromhex('b86400')):
        return '\n'.join(['ax = 100;'] + ['ax += 1;'] * (len(raw) - 3))
    return '\n'.join(f'ax += 200;\nax -= 1;' for _ in range(len(raw) // 4))


def test_report_schema_and_unknown_unconfigured_ghidra(monkeypatch):
    def fake_asm_to_c(lift, *, engine, analyze_headless=None, java_home=None, timeout_s=120):
        assert lift['source_kind'] == 'asm16'
        return {'text': c_matching_source(lift)}

    monkeypatch.setattr(benchmark, 'asm_to_c', fake_asm_to_c)
    monkeypatch.setattr(benchmark, '_tool_identity', lambda path, java: {
        'analyze_headless': path, 'java_home': java, 'java': None, 'ghidra_version': None})
    report = benchmark.run(repeats=1)

    assert report['format'] == 'fdisbull-asm-c-engine-benchmark-1'
    assert len(report['cases']) == 3
    assert [case['instruction_count'] for case in report['cases']] == [2, 16, 2]
    assert all(bytes.fromhex(case['source_hex']).startswith(bytes.fromhex('b86400'))
               for case in report['cases'][:2])
    assert report['cases'][2]['case_kind'] == 'input_dependent_ax_comparison'
    assert bytes.fromhex(report['cases'][2]['source_hex']) == bytes.fromhex('05c80048')
    assert 'game recovery' in report['method']['limitation']
    assert 'synthetic MZ' in report['method']['setup']
    assert 'fail closed as unknown' in report['method']['limitation']
    for case in report['cases']:
        assert len(case['source_sha256']) == 64
        assert case['bindings'] == {'ax': '$value'}
        assert case['outputs'] == ['ax']
        assert case['engines']['builtin']['status'] == 'measured'
        # Solver availability is environment-dependent and must stay visible.
        assert case['engines']['builtin']['equivalence'] in (
            'equivalent_under_assumptions', 'unavailable', 'unknown')
        assert 'cold_end_to_end' not in case['engines']['builtin']['timings']
        assert case['engines']['builtin']['timings']['warm_in_process']['repeats'] == 1
        assert case['engines']['ghidra'] == {
            'status': 'unknown', 'reason': 'analyze_headless was not supplied'}
        assert case['outputs_identical'] is None
        assert case['equivalence_gate'] == 'unknown'
        assert case['observed_request_latency_ratio']['status'] == 'unknown'
        assert case['observed_request_latency_ratio']['value'] is None


def test_engine_error_remains_unknown_and_is_not_equivalence_failure(monkeypatch):
    monkeypatch.setattr(benchmark, '_tool_identity', lambda path, java: {'analyze_headless': path})

    def failing(lift, *, engine, analyze_headless=None, java_home=None, timeout_s=120):
        if engine == 'ghidra':
            raise TimeoutError('analysis timed out')
        return {'text': c_matching_source(lift)}

    monkeypatch.setattr(benchmark, 'asm_to_c', failing)
    report = benchmark.run(repeats=1, analyze_headless='/tool/analyzeHeadless')
    for case in report['cases']:
        result = case['engines']['ghidra']
        assert result['status'] == 'unknown'
        assert result['error_type'] == 'TimeoutError'
        assert case['equivalence_gate'] == 'unknown'
        assert case['observed_request_latency_ratio']['status'] == 'unknown'


def test_records_ghidra_decompiler_output_and_gated_latency_ratio(monkeypatch):
    monkeypatch.setattr(benchmark, '_tool_identity', lambda path, java: {'analyze_headless': path})
    monkeypatch.setattr(benchmark, 'verify_block', lambda *args, **kwargs: {
        'status': 'equivalent_under_assumptions', 'scope': 'test output boundary',
        'assumptions': ['authored test contract']})

    def fake_asm_to_c(lift, *, engine, analyze_headless=None, java_home=None, timeout_s=120):
        result = {'text': c_matching_source(lift)}
        if engine == 'ghidra':
            result.update({'ghidra_c': 'uint16_t decompiled_value;',
                           'ghidra_version': 'test-ghidra-version',
                           'diagnostics': {'decompile_completed': True, 'decompiler_warnings': ''}})
        return result

    monkeypatch.setattr(benchmark, 'asm_to_c', fake_asm_to_c)
    report = benchmark.run(repeats=1, analyze_headless='/tool/analyzeHeadless')
    for case in report['cases']:
        ghidra = case['engines']['ghidra']
        assert ghidra['ghidra_version'] == 'test-ghidra-version'
        decompiler = ghidra['ghidra_decompiler']
        assert decompiler['text'] == 'uint16_t decompiled_value;'
        assert decompiler['sha256'] == hashlib.sha256(decompiler['text'].encode()).hexdigest()
        assert decompiler['characters'] == len(decompiler['text'])
        assert decompiler['diagnostics']['decompile_completed'] is True
        ratio = case['observed_request_latency_ratio']
        assert ratio['status'] == 'observed'
        assert ratio['value'] > 0
        assert 'different deployment modes' in ratio['interpretation']


def test_counterexample_is_known_failure_not_unknown(monkeypatch):
    monkeypatch.setattr(benchmark, '_tool_identity', lambda path, java: {'analyze_headless': path})
    monkeypatch.setattr(benchmark, 'verify_block', lambda *args, **kwargs: {
        'status': 'counterexample', 'scope': 'test counterexample', 'assumptions': []})
    monkeypatch.setattr(benchmark, 'asm_to_c', lambda *args, **kwargs: {'text': 'ax = 100;'} )
    report = benchmark.run(repeats=1, analyze_headless='/tool/analyzeHeadless')
    for case in report['cases']:
        assert case['equivalence_gate'] == 'counterexample'
        assert case['observed_request_latency_ratio']['status'] == 'unknown'


def test_rejects_invalid_repeat_count():
    try:
        benchmark.run(repeats=0)
    except ValueError as exc:
        assert 'repeats' in str(exc)
    else:
        raise AssertionError('invalid repeats must be rejected')


def test_timed_output_change_fails_closed(monkeypatch):
    monkeypatch.setattr(benchmark, '_tool_identity', lambda path, java: {'analyze_headless': path})
    calls = {}

    def changing(lift, *, engine, analyze_headless=None, java_home=None, timeout_s=120):
        key = (lift['source'], engine)
        calls[key] = calls.get(key, 0) + 1
        return {'text': c_matching_source(lift) if calls[key] == 1 else 'ax = 0;'}

    monkeypatch.setattr(benchmark, 'asm_to_c', changing)
    report = benchmark.run(repeats=1, analyze_headless='/tool/analyzeHeadless')
    for case in report['cases']:
        for engine in ('builtin', 'ghidra'):
            assert case['engines'][engine]['status'] == 'unknown'
            assert case['engines'][engine]['reason'] == 'timed invocation changed normalized output'
        assert case['observed_request_latency_ratio']['status'] == 'unknown'
