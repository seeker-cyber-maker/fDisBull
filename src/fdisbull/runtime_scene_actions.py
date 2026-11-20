"""Immutable declarations for one explicitly admitted native keyboard action.

The passive RAM grammar remains scene-2. Scene-3 adds a separate action profile;
neither a stored manifest nor its historical observation is live input authority.
"""
from copy import deepcopy


FORMAT = 'fdisbull-scene-3'
ACTION_PROFILE = {'kind': 'qemu-virtual-keyboard', 'version': 1}
_ACTION_FIELDS = {'action', 'guest_ms', 'timeout_ms', 'outcome_phase'}
_PRESS_FIELDS = {'kind', 'key', 'modifiers', 'hold_ms', 'gap_ms'}


def is_action_scene(value):
    return isinstance(value, dict) and value.get('format') == FORMAT


def validate_definition(definition, *, identity=None, stored=False):
    """Validate both profiles and every literal before creating storage rows."""
    from .qemu_keyboard_press import validate_keyboard_press_parameters
    from .runtime_scenes import FORMAT as PASSIVE_FORMAT, validate_definition as validate_passive
    from .scenes import encoded

    if (not is_action_scene(definition)
            or definition.get('action_profile') != ACTION_PROFILE
            or type(definition['action_profile']['version']) is not int):
        raise ValueError('Expected scene-3 with explicit qemu-virtual-keyboard action profile version 1')
    if len(encoded(definition)) > 1024 * 1024:
        raise ValueError('Runtime action scene exceeds 1 MiB')
    doc = deepcopy(definition)
    objects = doc.get('objects')
    if not isinstance(objects, list) or not 1 <= len(objects) <= 64:
        raise ValueError('Runtime action scene requires 1..64 objects')
    extensions = []
    for obj in objects:
        if not isinstance(obj, dict) or 'action' not in obj:
            raise ValueError('Each runtime action object requires an explicit keyboard press')
        action = obj['action']
        if (not isinstance(action, dict) or set(action) - _PRESS_FIELDS
                or not {'kind', 'key'} <= set(action) or action['kind'] != 'press'):
            raise ValueError('Runtime action profile accepts one literal physical keyboard press only')
        action.setdefault('modifiers', [])
        action.setdefault('hold_ms', 40)
        action.setdefault('gap_ms', 40)
        if not isinstance(action['modifiers'], list):
            raise ValueError('Stored keyboard modifiers must be a literal JSON list')
        validate_keyboard_press_parameters(**{key: value for key, value in action.items() if key != 'kind'})
        for key, maximum in (('guest_ms', 120000), ('timeout_ms', 60000)):
            value = obj.setdefault(key, 5000)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f'Runtime action {key} must be an integer in 1..{maximum}')
        phase = obj.setdefault('outcome_phase', 'state')
        if phase not in ('state', 'interface', 'persistence', 'unspecified'):
            raise ValueError('Invalid runtime action outcome phase')
        extensions.append({key: obj.pop(key) for key in _ACTION_FIELDS})

    # Only the explicit action fields are removed. Unknown fields still reach
    # the strict passive validator, including hidden predicate branches.
    doc.pop('action_profile')
    doc['format'] = PASSIVE_FORMAT
    doc = validate_passive(doc, identity=identity, stored=stored)
    doc['format'] = FORMAT
    doc['action_profile'] = deepcopy(ACTION_PROFILE)
    for obj, extension in zip(doc['objects'], extensions, strict=True):
        obj.update(extension)
    if len(encoded(doc)) > 1024 * 1024:
        raise ValueError('Runtime action scene exceeds 1 MiB')
    if stored and doc != definition:
        raise ValueError('Stored runtime action scene is missing canonical fields')
    return doc


def select(project, scene, version, target):
    """Resolve a stored action without issuing a reusable live intention."""
    from .runtime_scenes import select as select_runtime, validate_parameters
    if target is None:
        raise ValueError('A named keyboard action requires an explicit object')
    validate_parameters(scene, object=target)
    info, selected = select_runtime(project, scene, version, target)
    if not is_action_scene(info['definition']):
        raise ValueError('QEMU named keyboard actions require the explicit scene-3 action profile')
    return info, selected
