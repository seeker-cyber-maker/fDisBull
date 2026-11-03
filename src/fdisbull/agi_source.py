"""Immutable AGI resource sets and explicit component/scan-entry witnesses."""
from collections import deque
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import re

from .agi import AGI2917Processor, AGILogicResource, load_logic
from .processor import Location, decode_instruction


def validate_resource(resource):
    if type(resource) is not AGILogicResource:
        raise ValueError('expected immutable AGI logic resource')
    directory, volume, payload, code = resource._directory, resource._volume, resource.payload, resource.code
    if any(type(v) is not bytes for v in (directory, volume, payload, code)):
        raise ValueError('invalid resource snapshot bytes')
    if (resource.profile != '2.917' or type(resource.logic) is not int or not 0 <= resource.logic <= 255
            or len(directory) > 768 or len(directory) % 3 or resource.logic * 3 + 3 > len(directory)
            or len(volume) > 2 * 1024 * 1024):
        raise ValueError('invalid resource snapshot metadata')
    entry = int.from_bytes(directory[resource.logic*3:resource.logic*3+3], 'big')
    number, offset = entry >> 20, entry & 0xfffff
    if (offset == 0xfffff or type(resource.volume) is not int or resource.volume != number
            or type(resource.resource_offset) is not int or resource.resource_offset != offset
            or offset + 5 > len(volume) or volume[offset:offset+2] != b'\x12\x34'
            or volume[offset+2] != number):
        raise ValueError('resource directory or volume header mismatch')
    length = int.from_bytes(volume[offset+3:offset+5], 'little')
    if (type(resource.resource_length) is not int or length != resource.resource_length
            or length < 2 or offset + 5 + length > len(volume)
            or payload != volume[offset+5:offset+5+length]
            or type(resource.code_offset) is not int or resource.code_offset != offset+7):
        raise ValueError('resource payload provenance mismatch')
    size = int.from_bytes(payload[:2], 'little')
    if (size == 0 or size + 2 > len(payload) or code != payload[2:2+size]
            or resource.directory_sha256 != sha256(directory).hexdigest()
            or resource.volume_sha256 != sha256(volume).hexdigest()
            or resource.resource_sha256 != sha256(payload).hexdigest()
            or resource.space != f'agi.logic.{resource.logic}.{sha256(payload).hexdigest()}'):
        raise ValueError('resource source identity mismatch')


def normalize_entries(entries):
    if entries is None:
        return {}
    # CLI LOGIC:OFFSET pairs and JSON objects share one strict contract.
    if isinstance(entries, (list, tuple)):
        pairs = []
        for item in entries:
            if type(item) is not str or item.count(':') != 1:
                raise ValueError('callee entry must be LOGIC:OFFSET')
            key, value = item.split(':')
            try:
                pairs.append((int(key, 0), int(value, 0)))
            except ValueError:
                raise ValueError('callee entry must contain integer LOGIC:OFFSET') from None
    elif isinstance(entries, dict):
        pairs = list(entries.items())
    else:
        raise ValueError('callee_entries must be an explicit mapping or LOGIC:OFFSET pairs')
    result = {}
    for key, value in pairs:
        if type(key) is str and re.fullmatch(r'0|[1-9][0-9]*', key):
            key = int(key)
        if type(key) is not int or not 0 <= key <= 255 or type(value) is not int or value < 0:
            raise ValueError('invalid callee logic or code-relative entry')
        if key in result:
            raise ValueError('duplicate callee entry')
        result[key] = value
    if len(result) > 16:
        raise ValueError('at most 16 captured callee entries')
    return result


def normalize_stops(points):
    if points is None:
        return ()
    if not isinstance(points, (list, tuple)) or len(points) > 32:
        raise ValueError('at most 32 explicit stop_points')
    result = []
    for item in points:
        if type(item) is str:
            parts = item.split(':')
            try:
                item = [int(part, 0) for part in parts]
            except ValueError:
                raise ValueError('stop point must be LOGIC:OFFSET') from None
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or type(item[0]) is not int or not 0 <= item[0] <= 255
                or type(item[1]) is not int or item[1] < 0):
            raise ValueError('stop point must be an integer logic/offset pair')
        result.append(tuple(item))
    if len(set(result)) != len(result):
        raise ValueError('duplicate stop point')
    return tuple(sorted(result))


@dataclass(frozen=True)
class BoundaryEvidence:
    logic: int
    offset: int
    resource_sha256: str
    processor_revision: str
    basis: str
    inspected_instructions: int
    unresolved_paths: int
    runtime_observed: bool = False


