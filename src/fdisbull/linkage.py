"""Shared static import identities and calls over normalized expressions.

A linkage slot/stub identifies a requested symbol, never its runtime provider or
address. Loader adapters supply metadata; this pass has no CPU instruction or
container-specific traversal rules.
"""
from .flowdata import evaluate_expression,memory_read_allowed


def metadata_symbols(document):
    """Yield address identities, including code stubs separately from slots."""
    for item in document.get('imports', []):
        address=item.get('address')
        detail=dict(item)
        if type(address) is int and 0<=address<1<<64:
            detail.setdefault('slot_address',address)
            yield address,'imports',detail
        for stub in item.get('stub_addresses', []):
            if type(stub) is int and 0<=stub<1<<64:
                yield stub,'import_stubs',dict(detail,slot_address=address,stub_address=stub,address_kind='code_stub')
    for item in document.get('exports', []):
        address=item.get('address')
        if type(address) is int and 0<=address<1<<64:
            yield address,'exports',dict(item)


def import_call_bindings(snapshot, semantics_by_id, flow_result, imports, pointer_width):
    """Join calls to declared slots/stubs, without reading pointer contents.

    Direct calls to metadata stubs need no value inference. Register-indirect
    calls require a converged reachable state containing a pointer-width load
    from a declared slot, or a known code-stub address. Merely calling the
    address of a data slot is not an import call.
    """
    imports=[item for item in imports if item.get('callable') is not False]
    slots={item['address']:item for item in imports if type(item.get('address')) is int}
    stubs={stub:item for item in imports for stub in item.get('stub_addresses',[]) if type(stub) is int}
    found={}
    def add(node,item,slot=None,stub=None,expression=None):
        target=slot if slot is not None else stub
        if target is None:return
        key=(node['context'],node['address'],target,stub)
        found[key]=dict(source=node['id'],source_address=node['address'],source_context=node['context'],
                        slot=slot,stub=stub,target=target,name=item.get('name'),module=item.get('module'),
                        target_kind='import_slot' if slot is not None else 'code_stub',
                        expression=expression,evidence='declared import binding and native call target/normalized pointer load',
                        runtime_observed=False,external_target=None,identity_basis='declared_import_metadata',
                        binding_unchanged_under_static_state=None,contract_condition='declared binding is unchanged at this call')
    by_id={node['id']:node for node in snapshot.get('nodes',[])}
    for call in snapshot.get('calls',[]):
        node=by_id.get(call['source'])
        target=call.get('target_address')
        if node is not None and target is not None:
            a=int(target,16) if isinstance(target,str) else target
            if a in stubs:add(node,stubs[a],stubs[a].get('address'),a)
    if not flow_result.get('stable') or flow_result.get('budget_exhausted') or snapshot.get('budget_exhausted'):
        return list(found.values())
    for node in snapshot.get('nodes',[]):
        if node.get('flow')!='indirect_call':continue
        state=flow_result.get('in_states',{}).get(node['id'])
        semantic=semantics_by_id.get(node['id'],{})
        if state is None or semantic.get('indirect_target') is None:continue
        expression=evaluate_expression(semantic['indirect_target'],state)
        if expression.get('op')=='const' and expression.get('value') in stubs:
            address=expression['value'];item=stubs[address]
            add(node,item,item.get('address'),address,expression)
        elif expression.get('op')=='load' and expression.get('width')==pointer_width and not expression.get('signed'):
            address=expression.get('address',{})
            if address.get('op')=='const' and address.get('value') in slots:
                a=address['value'];add(node,slots[a],a,expression=expression)
    for binding in found.values():
        state=flow_result.get('in_states',{}).get(binding['source'])
        if binding['slot'] is not None and state is not None:
            binding['binding_unchanged_under_static_state']=memory_read_allowed(binding['slot'],pointer_width,state)
    return list(found.values())


def canonical_library_name(name,file_format):
    """Normalize only metadata-derived ABI spelling, preserving source names."""
    if file_format=='Mach-O' and name.startswith('_'):return name[1:]
    if file_format=='ELF':return name.split('@',1)[0]
    return name
