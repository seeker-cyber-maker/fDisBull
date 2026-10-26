import pytest

from fdisbull.project import Project
from test_typesystem import _project


def test_enum_flags_alias_and_bitfields_are_persistent_interpretations(tmp_path):
    with _project(tmp_path) as p:
        p.define_type('Flags', dict(kind='enum', size=2, flags=True, members={'FOOD': 1, 'PARKING': 2}))
        p.define_type('FlagAlias', dict(kind='typedef', target='Flags'))
        p.apply_type(0x1040, 'FlagAlias', name='flags')
        item = p.typed_data(0x1040)['items'][0]
        assert item['value'] == 3 and item['symbols'] == ['FOOD', 'PARKING'] and item['unknown_bits'] == 0
        p.define_type('Bits', dict(kind='bitfield', size=2, fields=[
            dict(name='food', lsb=0, width=1), dict(name='parking', lsb=1, width=1),
            dict(name='signed_delta', lsb=2, width=3, signed=True)]))
        p.apply_type(0x1050, 'Bits', name='bits')
        assert [i['value'] for i in p.typed_data(0x1050)['items']] == [1, 1, 1]
        child = p.patch(0x1050, '1f00')['version']
        assert p.typed_data(0x1050, version=child)['items'][2]['value'] == -1
        assert p.typed_data(0x1050, version=1)['items'][2]['value'] == 1
    with Project(tmp_path / 'types.fdb') as p:
        assert p.typed_data(0x1040)['items'][0]['symbols'] == ['FOOD', 'PARKING']


def test_union_exposes_all_members_without_guessing_active_interpretation(tmp_path):
    with _project(tmp_path) as p:
        p.define_type('WordView', dict(kind='union', size=2, fields=[
            dict(name='unsigned', type='u16'), dict(name='signed', type='i16')]))
        p.apply_type(0x1042, 'WordView', name='delta')
        items = p.typed_data(0x1042)['items']
        assert [(i['path'], i['value']) for i in items] == [('delta.unsigned', 65532), ('delta.signed', -4)]
        location = p.locate(0x1042)['presentation']['type']
        assert location['kind'] == 'union' and len(location['alternatives']) == 2
        assert p.locate(0x1042)['presentation']['name'] == 'delta'


def test_function_pointer_exposes_prototype_and_cannot_be_bound_as_data(tmp_path):
    with _project(tmp_path) as p:
        p.define_type('Callback', dict(kind='function', returns='u16', abi='x86_16_pascal_far',
            arguments=[dict(name='price', type='u16')], variadic=False))
        p.define_type('CallbackPtr', dict(kind='pointer', target='Callback', size=4, address_space='far16'))
        p.apply_type(0x1080, 'CallbackPtr', name='handler')
        item = p.typed_data(0x1080)['items'][0]
        assert item['prototype']['arguments'][0]['type']['name'] == 'u16'
        assert item['prototype']['abi'] == 'x86_16_pascal_far'
        with pytest.raises(ValueError, match='storage'):
            p.apply_type(0x1090, 'Callback')


@pytest.mark.parametrize('definition', [
    dict(kind='enum', size=1, members={'TOO_BIG': 256}),
    dict(kind='enum', size=1, members={'BAD': True}),
    dict(kind='bitfield', size=1, fields=[dict(name='a', lsb=0, width=3), dict(name='b', lsb=2, width=2)]),
    dict(kind='union', size=1, fields=[dict(name='a', type='u32')]),
    dict(kind='typedef', target='Missing'),
    dict(kind='function', returns='u8', abi='not_an_abi', arguments=[]),
])
def test_invalid_rich_layouts_are_rejected_atomically(tmp_path, definition):
    with _project(tmp_path) as p:
        before = p.types()
        with pytest.raises(ValueError):
            p.define_type('Bad', definition)
        assert p.types() == before


def test_pascal_prototype_uses_declared_order_and_exact_argument_width(tmp_path):
    from fdisbull.frames import _arguments
    source=tmp_path/'pascal.bin'
    source.write_bytes(bytes.fromhex('b8010050b8020050e80100c3c20400'))
    with Project.create(tmp_path/'pascal.fdb',source,arch='x86',bits=16,base=0x1000) as p:
        p.analyze()
        p.define_type('Buy',dict(kind='function',returns='u16',abi='x86_16_pascal_near',
            arguments=[dict(name='item',type='u16'),dict(name='quantity',type='u16')]))
        applied=p.set_function_type(0x100c,'Buy')
        abi=applied['summary']['abi']
        assert abi['callee_cleanup']==4
        assert [a['offset'] for a in abi['parameter_layout']]==[2,0]
        state=dict(memory={'entry_sp:-2:2':dict(op='const',value=1),'entry_sp:-4:2':dict(op='const',value=2)})
        def evaluate(expr,state):
            return dict(op='stack',base='entry_sp',offset=-4) if expr.get('op')=='reg' else expr
        observed=_arguments(abi,state,evaluate)
        assert [a['value'] for a in observed['argument_values']]==[1,2]
    with Project(tmp_path/'pascal.fdb') as p:
        assert p.summaries()['items'][0]['summary']['layout_snapshot']['name']=='Buy'


def test_rich_types_apply_to_external_snapshots_and_redefinition_cannot_remove_storage(tmp_path):
    with _project(tmp_path) as p:
        data=tmp_path/'flags.dat';data.write_bytes(b'\x03\x00')
        p.attach_file(data)
        p.define_type('Flags',dict(kind='enum',size=2,flags=True,members={'ONE':1,'TWO':2}))
        p.define_type('Alias',dict(kind='typedef',target='Flags'))
        p.apply_file_type('flags.dat','Alias')
        assert p.typed_file('flags.dat')['items'][0]['symbols']==['ONE','TWO']
        p.define_type('Fn',dict(kind='function',returns=None,arguments=[],abi='x86_16_cdecl_near'))
        with pytest.raises(ValueError,match='storage'):
            p.define_type('Alias',dict(kind='typedef',target='Fn'))


def test_union_expansion_budget_rejects_exponential_layout_before_persistence(tmp_path):
    with _project(tmp_path) as p:
        previous='u8'
        for index in range(12):
            name=f'Union{index}'
            p.define_type(name,dict(kind='union',size=1,fields=[dict(name='a',type=previous),dict(name='b',type=previous)]))
            previous=name
        with pytest.raises(ValueError,match='expansion'):
            p.define_type('TooLarge',dict(kind='union',size=1,fields=[dict(name='a',type=previous),dict(name='b',type=previous)]))
        assert p.db.execute("SELECT count(*) FROM type_definitions WHERE name='TooLarge'").fetchone()[0]==0