def boundary_evidence(resource, offset, *, allow_end=False):
    """Establish a candidate boundary from known encoded paths from code zero.

    This is not proof that an interpreter reached it or cached it as sIP.
    Unknown paths stay unknown; no unknown instruction length is guessed.
    """
    processor = AGI2917Processor(resource.space)
    if offset == 0 or (allow_end and offset == len(resource.code)):
        return BoundaryEvidence(resource.logic,offset,resource.resource_sha256,processor.info.version,
                                'resource-code-start' if offset==0 else 'declared-code-end',0,0)
    pending, queued, seen, spans = deque([0]), {0}, set(), []
    unresolved, consumed = 0, 0
    while pending and len(seen) < 4096 and consumed <= 262144:
        pc = pending.popleft();queued.remove(pc);seen.add(pc)
        try:
            decoded = decode_instruction(processor,resource.code,Location(resource.space,pc))
        except ValueError:
            unresolved += 1
            continue
        if decoded is None:
            unresolved += 1
            continue
        size = decoded.facts['size'];consumed += size
        if decoded.facts['mnemonic'] != 'unsupported':
            spans.append((pc,pc+size))
        for edge in decoded.successors:
            if edge.target is None:
                if edge.kind != 'return':unresolved += 1
            elif edge.target.offset not in seen and edge.target.offset not in queued:
                pending.append(edge.target.offset);queued.add(edge.target.offset)
    if pending or consumed > 262144:
        raise ValueError('instruction-boundary evidence budget exhausted')
    if offset not in seen or any(start < offset < end for start,end in spans):
        raise ValueError('entry/stop is not an established AGI instruction boundary')
    return BoundaryEvidence(resource.logic,offset,resource.resource_sha256,processor.info.version,
                            'candidate-start-from-known-static-edges',len(seen),unresolved)


@dataclass(frozen=True)
class AGIProgram:
    root: AGILogicResource
    callees: tuple[AGILogicResource, ...] = ()
    callee_entries: tuple[tuple[int, int], ...] = ()
    entry_offset: int = 0
    stop_offsets: tuple[int, ...] = ()
    stop_points: tuple[tuple[int, int], ...] = ()
    boundary_checks: tuple[BoundaryEvidence, ...] = field(init=False)

    def __post_init__(self):
        if type(self.callees) is not tuple or type(self.callee_entries) is not tuple:
            raise ValueError('resource and entry snapshots must be immutable tuples')
        resources, volumes = {}, {}
        for resource in (self.root, *self.callees):
            validate_resource(resource)
            if resource.logic in resources:
                raise ValueError('duplicate captured logic resource')
            if resource._directory != self.root._directory:
                raise ValueError('captured resources have different LOGDIR snapshots')
            previous = volumes.setdefault(resource.volume, resource._volume)
            if previous != resource._volume:
                raise ValueError('captured resources have inconsistent volume snapshots')
            resources[resource.logic] = resource
        if len(self.callees) > 16:
            raise ValueError('at most 16 captured callee resources')
        entries = normalize_entries(dict(self.callee_entries))
        if len(entries) != len(self.callee_entries):
            raise ValueError('duplicate callee entry')
        for logic, offset in entries.items():
            if logic not in resources or offset >= len(resources[logic].code):
                raise ValueError('callee entry is outside a captured logic')
        if set(resources) - {self.root.logic} != set(entries) - {self.root.logic}:
            raise ValueError('every captured callee requires an explicit entry witness')
        if type(self.entry_offset) is not int or not 0 <= self.entry_offset < len(self.root.code):
            raise ValueError('entry_offset outside root code')
        if (type(self.stop_offsets) is not tuple or len(self.stop_offsets) > 16
                or any(type(x) is not int or not 0 <= x <= len(self.root.code) for x in self.stop_offsets)
                or len(set(self.stop_offsets)) != len(self.stop_offsets)):
            raise ValueError('invalid or duplicate stop_offsets')
        if type(self.stop_points) is not tuple or normalize_stops(self.stop_points) != self.stop_points:
            raise ValueError('stop_points must be a canonical immutable snapshot')
        for logic, offset in self.stop_points:
            if logic not in resources or offset > len(resources[logic].code):
                raise ValueError('stop point is outside a captured logic')
            if logic == self.root.logic and offset in self.stop_offsets:
                raise ValueError('duplicate root stop point')
        requested = {(self.root.logic,self.entry_offset,False)}
        requested.update((logic,offset,False) for logic,offset in entries.items())
        requested.update((self.root.logic,offset,True) for offset in self.stop_offsets)
        requested.update((logic,offset,True) for logic,offset in self.stop_points)
        object.__setattr__(self,'boundary_checks',tuple(
            boundary_evidence(resources[logic],offset,allow_end=allow_end)
            for logic,offset,allow_end in sorted(requested)))

    @property
    def resources(self):
        return {resource.logic: resource for resource in (self.root, *self.callees)}

    def provenance(self):
        return dict(self.root.provenance(),
                    selection={'entry_offset':self.entry_offset, 'stop_offsets':list(self.stop_offsets),
                               'callee_entries':{str(k):v for k,v in self.callee_entries},
                               'stop_points':[list(point) for point in self.stop_points]},
                    dependencies=[resource.provenance() for resource in self.callees],
                    boundary_checks=[asdict(check) for check in self.boundary_checks])


def bind_program(root, *, callees=(), callee_entries=None, entry_offset=0, stop_offsets=(), stop_points=()):
    entries = normalize_entries(callee_entries)
    return AGIProgram(root, tuple(callees), tuple(sorted(entries.items())), entry_offset,
                      tuple(stop_offsets), normalize_stops(stop_points))


def load_program(logdir, volume_dir, logic, *, profile, entry_offset=0, stop_offsets=(), callee_entries=None,
                 stop_points=()):
    entries = normalize_entries(callee_entries)
    root = load_logic(logdir, volume_dir, logic, profile=profile)
    callees = tuple(load_logic(logdir, volume_dir, number, profile=profile)
                    for number in sorted(entries) if number != logic)
    return bind_program(root, callees=callees, callee_entries=entries,
                        entry_offset=entry_offset, stop_offsets=stop_offsets, stop_points=stop_points)
