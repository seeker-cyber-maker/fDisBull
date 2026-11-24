"""Schema-gated, architecture-neutral QEMU CPU inspection."""
from __future__ import annotations

import re
import time


FORMAT = 'fdisbull-native-cpu-inventory-2'
DEFAULT_TIMEOUT_MS = 10_000
SCHEMA_REPLY_BYTES = 4 * 1024 * 1024
QOM_REPLY_BYTES = 1024 * 1024
QOM_PROPERTY_LIMIT = 4096
_QOM_PARENT = '/machine/unattached'


def _schema_index(rows):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('QMP query-qmp-schema returned an invalid schema')
    result = {}
    for row in rows:
        name, meta = row.get('name'), row.get('meta-type')
        if not isinstance(name, str) or not isinstance(meta, str) or name in result:
            raise ValueError('QMP query-qmp-schema returned an invalid type entry')
        result[name] = row
    return result


def _command_return_type(schema, command):
    command_row = schema.get(command)
    if not command_row or command_row.get('meta-type') != 'command':
        return None
    root = command_row.get('ret-type')
    return root if isinstance(root, str) else None


def _field_type(schema, type_id, field_name, *, seen=None):
    """Resolve one named object field through only its declared base chain."""
    if seen is None:
        seen = set()
    if type_id in seen or len(seen) >= 64:
        return None
    seen.add(type_id)
    row = schema.get(type_id)
    if not isinstance(row, dict):
        return None
    members = row.get('members')
    if isinstance(members, list):
        for item in members:
            if isinstance(item, dict) and item.get('name') == field_name:
                member_type = item.get('type')
                if isinstance(member_type, str):
                    return member_type
                return None
    base = row.get('base')
    if isinstance(base, str):
        return _field_type(schema, base, field_name, seen=seen)
    if isinstance(base, list):
        for base_type in base:
            if isinstance(base_type, str):
                found = _field_type(schema, base_type, field_name, seen=seen)
                if found is not None:
                    return found
    return None


def _enum_values(schema, enum_type):
    row = schema.get(enum_type)
    if not isinstance(row, dict) or row.get('meta-type') != 'enum':
        return None
    values = row.get('values', row.get('members'))
    if not isinstance(values, list):
        return None
    resolved = []
    for value in values:
        if isinstance(value, str):
            resolved.append(value)
        elif isinstance(value, dict) and isinstance(value.get('name'), str):
            resolved.append(value['name'])
        else:
            return None
    return resolved


def _query_target_arch_type(schema):
    result_type = _command_return_type(schema, 'query-target')
    return _field_type(schema, result_type, 'arch') if result_type is not None else None


def _query_cpus_fast_target_type(schema):
    result_type = _command_return_type(schema, 'query-cpus-fast')
    result_row = schema.get(result_type) if result_type is not None else None
    if not isinstance(result_row, dict) or result_row.get('meta-type') != 'array':
        return None
    element_type = result_row.get('element-type')
    if not isinstance(element_type, str):
        return None
    return _field_type(schema, element_type, 'target')


def _has_command(schema, command):
    row = schema.get(command)
    return isinstance(row, dict) and row.get('meta-type') == 'command'


def _cpu_children(properties, expected_cpu_type):
    if not isinstance(properties, list) or len(properties) > QOM_PROPERTY_LIMIT:
        raise ValueError('QMP qom-list returned an invalid or oversized property list')
    children = []
    for prop in properties:
        if not isinstance(prop, dict) or not isinstance(prop.get('name'), str) or not isinstance(prop.get('type'), str):
            raise ValueError('QMP qom-list returned an invalid property')
        match = re.fullmatch(r'child<([^<>]+)>', prop['type'])
        if not match:
            continue
        cpu_type = match.group(1)
        if expected_cpu_type is None or cpu_type != expected_cpu_type:
            continue
        name = prop['name']
        if not name or '/' in name or name in ('.', '..') or len(name) > 255:
            raise ValueError('QMP qom-list returned an invalid child name')
        children.append({'qom_path': _QOM_PARENT + '/' + name, 'property': prop})
    return children


