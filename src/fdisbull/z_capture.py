"""Small persistent, inspectable recipes for controls learned during research.

Recipes use existing verbs, not generated Python. Observations and scene labels
are authored claims; optional state requirements are executable guards. Capturing
does not certify a transition, and replay never updates scene labels implicitly.
"""

import json
from pathlib import Path


def coordinate_grid(source, output, *, spacing=20, boxes=()):
    """Annotate a stored frame in its own pixel coordinates; never touch guest state."""
    from PIL import Image, ImageDraw
    if type(spacing) is not int or not 10 <= spacing <= 512:
        raise ValueError('grid spacing must be 10..512 pixels')
    with Image.open(source) as original:
        annotated = original.convert('RGB')
    width, height = annotated.size
    draw = ImageDraw.Draw(annotated)
    for x in range(0, width, spacing):
        draw.line((x, 0, x, height - 1), fill=(60, 120, 130))
        draw.text((x + 1, 0), str(x), fill='white', stroke_width=1, stroke_fill='black')
    for y in range(spacing, height, spacing):
        draw.line((0, y, width - 1, y), fill=(60, 120, 130))
        draw.text((0, y + 1), str(y), fill='white', stroke_width=1, stroke_fill='black')
    for box in boxes:
        rect, label = box['rect'], box['label']
        if (len(rect) != 4 or any(type(v) is not int for v in rect)
                or not 0 <= rect[0] < rect[2] < width or not 0 <= rect[1] < rect[3] < height
                or not isinstance(label, str)):
            raise ValueError('boxes need a label and in-frame integer [left,top,right,bottom] rect')
        draw.rectangle(rect, outline='yellow', width=1)
        draw.text((rect[0], max(0, rect[1] - 10)), label, fill='yellow', stroke_width=1, stroke_fill='black')
    annotated.save(output)
    return {'path': str(output), 'width': width, 'height': height,
            'spacing': spacing, 'boxes': list(boxes), 'derived_from': str(source)}


def read_recipes(path):
    path = Path(path)
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if value.get('format') != 'fdisbull-z-recipes-1' or not isinstance(value.get('actions'), dict):
        raise ValueError('invalid captured Z action file')
    return value['actions']


def validate_recipe(name, steps, *, reserved=(), entry='', next_state='',
                    observation=None, requires=None):
    if not isinstance(name, str) or not name.strip() or name in reserved:
        raise ValueError('capture needs a non-reserved action name')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 64:
        raise ValueError('steps must contain 1..64 named operations')
    normalized = []
    for step in steps:
        if not isinstance(step, dict) or set(step) - {'verb', 'params'}:
            raise ValueError('each step accepts verb and params')
        verb, params = step.get('verb'), step.get('params', {})
        if not isinstance(verb, str) or not verb or verb == name:
            raise ValueError('step needs a verb other than the captured action itself')
        if verb in ('close', 'capture-action', 'observe-state', 'list'):
            raise ValueError(f'{verb} cannot be captured as a replay step')
        if not isinstance(params, dict):
            raise ValueError('step params must be an object')
        normalized.append({'verb': verb, 'params': params})
    if not isinstance(entry, str) or not isinstance(next_state, str):
        raise ValueError('entry and next_state must be strings')
    if observation is not None and not isinstance(observation, dict):
        raise ValueError('observation must be an object of authored evidence references')
    if requires is not None and not isinstance(requires, dict):
        raise ValueError('requires must map state keys to expected values')
    result = {'steps': normalized, 'entry': entry, 'next_state': next_state,
              'observation': observation or {}, 'requires': requires or {}}
    json.dumps(result, allow_nan=False)
    return result


def save_recipe(path, name, recipe, *, replace=False):
    path = Path(path)
    actions = read_recipes(path)
    if name in actions and not replace:
        raise ValueError('captured action already exists; use replace=true to revise it')
    actions[name] = recipe
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(json.dumps({'format': 'fdisbull-z-recipes-1', 'actions': actions}, indent=2) + '\n')
    temporary.replace(path)


def recipe_handler(name, recipe):
    def execute(ctx, **params):
        if params:
            raise ValueError('captured recipes have fixed params; compose or promote to Python for parameters')
        mismatch = {key: {'expected': value, 'actual': ctx.state.get(key)}
                    for key, value in recipe.get('requires', {}).items()
                    if key not in ctx.state or ctx.state[key] != value}
        if mismatch:
            raise ValueError(f'captured action entry state differs: {mismatch}')
        results = []
        progress = {'action': name, 'completed_steps': results, 'active_step': None}
        ctx._controller._recipe_progress.append(progress)
        for index, step in enumerate(recipe['steps']):
            progress['active_step'] = index
            result = ctx.invoke(step['verb'], **step.get('params', {}))
            # A handler returning bytes/NaN must not poison the JSON error
            # response and close an otherwise recoverable retained session.
            json.dumps(result, allow_nan=False)
            results.append(result)
        progress['active_step'] = None
        return {'action': name, 'steps': results,
                'expected_next_state': recipe.get('next_state', ''),
                'transition_verified': False}
    return execute
