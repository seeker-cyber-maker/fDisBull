"""Typed source-instruction candidates for the declared classic/v6 profile.

These records describe source effects. They are not executable common UIL or
independently qualified semantics, and do not describe active fetch overlays.
"""
from copy import deepcopy
import json
import re

from .chip8 import _PATTERNS, MEMORY_SIZE

FORMAT='fdisbull-chip8-udl-instruction-1'
_TYPES={'pc':'u16','i':'u16','sp':'u8','stack':'u16[16]',
        'ram':'u8[4096]','framebuffer':'u1[64,32]','key_mask':'u16',
        'key_wait':'bool','key_wait_stop_owned':'bool','delay_timer':'u8',
        'sound_timer':'u8','rng_state':'u32','rng_draws':'u64',
        'faulted':'bool','fault_code':'u32','fault_pc':'u16','fault_opcode':'u16'}


def _port(name):
    result={'name':name,'type':'u8' if re.fullmatch(r'v[0-9a-f]',name) else _TYPES[name]}
    if name=='sp':result['bounds']=[0,16]
    return result


def _ports(names):return [_port(name) for name in dict.fromkeys(names)]


def _canonical(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError,UnicodeError) as error:raise ValueError('Malformed CHIP-8 source candidate') from error


def _fact(instruction):
    if not isinstance(instruction,dict):raise ValueError('Expected a decoded CHIP-8 source fact')
    pc=instruction.get('address');encoded=instruction.get('bytes')
    if (type(pc) is not int or not 0<=pc<MEMORY_SIZE-1 or pc&1 or
            instruction.get('size')!=2 or type(instruction.get('size')) is not int or
            not isinstance(encoded,str) or not re.fullmatch(r'[0-9a-f]{4}',encoded)):
        raise ValueError('Invalid CHIP-8 source instruction span')
    word=int(encoded,16)
    pattern=next(((family,form) for mask,value,family,form in _PATTERNS if word&mask==value),None)
    if pattern is None or instruction.get('mnemonic')!=pattern[0].lower():
        raise ValueError('CHIP-8 source word and family differ')
    family=pattern[0]
    flow=('conditional' if family.startswith(('SE_','SNE_')) or family in ('SKP','SKNP') else
          'jump' if family=='JP' else 'call' if family=='CALL' else
          'return' if family=='RET' else 'indirect_jump' if family=='JP_V0' else 'next')
    target=(word&0xfff) if family in ('JP','CALL') else pc+4 if flow=='conditional' and pc+4<MEMORY_SIZE else None
    if instruction.get('flow')!=flow or instruction.get('target')!=target:
        raise ValueError('CHIP-8 source word and control fact differ')
    if target is not None and type(instruction.get('target')) is not int:
        raise ValueError('CHIP-8 direct target must be an integer')
    form=pattern[1];x=(word>>8)&15;y=(word>>4)&15
    literals={'kk':word&255,'nnn':word&0xfff,'n':word&15}
    values={'x':'v%x'%x,'y':'v%x'%y,'kk':'0x%02x'%literals['kk'],
            'nnn':'0x%03x'%literals['nnn'],'n':'0x%x'%literals['n']}
    roles=form.split(',') if form else []
    operands=', '.join(values[role] for role in roles)
    references=[] if target is None else [dict(operand_index=0 if family in ('JP','CALL') else -1,
                                              role='code',target=target,width=2)]
    immediates=[dict(operand_index=index,value=literals[role]) for index,role in enumerate(roles)
                if role in literals and not (family in ('JP','CALL') and role=='nnn')]
    expected=dict(address=pc,size=2,bytes=encoded,mnemonic=family.lower(),operands=operands,
                  text=family.lower()+(' '+operands if operands else ''),flow=flow,target=target,
                  data_refs=[],references=references,immediates=immediates)
    if _canonical(instruction)!=_canonical(expected):
        raise ValueError('CHIP-8 decoded fields differ from the exact source word')
    return pc,word,family,flow,pattern[1]


