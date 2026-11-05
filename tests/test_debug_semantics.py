"""Shared meanings retain the differences of native debugger observations."""
from fdisbull.debug_semantics import contract, normalize_stop, normalize_trace


def test_dos_data_stop_is_after_access_but_pe_is_before_access():
    native={'kind':'breakpoint','address':{'space':'linear','offset':'0x12345'},
            'data_access':{'instruction':{'space':'segmented','segment':'0x1000','offset':'0x20'},'access':'w'}}
    next_pc={'space':'segmented','segment':'0x1000','offset':'0x25'}
    result=normalize_stop('dosbox',native,outcome='breakpoint',stopped_pc=next_pc)
    assert result['trigger']=='watchpoint' and result['instruction_completed'] is None
    assert result['causing_instruction']==native['data_access']['instruction']
    assert result['resume_pc']==next_pc and result['registers_stage']=='after-access'
    assert normalize_stop('dosbox',native,outcome='breakpoint')['resume_pc'] is None
    pe=normalize_stop('wine-qemu',{'kind':'watchpoint','address':'0x140001000','before_access':True},outcome='watchpoint')
    assert pe['instruction_completed'] is False and pe['registers_stage']=='before-instruction'
    assert contract('dosbox')['trace_completion']=='fetch-observed; completion unknown'


def test_dos_watch_does_not_infer_completion_from_the_stopped_pc():
    cause={'space':'segmented','segment':'0x1000','offset':'0x20'}
    native={'kind':'breakpoint','data_access':{'instruction':cause,'access':'w'}}
    # REP may still be executing; a different PC alone is not a completion
    # certificate either (for example when an interrupt changes the context).
    for backend in ('dosbox','dosbox-qemu'):
        for pc in (cause,{'space':'segmented','segment':'0x1234','offset':'0x21'},None):
            stop=normalize_stop(backend,native,outcome='breakpoint',stopped_pc=pc)
            assert stop['instruction_completed'] is None
            assert stop['registers_stage']=='after-access'
            assert stop['causing_instruction']==cause and stop['resume_pc']==pc


def test_fetch_trace_is_not_upgraded_to_completed_instructions():
    events=[{'address':{'space':'segmented','segment':'0x1234','offset':'0x20'},'project_address':'0x10020','bytes':'90','cpu_mode':'real'},
            {'address':{'space':'segmented','segment':'0x1234','offset':'0x21'},'project_address':'0x10021','bytes':'90','cpu_mode':'real'}]
    normalize_trace('dosbox',events,version=1,delta=0x2340,budget_reached=True)
    assert events[0]['observation']['instruction_completed'] is None
    assert events[1]['observation']['instruction_completed'] is False
    assert events[0]['identity']['context']=='real:1000'
    assert events[0]['identity']['source_version']==1
    pe=[{'address':'0x140001000','bytes':'90','project_address':'0x140001000'}]
    normalize_trace('wine-qemu',pe,version=1,delta=0)
    assert pe[0]['observation']['instruction_completed'] is True


def test_unknown_machine_stop_does_not_guess_watchpoint_timing():
    result=normalize_stop('qemu-machine',{'kind':'watchpoint','address':'0x1000'},outcome='watchpoint')
    assert result['instruction_completed'] is None and result['registers_stage']=='stopped; stage unknown'


def test_dos_guest_exit_retains_process_evidence_without_inventing_final_registers():
    exit_info={'psp':'0x0814','parent_psp':'0x071B','requested_exit_code':37,
               'resident':False,'source':'DOS_Terminate','stage':'after-process-cleanup'}
    for kind in ('guest_exit','guest_tsr'):
        native={'kind':kind,'guest_exit':{**exit_info,'resident':kind=='guest_tsr'}}
        result=normalize_stop('dosbox',native,outcome=kind)
        assert result['guest_exit']==native['guest_exit']
        assert result['context']=='dos-process' and result['trigger']==kind
        assert result['causing_instruction'] is None and result['resume_pc'] is None
        assert result['instruction_completed'] is None
        assert result['registers_stage']=='after-process-cleanup; target registers unavailable'


def test_session_shutdown_does_not_acquire_guest_exit_evidence():
    result=normalize_stop('dosbox',{'kind':'program_exit'},outcome='program_exit')
    assert 'guest_exit' not in result
    assert result['context']=='dos-cpu'
