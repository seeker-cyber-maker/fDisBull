"""Coverage-guided, newly authored one-instruction probes for missed families.

These are **not** recovered game blocks or sweded UDC implementations. They give
future agents concrete acceptance inputs when a small corpus misses an opcode.
"""
from __future__ import annotations
from .vm import Machine

PROBES={
    'JP_V0': {'word':0xB200,'v':{0:4},'expect_pc':0x204},
    'LD_ST_VX': {'word':0xF118,'v':{1:5},'expect_sound':5},
    'OR': {'word':0x8121,'v':{1:1,2:2},'expect_v1':3},
    'SAVE': {'word':0xF155,'v':{0:9,1:10},'expect_mem':[9,10]},
    'SHR': {'word':0x8126,'v':{1:1,2:4},'expect_v1':2},
    'SNE_VX_VY': {'word':0x9120,'v':{1:1,2:2},'expect_pc':0x204},
    'WAIT_KEY': {'word':0xF10A,'keys':[5],'expect_v1':5},
    'XOR': {'word':0x8123,'v':{1:1,2:3},'expect_v1':2},
}

def run_gap_probes(unseen_families):
    out=[]
    for name in sorted(unseen_families):
        if name not in PROBES:
            out.append({'family':name,'status':'missing_authored_probe'})
            continue
        item=PROBES[name];m=Machine()
        m.memory[0x200:0x202]=item['word'].to_bytes(2,'big')
        m.i=0x300
        for k,v in item.get('v',{}).items():m.v[k]=v
        m.keys=set(item.get('keys',[]))
        status=m.step()
        checks={'expect_pc':m.pc,'expect_sound':m.sound,'expect_v1':m.v[1],
                'expect_mem':list(m.memory[0x300:0x302])}
        keys=[key for key in item if key.startswith('expect_')]
        passes=(status=='executed' and all(item[key]==checks[key] for key in keys))
        out.append({'family':name,'word':f"{item['word']:04X}",'status':'pass' if passes else 'failed',
                    'expected':{key:item[key] for key in keys},'observed':{key:checks[key] for key in keys},
                    'scope':'authored VM probe only; independently qualified original behavior remains outstanding'})
    return out