def inspect_native_cpu(qmp, *, expected_target, expected_cpu_type=None, timeout_ms=None):
    """Inspect standard QMP CPU data without triggering an unknown target enum.

    ``expected_target`` is session-owned launch identity, never a value inferred
    from a failed QMP query. The complete QMP return schema is read first.
    ``query-target`` and ``query-cpus-fast`` are called only when their
    transitive return types can represent that target. Otherwise one bounded
    ``qom-list`` of ``/machine/unattached`` retains actual CPU child metadata.
    No registers or CPU fields are synthesized from QOM child names.
    """
    if not isinstance(expected_target, str) or not expected_target or len(expected_target) > 128:
        raise ValueError('expected_target must be a nonempty session identity')
    if expected_cpu_type is not None and (
            not isinstance(expected_cpu_type, str) or not expected_cpu_type or len(expected_cpu_type) > 256):
        raise ValueError('expected_cpu_type must be a nonempty QOM type name')
    if timeout_ms is None:
        timeout_ms = DEFAULT_TIMEOUT_MS
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600_000:
        raise ValueError('timeout_ms must be 1..600000 ms')
    deadline = time.monotonic() + timeout_ms / 1000

    def query(command, arguments=None, *, max_reply_bytes=QOM_REPLY_BYTES):
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms < 1:
            raise TimeoutError('Native CPU inspection deadline expired')
        return qmp.call(command, arguments, timeout_ms=remaining_ms,
                        max_reply_bytes=max_reply_bytes)

    schema = _schema_index(query('query-qmp-schema', max_reply_bytes=SCHEMA_REPLY_BYTES))
    target = None
    target_source = None
    target_enum_type = _query_target_arch_type(schema)
    target_enum_values = _enum_values(schema, target_enum_type) if target_enum_type is not None else None
    target_schema_matches = target_enum_values is not None and expected_target in target_enum_values
    if target_schema_matches:
        value = query('query-target')
        if not isinstance(value, dict):
            raise ValueError('QMP query-target returned an invalid result')
        target, target_source = value, 'qmp'

    cpus = None
    qom_cpu_children = []
    cpu_target_enum_type = _query_cpus_fast_target_type(schema)
    cpu_target_values = _enum_values(schema, cpu_target_enum_type) if cpu_target_enum_type is not None else None
    cpus_schema_matches = (target_schema_matches and cpu_target_enum_type == target_enum_type
                           and cpu_target_values is not None and expected_target in cpu_target_values)
    if cpus_schema_matches:
        value = query('query-cpus-fast')
        if not isinstance(value, list) or any(not isinstance(cpu, dict) for cpu in value):
            raise ValueError('QMP query-cpus-fast returned an invalid CPU list')
        cpus = value
        cpu_source = 'query-cpus-fast'
        cpu_paths = [cpu['qom-path'] for cpu in cpus
                     if isinstance(cpu.get('qom-path'), str) and cpu['qom-path']]
    elif _has_command(schema, 'qom-list'):
        properties = query('qom-list', {'path': _QOM_PARENT})
        qom_cpu_children = _cpu_children(properties, expected_cpu_type)
        cpu_source = 'qom-list'
        cpu_paths = [child['qom_path'] for child in qom_cpu_children]
    else:
        cpu_source = 'unavailable'
        cpu_paths = []

    status = None
    status_source = None
    if _has_command(schema, 'query-status'):
        value = query('query-status')
        if not isinstance(value, dict):
            raise ValueError('QMP query-status returned an invalid result')
        status, status_source = value, 'qmp'

    return {
        'format': FORMAT,
        'expected_target': expected_target,
        'expected_target_source': 'caller-declared',
        'expected_cpu_type': expected_cpu_type,
        'target': target,
        'target_source': target_source,
        'cpus': cpus,
        'cpu_paths': cpu_paths,
        'cpu_source': cpu_source,
        'qom_cpu_children': qom_cpu_children,
        'status': status,
        'status_source': status_source,
    }