def describe(instruction):
    """Describe typed may-read/write candidates without executing the word."""
    pc,word,family,flow,form=_fact(instruction)
    x=(word>>8)&15;y=(word>>4)&15;kk=word&255;n=word&15;nnn=word&0xfff
    vx='v%x'%x;vy='v%x'%y
    reads=['pc','faulted'];writes=[];effects=[];memory=[];unknowns=[]
    guards=['native execution controls released','not faulted','effective fetch matches original source word']
    possible=[]
    control=dict(flow=flow,pc_update='pc + 2',success_condition='nonfaulting retirement')

    def write(*names):writes.extend(names)
    def effect(kind,**fields):effects.append(dict(kind=kind,**fields))
    def access(operation,length):
        reads.append('i');possible.append('data-out-of-bounds')
        memory.append(dict(operation=operation,space='ram',base='i',base_type='u16',
            byte_length=length,element_type='u8',guard='0 <= i and i + byte_length <= 4096',
            may_modify_source=operation=='write' and length>0))
        if length:
            if operation=='read':reads.append('ram')
            else:write('ram');unknowns.append('symbolic I write may modify later source fetches')
        unknowns.append('I address and range feasibility are unknown')

    if family=='CLS':
        write('framebuffer');effect('framebuffer-clear',width=64,height=32)
    elif family=='RET':
        reads.extend(['sp','stack']);write('sp','stack');possible.append('stack-underflow')
        guards.append('1 <= sp <= 16')
        control['pc_update']='old stack[old sp - 1]'
        effect('stack-return',index='old sp - 1',slot_type='u16',clear_popped_slot=True)
    elif family=='CALL':
        reads.append('sp');write('stack','sp');possible.append('stack-overflow')
        guards.append('0 <= sp < 16');control.update(pc_update='direct target',target=nnn)
        effect('stack-call',index='old sp',return_pc=pc+2,slot_type='u16')
    elif family=='JP':control.update(pc_update='direct target',target=nnn)
    elif family=='JP_V0':
        reads.append('v0');control.update(pc_update='nnn + old v0',base=nnn,target=None)
        unknowns.append('V0-dependent successor is unresolved; no 12-bit wrapping')
    elif family.startswith(('SE_','SNE_')):
        reads.append(vx)
        if family.endswith('_VY'):reads.append(vy)
        control.update(pc_update='conditional skip',successors=[pc+2,pc+4],condition=family,
                       feasibility='unknown')
        control['predicate']=dict(op='eq' if family.startswith('SE_') else 'ne',
            left=dict(state=vx,type='u8'),
            right=dict(state=vy,type='u8') if family.endswith('_VY') else dict(value=kk,type='u8'))
    elif family in ('SKP','SKNP'):
        reads.extend([vx,'key_mask'])
        control.update(pc_update='conditional skip',successors=[pc+2,pc+4],condition=family,
                       feasibility='unknown')
        held=dict(op='held-key',key=dict(state=vx,type='u8'),mask=dict(state='key_mask',type='u16'),
                  invalid_key='unpressed')
        control['predicate']=held if family=='SKP' else dict(op='not',argument=held)
        effect('key-test',key_register=vx,invalid_key='unpressed')
    elif family=='LD_VX_KK':write(vx);effect('register-operation',operation=family,immediate=kk,result_bits=8)
    elif family=='ADD_VX_KK':
        reads.append(vx);write(vx);effect('register-operation',operation=family,immediate=kk,result_bits=8,vf='preserved-unless-destination')
    elif family=='LD_VX_VY':
        reads.append(vy);write(vx);effect('register-operation',operation=family,result_bits=8)
    elif family in ('OR','AND','XOR','ADD_VX_VY','SUB','SUBN','SHR','SHL'):
        reads.extend([vy] if family in ('SHR','SHL') else [vx,vy]);write(vx,'vf')
        flag=('clear' if family in ('OR','AND','XOR') else 'carry' if family=='ADD_VX_VY' else
              'not-borrow' if family in ('SUB','SUBN') else 'shifted-out-bit')
        effect('register-operation',operation=family,result_bits=8,flag=flag,
               shift_source='vy' if family in ('SHR','SHL') else None,
               alias_order='destination before VF; both operands captured from pre-state')
    elif family=='LD_I':write('i');effect('index-set',immediate=nnn,result_bits=16)
    elif family=='ADD_I_VX':
        reads.extend(['i',vx]);write('i');effect('index-add',operand=vx,result_bits=16,vf='preserved')
    elif family=='FONT':
        reads.append(vx);write('i');effect('font-address',base=80,glyph_bytes=5,index='old '+vx+' & 15',result_bits=16)
    elif family=='RND':
        reads.extend(['rng_state','rng_draws']);write('rng_state','rng_draws',vx)
        effect('rng-draw',model='fdisbull-lcg32-high8-v1',mask=kk,draws=1,
               zero_mask_consumes_draw=True,draw_counter='saturating-u64')
    elif family=='DRW':
        reads.extend([vx,vy]);access('read',n)
        if n:reads.append('framebuffer');write('framebuffer')
        write('vf');effect('framebuffer-xor',rows=n,columns=8,coordinates='pre-state Vx/Vy modulo 64/32',
                           edges='clip',collision='VF',pixel_write=n>0)
    elif family=='BCD':
        reads.append(vx);access('write',3);effect('bcd-store',operand=vx,bytes=3,index_preserved=True)
    elif family in ('SAVE','LOAD'):
        registers=['v%x'%k for k in range(x+1)]
        if family=='SAVE':reads.extend(registers);access('write',x+1)
        else:access('read',x+1);write(*registers)
        write('i');effect('register-transfer',operation=family,registers=registers,
                          index_update='old i + '+str(x+1),index_bits=16,
                          bounds='no 12-bit wrapping; later transfer may fault')
    elif family=='LD_VX_DT':
        reads.append('delay_timer');write(vx);effect('timer-read',timer='delay_timer',clock='virtual-rational-60hz')
    elif family in ('LD_DT_VX','LD_ST_VX'):
        timer='delay_timer' if family=='LD_DT_VX' else 'sound_timer'
        reads.append(vx);write(timer);effect('timer-write',timer=timer,clock='virtual-rational-60hz')
        if family=='LD_ST_VX':effect('sound-status',derived_from='sound_timer != 0',waveform=False)
    elif family=='WAIT_KEY':
        reads.extend(['key_mask','key_wait']);write(vx,'key_wait','key_wait_stop_owned')
        control.update(pc_update='pc + 2 when key_mask != 0; unchanged while waiting',
                       success_condition='held key available and explicit native resume')
        effect('key-wait',selection='lowest held key including zero',
               outcomes=[dict(condition='key_mask == 0',retired=False,
                              writes=['key_wait','key_wait_stop_owned','pc']),
                         dict(condition='key_mask != 0',retired=True,writes=[vx,'key_wait','pc'])])
        unknowns.append('held keys and wait/resume path are unknown')
    else:raise ValueError('Missing CHIP-8 typed source candidate')

    write('pc')
    operands=[]
    for role in form.split(',') if form else ():
        if role in ('x','y'):
            operands.append(dict(role=role,kind='register',name=vx if role=='x' else vy,type='u8'))
        else:
            value,width={'kk':(kk,8),'nnn':(nnn,12),'n':(n,4)}[role]
            operands.append(dict(role=role,kind='immediate',value=value,type='u'+str(width)))
    return dict(format=FORMAT,qualification='static-candidate',family=family,
        operands=operands,
        reads=_ports(reads),writes=_ports(writes),write_order=list(writes),memory=memory,effects=effects,
        control=control,guards=guards,
        fault=dict(policy='sticky-atomic',possible=possible,
                   outputs=_ports(['faulted','fault_code','fault_pc','fault_opcode']),
                   architectural_effect='nonfaulting writes do not commit on a fault in this instruction; waiting is separate',
                   successor_fetch=dict(stage='after this instruction commits and before the successor executes',
                       next_pc=control['pc_update'],
                       conditions=[dict(fault='odd-pc',condition='next_pc % 2 != 0'),
                                   dict(fault='fetch-out-of-bounds',condition='next_pc is even and (next_pc < 0 or next_pc + 2 > 4096)')],
                       preserves='this instruction has already committed; successor fetch faults do not undo its writes')),
        operand_capture='source operands before destination writes; may-read/write summary, not minimal liveness',
        unknowns=unknowns,
        scope='declared classic/v6 original-fetch candidate; asynchronous clocks/input, native ownership/generation counters and active overlays require separate evidence; no G3/G4 qualification')


def validate(instruction,descriptor):
    """Check a retained candidate against its word/family without decoder calls."""
    if not isinstance(descriptor,dict) or _canonical(descriptor)!=_canonical(describe(instruction)):
        raise ValueError('CHIP-8 typed source candidate differs from its instruction')
    return deepcopy(descriptor)
