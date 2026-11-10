"""Source-identified, hand-modeled Castles II CMP/JAE acceptance specimen.

No commercial bytes are included. This proves *formulas*, not recovered binary semantics.
"""
from fdisbull.influence_pilot import analyze_linear_influence
from fdisbull.proofs import check_equivalence


def test_castles2_cmp_jae_handmodeled_mask_and_z3():
    # Actual 0.34.1 static listing of C2CDTOOL.EXE SHA-256
    # 512efad4a4d771f6c975702cad9a688aeef10f8d81798b8c7260e37c74e87d43:
    # 1000:0067 cmp di,200h ; 1000:006b jae short 0075h
    flags=('flag.cf','flag.zf','flag.pf','flag.af','flag.sf','flag.of')
    steps=[{'id':'cmp','reads':['reg.di'],'writes':list(flags),
            'dependencies':{k:['reg.di'] for k in flags}},
           {'id':'jae','reads':['flag.cf'],'writes':['control.pc'],
            'dependencies':{'control.pc':['flag.cf']}}]
    model={'format':'fdisbull-influence-pilot-1','scope':'linear',
           'steps':steps,'observables':['control.pc'],
           'closed_semantics':True,'closed_observers':True}
    result=analyze_linear_influence(model)
    assert result['required_entry']==['reg.di']
    assert result['contracts'][0]['produced_live']==['flag.cf']
    assert result['contracts'][0]['dead_written_candidates']==sorted(set(flags)-{'flag.cf'})

    # JAE after CMP DI,200h: CF=0, i.e. unsigned DI >= 0x200.
    di={'var':'di'};k={'const':512,'width':16}
    original={'op':'not','args':[{'op':'ult','args':[di,k]}]}
    equivalent={'op':'ule','args':[k,di]}
    incorrect={'op':'ult','args':[di,k]}
    base={'format':'fdisbull-proof-1','scope':'Hand-modeled Castles II 1000:0067-006b predicate only',
          'variables':{'di':16},'assumptions':[],'left':original}
    yes=check_equivalence({**base,'right':equivalent})
    no=check_equivalence({**base,'right':incorrect})
    assert yes['status']=='equivalent_under_assumptions'
    assert no['status']=='counterexample'
