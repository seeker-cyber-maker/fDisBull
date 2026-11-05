"""Historical mode comes from each native fetch, independently of a later stop."""
from copy import deepcopy

import pytest

from fdisbull.code_layers import LayerSessionMixin
from fdisbull.debug_experiments import _trace_event
from fdisbull.debug_semantics import normalize_stop, normalize_trace, trace_decode_bits


def event(**values):
    return {'address': {'space': 'segmented', 'segment': '0x1234', 'offset': '0x20'},
            'instruction': 'native instruction text', 'execution_bytes': 'b83412112290',
            'ram_bytes': 'b83412112290', **values}


class Session(LayerSessionMixin):
    # A later stopped mode is deliberately available but must never be queried
    # to reinterpret historical events.
    def registers(self):
        raise AssertionError('Historical trace must not query the current stop')


@pytest.mark.parametrize('mode,bits,expected', [
    ('real', None, 16), ('real', 32, 16), ('protected', 16, 16),
    ('protected', 32, 32), ('v86', 16, 16), ('v86', 32, 32),
    ('protected', None, None), ('protected', 64, None), ('protected', '32', None),
    ('v86', None, None), (None, 16, None), ('unknown', 16, None),
])
def test_decoder_width_requires_the_historical_mode_and_observed_width(mode, bits, expected):
    value = event(cpu_mode=mode, code_bits=bits)
    assert trace_decode_bits(value) == expected
    Session()._layer_trace([value])
    if expected is None:
        assert value['instruction'] == value['native_instruction'] == 'native instruction text'
        assert 'instruction_bits' not in value
        assert 'unqualified' in value['instruction_decoding']
    else:
        assert value['instruction_bits'] == expected
        assert value['instruction'].startswith('mov ax' if expected == 16 else 'mov eax')


@pytest.mark.parametrize('mode', ['protected', 'v86', None])
def test_non_real_or_legacy_trace_has_no_dos_paragraph_source_projection(mode):
    value = event(cpu_mode=mode, code_bits=32, project_address='0x10020',
                  project_segmented_address='1000:0020')
    normalize_trace('dosbox', [value], version=7, delta=0x2340)
    assert value['identity']['context'] is None
    assert value['identity']['project_address'] is None and value['project_address'] is None
    assert value['project_segmented_address'] is None
    assert value['identity']['runtime_address'] == value['address']


def test_mixed_trace_keeps_per_record_modes_and_only_projects_the_real_record():
    records = [event(cpu_mode='real', project_address='0x10020'),
               event(cpu_mode='protected', code_bits=32, project_address='0x10020'),
               event(project_address='0x10020')]
    normalize_trace('dosbox-qemu', records, version=7, delta=0x2340, budget_reached=True)
    assert records[0]['identity']['context'] == 'real:1000'
    assert records[0]['project_address'] == '0x10020'
    assert [item['identity']['context'] for item in records[1:]] == [None, None]
    assert records[2]['observation']['instruction_completed'] is False
    assert 'cpu_mode' not in records[2]  # No invented mode for legacy data.


@pytest.mark.parametrize('mode,bits,trimmed', [('real', None, True), ('protected', 16, True),
                                           ('protected', 32, False), ('v86', 32, False),
                                           ('protected', None, False), (None, 16, False)])
def test_trial_comparison_trims_only_the_observed_instruction_width(mode, bits, trimmed):
    first = event(cpu_mode=mode, code_bits=bits)
    second = {**first, 'execution_bytes': 'b83412334490'}
    # B8 imm is three bytes in 16-bit mode, five in 32-bit mode. The apparent
    # lookahead difference belongs to the current immediate only in 32-bit mode.
    assert (_trace_event(first) == _trace_event(second)) is trimmed
    compared = _trace_event(first)
    assert compared['cpu_mode'] == mode and compared['code_bits'] == bits


def test_trial_comparison_preserves_cpu_mode_and_width_changes():
    first = event(cpu_mode='protected', code_bits=16, stack_bits=16)
    assert _trace_event(first) != _trace_event({**first, 'cpu_mode': 'v86'})
    assert _trace_event(first) != _trace_event({**first, 'stack_bits': 32})


@pytest.mark.parametrize('bits,address', [(32, '0x401000'), (64, '0x140001000')])
def test_pe_trace_retains_its_native_decoded_instruction_and_flat_source_mapping(bits, address):
    native = {'address': address, 'project_address': address, 'bytes': '90',
              'instruction': {'text': 'nop', 'size': 1}, 'completed': True,
              'registers': {'bits': bits}, 'execution_bytes': '909090'}
    before = deepcopy(native)
    compared = _trace_event(native)
    assert compared['instruction'] == before['instruction']
    assert compared['execution_bytes'] == before['execution_bytes']
    normalize_trace('wine-qemu', [native], version=7)
    assert native['identity']['context'] == 'flat'
    assert native['identity']['project_address'] == address
    assert native['instruction'] == before['instruction']
    assert native['observation']['instruction_completed'] is True


def test_dos_stop_reports_only_the_native_observed_mode():
    assert normalize_stop('dosbox', {'kind': 'pause', 'cpu_mode': 'protected'},
                          outcome='pause')['cpu_mode'] == 'protected'
    assert normalize_stop('dosbox', {'kind': 'pause'}, outcome='pause')['cpu_mode'] is None


@pytest.mark.parametrize('mode', ['protected', 'v86', None])
def test_dos_layer_code_view_refuses_non_real_mapping_before_read_or_mutation(mode):
    class ViewSession(LayerSessionMixin):
        def __init__(self):self.calls=[]
        def call(self, method, params=None):
            self.calls.append(method)
            assert method == 'state.get_registers', 'Refused mapping reached a native read/mutation'
            return {'cpu_mode': mode}
        def _layer_setup(self):
            raise AssertionError('Refused mapping changed layer state')

    session=ViewSession()
    with pytest.raises(ValueError, match='source mapping is unavailable'):
        session._view('1000:0010', length=2)
    assert session.calls == ['state.get_registers']
