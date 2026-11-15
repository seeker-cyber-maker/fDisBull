"""Explicit specializations when joining partial caller and dispatcher proofs.

The outer loader has not been proved. Its caller layout and metadata bindings
remain requirements, rather than consequences of matching native samples.
"""
import time


def join_caller_contract(z, fragment, caller_proof, caller_contract, dispatcher, *, deadline):
    from .pe_loader_module_recovery import _cells, _rows
    interval, capsule = fragment['interval'], dispatcher['capsule']
    module_proof = dispatcher['proof']
    def declarations(proof):
        return {n: z.Bool(n) if w == 'Bool' else z.BitVec(n, w) for n, w in proof['symbols'].items()}
    def parse(expression, width, symbols):
        value = z.Const('__caller_join_value', z.BoolSort() if width == 'Bool' else z.BitVecSort(width))
        if '__caller_join_value' in symbols:
            raise ValueError('Reserved caller join symbol')
        try:
            rows = z.parse_smt2_string('(assert (= __caller_join_value ' + expression + '))',
                                      decls=symbols | {'__caller_join_value': value})
        except z.Z3Exception as error:
            raise ValueError('Invalid typed caller join expression') from error
        if len(rows) != 1 or not z.is_eq(rows[0]) or not rows[0].arg(0).eq(value):
            raise ValueError('Caller join requires a single typed expression')
        return rows[0].arg(1)
    solver = z.Solver()
    def check(conditions, claim=None):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining < 1:
            raise ValueError('Caller contract join deadline exhausted')
        solver.set(timeout=min(remaining, 10000)); solver.push(); solver.add(*conditions)
        if claim is not None:
            solver.add(z.Not(claim))
        answer = solver.check(); solver.pop()
        if answer != (z.sat if claim is None else z.unsat):
            raise ValueError('Caller specialization does not establish the dispatcher/caller precondition')
    cs = declarations(caller_proof)
    transfer = caller_proof['transfer']
    guard = parse(transfer['entry_guard'], 'Bool', cs)
    role = fragment['role']
    wm = int(caller_contract['addresses']['modref'], 16)
    if wm != int(capsule['selection']['modref'], 16):
        raise ValueError('Caller specialization selects a different WINE_MODREF')
    if role == 'attach_success_tail':
        ms = declarations(module_proof)
        registers = {n: parse(e, 64, ms) for n, e in module_proof['transfer']['registers'].items()}
        flags = parse(module_proof['transfer']['flags'], 32, ms)
        # R12 layout comes from the still-unproved enclosing caller. The
        # MODULE proof preserves it; a native R12 value is not a universal fact.
        bindings = [ms['loader_entry_rsp'] == int(capsule['entry']['general']['rsp'], 16),
                    ms['loader_entry_r12'] == wm + 0xa0, (ms['loader_entry_flags'] & 2) == 2]
        joined = z.substitute(guard, *[(cs['interval_entry_' + n], registers[n])
                                       for n in ('rsp', 'r12', 'rax')],
                              (cs['interval_entry_flags'], flags))
        check(bindings); check(bindings, joined)
        return {'status': 'proved_under_explicit_caller_layout',
            'required_outer_entry_bindings': {'module_entry_r12': hex(wm + 0xa0)},
            'required_outer_metadata_conditions': ['WINE_MODREF+0x88 activation context is null',
                                                    '__wine_dbch_module tracing bit 0x08 is clear'],
            'established': ['MODULE status, stack and preserved R12 imply the tail entry guard'],
            'limits': 'Enclosing process_attach entry and fixed metadata, saved stack provenance and prior-current_modref meaning remain conditional'}
    if role != 'detach_selection_prefix':
        raise ValueError('Unsupported caller join role')
    before = _cells(interval['entry_memory'])
    after = _cells(capsule['entry_memory'])
    metadata = {int(a, 16) for a in transfer['metadata_memory']}
    substitutions, specialization = [], {}
    for address in sorted(metadata):
        symbol = cs.get(f'interval_entry_ram_{address:x}')
        if symbol is not None:
            substitutions.append((symbol, z.BitVecVal(before[address], 8)))
            specialization[address] = before[address]
    specialize = lambda expression: z.simplify(z.substitute(expression, *substitutions))
    conditions = [specialize(guard)]
    check(conditions)
    for name in ('rcx', 'rdx', 'r8', 'rsp'):
        expression = specialize(parse(transfer['registers'][name], 64, cs))
        check(conditions, expression == int(capsule['entry']['general'][name], 16))
    for address in range(wm + 0x68, wm + 0x6c):
        expression = specialize(parse(transfer['metadata_memory'][hex(address)], 8, cs))
        check(conditions, expression == after[address])
    pending = transfer['pending_call']
    check(conditions, specialize(parse(pending['target'], 64, cs)) == int(capsule['entry']['rip'], 16))
    if pending['return_address'] != capsule['return_address']:
        raise ValueError('Caller pending return differs from the actual dispatcher frame')
    if transfer['defined_flags_mask'] & 2 != 2:
        raise ValueError('Caller leaves a required dispatcher FLAGS bit undefined')
    check(conditions, (specialize(parse(transfer['flags'], 32, cs)) & 2) == 2)
    return {'status': 'proved_under_explicit_metadata_specialization',
        'required_outer_metadata_bindings': _rows(specialization),
        'established': ['Selected source WM, reason, reserved argument, stack, return word and flags match dispatcher entry',
                        'Symbolic WM flag update specializes to the fixed following MODULE metadata'],
        'limits': 'General prefix metadata does not imply the frozen MODULE path; these entry bindings and outer list construction remain conditional'}
