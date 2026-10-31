"""Check one exact-edition, two-flag AGI invariant without executing a game.

Owner-supplied resources stay private. This utility qualifies source witnesses
and a declared transition abstraction, not the complete AGI interpreter.
"""
import argparse
from collections import deque
from hashlib import sha256
import json
from pathlib import Path

from fdisbull.agi import AGI2917Processor, load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.processor import Location


DIRECTORY_SHA256 = '18d53ac02a5457494f03352c36a4a4c2eb8251df70fff8dae6dc3d5b41d55b38'
VOLUME_SHA256 = {
    0: '7f10c63737b4da8cf1633ba7c317ffc84a4bbc4eca10b39d2e349b18636bb5e2',
    1: '7c3a0c86c8ad1b028dc3d56cafb30a925690f243d70f2e7b2ac6f0dc802b00d0',
    2: 'b6e321821a0d90809d985f57b279c2f155a6972482c4811c4a737987042a53cf',
}
WRITER_SHA256 = '73e97caaef4951d16b3b75dab2685cb7024e1d6f54212db86077aef9ff9baf50'
# Digests retain source identity without embedding original resources or text.
GUARDS = (
    (10, 0x27e, 0x2b6, ((77, True), (75, False), (79, False)),
     '6225f998b7a4c4b18f3e377c8785ef283bd467d4e3ff3c1a5deb9ffb46a4864e', 'lure'),
    (11, 0x34c, 0x384, ((77, True), (75, False), (79, False)),
     '6225f998b7a4c4b18f3e377c8785ef283bd467d4e3ff3c1a5deb9ffb46a4864e', 'lure'),
    (0, 0x978, 0x9c0, ((133, True), (75, False), (79, False)),
     '2f825e9c3c6871a44a8bbb1b401c339968b31e0a6409d08bd79a9eca63334d8e', 'ring'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def instruction_rows(resource):
    """Use established layout boundaries, including unsupported-effect actions."""
    offsets = [offset - 2 for offset in logic_layout(resource.payload)['instructions']]
    return {pc: resource.code[pc:(offsets[i + 1] if i + 1 < len(offsets) else len(resource.code))]
            for i, pc in enumerate(offsets)}


def writers(resources):
    result = []
    for number, resource in sorted(resources.items()):
        for pc, raw in instruction_rows(resource).items():
            if (raw[0] in (12, 13, 14) and raw[1] in (75, 79)) or raw[0] in (15, 16, 17):
                result.append(dict(logic=number, offset=pc, opcode=raw[0], operand=raw[1]))
    return result


def load_resources(logdir, volume_dir, profile):
    require(profile == '2.917', 'Only the explicit 2.917 source profile is admitted')
    directory = Path(logdir).read_bytes()
    require(0 < len(directory) <= 768 and len(directory) % 3 == 0, 'Invalid LOGDIR size')
    resources = {}
    for number in range(len(directory) // 3):
        entry = int.from_bytes(directory[3 * number:3 * number + 3], 'big')
        if entry & 0xfffff != 0xfffff:
            resource = load_logic(logdir, volume_dir, number, profile=profile)
            instruction_rows(resource)
            resources[number] = resource
    require(resources, 'No present logic resources')
    return resources


def cfg(resource):
    rows = instruction_rows(resource)
    graph = {}
    for pc, raw in rows.items():
        following = pc + len(raw)
        if raw[0] == 255:
            targets = (following, following + int.from_bytes(raw[-2:], 'little'))
        elif raw[0] == 254:
            targets = (following + int.from_bytes(raw[1:], 'little', signed=True),)
        elif raw[0] in (0, 18, 19):
            targets = ()
        else:
            targets = (following,)
        require(all(target in rows or target == len(resource.code) for target in targets),
                'Control-flow target is not a qualified instruction boundary')
        graph[pc] = targets
    return graph


def reachable(graph, goal, excluded_edge=None):
    queue = deque([0])
    seen = set()
    while queue:
        point = queue.popleft()
        if point == goal:
            return True
        if point in seen:
            continue
        seen.add(point)
        queue.extend(target for target in graph.get(point, ())
                     if (point, target) != excluded_edge)
    return False


def flag_terms(conditions):
    """Decode only a conjunction of flag literals; fail closed on other forms."""
    result = []
    negate = False
    for item in conditions:
        if item.get('marker') == 'not':
            require(not negate, 'Repeated NOT marker')
            negate = True
        else:
            require('marker' not in item and item.get('opcode') == 7,
                    'Expected a conjunction of literal flag conditions')
            result.append((item['operands'][0], not negate))
            negate = False
    require(not negate, 'Dangling NOT marker')
    return tuple(result)


def qualify_guard(resource, pc, target, terms, instruction_sha256, edge='true'):
    rows = instruction_rows(resource)
    require(pc in rows and target in rows, 'Guard or target is not an instruction boundary')
    raw = rows[pc]
    require(sha256(raw).hexdigest() == instruction_sha256, 'Guard byte witness differs')
    decoded = AGI2917Processor(resource.space).decode(resource.code, Location(resource.space, pc))
    require(decoded.facts['mnemonic'] == 'if' and flag_terms(decoded.facts['conditions']) == terms,
            'Decoded guard differs')
    successors = {successor.kind: successor.target.offset for successor in decoded.successors}
    graph = cfg(resource)
    require(reachable(graph, target), 'Writer/target is unreachable in the local static graph')
    require(not reachable(graph, target, (pc, successors[edge])),
            'Required guard edge does not dominate the writer/target')
    # A scan-start entry would invalidate the declared entry-at-zero graph.
    require(not any(raw[0] in (145, 146) for raw in rows.values()),
            'Scan-start commands need a separate entry qualification')
    return dict(logic=resource.logic, guard_offset=pc, target_offset=target,
                instruction_sha256=instruction_sha256,
                terms=[dict(flag=flag, required=value) for flag, value in terms],
                required_edge=edge, edge_dominates_target=True,
                resource_sha256=resource.resource_sha256)


def qualify_reset_loop(resource):
    rows = instruction_rows(resource)
    expected = {0x194: (3, 45, 20), 0x197: (16, 45), 0x199: (1, 45)}
    require(all(tuple(rows.get(pc, b'')) == values for pc, values in expected.items()),
            'Room-init dynamic reset-loop actions differ')
    decoded = AGI2917Processor(resource.space).decode(resource.code, Location(resource.space, 0x19b))
    conditions = decoded.facts.get('conditions', [])
    require(len(conditions) == 1 and conditions[0].get('opcode') == 3
            and conditions[0]['operands'] == [45, 45], 'Room-init reset-loop bound differs')
    graph = cfg(resource)
    require(graph[0x19b] == (0x1a2, 0x1a5) and graph[0x1a2] == (0x197,),
            'Room-init reset-loop control flow differs')
    return dict(logic=0, offset=0x197, opcode=16, variable=45,
                admitted_flag_range=dict(minimum=20, maximum=44, inclusive=True),
                affects_target_flags=False,
                basis='exact-edition code plus decoded bounded reset-loop witness')


def qualify_source(resources):
    for resource in resources.values():
        require(resource.profile == '2.917', 'Unexpected source profile')
        require(resource.directory_sha256 == DIRECTORY_SHA256, 'Unqualified exact-edition LOGDIR')
        require(resource.volume_sha256 == VOLUME_SHA256.get(resource.volume),
                'Unqualified exact-edition volume')
    require(all(number in resources for number in (0, 10, 11, 99, 103)),
            'Required source resources are absent')
    inventory = writers(resources)
    require(digest(inventory) == WRITER_SHA256, 'Unexpected literal or dynamic flag writers')
    guards = []
    for number, guard, writer, terms, witness, command in GUARDS:
        item = qualify_guard(resources[number], guard, writer, terms, witness)
        require(tuple(instruction_rows(resources[number])[writer]) ==
                (12, 75 if command == 'lure' else 79), 'Writer action differs')
        item['admitted_command'] = command
        guards.append(item)
    following = qualify_guard(resources[103], 0xcd, 0x192, ((75, False),),
        '8b19c12329ef43e92651e8bfe776534d31a685a58aa490f6b3fb323cc93a78e6', edge='false')
    invisible = qualify_guard(resources[103], 0x192, 0x19d, ((79, True), (42, False)),
        '2183c1c38f3df6dc87ef496b9930db9812970a3aef6953fc36b219959cabef8e')
    dynamic = [qualify_reset_loop(resources[0])]
    for offset, opcode in ((0x9d, 16), (0xac, 15)):
        require(tuple(instruction_rows(resources[99])[offset]) == (opcode, 73),
                'Debug dynamic flag-writer witness differs')
        dynamic.append(dict(logic=99, offset=offset, opcode=opcode, variable=73,
                            admitted=False, classification='debug flag-edit command'))
    return dict(writer_inventory=inventory, writer_inventory_sha256=digest(inventory),
                guarded_commands=guards, dynamic_writers=dynamic,
                named_target=dict(logic=103, message=2, print_offset=0x19d,
                                  required_flags=[75, 79], guard_witnesses=[following, invisible]))


def solve_flags(steps=8, timeout_ms=5000):
    """One-step induction and a finite path query over an explicit abstraction."""
    import z3
    require(type(steps) is int and 2 <= steps <= 64, 'steps must be 2..64')
    require(type(timeout_ms) is int and 1 <= timeout_ms <= 60000, 'Invalid solver timeout')
    f, i, nf, ni = z3.Bools('following invisible next_following next_invisible')
    invariant = lambda a, b: z3.Not(z3.And(a, b))

    def transition(a, b, c, d):
        return z3.Or(
            z3.And(c == a, d == b),  # Commands with no target-flag effect.
            z3.And(z3.Not(a), z3.Not(b), c, d == b),  # Lure.
            z3.And(z3.Not(a), z3.Not(b), c == a, d),  # Ring.
            z3.And(z3.Not(c), d == b),  # Any literal reset of following.
            z3.And(c == a, z3.Not(d)),  # Any literal reset of invisible.
        )

    def query(*constraints):
        solver = z3.Solver()
        solver.set(timeout=timeout_ms)
        solver.add(*constraints)
        outcome = solver.check()
        return str(outcome), solver

    base, _ = query(z3.Not(f), z3.Not(i), z3.Not(invariant(f, i)))
    induction, _ = query(invariant(f, i), transition(f, i, nf, ni), z3.Not(invariant(nf, ni)))
    fs = z3.Bools(' '.join(f'following_{n}' for n in range(steps + 1)))
    ins = z3.Bools(' '.join(f'invisible_{n}' for n in range(steps + 1)))
    bounded, _ = query(z3.Not(fs[0]), z3.Not(ins[0]),
        *(transition(fs[n], ins[n], fs[n + 1], ins[n + 1]) for n in range(steps)),
        z3.Or(*(z3.And(fs[n], ins[n]) for n in range(steps + 1))))
    # Intentionally admit the forbidden debug set-f79 after an ordinary lure.
    negative, solver = query(z3.Not(fs[0]), z3.Not(ins[0]), fs[1], ins[1] == ins[0],
        fs[2] == fs[1], ins[2], z3.And(fs[2], ins[2]))
    witness = None
    if negative == 'sat':
        model = solver.model()
        witness = [dict(following=z3.is_true(model.eval(fs[n], model_completion=True)),
                        invisible=z3.is_true(model.eval(ins[n], model_completion=True)))
                   for n in range(3)]
    return dict(z3_version=z3.get_version_string(), timeout_ms=timeout_ms, path_steps=steps,
                initial_violation=base, inductive_step_violation=induction,
                bounded_violation=bounded, debug_negative_control=negative,
                negative_control_commands=['lure', 'debug set flag79'],
                negative_control_witness=witness,
                verified=(base == induction == bounded == 'unsat' and negative == 'sat'))


def analyze(logdir, volume_dir, profile='2.917', steps=8):
    resources = load_resources(logdir, volume_dir, profile)
    qualification = qualify_source(resources)
    solver = solve_flags(steps)
    return dict(format='fdisbull-agi-goat-invisibility-check-1',
        status='verified-under-assumptions' if solver['verified'] else 'inconclusive',
        complete=solver['verified'], qualification=qualification, solver=solver,
        source_scan=dict(present_logic_count=len(resources), all_present_layouts_checked=True,
                         instruction_count=sum(len(instruction_rows(resource)) for resource in resources.values()),
                         target_or_dynamic_writers=len(qualification['writer_inventory'])),
        source_resources=[resource.provenance() for resource in resources.values()],
        implementation_sha256={str(path): sha256(path.read_bytes()).hexdigest() for path in
            (Path(__file__).resolve(), Path(__import__('fdisbull.agi', fromlist=['x']).__file__).resolve(),
             Path(__import__('fdisbull.agi_layout', fromlist=['x']).__file__).resolve())},
        assumptions=[
            'Initial following and invisible flags are both false.',
            'Only source-qualified lure, ring, literal-reset and stutter transitions are admitted.',
            'Logic99 debug flag-edit commands, external state edits/restores and interpreter faults are excluded.',
            'Each admitted source flag effect is atomic; no asynchronous flag mutation is modeled.',
            'Logic CFG entries begin at zero; calls return normally and do not bypass recorded guard edges.',
            'Additional source guards and other state are omitted, overapproximating the admitted commands.',
        ], limitations=[
            'Solver queries cover a two-flag abstraction and a bounded source-linked witness contract.',
            'This is not whole-game reachability, an AGI engine proof, native execution or compatibility evidence.',
            'Resource boundary enumeration does not prove every source instruction is reachable.',
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--logdir', required=True, type=Path)
    parser.add_argument('--volume-dir', required=True, type=Path)
    parser.add_argument('--profile', default='2.917')
    parser.add_argument('--steps', default=8, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(output != checkout and checkout not in output.parents, 'Keep source receipts outside Git')
    try:
        report = analyze(args.logdir, args.volume_dir, args.profile, args.steps)
    except (ValueError, OSError) as exc:
        report = dict(format='fdisbull-agi-goat-invisibility-check-1', status='refused',
                      complete=False, reason=str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], complete=report['complete'],
                         output=str(output), sha256=sha256(output.read_bytes()).hexdigest())))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
