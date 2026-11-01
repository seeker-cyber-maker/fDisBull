"""Playable bounded office/bank text projection over the original DOS game."""
import argparse
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import struct
import time
from collections import deque

from PIL import Image
import fdisbull
from fdisbull.action_continuations import ActionContinuation
from fdisbull.dinopark_purchase import bounded_preparation
from fdisbull.project import Project

EXPECTED_EXE = '2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
EXPECTED_VARS = '5e4b32d6e4afd060d72da79bfcac27fdca493905a7e19e299729e31431a1d153'
PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-newgame.json'
SHOP_PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-shop.json'
SAVE_PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-save.json'
STREET_PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-street.json'
MART_PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-mart.json'
OPERATING_PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-operating.json'
CATALOGUE_PATTERNS = Path(__file__).resolve().parent / 'data' / 'dinopark-e55-catalogue.json'
MART_OBSERVATIONS = json.loads(MART_PATTERNS.read_text())['scenes']
BORROW_POPUP = {'samples': [{'x': x, 'y': 73, 'rgb': [44, 44, 44]} for x in
    (80, 87, 99, 105, 111, 123, 132, 137, 147, 167, 172, 178, 184, 195, 201, 212, 217, 222, 230, 235, 244)],
    'min_matches': 21, 'tolerance': 0}
QUALIFICATIONS = ('land_bought', 'dinosaur_bought', 'fence_bought', 'guide_hired',
                  'food_bought', 'park_opened')


class SceneInterrupted(BaseException):
    """Owned session cancellation; it must retain an incomplete native receipt."""


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as output:
        json.dump(value, output, indent=2, default=str)
        output.write('\n'); output.flush(); os.fsync(output.fileno())
    os.replace(temporary, path)

# E49 save overlay, freshly checked against native writer and fresh loader.
# Pen geometry prefixes are rebuilt by the original loader; the trailing ten
# bytes hold the qualified saved pen state and must survive exactly.
SAVE_RANGES = [('cash', '4020:5c3a', 3434, 4), ('loan', '4020:bfbb', 3906, 4),
               ('month', '4020:ccfe', 46, 2), ('year', '4020:ccfc', 48, 2),
               ('day', '4020:6fcb', 60, 2), ('week', '4020:6fc9', 4007, 2),
               ('hunger', '4020:6fc0', 3850, 4), ('food', '4020:6f94', 3854, 18),
               ('staff', '4020:6f88', 3880, 12), ('species', '4020:bfe3', 542, 40)] + [
               (f'pen-{i + 1}', f'4020:{0x4384 + i * 20 + 10:x}', 3442 + i * 20 + 10, 10)
               for i in range(10)]


def native_fields(data):
    if len(data) != 4153 or data[:6] != b'DINOSG':
        raise ValueError('Unsupported original DinoPark save format.')
    return {name: data[offset:offset + length].hex() for name, _, offset, length in SAVE_RANGES}


def live_saved_fields(debug):
    return {name: debug.memory(address, length=length)['hex'].lower()
            for name, address, _, length in SAVE_RANGES}


def navigation_route(current, command, *, park_opened):
    """Bounded menu travel using original transitions, with no scene-field edits."""
    targets = {'office': 'go office', 'bank': 'go bank', 'street': 'go street',
               'dinomart': 'go dinomart', 'general_store': 'go store',
               'employment': 'go employment', 'dino_diner': 'go diner', 'park': 'go park'}
    destination = next((k for k, v in targets.items() if v == command), None)
    if destination is None:
        return None
    if destination == current:
        return []
    edges = {'office': ['bank', 'street'], 'bank': ['office'],
             'street': ['office', 'dinomart', 'general_store', 'employment', 'dino_diner'],
             'dinomart': ['street'], 'general_store': ['street'],
             'employment': ['street'], 'dino_diner': ['street'], 'park': ['street']}
    if park_opened:
        edges['street'].append('park')
    queue = deque([(current, [])])
    visited = {current}
    while queue:
        node, path = queue.popleft()
        for target in edges[node]:
            route = path + [(targets[target], target)]
            if target == destination:
                return route
            if target not in visited:
                visited.add(target)
                queue.append((target, route))
    return None


def save_name(value):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,31}', value):
        raise ValueError('Save names need 1–32 lowercase letters, numbers, underscores or hyphens.')
    return value


def resource_inventory(files):
    return {name: sha for name, sha in files.items()
            if not Path(name).name.upper().startswith('DINOSG.')}


def document_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def pattern_hashes():
    return {'main': digest(PATTERNS), 'shop': digest(SHOP_PATTERNS),
            'save': digest(SAVE_PATTERNS), 'street': digest(STREET_PATTERNS),
            'operating': digest(OPERATING_PATTERNS), 'catalogue': digest(CATALOGUE_PATTERNS)}


def native_save_label(game, number):
    """A native title is distinct from its possibly renumbered disk slot."""
    titles = set()
    for path in game.glob('DINOSG.*'):
        data = path.read_bytes()
        native_fields(data)
        titles.add(data[6:42].split(b'\0', 1)[0].lower())
    for offset in range(1000):
        label = f'agent{(number + offset) % 1000:03d}'
        if label.encode() not in titles:
            return label
    raise ValueError('No unused native save title is available; no save input sent.')


def read_save_bundle(path, source_files):
    """Validate a native save package before any guest input or private copy."""
    path = path.resolve(strict=True)
    manifest = path / 'save.json'
    if manifest.is_symlink() or manifest.stat().st_size > 65536:
        raise ValueError('Unsupported save manifest.')
    envelope = json.loads(manifest.read_text())
    payload = envelope['payload']
    if envelope.get('format') != 'dinopark-native-save-1' or envelope.get('sha256') != document_hash(payload):
        raise ValueError('Save manifest is corrupt or incompatible.')
    if payload['resources'] != resource_inventory(source_files):
        raise ValueError('Saved park resources do not match the supplied original game.')
    expected_patterns = pattern_hashes()
    # Earlier bundles did not bind a separate street recognizer. Their three
    # original pattern identities must still match exactly. The original disk
    # data is checked after loading, and street controls always receive fresh
    # recognition using the current profile; no old scene revision is reused.
    operating_patterns = {key: value for key, value in expected_patterns.items() if key != 'catalogue'}
    previous_patterns = {key: value for key, value in operating_patterns.items() if key != 'operating'}
    legacy_patterns = {key: value for key, value in previous_patterns.items() if key != 'street'}
    if payload['patterns'] not in (expected_patterns, operating_patterns, previous_patterns, legacy_patterns):
        raise ValueError('Saved park scene qualification is incompatible.')
    if set(payload['qualifications']) != set(QUALIFICATIONS) or any(
            payload['qualifications'][key] is not True for key in QUALIFICATIONS):
        raise ValueError('Saved park is outside the qualified running-park route.')
    native = path / 'DINOSG.000'
    if native.is_symlink() or not 1 <= native.stat().st_size <= 1048576 or digest(native) != payload['native_sha256']:
        raise ValueError('Native game save is missing, corrupt or incompatible.')
    if native_fields(native.read_bytes()) != payload['saved_fields']:
        raise ValueError('Native game save fields disagree with the manifest.')
    return payload, native


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob('*')) if p.is_file()}


def pixel_predicate(pattern):
    base = {'pixels': {key: pattern[key] for key in ('samples', 'min_matches', 'tolerance')}}
    rejected = pattern.get('reject', [])
    return {'all': [base] + [{'not': pixel_predicate(other)} for other in rejected]} if rejected else base


def take_frame(project, debug, name, *, hooks=True):
    filename = name + '.png'
    number = 2
    while (project.path.parent / filename).exists():
        filename = f'{name}-{number}.png'
        number += 1
    frame = debug.screenshot(filename, hooks=hooks)
    project.debug_export(frame['artifact'], project.path.parent / filename)
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (frame['artifact'],)).fetchone()
    with Image.open(io.BytesIO(row['data'])) as picture:
        image = picture.convert('RGB')
        if image.size != (320, 200):
            raise RuntimeError('unsupported video dimensions')
        return frame, image


def matches(image, pattern):
    return (sum(all(abs(a-b) <= pattern['tolerance'] for a, b in zip(image.getpixel((s['x'], s['y'])), s['rgb']))
                for s in pattern['samples']) >= pattern['min_matches'] and
            not any(matches(image, other) for other in pattern.get('reject', [])))


def park_static_pattern(pattern):
    """Project the retained profile outside the occupied first pen contents.

    The original 40-anchor profile remains immutable for native-save identity.
    Every retained anchor still requires its exact color; this excludes an
    entire actor region rather than permitting an arbitrary missed sample.
    """
    samples = [s for s in pattern['samples'] if not (s['x'] < 90 and 115 <= s['y'] < 175)]
    if len(pattern['samples']) != 40 or len(samples) != 32:
        raise ValueError('Unexpected park observation profile; qualify its actor regions explicitly')
    return {**pattern, 'samples': samples, 'min_matches': len(samples)}


def parking_notice_input(text):
    """Press the original advice window's visible thumb, never a purchase."""
    frame, image = take_frame(text.project, text.debug, 'parking-input-before')
    if (not matches(image, text.patterns['parking_hint']) or
            matches(image, text.patterns['quarter_popup'])):
        raise RuntimeError('Parking advice is not uniquely qualified; acknowledgment withheld')
    mouse = text.debug.call('input.mouse.state')['mouse']
    if mouse['buttons'] or mouse['release_pending']:
        raise RuntimeError('Parking pointer is held; acknowledgment withheld')
    moved = text.debug.call('input.mouse.move', {'x': 160, 'y': 111,
        'mode_id': frame['metadata']['mode_id'], 'frame_id': frame['metadata']['frame_id']})
    if moved.get('accepted') is not True:
        raise RuntimeError('Parking pointer movement unavailable; acknowledgment withheld')
    run_guest(text.debug, 1000)
    frame, image = take_frame(text.project, text.debug, 'parking-input-prepared')
    if (not matches(image, text.patterns['parking_hint']) or
            matches(image, text.patterns['quarter_popup'])):
        raise RuntimeError('Parking view changed; acknowledgment withheld')
    text.event({'phase': 'parking_pointer_prepared', 'point': [160, 111],
                'frame': frame, 'acknowledgment_input': 'not_sent'})
    return text.debug.click(160, 111, hold_ms=150,
                            mode_id=frame['metadata']['mode_id'], frame_id=frame['metadata']['frame_id'])


def food_draft_state(debug):
    cash = balances(debug)
    resources = park_resources(debug)
    pending = pending_small_feeders(debug)
    reserved = cash['cash'] - cash['working_cash']
    quantity = pending - resources['small_feeders']
    if resources['guides'] != 1 or not 0 <= quantity <= 20 or reserved != 25 * quantity:
        raise RuntimeError('Food draft counters disagree; outcome unknown')
    return quantity, {'balances': cash, 'resources': resources, 'pending_small_feeders': pending}


def notice_return_frame(text, label, views, *, continuation=None):
    """Observe a completed destination without replaying the notice input."""
    continuation = continuation or ActionContinuation(label, event=text.event)
    latest = []
    def observe():
        frame, image = take_frame(text.project, text.debug, label)
        latest[:] = [frame, image]
        found = [view for view in views if matches(image, text.patterns[view])]
        notices = [n for n in ('parking_hint', 'quarter_popup') if matches(image, text.patterns[n])]
        text.event({'phase': 'notice_return_observation', 'frame': frame,
                    'matched_views': found, 'remaining_notices': notices, 'following_input': 'not_sent'})
        return {'destinations': found, 'interruptions': notices, 'evidence': frame}
    continuation.wait(observe, lambda ms: run_guest(text.debug, ms))
    text.last_continuation = dict(continuation.record)
    return tuple(latest)


def wait_for_office(project, debug, patterns):
    # A slow or blank frame is not readiness. Wait without replaying any input.
    for attempt in range(13):
        name = 'office-before' if attempt == 0 else f'office-wait-{attempt:02d}'
        frame, image = take_frame(project, debug, name)
        if matches(image, patterns['office']) and not matches(image, patterns['bank']):
            return frame
        if attempt < 12:
            run_guest(debug, 500)
    raise RuntimeError('office not uniquely recognized after startup')


def load_view(project, debug, patterns, view, event):
    for attempt in range(13):
        frame, image = take_frame(project, debug, 'load-' + view)
        matched = matches(image, patterns[view])
        event({'phase': 'load_view', 'view': view, 'frame': frame, 'matched': matched})
        if matched:
            return frame
        if attempt < 12:
            run_guest(debug, 500)
    raise RuntimeError('Original load view not recognized: ' + view + '; further input withheld')


def run_guest(debug, ms):
    result = debug.run(guest_ms=ms, timeout_ms=15000, fast_forward=True)
    if result['outcome'] != 'guest_time':
        raise RuntimeError('guest stopped unexpectedly: ' + result['outcome'])
    return result


def click(debug, x, y):
    return debug.click(x, y, hold_ms=80)


def prepare_scene_pointer(debug, scene, event, *, object_name='office.bank'):
    """Consume cursor movement before a qualified named control is pressed.

    Frame recognition establishes appearance, not consumption of prior mouse
    callbacks. Do not merge movement and press or repeat a timed-out press.
    """
    commands={'office.bank':'go bank','bank.payoff':'repay',
              'bank.borrow':'borrow','bank.back':'go office','mart.back':'go street',
              'park.back':'go street'}
    if object_name not in commands:
        raise ValueError('Unqualified named control')
    document=debug.project.debug_scene_info(scene,version=debug.version['id'])['definition']
    targets=[o for o in document['objects'] if o['name']==object_name]
    if len(targets)!=1 or targets[0]['action']['kind']!='click':
        raise ValueError('Named control definition unavailable; press withheld')
    point=targets[0]['point']
    before=debug.scene_assert(scene,object=object_name)
    mouse=debug.call('input.mouse.state')['mouse']
    if mouse['buttons'] or mouse['release_pending']:
        raise ValueError('Pointer is held or releasing; press withheld')
    frame=before['frame']
    moved=debug.call('input.mouse.move',{'x':point[0],'y':point[1],
        'mode_id':frame['mode_id'],'frame_id':frame['frame_id']})
    settle_ms = 1000 if object_name in ('mart.back', 'park.back') else 150
    run_guest(debug,settle_ms)
    after=debug.call('input.mouse.state')['mouse']
    if (after['buttons'] or after['release_pending'] or
            any(after[k]!=moved['mouse'][k] for k in ('x','y'))):
        raise ValueError('Pointer did not settle; press withheld')
    checked=debug.scene_assert(scene,object=object_name)
    event({'phase':'pointer_prepared','command':commands[object_name],
           'object':object_name,'point':point,
           'guest_ms':settle_ms,'mouse_before':mouse,'mouse_after':after,
           'observation':checked['observation'],'bank_press':'not_sent', 'press':'not_sent'})
    return point


# Retain the original helper entry point for existing native probes.
prepare_bank_pointer = prepare_scene_pointer


def park_catalogue_pointer(text, *, budget=None):
    """Move the original software cursor away from labels and toolbar probes."""
    if budget is not None:
        budget.timeout()
    moved = text.debug.call('input.mouse.move', {'x': 270, 'y': 170})
    text.event({'phase': 'mart_pointer_parked', 'point': [270, 170], 'result': moved})
    if moved.get('accepted') is not True:
        raise RuntimeError('Catalogue pointer movement unavailable; no purchase input sent')
    if budget is None:
        run_guest(text.debug, 150)
    else:
        budget.run(text.debug, 150)


def catalogue_pan_valid(text, frame, image, selector):
    surface = matches(image, text.patterns['mart_surface'])
    current = text.debug.memory('4020:3c5c', length=2)['hex']
    modals = [name for name in ('quarter_popup', 'parking_hint', 'game_menu',
                               'save_dialog', 'load_dialog')
              if matches(image, text.patterns[name])]
    valid = surface and current == selector and not modals
    if not valid:
        text.event({'phase': 'catalogue_pan_rejected', 'frame': frame,
                    'surface_matched': surface, 'scene_request_before': selector,
                    'scene_request_after': current, 'modal_matches': modals,
                    'purchase_input': 'not_sent'})
    return valid


class BankInputSession:
    """Prepare bank controls and catalogue/park exits; delegate other native calls."""
    def __init__(self, native, event):
        self.native, self.event = native, event

    def __getattr__(self, name):
        return getattr(self.native,name)

    def scene_click(self, scene, object, **options):
        if object in ('office.bank','bank.payoff','bank.borrow','bank.back','mart.back','park.back'):
            prepare_scene_pointer(self.native,scene,self.event,object_name=object)
        return self.native.scene_click(scene,object,**options)


class KnownSceneNotice(RuntimeError):
    def __init__(self, notice, frame):
        super().__init__('Recognized original notice: ' + notice)
        self.notice, self.frame = notice, frame


def prepare_mart_first_page(text, *, budget=None):
    """Resolve the Coelophysis intent independently of the last catalogue read."""
    text.debug.scene_assert(text.mart, object='mart.back')
    park_catalogue_pointer(text, budget=budget)
    selector = text.debug.memory('4020:3c5c', length=2)['hex']
    for attempt in range(49):
        if budget is not None:
            budget.timeout()
        frame, image = take_frame(text.project, text.debug, 'mart-first-page')
        if matches(image, text.patterns['coel_page']):
            predicate = pixel_predicate(text.patterns['coel_page'])
            context = {'memory': {'address': '4020:3c5c', 'length': 2, 'hex': selector}}
            doc = definition(frame, 'DinoMart first catalogue page', predicate, context,
                             'mart.back', [216, 187], pixel_predicate(text.patterns['shop_street']))
            text.mart = text.project.debug_save_scene('dinomart', doc, parent=text.mart)['id']
            text.event({'phase': 'catalogue_prepared', 'command': 'buy coelophysis',
                        'page': 'first', 'frame': frame, 'purchase_input': 'not_sent'})
            return
        if not catalogue_pan_valid(text, frame, image, selector):
            raise RuntimeError('Catalogue navigation context changed; purchase input withheld')
        if attempt == 48:
            break
        if budget is not None:
            budget.timeout()
        moved = text.debug.call('input.mouse.move', {'x': 0, 'y': 50})
        text.event({'phase': 'mart_pan_input', 'result': moved, 'point': [0, 50]})
        if moved.get('accepted') is not True:
            raise RuntimeError('Catalogue movement outcome unknown; do not retry')
        if budget is None:
            run_guest(text.debug, 80)
        else:
            budget.run(text.debug, 80)
        park_catalogue_pointer(text, budget=budget)
    raise RuntimeError('First catalogue page not reached within the pan budget; purchase input withheld')


def definition(reference, title, predicate, selector, action, point, outcome):
    document = {'format': 'fdisbull-scene-1', 'reference': reference['artifact'],
        'width': 320, 'height': 200, 'mode_id': reference['metadata']['mode_id'],
        'context': {'state': title, 'triggers': ['original guest navigation'],
                    'qualification': 'visual samples plus observed selector correlation; not universal control readiness'},
        'match': predicate,
        'objects': [{'name': action, 'area': {'rect': [point[0]-4, point[1]-4, point[0]+5, point[1]+5]},
                     'point': point, 'context': {'state': action, 'triggers': ['containing scene'],
                         'qualification': 'fixture-calibrated click point and dispatch selector'},
                     'visible': predicate, 'ready': selector, 'enabled': selector,
                     'action': {'kind': 'click'}, 'outcome': outcome,
                     'guest_ms': 12000, 'timeout_ms': 10000}]}
    if action == 'park.back':
        # Returning to MALL loads original assets through registered observers,
        # just like business entry. Bound loading without another queued press.
        document['objects'][0]['timeout_ms'] = 40000
    return document


BUSINESS_ENTRIES = {
    'dinomart': ('street.mart', [160, 66], ('mart', 'after')),
    'employment': ('street.employment', [270, 66], ('employment',)),
    'dino_diner': ('street.diner', [55, 65], ('dino_diner', 'food_menu', 'food_selected')),
    'general_store': ('street.store', [270, 140], ('general_store', 'fence_tab', 'fence_selected')),
}


def business_entry_object(reference, predicate, selector, patterns, view):
    name, point, views = BUSINESS_ENTRIES[view]
    outcome = {'any': [pixel_predicate(patterns[v]) for v in views]}
    obj = definition(reference, 'street', predicate, selector, name, point, outcome)['objects'][0]
    # Loading a business reads several original assets. Native observation
    # hooks can consume host time while only a few guest seconds have elapsed.
    # Keep both budgets finite and below the player's 60-second request bound.
    obj['timeout_ms'] = 40000
    return obj


def mart_entry_object(reference, predicate, selector, patterns):
    return business_entry_object(reference, predicate, selector, patterns, 'dinomart')


def click_business(text, command, scene, name):
    """Retain navigation input evidence even when destination observation raises."""
    from .scenes import SceneError
    def retain(result):
        receipt = dict(result)
        for field, value in (('scene_revision', scene), ('action_name', name), ('run', text.debug.run_id)):
            receipt.setdefault(field, value)
        text.event({'phase': 'navigation_input_result', 'command': command, 'result': receipt})
    try:
        result = text.debug.scene_click(scene, name)
    except SceneError as error:
        retain(error.result)
        raise
    retain(result)
    return result


def qualify_street(text):
    """Read and bind the original street destination without guest execution."""
    frame, image = take_frame(text.project, text.debug, 'park-exit-street', hooks=False)
    if not matches(image, text.patterns['shop_street']):
        raise RuntimeError('Street destination not recognized; outcome unknown')
    selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                          'hex': text.debug.memory('4020:3c5c', length=2)['hex']}}
    predicate = pixel_predicate(text.patterns['shop_street'])
    office = text.project.debug_scene_info(text.office)['definition']['match']
    doc = definition(frame, 'street', predicate, selector,
                     'street.office', [175, 140], office)
    for view in BUSINESS_ENTRIES:
        doc['objects'].append(business_entry_object(frame, predicate, selector, text.patterns, view))
    version = text.debug.version['id']
    original = text.project.debug_scene_info(text.street, version=version)
    latest = text.project.debug_scene_info(original['name'], version=version)
    if latest['scene'] != original['scene']:
        raise RuntimeError('Street scene root changed; outcome unknown')
    # Publication can commit before its return readback raises. Re-read the
    # committed host head so a later read-only retry never forks a stale parent.
    saved = text.project.debug_save_scene('street', doc, parent=latest['id'], version=version)
    text.street, text.current = saved['id'], 'street'
    return {'frame': frame, 'view': 'street', 'scene': saved}


def qualify_park(text):
    """Bind the existing original park from reads only; never repeat entry."""
    frame, image = take_frame(text.project, text.debug, 'park-revisited', hooks=False)
    if (not matches(image, text.patterns['park_view']) or
            any(matches(image, text.patterns[n]) for n in ('quarter_popup', 'parking_hint'))):
        raise RuntimeError('Park destination not uniquely recognized; outcome unknown')
    selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                          'hex': text.debug.memory('4020:3c5c', length=2)['hex']}}
    doc = definition(frame, 'park', pixel_predicate(text.patterns['park_view']), selector,
                     'park.back', [173, 187], pixel_predicate(text.patterns['street_view']))
    version = text.debug.version['id']
    original = text.project.debug_scene_info(text.park, version=version)
    latest = text.project.debug_scene_info(original['name'], version=version)
    if latest['scene'] != original['scene']:
        raise RuntimeError('Park scene root changed; outcome unknown')
    saved = text.project.debug_save_scene('park', doc, parent=latest['id'], version=version)
    text.park, text.current, text.pending_park_entry = saved['id'], 'park', False
    return {'frame': frame, 'view': 'park', 'scene': saved}


def qualify_business(text, view):
    """Publish a fresh destination from host reads only, including scene re-entry."""
    if view == 'dinomart':
        return qualify_dinomart(text)
    _, _, views = BUSINESS_ENTRIES[view]
    frame, image = take_frame(text.project, text.debug, view + '-entry', hooks=False)
    if not any(matches(image, text.patterns[v]) for v in views):
        raise RuntimeError('Location not recognized; outcome unknown: ' + view)
    selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                          'hex': text.debug.memory('4020:3c5c', length=2)['hex']}}
    street = text.project.debug_scene_info(text.street)['definition']['match']
    target, point = ((view + '.catalogue', [205, 105]) if view == 'general_store'
                     else (view + '.back', [173, 187]))
    predicate = {'any': [pixel_predicate(text.patterns[v]) for v in views]}
    doc = definition(frame, view, predicate, selector, target, point, street)
    saved = text.project.debug_save_scene(view, doc, parent=text.locations.get(view))
    text.locations[view], text.current = saved['id'], view
    return {'frame': frame, 'view': view, 'scene': saved}


def qualify_dinomart(text):
    """Read the current destination and publish its scene; never send guest input."""
    frame, image = take_frame(text.project, text.debug, 'dinomart-before', hooks=False)
    views = [view for view in ('mart', 'after') if matches(image, text.patterns[view])]
    if not views:
        raise RuntimeError('DinoMart catalogue not recognized; outcome unknown')
    view = views[0]
    selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                          'hex': text.debug.memory('4020:3c5c', length=2)['hex']}}
    street = text.project.debug_scene_info(text.street)['definition']['match']
    doc = definition(frame, 'dinomart', pixel_predicate(text.patterns[view]), selector,
                     'mart.back', [216, 187], street)
    saved = text.project.debug_save_scene('dinomart', doc, parent=text.mart)
    text.mart, text.current = saved['id'], 'dinomart'
    return {'frame': frame, 'view': view, 'scene': saved}


def balances(debug):
    fields = {'cash': '4020:5c3a', 'loan': '4020:bfbb', 'working_cash': '4020:bad4'}
    return {key: int.from_bytes(bytes.fromhex(debug.memory(address, length=4)['hex']), 'little', signed=True)
            for key, address in fields.items()}


def park_resources(debug):
    """Read the live, committed guide and small-feeder counts."""
    fields = {'guides': '4020:6f8e', 'small_feeders': '4020:6f94'}
    return {key: int.from_bytes(bytes.fromhex(debug.memory(address, length=2)['hex']), 'little')
            for key, address in fields.items()}


def pending_guide(debug):
    return int.from_bytes(bytes.fromhex(debug.memory('4020:b9fc', length=2)['hex']), 'little')


def pending_small_feeders(debug):
    return int.from_bytes(bytes.fromhex(debug.memory('4020:b9e4', length=2)['hex']), 'little', signed=True)


def food_order_state(debug):
    def word(address):
        return int.from_bytes(bytes.fromhex(debug.memory(address, length=2)['hex']), 'little')
    calendar = [word(address) for address in ('4020:ccfc', '4020:ccfe', '4020:6fcb', '4020:6fc9')]
    if not 0 <= calendar[1] < 12:
        raise RuntimeError('Food commit month is outside the qualified calendar')
    return {'balances': balances(debug), 'calendar': calendar,
            'live_food': list(struct.unpack('<9h', bytes.fromhex(debug.memory('4020:6f94', length=18)['hex']))),
            'pending_food': list(struct.unpack('<9h', bytes.fromhex(debug.memory('4020:b9e4', length=18)['hex']))),
            'expenses': int.from_bytes(bytes.fromhex(debug.memory(
                f'4020:{0xc03b + calendar[1] * 4:x}', length=4)['hex']), 'little')}


def park_snapshot(debug):
    """Read a bounded runtime snapshot; fields are not saved-game claims."""
    def word(address):
        return int.from_bytes(bytes.fromhex(debug.memory(address, length=2)['hex']), 'little')
    raw = bytes.fromhex(debug.memory('4020:4384', length=200)['hex'])
    pens = []
    for index in range(10):
        species, count = struct.unpack_from('<hh', raw, index * 20 + 14)
        if count < 0 or species < -1 or species >= 20 or (species == -1 and count != 0):
            raise RuntimeError('unrecognized pen data; dinosaur count unknown')
        if species != -1 or count:
            pens.append({'pen': index + 1, 'species_id': species, 'count': count})
    bins_raw = bytes.fromhex(debug.memory('4020:6f94', length=18)['hex'])
    food = list(struct.unpack('<9h', bins_raw))
    if any(value < 0 for value in food):
        raise RuntimeError('unrecognized food stock; food quantities unknown')
    return {'year_index': word('4020:ccfc'), 'month_index': word('4020:ccfe'),
            'day_of_month_counter': word('4020:6fcb'), 'weekly_counter': word('4020:6fc9'),
            'balances': balances(debug), 'guides': park_resources(debug)['guides'],
            'hunger_counter': int.from_bytes(bytes.fromhex(debug.memory('4020:6fc0', length=4)['hex']), 'little'),
            'food_bins': food, 'pens': pens, 'dinosaurs': sum(p['count'] for p in pens)}


def vegasaurus_order_state(debug):
    snapshot = park_snapshot(debug)
    return {'balances': snapshot['balances'],
            'calendar': [snapshot[k] for k in ('year_index', 'month_index', 'day_of_month_counter', 'weekly_counter')],
            'expenses': list(struct.unpack('<12I', bytes.fromhex(debug.memory('4020:c30b', length=48)['hex']))),
            'pens': debug.memory('4020:4384', length=200)['hex'],
            'species': debug.memory('4020:bfe3', length=40)['hex'],
            'selection': int.from_bytes(bytes.fromhex(debug.memory('4020:68a5', length=2)['hex']), 'little'),
            'dinosaurs': snapshot['dinosaurs']}


def verify_vegasaurus_order(states):
    """Check full native debit/expense/refund instruction boundaries."""
    before, reserved, refund_before, refunded = states
    money = before['balances']
    month = before['calendar'][1]
    if (before['selection'] != 19 or not 0 <= month < 12 or money['cash'] < 25000 or
            money['cash'] != money['working_cash']):
        raise RuntimeError('Vegasaurus order was not qualified at the native purchase boundary')
    expenses = list(before['expenses'])
    expenses[month] = (expenses[month] + 25000) & 0xffffffff
    staged = {**money, 'working_cash': money['cash'] - 25000}
    for state in (reserved, refund_before, refunded):
        if (any(state[k] != before[k] for k in ('pens', 'species', 'dinosaurs')) or
                state['expenses'] != expenses):
            raise RuntimeError('Vegasaurus expense or ownership proof did not match; outcome unknown')
    # Calendar settlement can occur during the original animation. Freeze
    # each tight instruction pair, not the interval between debit and release.
    release_money = refund_before['balances']
    released = {**release_money, 'working_cash': release_money['working_cash'] + 25000}
    if (reserved['calendar'] != before['calendar'] or reserved['balances'] != staged or
            refunded['calendar'] != refund_before['calendar'] or
            release_money['cash'] - release_money['working_cash'] != 25000 or
            refunded['balances'] != released or released['cash'] != released['working_cash']):
        raise RuntimeError('Vegasaurus reservation/refund did not match; outcome unknown')
    return {'reservation_released': 25000, 'committed_cash_before': money['cash'],
            'committed_cash_after': refunded['balances']['cash'], 'expense_posted': 25000,
            'cash_change_during_animation': release_money['cash'] - money['cash'],
            'loan_before': money['loan'], 'loan_after': release_money['loan'],
            'calendar_before': before['calendar'], 'calendar_after': refunded['calendar'],
            'expense_month': month, 'dinosaurs_before': before['dinosaurs'],
            'dinosaurs_after': refunded['dinosaurs']}


class TextScene:
    def __init__(self, debug, office, bank, *, project=None, patterns=None, event=None):
        self.debug, self.office, self.bank = debug, office, bank
        self.street = None
        self.mart = None
        self.park = None
        self.locations = {}
        self.land_bought = False
        self.dinosaur_bought = False
        self.fence_bought = False
        self.guide_hired = False
        self.food_bought = False
        self.park_opened = False
        self.notice_outcome_unknown = False
        self.pending_park_entry = False
        self.pending_food_notice = False
        self.pending_food_return = False
        self.project, self.patterns, self.event = project, patterns, event
        self.current = 'office'
        self.last_action = None
        self.transaction_count = 0
        self.vegasaurus_attempted = False
        self.vegasaurus_proof = None
        self.vegasaurus_extinct = False
        self.last_continuation = None
        self.bounded_purchases = False
        self.dinosaur_order = None
        self.land_order = None
        self.fence_order = None

    def save_preflight(self, name):
        try:
            save_name(name)
        except ValueError as exc:
            return str(exc) + ' No input was sent.'
        if (self.notice_outcome_unknown or self.pending_park_entry or self.pending_food_notice or
                not all(getattr(self, key) for key in QUALIFICATIONS)):
            return 'Saving is available after completing the running-park setup. No input was sent.'
        if (self.save_library / name).exists():
            return 'That saved-park name already exists. Choose a new name. No input was sent.'
        return None

    def saved_view(self, name):
        for attempt in range(13):
            frame, image = take_frame(self.project, self.debug, name)
            matched = matches(image, self.patterns[name])
            self.event({'phase': 'save_view', 'view': name, 'matched': matched, 'frame': frame})
            if matched:
                return frame
            if attempt < 12:
                run_guest(self.debug, 500)
        raise RuntimeError('Save view was not recognized: ' + name + '; outcome unknown')

    def save_key(self, key):
        result = self.debug.keyboard_press(key)
        self.event({'phase': 'save_key', 'key': key, 'result': result})
        if result.get('accepted') is not True or result.get('delivery') != 'queued':
            raise RuntimeError('Save keyboard input outcome unknown; do not retry')
        run_guest(self.debug, 100)

    def restore_qualifications(self, payload):
        observed = live_saved_fields(self.debug)
        self.event({'phase': 'native_load_readback', 'expected': payload['saved_fields'],
                    'observed': observed, 'matched': observed == payload['saved_fields']})
        if observed != payload['saved_fields']:
            raise RuntimeError('Original loaded park differs from its native save; resume withheld')
        self.event({'phase': 'street_guard_binding', 'saved_profile_sha256': payload['patterns'].get('street'),
                    'current_profile_sha256': digest(STREET_PATTERNS),
                    'legacy_bundle': 'street' not in payload['patterns'],
                    'native_fields_verified': True,
                    'policy': 'new live scene recognition required; earlier scene revisions not reused'})
        for key in QUALIFICATIONS:
            setattr(self, key, payload['qualifications'][key])
        snapshot = park_snapshot(self.debug)
        self.event({'phase': 'result', 'command': 'load park', 'after': snapshot,
                    'persistence': 'native disk save and fresh original loader verified',
                    'session_rng_and_day_phase': 'not restored by this interface'})

    def save_park(self, name):
        refusal = self.save_preflight(name)
        if refusal:
            self.event({'phase': 'refused', 'command': 'save park ' + name, 'input': 'not_sent', 'reason': refusal})
            return refusal
        if self.current != 'office':
            return 'Go to the office before saving. No input was sent.'
        self.debug.scene_assert(self.office, object='office.bank')
        before = park_snapshot(self.debug)
        if before['balances']['cash'] != before['balances']['working_cash']:
            return 'Finish the pending transaction before saving. No input was sent.'
        old_files = {p.name: digest(p) for p in self.game.glob('DINOSG.*')}
        number = next((i for i in range(1000) if f'DINOSG.{i:03d}' not in old_files), None)
        if number is None:
            return 'No unused native save slot is available. No input was sent.'
        label = native_save_label(self.game, number)
        self.event({'phase': 'intent', 'command': 'save park ' + name, 'before': before,
                    'native_label': label, 'input': 'not_yet_sent'})
        self.save_key('escape')
        run_guest(self.debug, 1200)
        self.saved_view('game_menu')
        self.shop_click((217, 121), 1200, 'open original save dialog', hold_ms=80)
        self.saved_view('save_dialog')
        self.shop_click((85, 58), 500, 'focus original save name', hold_ms=80)
        for key in ['backspace'] * 32 + list(label):
            self.save_key(key)
        self.saved_view('save_dialog')
        # The focused name editor consumes a mouse OK without committing.
        # Enter is the independently observed native submit action.
        self.save_key('enter')
        run_guest(self.debug, 1000)
        self.saved_view('game_menu')
        changed = [p for p in self.game.glob('DINOSG.*') if old_files.get(p.name) != digest(p)]
        if len(changed) != 1 or changed[0].name in old_files:
            raise RuntimeError('Expected one new native save; save outcome unknown')
        data = changed[0].read_bytes()
        fields = native_fields(data)
        observed = live_saved_fields(self.debug)
        self.event({'phase': 'native_save_readback', 'file': changed[0].name,
                    'native_sha256': digest(changed[0]), 'expected': fields, 'observed': observed})
        if fields != observed or not data[6:42].startswith(label.encode() + b'\0'):
            raise RuntimeError('Native save bytes or label differ from live park; export withheld')
        self.shop_click((160, 170), 1200, 'return from main menu', hold_ms=80)
        frame = wait_for_office(self.project, self.debug, self.patterns)
        self.debug.scene_assert(self.office, object='office.bank')
        self.save_library.mkdir(parents=True, exist_ok=True)
        bundle = self.save_library / name
        bundle.mkdir()  # Never overwrite an earlier named park.
        payload = {'resources': resource_inventory(self.source_files),
                   'patterns': pattern_hashes(),
                   'qualifications': {key: getattr(self, key) for key in QUALIFICATIONS},
                   'saved_fields': fields, 'snapshot': before, 'native_sha256': digest(changed[0]),
                   'script_sha256': digest(Path(__file__)), 'fdisbull_version': fdisbull.__version__}
        with (bundle / 'DINOSG.000').open('xb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        with (bundle / 'save.json').open('x') as output:
            json.dump({'format': 'dinopark-native-save-1', 'payload': payload,
                       'sha256': document_hash(payload)}, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        directory = os.open(bundle, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        read_save_bundle(bundle, self.source_files)
        self.event({'phase': 'result', 'command': 'save park ' + name, 'bundle': str(bundle),
                    'native_sha256': payload['native_sha256'], 'frame': frame,
                    'persistence': 'native disk bytes verified; fresh load not yet checked'})
        return f'Park saved as {name}. Resume folder: {bundle}\nUse load park {name}, or --load-save with that folder in a later session.'

    def describe(self):
        selected, obj = {'office': (self.office, 'office.bank'),
                         'bank': (self.bank, 'bank.back'),
                         'street': (self.street, 'street.office'),
                         'dinomart': (self.mart, 'mart.back'),
                         'employment': (self.locations.get('employment'), 'employment.back'),
                         'dino_diner': (self.locations.get('dino_diner'), 'dino_diner.back'),
                         'park': (self.park, 'park.back'),
                         'general_store': (self.locations.get('general_store'), 'general_store.catalogue')}[self.current]
        result = self.debug.scene_assert(selected, object=obj)
        if result.get('status') != 'matched':
            raise RuntimeError('scene observation was not matched')
        if self.current == 'office':
            return 'You are in the park office. You can go to the bank or out to the street.\nCommands: go bank, go street, look, quit.'
        if self.current == 'street':
            return ('You are on the street outside the park businesses. The office and DinoMart are here.\n'
                    'A desert plot costs $500. Commands: buy desert plot, go dinomart, go store, go employment, go diner, check inventory, open park, go park, status, advance time, acknowledge notice, go office, look, quit.')
        if self.current == 'park':
            day = int.from_bytes(bytes.fromhex(self.debug.memory('4020:6fcb', length=2)['hex']), 'little')
            cash = balances(self.debug)['cash']
            return (f'You are viewing the park. Day counter: {day}. Cash: ${cash:,}. '
                    'Time advanced during entry; a separate open/closed status is not established.\n'
                    'Commands: status, advance time, acknowledge notice, go street, look, quit.')
        if self.current == 'general_store':
            return ('You are in the General Store. A catalogue and an order form lie on the counter. '
                    'A wood fence costs $1,000 per pen.\n'
                    'Commands: buy wood fence, go street, look, quit.')
        if self.current == 'employment':
            return ('You are at the employment office. Posters list the park jobs.\n'
                    'A tour guide costs $900 per month. Commands: hire tour guide, go street, look, quit.')
        if self.current == 'dino_diner':
            return ('You are in the Dino Diner. The menu offers meat, plants and seeds.\n'
                    'Twenty small feeders cost $500. Commands: buy 20 small feeders, go street, look, quit.')
        if self.current == 'dinomart':
            values = balances(self.debug)
            if self.vegasaurus_extinct:
                return (f"You are in DinoMart. The Vegasaurus listing now reads NOW EXTINCT. Cash: ${values['cash']:,}.\n"
                        'Commands: go street, look, quit.')
            return (f"You are in DinoMart, among rows of dinosaur listings. Coelophysis costs $1,250; Vegasaurus costs $25,000. Cash: ${values['cash']:,}.\n"
                    'Commands: buy coelophysis, buy vegasaurus, read vegasaurus, go street, look, quit.')
        values = balances(self.debug)
        return (f"You are at the bank. Cash: ${values['cash']:,}. Loan: ${values['loan']:,}.\n"
                'Commands: borrow, repay, go office, look, quit.')

    def transact(self, command):
        if self.current != 'bank':
            return 'That action is not available in this scene.'
        self.debug.scene_assert(self.bank, object='bank.back')
        before = balances(self.debug)
        # The actual UI offers the full available quote. Only these two exact
        # states are qualified for this first slice, rather than extrapolating.
        cases = {'repay': ((5000, 5000), (0, 0), (5000, 5000), 'bank.payoff', 'paid_popup'),
                 'borrow': ((0, 0), (5000, 5000), (0, 5000), 'bank.borrow', 'borrow_popup')}
        expected_before, expected_after, expected_modal, obj, pattern = cases[command]
        if (before['cash'], before['loan']) != expected_before:
            reason = 'unqualified balances'
            message = 'That transaction is not qualified for the current balances; no input was sent.'
            if command == 'borrow' and before['loan'] == 5000:
                reason = 'credit ceiling'
                message = 'No additional credit is available at the $5,000 ceiling; no input was sent.'
            elif command == 'repay' and before['loan'] == 0:
                reason = 'no outstanding loan'
                message = 'There is no outstanding loan to repay; no input was sent.'
            self.event({'phase': 'refused', 'command': command, 'scene': 'bank', 'input': 'not_sent',
                        'reason': reason, 'before': before, 'persistence': 'unknown'})
            return message
        self.event({'phase': 'intent', 'command': command, 'scene': 'bank', 'input': 'not_yet_sent',
                    'before': before, 'persistence': 'unknown'})
        action = self.debug.scene_click(self.bank, obj)
        # An observed popup can precede its input loop. Give the guest a bounded
        # settling interval, then recheck the same modal and its staged values.
        # This is a tested timing qualification, not a general ready proof.
        run_guest(self.debug, 1200)
        self.transaction_count += 1
        frame, image = take_frame(self.project, self.debug, f'transaction-{self.transaction_count}-modal')
        if not matches(image, self.patterns[pattern]):
            raise RuntimeError('expected transaction confirmation not recognized; outcome unknown')
        modal = balances(self.debug)
        self.event({'phase': 'modal', 'command': command, 'scene': 'bank_confirmation',
                    'input': 'queued', 'before': before, 'observed': modal,
                    'frame': frame, 'scene_result': action, 'persistence': 'unknown'})
        if (modal['cash'], modal['loan']) != expected_modal or modal['working_cash'] != before['working_cash']:
            raise RuntimeError('unexpected intermediate balance; acknowledgment withheld')
        queued = self.debug.keyboard_press('enter')
        if queued.get('accepted') is not True or queued.get('delivery') != 'queued':
            raise RuntimeError('confirmation input not queued; outcome unknown')
        run_guest(self.debug, 1200)
        self.debug.scene_wait(self.bank, object='bank.back', guest_ms=6000, timeout_ms=10000)
        after = balances(self.debug)
        frame_after, image_after = take_frame(self.project, self.debug, f'transaction-{self.transaction_count}-after')
        if not matches(image_after, self.patterns['bank']):
            raise RuntimeError('bank display not recognized after acknowledgment')
        if (after['cash'], after['loan']) != expected_after or after['working_cash'] != before['working_cash']:
            self.event({'phase': 'indeterminate', 'command': command, 'scene': 'bank',
                        'observed': after, 'frame': frame_after, 'persistence': 'unknown',
                        'reason': 'unexpected final balance'})
            raise RuntimeError('unexpected final balance; no successful transaction claimed')
        self.last_action = {'before': before, 'modal': modal, 'after': after,
                            'modal_screenshot': frame, 'after_screenshot': frame_after,
                            'confirmation_input': queued, 'scene_result': action}
        self.event({'phase': 'result', 'command': command, 'scene': 'bank',
                    'result': self.last_action, 'persistence': 'unknown'})
        return (f"{'Repayment' if command == 'repay' else 'Borrowing'} completed. "
                f"Cash: ${after['cash']:,}. Loan: ${after['loan']:,}.")

    def shop_observe(self, view, expected, name, *, wait_slices=0, interrupts=()):
        for attempt in range(wait_slices + 1):
            frame, image = take_frame(self.project, self.debug, name)
            observed = balances(self.debug)
            matched = matches(image, self.patterns[view])
            notices = [n for n in interrupts if matches(image, self.patterns[n])]
            self.event({'phase': 'shop_observation', 'view': view, 'frame': frame,
                        'matched': matched, 'observed_balances': observed, 'persistence': 'unknown'})
            if any(observed[k] != v for k, v in expected.items()):
                raise RuntimeError('shop balances not qualified: ' + view + '; outcome unknown')
            if matched and not notices:
                return frame
            if (not matched and len(notices) == 1 and
                    (not matches(image, self.patterns['quarter_popup']) or notices == ['quarter_popup'])):
                raise KnownSceneNotice(notices[0], frame)
            if attempt < wait_slices:
                run_guest(self.debug, 500)
        raise RuntimeError('shop observation not qualified: ' + view + '; outcome unknown')

    def shop_click(self, point, ms, name, *, hold_ms=150):
        # Every input has a durable intent; an interrupted or failed action must
        # never be replayed automatically.
        self.event({'phase': 'shop_input_intent', 'action': name, 'point': point,
                    'input': 'not_yet_sent', 'persistence': 'unknown'})
        result = self.debug.click(*point, hold_ms=hold_ms)
        self.event({'phase': 'shop_input_sent', 'action': name, 'result': result,
                    'persistence': 'unknown'})
        if result.get('accepted') is not True or result.get('delivery') != 'queued':
            raise RuntimeError('shop input not queued; outcome unknown')
        return result if ms is None else run_guest(self.debug, ms)

    def observe_resources(self, expected, label):
        observed = park_resources(self.debug)
        self.event({'phase': 'resource_observation', 'view': label,
                    'resources': observed, 'persistence': 'unknown'})
        if any(observed[k] != value for k, value in expected.items()):
            raise RuntimeError('unexpected committed resources: ' + label + '; outcome unknown')
        return observed

    def observe_pending_guide(self, expected, label):
        observed = pending_guide(self.debug)
        self.event({'phase': 'pending_guide', 'view': label, 'count': observed, 'persistence': 'unknown'})
        if observed != expected:
            raise RuntimeError('unexpected pending guide count: ' + label + '; outcome unknown')

    def observe_park_status(self, label):
        if self.current not in ('office', 'street', 'park') or not self.park_opened:
            self.event({'phase': 'refused', 'command': label, 'input': 'not_sent',
                        'reason': 'qualified park session not active'})
            return None, 'Park status is available after the first park entry. No input was sent.'
        if self.notice_outcome_unknown:
            return None, 'The last notice acknowledgment has an unknown outcome; do not retry automatically.'
        frame, image = take_frame(self.project, self.debug, 'park-status')
        notices = [name for name in ('quarter_popup', 'parking_hint') if matches(image, self.patterns[name])]
        if notices:
            self.event({'phase': 'notice', 'command': label, 'notices': notices, 'frame': frame,
                        'persistence': 'unknown'})
            if notices == ['quarter_popup'] and self.current == 'park':
                return None, 'A recognized quarter notice is visible. Use acknowledge notice to continue.'
            return None, 'A game notice is visible; handling it in this scene is not qualified. No input was sent.'
        selected, obj = {'park': (self.park, 'park.back'), 'street': (self.street, 'street.office'),
                         'office': (self.office, 'office.bank')}[self.current]
        self.debug.scene_assert(selected, object=obj)
        snapshot = park_snapshot(self.debug)
        self.event({'phase': 'park_status', 'command': label, 'scene': self.current,
                    'snapshot': snapshot, 'frame': frame, 'persistence': 'unknown'})
        return snapshot, self.format_status(snapshot)

    @staticmethod
    def format_status(snapshot):
        money, bins = snapshot['balances'], snapshot['food_bins']
        pen_text = ', '.join(
            f"pen record {p['pen']}: {'Coelophysis' if p['species_id'] == 4 else 'species ID ' + str(p['species_id'])}, {p['count']}"
            for p in snapshot['pens']) or 'none'
        return (f"Year index {snapshot['year_index']}, month index {snapshot['month_index']}, "
                f"day counter {snapshot['day_of_month_counter']}; weekly counter {snapshot['weekly_counter']}.\n"
                f"Cash: ${money['cash']:,}. Loan: ${money['loan']:,}. Guides: {snapshot['guides']}.\n"
                f"Food units — small/medium/large feeders: {bins[0]}/{bins[1]}/{bins[2]}; "
                f"plant bins: {bins[3]}/{bins[4]}/{bins[5]}; seed bins: {bins[6]}/{bins[7]}/{bins[8]}.\n"
                f"Dinosaurs: {snapshot['dinosaurs']} ({pen_text}). Hunger counter: {snapshot['hunger_counter']}.")

    def advance_time(self):
        if self.current not in ('street', 'park'):
            return 'Go to the park or street before advancing time. No input was sent.'
        before, message = self.observe_park_status('advance time')
        if before is None:
            return message
        self.event({'phase': 'intent', 'command': 'advance time', 'input': 'not_yet_sent',
                    'requested_guest_ms': 1000, 'before': before, 'persistence': 'unknown'})
        result = run_guest(self.debug, 1000)
        frame, image = take_frame(self.project, self.debug, 'advance-after')
        notices = [name for name in ('quarter_popup', 'parking_hint') if matches(image, self.patterns[name])]
        if notices:
            self.event({'phase': 'interrupted', 'command': 'advance time', 'notices': notices,
                        'frame': frame, 'run': result, 'persistence': 'unknown'})
            if notices == ['quarter_popup'] and self.current == 'park':
                return 'A recognized quarter notice interrupted the advance. Use acknowledge notice to continue.'
            return 'A game notice interrupted the advance; handling it in this scene is not qualified.'
        selected, obj = (self.park, 'park.back') if self.current == 'park' else (self.street, 'street.office')
        self.debug.scene_assert(selected, object=obj)
        after = park_snapshot(self.debug)
        self.event({'phase': 'result', 'command': 'advance time', 'before': before, 'after': after,
                    'frame': frame, 'run': result, 'persistence': 'unknown'})
        changed = any(before[k] != after[k] for k in ('year_index', 'month_index', 'day_of_month_counter'))
        prefix = 'The calendar changed.' if changed else 'No calendar change was observed during this interval.'
        return prefix + '\n' + self.format_status(after)

    def acknowledge_notice(self):
        if getattr(self, 'pending_food_notice', False):
            return self.acknowledge_food_notice()
        if self.current not in ('street', 'park') or not self.park_opened or self.notice_outcome_unknown:
            return 'No notice acknowledgment is qualified in this state. No input was sent.'
        frame, image = take_frame(self.project, self.debug, 'notice-before')
        notices = [n for n in ('quarter_popup', 'parking_hint') if matches(image, self.patterns[n])]
        if len(notices) != 1:
            self.event({'phase': 'refused', 'command': 'acknowledge notice', 'input': 'not_sent',
                        'notices': notices, 'frame': frame})
            return 'No uniquely recognized notice is visible. No input was sent.'
        notice = notices[0]
        entering = self.pending_park_entry and self.current == 'street'
        food_return = getattr(self, 'pending_food_return', False) and self.current == 'street'
        if notice not in ('quarter_popup', 'parking_hint') or self.current != 'park' and not entering and not food_return:
            self.event({'phase': 'refused', 'command': 'acknowledge notice', 'input': 'not_sent',
                        'notice': notice, 'reason': 'notice and scene not qualified', 'frame': frame})
            return 'Acknowledging this notice in the current scene is not qualified. No input was sent.'
        self.event({'phase': 'intent', 'command': 'acknowledge notice', 'notice': notice,
                    'frame': frame, 'input': 'not_yet_sent', 'persistence': 'unknown'})
        run_guest(self.debug, 1200)
        frame, image = take_frame(self.project, self.debug, 'notice-settled')
        if not matches(image, self.patterns[notice]):
            self.event({'phase': 'indeterminate', 'command': 'acknowledge notice',
                        'reason': 'notice changed during settling', 'frame': frame, 'input': 'not_sent'})
            return 'The notice changed before acknowledgment. No input was sent; inspect the session.'
        self.notice_outcome_unknown = True
        continuation = ActionContinuation('acknowledge notice', event=self.event)
        result = continuation.send_once(lambda: parking_notice_input(self) if notice == 'parking_hint' else
                                         self.debug.keyboard_press('enter'))
        self.event({'phase': 'notice_input', 'command': 'acknowledge notice', 'result': result,
                    'notice': notice, 'persistence': 'unknown'})
        if result.get('accepted') is not True or result.get('delivery') != 'queued':
            return 'Notice input was not confirmed; the outcome is unknown. Do not retry automatically.'
        run_guest(self.debug, 1200)
        view = 'park_view' if self.current == 'park' or entering else 'street_view'
        views = (view, 'shop_street') if entering else (view,)
        frame, image = notice_return_frame(self, 'notice-after', views, continuation=continuation)
        if continuation.record['arrival'] != 'qualified':
            return 'The resulting view is not uniquely recognized; the outcome is unknown. Do not retry automatically.'
        remaining = [n for n in ('quarter_popup', 'parking_hint') if matches(image, self.patterns[n])]
        if remaining:
            self.event({'phase': 'indeterminate', 'command': 'acknowledge notice',
                        'remaining_notices': remaining, 'frame': frame, 'persistence': 'unknown'})
            return 'A notice remains after input; the outcome is unknown. Do not retry automatically.'
        returned_to_street = entering and matches(image, self.patterns['shop_street'])
        if not matches(image, self.patterns[view]) and not returned_to_street:
            self.event({'phase': 'indeterminate', 'command': 'acknowledge notice',
                        'reason': 'unexpected view', 'frame': frame, 'persistence': 'unknown'})
            return 'The resulting view is not recognized; the outcome is unknown. Do not retry automatically.'
        if returned_to_street:
            # A quarter can interrupt the original entry before travel occurs.
            # Its acknowledgment returns to the street; a new public intent
            # must request park entry rather than replaying the earlier click.
            self.pending_park_entry = False
        elif entering:
            selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                                   'hex': self.debug.memory('4020:3c5c', length=2)['hex']}}
            doc = definition(frame, 'park after acknowledged notice', pixel_predicate(self.patterns['park_view']),
                             selector, 'park.back', [173, 187], pixel_predicate(self.patterns['street_view']))
            self.park = self.project.debug_save_scene('park', doc, parent=self.park)['id']
            self.current, self.pending_park_entry = 'park', False
        selected, obj = (self.park, 'park.back') if self.current == 'park' else (self.street, 'street.office')
        self.debug.scene_assert(selected, object=obj)
        after = park_snapshot(self.debug)
        self.notice_outcome_unknown = False
        self.pending_food_return = False
        self.last_continuation = continuation.confirm_effect()
        self.event({'phase': 'result', 'command': 'acknowledge notice', 'notice': notice,
                    'after': after, 'frame': frame, 'persistence': 'unknown',
                    'park_entry_outcome': ('not_completed' if returned_to_street else
                                           'completed' if entering else 'not_applicable'),
                    'food_return_outcome': 'completed' if food_return else 'not_applicable'})
        continuation = (' You are on the street; park entry has not completed. Use go park to enter.'
                        if returned_to_street else '')
        if food_return:
            continuation += ' The food purchase was already confirmed; its return to the street is complete.'
        return 'Notice acknowledged.' + continuation + '\n' + self.format_status(after)

    def acknowledge_food_notice(self):
        if self.current != 'dino_diner' or self.notice_outcome_unknown:
            return 'This notice is not qualified for acknowledgment. No input was sent.'
        frame, image = take_frame(self.project, self.debug, 'food-notice-before')
        if (not matches(image, self.patterns['parking_hint']) or
                matches(image, self.patterns['quarter_popup'])):
            return 'No unique parking advice is visible. No input was sent.'
        self.event({'phase': 'intent', 'command': 'acknowledge notice',
                    'notice': 'parking_hint', 'frame': frame, 'purchase_input': 'not_sent'})
        run_guest(self.debug, 1200)
        frame, image = take_frame(self.project, self.debug, 'food-notice-settled')
        if (not matches(image, self.patterns['parking_hint']) or
                matches(image, self.patterns['quarter_popup'])):
            return 'The advice changed before acknowledgment. No input was sent; inspect the session.'
        self.notice_outcome_unknown = True
        continuation = ActionContinuation('acknowledge food notice', event=self.event)
        result = continuation.send_once(lambda: parking_notice_input(self))
        self.event({'phase': 'notice_input', 'command': 'acknowledge notice',
                    'notice': 'parking_hint', 'result': result, 'purchase_input': 'not_sent'})
        if result.get('accepted') is not True or result.get('delivery') != 'queued':
            return 'Notice input outcome unknown. Do not retry automatically.'
        run_guest(self.debug, 1200)
        frame, image = notice_return_frame(self, 'food-notice-after', ('dino_diner', 'food_menu', 'shop_street'),
                                          continuation=continuation)
        if continuation.record['arrival'] != 'qualified':
            return 'The resulting view is not uniquely recognized; outcome unknown. Do not retry automatically.'
        views = [n for n in ('dino_diner', 'food_menu', 'shop_street')
                 if matches(image, self.patterns[n])]
        if (len(views) != 1 or any(matches(image, self.patterns[n]) for n in
                ('parking_hint', 'quarter_popup', 'food_selected'))):
            self.event({'phase': 'indeterminate', 'command': 'acknowledge notice',
                        'frame': frame, 'views': views, 'purchase_input': 'not_sent'})
            return 'The resulting view is not recognized; outcome unknown. Do not retry automatically.'
        self.current = 'street' if views == ['shop_street'] else 'dino_diner'
        scene, obj = ((self.street, 'street.office') if self.current == 'street' else
                      (self.locations['dino_diner'], 'dino_diner.back'))
        self.debug.scene_assert(scene, object=obj)
        self.pending_food_notice = self.notice_outcome_unknown = False
        self.last_continuation = continuation.confirm_effect()
        self.event({'phase': 'result', 'command': 'acknowledge notice',
                    'notice': 'parking_hint', 'frame': frame, 'purchase_input': 'not_sent',
                    'food_order_submitted': False, 'scene': self.current})
        return ('Parking advice acknowledged. No food order was submitted. ' +
                ('Use go diner, then buy 20 small feeders.' if self.current == 'street' else
                 'Use buy 20 small feeders to submit a new order.'))

    def observe_one_of(self, views, expected, label, *, wait_slices=12):
        for attempt in range(wait_slices + 1):
            frame, image = take_frame(self.project, self.debug, label)
            observed = balances(self.debug)
            found = [view for view in views if matches(image, self.patterns[view])]
            self.event({'phase': 'shop_observation', 'view': label, 'frame': frame,
                        'matched_views': found, 'observed_balances': observed, 'persistence': 'unknown'})
            if observed != expected:
                raise RuntimeError('unexpected balances at ' + label + '; outcome unknown')
            if len(found) == 1:
                return found[0]
            if attempt < wait_slices:
                run_guest(self.debug, 500)
        raise RuntimeError('view not uniquely recognized: ' + label + '; outcome unknown')

    def buy_land(self):
        from .dinopark_land import buy
        return buy(self)

    def mart_observe(self, view, label, *, wait_slices=12):
        for attempt in range(wait_slices + 1):
            frame, image = take_frame(self.project, self.debug, label)
            matched = matches(image, MART_OBSERVATIONS[view])
            self.event({'phase': 'mart_observation', 'view': view, 'frame': frame,
                        'matched': matched, 'observed_balances': balances(self.debug)})
            if matched:
                return frame
            if attempt < wait_slices:
                run_guest(self.debug, 500)
        raise RuntimeError('DinoMart view not recognized: ' + view + '; further input withheld')

    def qualify_mart_last_page(self, frame):
        selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                               'hex': self.debug.memory('4020:3c5c', length=2)['hex']}}
        doc = definition(frame, 'DinoMart last catalogue page',
                         pixel_predicate(MART_OBSERVATIONS['last_page']), selector,
                         'mart.back', [216, 187], pixel_predicate(self.patterns['shop_street']))
        self.mart = self.project.debug_save_scene('dinomart', doc, parent=self.mart)['id']

    def mart_last_page(self):
        self.debug.scene_assert(self.mart, object='mart.back')
        park_catalogue_pointer(self)
        selector = self.debug.memory('4020:3c5c', length=2)['hex']
        # Pan the original wide catalogue with ordinary mouse movement. The
        # margin receives no clicks, and no camera or story memory is edited.
        for attempt in range(49):
            frame, image = take_frame(self.project, self.debug, 'mart-pan')
            if matches(image, MART_OBSERVATIONS['last_page']):
                self.vegasaurus_extinct = matches(image, MART_OBSERVATIONS['vegasaurus_extinct'])
                self.qualify_mart_last_page(frame)
                return
            if not catalogue_pan_valid(self, frame, image, selector):
                raise RuntimeError('Catalogue pan context changed; further input withheld')
            if attempt == 48:
                break
            moved = self.debug.call('input.mouse.move', {'x': 319, 'y': 50})
            self.event({'phase': 'mart_pan_input', 'result': moved, 'point': [319, 50]})
            if moved.get('accepted') is not True:
                raise RuntimeError('Catalogue movement outcome unknown; do not retry')
            run_guest(self.debug, 80)
            park_catalogue_pointer(self)
        raise RuntimeError('Last catalogue page not reached within the pan budget')

    def read_vegasaurus(self):
        if self.current != 'dinomart':
            return 'Read the dinosaur encyclopedia in DinoMart. No input was sent.'
        self.event({'phase': 'intent', 'command': 'read vegasaurus', 'input': 'not_yet_sent'})
        self.mart_last_page()
        if self.vegasaurus_extinct:
            self.event({'phase': 'refused', 'command': 'read vegasaurus', 'input': 'not_sent',
                        'reason': 'original listing marked NOW EXTINCT'})
            return 'The Vegasaurus listing is marked NOW EXTINCT and cannot be selected here. No input was sent.'
        self.shop_click((286, 136), 500, 'select Vegasaurus listing')
        self.mart_observe('vegasaurus_selected', 'vegasaurus-selected')
        self.shop_click((158, 187), 1500, 'read selected dinosaur information')
        frame = self.mart_observe('vegasaurus_entry', 'vegasaurus-encyclopedia')
        entry = ('Vegasaurus\nEra: Red Velvet\nDiet: Room Service\nLength: 5 ft. 6 in.\n'
                 'Weight: 165 lbs.\nClimate: Air-Conditioned\n'
                 'The illustration shows a green dinosaur in a purple suit beside a microphone.')
        self.event({'phase': 'encyclopedia_read', 'command': 'read vegasaurus',
                    'entry': entry, 'frame': frame, 'source': 'original printed encyclopedia page'})
        self.shop_click((173, 187), 1500, 'close encyclopedia')
        frame = self.mart_observe('last_page', 'encyclopedia-closed')
        self.qualify_mart_last_page(frame)
        self.event({'phase': 'result', 'command': 'read vegasaurus', 'scene': 'dinomart',
                    'observed_balances': balances(self.debug)})
        return entry + '\nYou close the encyclopedia and return to the catalogue.'

    def confirm_vegasaurus_order(self):
        # Both halves of each original 32-bit update have finished at the
        # post boundaries. A partial watchpoint value is not a commit proof.
        boundaries = ('334b:205e', '334b:208b', '334b:18b6', '334b:18be')
        armed = []
        states = []
        try:
            for address in boundaries:
                analysis = self.project.analyze(start=address, max_instructions=64)
                bp = self.debug.breakpoint(address)
                armed.append(bp['breakpoint_id'])
                self.event({'phase': 'vegasaurus_boundary', 'address': address,
                            'analysis': analysis, 'breakpoint': bp})
                if bp.get('bytes_verified') is not True:
                    raise RuntimeError('Dinosaur instruction identity unverified; no BUY sent')
            self.vegasaurus_attempted = True
            queued = self.debug.click(187, 187, hold_ms=80)
            self.event({'phase': 'shop_input_sent', 'action': 'order Vegasaurus', 'result': queued})
            if queued.get('accepted') is not True or queued.get('delivery') != 'queued':
                raise RuntimeError('Dinosaur order input outcome unknown; do not retry')
            for index, address in enumerate(boundaries):
                for attempt in range(25):
                    stop = self.debug.run(guest_ms=1000, timeout_ms=15000, fast_forward=True)
                    self.event({'phase': 'vegasaurus_stop', 'address': address, 'stop': stop})
                    if stop.get('outcome') == 'breakpoint':
                        if stop.get('session', {}).get('stop_reason', {}).get('breakpoint_id') != armed[0]:
                            raise RuntimeError('Unexpected dinosaur stop; outcome unknown')
                        state = vegasaurus_order_state(self.debug)
                        self.event({'phase': 'vegasaurus_native_state', 'address': address, 'state': state})
                        states.append(state)
                        self.debug.delete_breakpoint(armed.pop(0))
                        break
                    if stop.get('outcome') != 'guest_time':
                        raise RuntimeError('Dinosaur order interrupted; outcome unknown')
                    frame, _ = take_frame(self.project, self.debug, 'vegasaurus-animation')
                    self.event({'phase': 'vegasaurus_animation', 'frame': frame, 'boundary_index': index})
                else:
                    raise RuntimeError('Dinosaur order did not reach its next boundary; outcome unknown')
            proof = verify_vegasaurus_order(states)
            self.vegasaurus_proof = proof
            self.event({'phase': 'vegasaurus_purchase_confirmed', 'command': 'buy vegasaurus',
                        'proof': proof, 'persistence': 'live game; disk save separate'})
            return proof
        finally:
            for identifier in armed:
                self.debug.delete_breakpoint(identifier)

    def buy_vegasaurus(self):
        if self.current != 'dinomart':
            return 'Buy dinosaurs in DinoMart. No input was sent.'
        before = balances(self.debug)
        if self.vegasaurus_attempted or before['cash'] < 25000 or before['cash'] != before['working_cash']:
            reason = ('order already confirmed' if self.vegasaurus_proof else
                      'earlier order outcome unknown') if self.vegasaurus_attempted else 'insufficient cash or unresolved reservation'
            self.event({'phase': 'refused', 'command': 'buy vegasaurus', 'reason': reason,
                        'before': before, 'input': 'not_sent'})
            return 'Vegasaurus costs $25,000. Cannot order: ' + reason + '. No input was sent.'
        self.event({'phase': 'intent', 'command': 'buy vegasaurus', 'before': before, 'input': 'not_yet_sent'})
        self.mart_last_page()
        if self.vegasaurus_extinct:
            return 'The Vegasaurus listing is marked NOW EXTINCT. No purchase input was sent.'
        self.shop_click((286, 136), 500, 'select Vegasaurus listing')
        self.mart_observe('vegasaurus_selected', 'vegasaurus-selected')
        self.shop_click((286, 157), 500, 'select Vegasaurus price')
        self.mart_observe('vegasaurus_selected', 'vegasaurus-price')
        now = balances(self.debug)
        if now['cash'] < 25000 or now['cash'] != now['working_cash']:
            self.event({'phase': 'refused', 'command': 'buy vegasaurus', 'before': now,
                        'reason': 'financial state changed during selection', 'input': 'no BUY sent'})
            return 'The order cannot be funded after selecting its price. No purchase input was sent.'
        proof = self.confirm_vegasaurus_order()
        try:
            run_guest(self.debug, 500)
            frame = self.mart_observe('vegasaurus_extinct', 'vegasaurus-completed')
            self.qualify_mart_last_page(frame)
            self.vegasaurus_extinct = True
        except Exception as exc:
            self.event({'phase': 'vegasaurus_followup_failed', 'purchase_outcome': 'confirmed',
                        'proof': proof, 'following_input': 'not_sent', 'error': str(exc)})
            raise RuntimeError('Vegasaurus order confirmed: $25,000 reservation released; no dinosaur added. '
                               'The later view is unknown; do not repeat the order.') from exc
        after = balances(self.debug)
        self.event({'phase': 'result', 'command': 'buy vegasaurus', 'purchase_outcome': 'confirmed',
                    'proof': proof, 'after': after, 'frame': frame})
        return (f"Vegasaurus is now marked NOW EXTINCT. The $25,000 reservation was released. "
                f"Cash at order: ${proof['committed_cash_before']:,}; at release: ${proof['committed_cash_after']:,}; "
                f"now: ${after['cash']:,}. Loan: ${proof['loan_before']:,} at order, ${after['loan']:,} now. "
                f"No dinosaur was added; your herd still contains {proof['dinosaurs_after']}. "
                'The finances retain a $25,000 dinosaur-purchase expense. You are in DinoMart.')

    def buy_dinosaur(self):
        if self.bounded_purchases:
            from .dinopark_purchase import buy
            return buy(self)
        if self.current != 'dinomart':
            return 'That action is not available in this scene.'
        before = balances(self.debug)
        if not self.land_bought or self.dinosaur_bought or (before['cash'], before['loan'], before['working_cash']) != (4500, 5000, 4500):
            self.event({'phase': 'refused', 'command': 'buy coelophysis', 'input': 'not_sent',
                        'reason': 'unqualified land, purchase history or balances', 'before': before})
            if self.dinosaur_bought:
                return 'This dinosaur purchase was already completed. No input was sent.'
            if not self.land_bought:
                return 'Buy the $500 desert plot first. No input was sent.'
            return 'This purchase is not qualified for the current balances. No input was sent.'
        prepare_mart_first_page(self)
        self.debug.scene_assert(self.mart, object='mart.back')
        self.event({'phase': 'intent', 'command': 'buy coelophysis', 'before': before, 'input': 'not_yet_sent'})
        unchanged = {'cash': 4500, 'loan': 5000, 'working_cash': 4500}
        self.shop_click((160, 87), 5000, 'select dinosaur')
        self.shop_observe('coel_picked', unchanged, 'dinosaur-picked')
        self.shop_click((160, 103), 6000, 'select price')
        self.shop_observe('coel_selected', unchanged, 'dinosaur-selected')
        # The original purchase code indexes 26-byte species records from
        # DS:4550 using DS:68a5, then posts that price at 334b:205e..2087.
        selected = int.from_bytes(bytes.fromhex(self.debug.memory('4020:68a5', length=2)['hex']), 'little')
        price = int.from_bytes(bytes.fromhex(self.debug.memory('4020:45b8', length=4)['hex']), 'little')
        self.event({'phase': 'dinosaur_selection', 'species': selected, 'price': price,
                    'purchase_input': 'not_sent'})
        if selected != 4 or price != 1250:
            raise RuntimeError('Original species or price is not the qualified Coelophysis order; BUY withheld')
        self.shop_click((187, 187), 6000, 'order dinosaur')
        staged = {'cash': 4500, 'loan': 5000, 'working_cash': 3250}
        observed = balances(self.debug)
        frame, _ = take_frame(self.project, self.debug, 'dinosaur-arrival')
        self.event({'phase': 'shop_observation', 'view': 'arrival', 'frame': frame,
                    'observed_balances': observed, 'persistence': 'unknown'})
        if any(observed[k] != v for k, v in staged.items()):
            raise RuntimeError('unexpected dinosaur reservation; outcome unknown')
        run_guest(self.debug, 8000)
        self.shop_observe('placement', staged, 'dinosaur-placement', wait_slices=24)
        self.shop_click((42, 50), 2000, 'place dinosaur')
        self.shop_observe('placed', staged, 'dinosaur-placed')
        self.shop_click((188, 187), 10000, 'confirm dinosaur placement')
        committed = {'cash': 3250, 'loan': 5000, 'working_cash': 3250}
        frame = self.shop_observe('after', committed, 'dinosaur-committed')
        # After a purchase the catalogue has scrolled. Give its new view its
        # own scene revision instead of reusing the initial catalogue guard.
        pred = pixel_predicate(self.patterns['after'])
        selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                               'hex': self.debug.memory('4020:3c5c', length=2)['hex']}}
        doc = definition(frame, 'dinomart after purchase', pred, selector,
                         'mart.back', [216, 187], pixel_predicate(self.patterns['street_view']))
        self.mart = self.project.debug_save_scene('dinomart', doc, parent=self.mart)['id']
        self.dinosaur_bought = True
        self.event({'phase': 'result', 'command': 'buy coelophysis', 'before': before,
                    'after': committed, 'persistence': 'unknown'})
        return 'Coelophysis placed in the desert plot for $1,250. Cash: $3,250.'

    def check_inventory(self):
        if self.current != 'street':
            return 'That action is not available in this scene.'
        before = balances(self.debug)
        qualified_cash = 1750 if self.food_bought else (2250 if self.fence_bought else 3250)
        if not self.dinosaur_bought or (before['cash'], before['loan'], before['working_cash']) != (qualified_cash, 5000, qualified_cash):
            self.event({'phase': 'refused', 'command': 'check inventory', 'input': 'not_sent',
                        'reason': 'inventory view not qualified for current state'})
            if not self.dinosaur_bought:
                return 'Inventory checking is qualified after the first dinosaur purchase; no input was sent.'
            return 'The inventory screen is not qualified at the current balances. Use status after entering the park. No input was sent.'
        self.debug.scene_assert(self.street, object='street.office')
        self.event({'phase': 'intent', 'command': 'check inventory', 'input': 'not_yet_sent'})
        self.shop_click((145, 187), 2500, 'open inventory after purchase')
        self.shop_observe('inventory', before, 'inventory-after-purchase')
        frame, image = take_frame(self.project, self.debug, 'inventory-counts')
        if not matches(image, self.patterns['inventory']):
            raise RuntimeError('inventory count frame not recognized; outcome unknown')
        # Each displayed digit is sampled separately; the shared catalogue
        # fingerprint alone cannot establish the inventory values.
        for y in (123, 133, 143):
            if any(image.getpixel((x, y)) != rgb for x, rgb in
                   ((309, (239, 207, 0)), (310, (44, 44, 44)),
                    (311, (44, 44, 44)), (312, (239, 207, 0)))):
                raise RuntimeError('inventory counts not recognized; outcome unknown')
        self.event({'phase': 'inventory_counts', 'dinosaurs': 1, 'pens': 1, 'pens_in_use': 1,
                    'frame': frame, 'persistence': 'unknown'})
        self.shop_click((172, 187), 5000, 'close inventory after purchase')
        self.debug.scene_assert(self.street, object='street.office')
        self.event({'phase': 'result', 'command': 'check inventory', 'persistence': 'unknown'})
        return 'Inventory: 1 dinosaur, 1 pen, 1 pen in use. You are on the street.'

    def store_fences_tab(self, expected):
        self.debug.scene_assert(self.locations['general_store'], object='general_store.catalogue')
        frame, image = take_frame(self.project, self.debug, 'store-current')
        self.event({'phase': 'shop_observation', 'view': 'store-current', 'frame': frame,
                    'observed_balances': balances(self.debug), 'persistence': 'unknown'})
        if matches(image, self.patterns['fence_tab']) or matches(image, self.patterns['fence_selected']):
            return
        if not matches(image, self.patterns['general_store']):
            raise RuntimeError('store catalogue view not recognized; no input sent')
        self.shop_click((205, 105), 5000, 'open store catalogue')
        self.shop_observe('general_store', expected, 'store-catalogue-cover', wait_slices=12)
        self.shop_click((263, 165), 5000, 'turn catalogue cover')
        self.shop_observe('general_store', expected, 'store-catalogue-open', wait_slices=12)
        self.shop_click((160, 54), 5000, 'open fences tab')
        self.shop_observe('fence_tab', expected, 'store-fences-tab', wait_slices=12)

    def leave_store(self):
        before = balances(self.debug)
        if before['cash'] != before['working_cash']:
            self.event({'phase': 'refused', 'command': 'go street', 'scene': 'general_store',
                        'input': 'not_sent', 'reason': 'unresolved store reservation', 'before': before})
            return 'The store has an unresolved reservation. No input was sent; inspect it before leaving.'
        self.event({'phase': 'intent', 'command': 'go street', 'scene': 'general_store',
                    'input': 'not_yet_sent', 'before': before, 'action_scope': 'navigation only'})
        # The park may earn income, pay staff or settle a loan during these
        # original page transitions. Purchase paths still pass exact expected
        # balances; navigation verifies views without freezing the finances.
        self.store_fences_tab({})
        self.shop_click((188, 187), 8000, 'leave store catalogue')
        self.shop_observe('shop_street', {}, 'store-exit', wait_slices=12)
        self.debug.scene_assert(self.street, object='street.office')
        after = balances(self.debug)
        self.current = 'street'
        self.event({'phase': 'result', 'command': 'go street', 'scene': 'street',
                    'before': before, 'after': after, 'action_scope': 'navigation only', 'persistence': 'unknown'})
        return self.describe()

    def leave_mart(self):
        before = balances(self.debug)
        if before['cash'] != before['working_cash']:
            self.event({'phase': 'refused', 'command': 'go street', 'scene': 'dinomart',
                        'input': 'not_sent', 'reason': 'unresolved dinosaur reservation'})
            return 'The catalogue has an unresolved reservation. No input was sent.'
        self.event({'phase': 'intent', 'command': 'go street', 'scene': 'dinomart',
                    'before': before, 'input': 'not_yet_sent'})
        point = prepare_scene_pointer(self.debug, self.mart, self.event, object_name='mart.back')
        # The original catalogue completes this input during one continuous
        # guest interval. Verify its destination after that interval rather
        # than relying on the generic 100 ms scene-polling path.
        self.shop_click(point, 2000, 'leave DinoMart catalogue', hold_ms=80)
        self.shop_observe('shop_street', {}, 'mart-exit', wait_slices=12)
        self.debug.scene_assert(self.street, object='street.office')
        self.current = 'street'
        self.event({'phase': 'result', 'command': 'go street', 'scene': 'street',
                    'before': before, 'after': balances(self.debug), 'persistence': 'unknown'})
        return self.describe()

    def leave_park(self):
        from .dinopark_purchase import PurchaseBudget
        with PurchaseBudget(label='Park exit').bind(self.debug):
            self.event({'phase': 'intent', 'command': 'go street', 'scene': 'park',
                        'input': 'not_yet_sent'})
            self.last_action = click_business(self, 'go street', self.park, 'park.back')
            qualified = qualify_street(self)
            self.event({'phase': 'result', 'command': 'go street', 'scene': 'street',
                        'result': self.last_action, 'frame': qualified['frame'],
                        'persistence': 'live original destination; disk save separate'})
            return self.describe()

    def buy_fence(self):
        from .dinopark_fence import buy
        return buy(self)

    @bounded_preparation
    def hire_guide(self):
        if self.current != 'employment':
            return 'That action is not available in this scene.'
        before = balances(self.debug)
        if not self.fence_bought or self.guide_hired or before != {'cash': 2250, 'loan': 5000, 'working_cash': 2250}:
            self.event({'phase': 'refused', 'command': 'hire tour guide', 'input': 'not_sent',
                        'reason': 'unqualified park, staffing history or balances', 'before': before})
            return 'This hire requires the qualified fenced-pen setup and is available once. No input was sent.'
        self.debug.scene_assert(self.locations['employment'], object='employment.back')
        self.observe_resources({'guides': 0, 'small_feeders': 0}, 'before hire')
        self.observe_pending_guide(0, 'before hire')
        self.event({'phase': 'intent', 'command': 'hire tour guide', 'input': 'not_yet_sent', 'before': before})
        self.shop_click((55, 140), 250, 'select tour guide poster')
        view = self.observe_one_of(['guide_posters', 'guide_detail'], before, 'guide-poster')
        if view == 'guide_posters':
            self.shop_click((55, 160), 250, 'open tour guide details', hold_ms=200)
            self.shop_observe('guide_detail', before, 'guide-detail', wait_slices=12)
        self.observe_pending_guide(0, 'guide detail')
        self.shop_click((226, 148), 250, 'stage tour guide hire')
        self.shop_observe('guide_staged', before, 'guide-staged', wait_slices=12)
        self.observe_resources({'guides': 0, 'small_feeders': 0}, 'guide staged')
        self.observe_pending_guide(1, 'guide staged')
        self.shop_click((201, 187), 250, 'accept guide detail')
        self.shop_observe('employment', before, 'guide-detail-accepted', wait_slices=12)
        self.observe_resources({'guides': 0, 'small_feeders': 0}, 'guide detail accepted')
        self.observe_pending_guide(1, 'guide detail accepted')
        queued = self.shop_click((201, 187), None, 'commit employment roster')
        run_guest(self.debug, 250)
        # Native roster commitment precedes the first presentation read. A
        # missing frame must not erase a completed original hire.
        for attempt in range(13):
            committed = self.observe_resources({'small_feeders':0}, 'guide commit candidate')
            if balances(self.debug) != before:
                raise RuntimeError('Guide commit balances remain unqualified')
            if committed['guides'] == 1:
                self.event({'phase':'guide_hire_confirmed','command':'hire tour guide',
                            'before':before,'guides_before':0,'guides_after':1,
                            'input':queued,'presentation':'not_yet_qualified'})
                break
            if committed['guides'] != 0:
                raise RuntimeError('unexpected committed resources: guide roster; outcome unknown')
            if attempt < 12:run_guest(self.debug, 500)
        else:
            raise RuntimeError('Guide roster commit remains unqualified')
        self.shop_observe('shop_street', before, 'guide-committed', wait_slices=12)
        self.observe_resources({'guides': 1, 'small_feeders': 0}, 'guide committed')
        self.debug.scene_assert(self.street, object='street.office')
        self.current, self.guide_hired = 'street', True
        self.event({'phase': 'result', 'command': 'hire tour guide', 'after': before,
                    'guides': 1, 'persistence': 'unknown'})
        return 'One tour guide hired at $900 per month. Cash: $2,250. You are on the street.'

    def confirm_food_order(self):
        """Observe native stock/accounting completion before later simulation.

        The original 2d0a:2810 copies all nine pending bins, then posts the
        expense and commits cash before 2d0a:283d requests the street. These
        exact execution boundaries avoid treating a partial REP write as a
        completed transaction. No guest state is edited.
        """
        armed = []
        try:
            analysis = self.project.analyze(max_instructions=64)
            self.event({'phase': 'food_commit_analysis', 'analysis': analysis})
            for address in ('2d0a:2810', '2d0a:283d'):
                analysis = self.project.analyze(start=address, max_instructions=64)
                breakpoint = self.debug.breakpoint(address)
                armed.append(breakpoint['breakpoint_id'])
                self.event({'phase': 'food_commit_boundary', 'address': address,
                            'analysis': analysis, 'breakpoint': breakpoint})
                if breakpoint.get('bytes_verified') is not True:
                    raise RuntimeError('Food commit instruction identity was not verified; no confirmation sent')
            self.event({'phase': 'shop_input_intent', 'action': 'commit food order',
                        'point': [201, 187], 'input': 'not_yet_sent'})
            queued = self.debug.click(201, 187, hold_ms=80)
            self.event({'phase': 'shop_input_sent', 'action': 'commit food order', 'result': queued})
            if queued.get('accepted') is not True or queued.get('delivery') != 'queued':
                raise RuntimeError('Food commit input outcome unknown; do not retry')
            states = []
            for index in range(2):
                stop = self.debug.run(guest_ms=6000, timeout_ms=15000, fast_forward=True)
                expected = armed[0]
                self.event({'phase': 'food_commit_stop', 'index': index, 'stop': stop})
                if (stop.get('outcome') != 'breakpoint' or
                        stop.get('session', {}).get('stop_reason', {}).get('breakpoint_id') != expected):
                    raise RuntimeError('Food commit boundary not reached; outcome unknown; do not retry')
                state = food_order_state(self.debug)
                states.append(state)
                self.event({'phase': 'food_commit_before' if index == 0 else 'food_commit_after', 'state': state})
                if index == 0:
                    differences = [a - b for a, b in zip(state['pending_food'], state['live_food'])]
                    if (differences != [20] + [0] * 8 or min(state['pending_food'] + state['live_food']) < 0 or
                            state['balances']['cash'] - state['balances']['working_cash'] != 500):
                        raise RuntimeError('Food commit reservation is not the qualified 20-unit order; outcome unknown')
                self.debug.delete_breakpoint(expected)
                armed.pop(0)
            before, after = states
            if (after['calendar'] != before['calendar'] or after['live_food'] != before['pending_food'] or
                    after['pending_food'] != before['pending_food'] or
                    after['balances'] != {'cash': before['balances']['working_cash'],
                                          'working_cash': before['balances']['working_cash'],
                                          'loan': before['balances']['loan']} or
                    (after['expenses'] - before['expenses']) % (1 << 32) != 500):
                raise RuntimeError('Food commit delivery or accounting mismatch; outcome unknown; do not retry')
            result = {'quantity': 20, 'price': 500, 'stock_at_commit': after['live_food'][0],
                      'before': before, 'after': after, 'confirmation_input_count': 1}
            self.food_bought = True
            self.event({'phase': 'food_purchase_committed', 'result': result,
                        'outcome': 'confirmed', 'persistence': 'live game commit; disk save separate'})
            return result
        finally:
            # Release only this action's breakpoints, preserving another owner's
            # controls. Cleanup never dispatches a second guest input.
            for identifier in armed:
                self.debug.delete_breakpoint(identifier)

    def food_order_view(self, label):
        """Dismiss one known advisory, then verify the order view and counters."""
        try:
            self.shop_observe('food_selected', {}, label, wait_slices=6, interrupts=('parking_hint',))
            return False
        except KnownSceneNotice as notice:
            self.event({'phase': 'food_advice', 'frame': notice.frame,
                        'order_committed': False, 'stage': label, 'acknowledgment_input': 'not_sent'})
            result = parking_notice_input(self)
            self.event({'phase': 'notice_input', 'command': 'buy 20 small feeders',
                        'notice': 'parking_hint', 'result': result, 'order_committed': False})
            if result.get('accepted') is not True or result.get('delivery') != 'queued':
                raise RuntimeError('Food advisory acknowledgment outcome unknown; do not retry')
            run_guest(self.debug, 1200)
            frame, image = take_frame(self.project, self.debug, label + '-resumed')
            if (label == 'food-selected' and matches(image, self.patterns['food_menu']) and
                    not matches(image, self.patterns['food_selected'])):
                self.event({'phase': 'food_selection_not_applied', 'frame': frame,
                            'selection_input': 'not_yet_sent', 'order_committed': False})
                self.shop_click((44, 101), 600, 'select feeders after verified unselected menu', hold_ms=80)
            self.shop_observe('food_selected', {}, label + '-after-advice', wait_slices=6)
            self.food_advice_count += 1
            return True

    @bounded_preparation
    def buy_food(self):
        if self.current != 'dino_diner':
            return 'That action is not available in this scene.'
        before = balances(self.debug)
        resources = park_resources(self.debug)
        initial = not self.food_bought and before == {'cash': 2250, 'loan': 5000, 'working_cash': 2250} and resources['small_feeders'] == 0
        replenishment = (self.food_bought and self.park_opened and before['cash'] >= 500 and
                         before['cash'] == before['working_cash'] and resources['small_feeders'] <= 32747)
        if not self.guide_hired or resources['guides'] != 1 or not (initial or replenishment):
            self.event({'phase': 'refused', 'command': 'buy 20 small feeders', 'input': 'not_sent',
                        'reason': 'unqualified staffing, order history or balances', 'before': before,
                        'resources': resources})
            return 'This order is not qualified for the current staffing, stock or balances. No input was sent.'
        self.debug.scene_assert(self.locations['dino_diner'], object='dino_diner.back')
        start_food = resources['small_feeders']
        frame, image = take_frame(self.project, self.debug, 'food-order-before')
        self.event({'phase': 'shop_observation', 'view': 'food-order-before', 'frame': frame,
                    'observed_balances': before, 'resources': resources, 'persistence': 'unknown'})
        if matches(image, self.patterns['dino_diner']):
            menu_open = False
        elif matches(image, self.patterns['food_menu']) and not matches(image, self.patterns['food_selected']):
            menu_open = True
        else:
            self.event({'phase': 'refused', 'command': 'buy 20 small feeders', 'input': 'not_sent',
                        'reason': 'unqualified food menu selection'})
            return 'The current food menu is not qualified for a new order. No input was sent.'
        self.food_advice_count = 0
        self.event({'phase': 'intent', 'command': 'buy 20 small feeders', 'input': 'not_yet_sent', 'before': before})
        if not menu_open:
            opened = self.shop_click((133, 54), 250, 'open meat menu')
            try:
                self.shop_observe('food_menu', {}, 'food-menu',
                                  wait_slices=12, interrupts=('parking_hint',))
            except KnownSceneNotice as notice:
                self.pending_food_notice = True
                self.event({'phase': 'interrupted', 'command': 'buy 20 small feeders',
                            'notices': [notice.notice], 'frame': notice.frame, 'run': opened,
                            'purchase_input': 'not_sent', 'food_order_submitted': False})
                return ('Parking advice interrupted the food menu before an order was submitted. '
                        'Use acknowledge notice, then inspect the available actions.')
        self.shop_click((44, 101), 250, 'select small feeders', hold_ms=80)
        self.food_order_view('food-selected')
        selected_balances = balances(self.debug)
        if selected_balances['cash'] != selected_balances['working_cash']:
            raise RuntimeError('unexpected pending balance before food order; outcome unknown')
        selected_resources = self.observe_resources({'guides': 1}, 'food selection')
        if pending_small_feeders(self.debug) != selected_resources['small_feeders']:
            raise RuntimeError('food draft not synchronized before order; outcome unknown')
        for quantity in range(1, 21):
            self.shop_click((133, 108), 220, f'add small feeder {quantity}', hold_ms=80)
            advised = self.food_order_view(f'food-staged-{quantity:02d}')
            if advised:
                actual, draft = food_draft_state(self.debug)
                self.event({'phase': 'food_draft_reconciled', 'requested_quantity': quantity,
                            'actual_quantity': actual, 'draft': draft, 'order_committed': False})
                if actual == quantity - 1:
                    # The known draft proves this increment was not applied.
                    # Send one newly qualified increment; never repeat an unknown one.
                    self.shop_click((133, 108), 220, f'complete verified small feeder {quantity}', hold_ms=80)
                    self.food_order_view(f'food-reconciled-{quantity:02d}')
                elif actual != quantity:
                    raise RuntimeError('Unexpected food draft after advice; outcome unknown')
            staged = balances(self.debug)
            self.event({'phase': 'food_reservation', 'quantity': quantity, 'balances': staged,
                        'persistence': 'unknown'})
            if staged['cash'] - staged['working_cash'] != 25 * quantity:
                raise RuntimeError('unexpected food reservation; outcome unknown')
            staged_resources = self.observe_resources({'guides': 1}, f'food staged {quantity}')
            pending_food = pending_small_feeders(self.debug)
            self.event({'phase': 'food_stock_reservation', 'quantity': quantity,
                        'live': staged_resources['small_feeders'], 'pending': pending_food,
                        'persistence': 'unknown'})
            if pending_food - staged_resources['small_feeders'] != quantity:
                raise RuntimeError('unexpected food stock reservation; outcome unknown')
        proof = self.confirm_food_order()
        return self.finish_food_return(proof, before, start_food)

    def finish_food_return(self, proof, before, start_food):
        """Keep a proven purchase separate from its modal-obscured destination."""
        try:
            run_guest(self.debug, 250)
            self.shop_observe('shop_street', {}, 'food-committed', wait_slices=12,
                              interrupts=('quarter_popup', 'parking_hint'))
            committed = balances(self.debug)
            final_resources = self.observe_resources({}, 'food committed')
            self.debug.scene_assert(self.street, object='street.office')
        except KnownSceneNotice as notice:
            # The original commit is already proven. A known modal can obscure
            # its street destination; expose a continuation, never another BUY.
            self.current, self.pending_food_return = 'street', True
            self.event({'phase':'food_return_interrupted', 'command':'buy 20 small feeders',
                        'notices':[notice.notice], 'frame':notice.frame, 'commit':proof,
                        'purchase_outcome':'confirmed', 'purchase_input':'already_sent',
                        'following_input':'not_sent'})
            return ('The 20-feeder purchase is confirmed for $500. A recognized notice interrupted '
                    'the return to the street. Acknowledge the notice to finish; do not repeat the purchase.')
        except Exception as exc:
            self.event({'phase': 'food_followup_failed', 'purchase_outcome': 'confirmed',
                        'commit': proof, 'error': str(exc), 'do_not_repeat_purchase': True})
            raise RuntimeError('Food purchase confirmed: 20 small feeders for $500. '
                               'The later view or status is unknown; do not repeat the purchase.') from exc
        self.current = 'street'
        change = final_resources['small_feeders'] - proof['stock_at_commit']
        self.event({'phase': 'result', 'command': 'buy 20 small feeders', 'before': before,
                    'after': committed, 'small_feeders_before': start_food,
                    'small_feeders': final_resources['small_feeders'], 'commit': proof,
                    'stock_change_after_commit': change, 'purchase_outcome': 'confirmed',
                    'guides_now': final_resources['guides'], 'persistence': 'live game commit; disk save separate'})
        advice = ('The adviser suggested another parking lot; its message was acknowledged during preparation. '
                  if self.food_advice_count else '')
        return (advice + f"Bought 20 small feeders for $500. Stock at confirmation: {proof['stock_at_commit']}. "
                f"Stock now: {final_resources['small_feeders']} (change while returning: {change:+d}). "
                f"Cash: ${committed['cash']:,}. Guides: {final_resources['guides']}. You are on the street.")

    @bounded_preparation
    def open_park(self):
        if self.current != 'street':
            return 'That action is not available in this scene.'
        before = balances(self.debug)
        if not self.food_bought or self.park_opened or before != {'cash': 1750, 'loan': 5000, 'working_cash': 1750}:
            self.event({'phase': 'refused', 'command': 'open park', 'input': 'not_sent',
                        'reason': 'unqualified preparation, prior entry or balances', 'before': before})
            return 'Park entry is qualified once after the guide and food order. No input was sent.'
        self.debug.scene_assert(self.street, object='street.office')
        self.observe_resources({'guides': 1, 'small_feeders': 20}, 'before park entry')
        day_before = int.from_bytes(bytes.fromhex(self.debug.memory('4020:6fcb', length=2)['hex']), 'little')
        self.event({'phase': 'intent', 'command': 'open park', 'input': 'not_yet_sent',
                    'before': before, 'day_before': day_before})
        self.shop_click((201, 187), 250, 'enter park view', hold_ms=80)
        for attempt in range(13):
            frame, image = take_frame(self.project, self.debug, 'park-running')
            day = int.from_bytes(bytes.fromhex(self.debug.memory('4020:6fcb', length=2)['hex']), 'little')
            observed = balances(self.debug)
            resources = park_resources(self.debug)
            self.event({'phase': 'park_observation', 'frame': frame, 'day': day,
                        'balances': observed, 'resources': resources,
                        'open_closed_status': 'unknown', 'persistence': 'unknown'})
            if matches(image, self.patterns['park_view']) and day > day_before:
                break
            if attempt < 12:
                run_guest(self.debug, 500)
        else:
            raise RuntimeError('park view or advancing day not observed; outcome unknown')
        selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                               'hex': self.debug.memory('4020:3c5c', length=2)['hex']}}
        doc = definition(frame, 'park', pixel_predicate(self.patterns['park_view']), selector,
                         'park.back', [173, 187], pixel_predicate(self.patterns['street_view']))
        self.park = self.project.debug_save_scene('park', doc)['id']
        self.current, self.park_opened = 'park', True
        self.event({'phase': 'result', 'command': 'open park', 'day_before': day_before,
                    'day_after': day, 'balances': observed, 'resources': resources,
                    'open_closed_status': 'unknown', 'persistence': 'unknown'})
        return self.describe()

    @bounded_preparation
    def revisit_park(self):
        if self.current != 'street':
            return 'That action is not available in this scene.'
        if not self.park_opened:
            self.event({'phase': 'refused', 'command': 'go park', 'input': 'not_sent',
                        'reason': 'park entry not yet qualified'})
            return 'Use open park after completing the opening setup. No input was sent.'
        before, message = self.observe_park_status('go park')
        if before is None:
            return message
        self.event({'phase': 'intent', 'command': 'go park', 'input': 'not_yet_sent',
                    'before': before, 'persistence': 'unknown'})
        source = self.street
        observed = self.debug.scene_assert(source, object='street.office')
        receipt = {'complete': False, 'status': 'observation-failed',
                   'run': self.debug.run_id, 'scene_revision': source, 'action_name': 'street.park',
                   'before_observation': observed['observation']}
        try:
            # Preserve the original press and continuous guest interval. Capture
            # its actual ticket before a wait/readback can raise.
            receipt['input'] = self.shop_click((201, 187), None, 'return to park view', hold_ms=80)
            entry_run = self.debug.run(guest_ms=8000, timeout_ms=40000, fast_forward=True)
            if entry_run.get('outcome') != 'guest_time':
                raise RuntimeError('park entry stopped unexpectedly; outcome unknown')
            frame, image = take_frame(self.project, self.debug, 'park-entry-notices')
            notices = [n for n in ('quarter_popup', 'parking_hint') if matches(image, self.patterns[n])]
            if notices:
                if len(notices) == 1:
                    self.pending_park_entry = True
                    self.event({'phase': 'interrupted', 'command': 'go park', 'notices': notices,
                                'frame': frame, 'run': entry_run, 'destination': 'not_yet_verified'})
                    label = 'A quarter notice' if notices == ['quarter_popup'] else 'Parking advice'
                    return label + ' interrupted park entry. Use acknowledge notice to continue.'
                self.event({'phase': 'indeterminate', 'command': 'go park', 'frame': frame,
                            'notices': notices, 'persistence': 'unknown'})
                raise RuntimeError('notice during park entry; outcome unknown')
            qualified = qualify_park(self)
            frame = qualified['frame']
            receipt.update(complete=True, status='matched', frame=frame)
            self.last_action = receipt
        finally:
            self.event({'phase': 'navigation_input_result', 'command': 'go park', 'result': receipt})
        after = park_snapshot(self.debug)
        self.event({'phase': 'result', 'command': 'go park', 'before': before, 'after': after,
                    'frame': frame, 'persistence': 'unknown'})
        return self.describe()

    def act(self, command):
        if self.notice_outcome_unknown and command != 'status':
            self.event({'phase': 'refused', 'command': command, 'input': 'not_sent',
                        'reason': 'notice acknowledgment outcome unknown'})
            return 'The notice acknowledgment outcome is unknown. No input was sent; do not retry blindly.'
        if (getattr(self, 'pending_food_notice', False) and
                command not in ('status', 'acknowledge notice')):
            return 'Acknowledge the parking advice before continuing. No input was sent.'
        if command == 'look':
            return self.describe()
        if command in ('borrow', 'repay'):
            return self.transact(command)
        if command == 'continue land purchase':
            from .dinopark_land import resume
            return resume(self)
        if command == 'buy desert plot':
            return self.buy_land()
        if command == 'buy coelophysis':
            return self.buy_dinosaur()
        if command == 'continue dinosaur order':
            if self.dinosaur_order is None:
                return 'There is no active dinosaur order. No input was sent.'
            from .dinopark_purchase import resume
            return resume(self)
        if command in ('buy vegasaurus', 'buy vegasosaurus'):
            return self.buy_vegasaurus()
        if command == 'read vegasaurus':
            return self.read_vegasaurus()
        if command == 'check inventory':
            return self.check_inventory()
        if command == 'continue fence order':
            from .dinopark_fence import resume
            return resume(self)
        if command == 'buy wood fence':
            return self.buy_fence()
        if command == 'hire tour guide':
            return self.hire_guide()
        if command == 'buy 20 small feeders':
            return self.buy_food()
        if command == 'open park':
            return self.open_park()
        if command == 'go park':
            return self.revisit_park()
        if command == 'status':
            return self.observe_park_status('status')[1]
        if command == 'advance time':
            return self.advance_time()
        if command == 'acknowledge notice':
            return self.acknowledge_notice()
        if self.current == 'general_store' and command == 'go street':
            return self.leave_store()
        if self.current == 'dinomart' and command == 'go street':
            return self.leave_mart()
        if self.current == 'park' and command == 'go street':
            return self.leave_park()
        if self.current == 'street' and command in ('go dinomart', 'go store', 'go employment', 'go diner') and not self.land_bought:
            self.event({'phase': 'refused', 'command': command, 'input': 'not_sent',
                        'reason': 'location is closed before land purchase'})
            return 'That business is closed until you buy land. No input was sent.'
        choices = {('office', 'go bank'): (self.office, 'office.bank', 'bank'),
                   ('bank', 'go office'): (self.bank, 'bank.back', 'office'),
                   ('office', 'go street'): (self.office, 'office.street', 'street'),
                   ('street', 'go office'): (self.street, 'street.office', 'office'),
                   ('street', 'go dinomart'): (self.street, 'street.mart', 'dinomart'),
                   ('dinomart', 'go street'): (self.mart, 'mart.back', 'street'),
                   ('street', 'go employment'): (self.street, 'street.employment', 'employment'),
                   ('street', 'go diner'): (self.street, 'street.diner', 'dino_diner'),
                   ('street', 'go store'): (self.street, 'street.store', 'general_store'),
                   ('park', 'go street'): (self.park, 'park.back', 'street'),
                   ('employment', 'go street'): (self.locations.get('employment'), 'employment.back', 'street'),
                   ('dino_diner', 'go street'): (self.locations.get('dino_diner'), 'dino_diner.back', 'street')}
        if (self.current, command) not in choices:
            return 'That action is not available in this scene.'
        selected, obj, target = choices[(self.current, command)]
        self.last_action = self.debug.scene_click(selected, obj)
        # scene_click has already matched the fresh target predicate.
        self.current = target
        return self.describe()


def dispatch_local_action(text, command):
    """Use the same local action dispatcher for CLI and Z; route travel separately."""
    if command.startswith('go ') and command != 'go park' and not (
            text.current == 'park' and command == 'go street'):
        return None
    return text.act(command)


def run_session(argv=None, *, command_reader=None, output=None, on_ready=None, on_event=None, on_spawn=None,
                on_action_error=None, recovery_required=None):
    say = print if output is None else output
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True, help='new private directory, outside repository and source game')
    parser.add_argument('--verify', action='store_true', help='run bounded office/bank/office check')
    parser.add_argument('--load-save', type=Path, help='resume a named native save bundle in a fresh guest')
    parser.add_argument('--save-library', type=Path, help='private named-save directory; defaults to WORK/saves')
    args = parser.parse_args(argv)
    source = args.game_dir.resolve(strict=True)
    work = args.work_dir.resolve()
    if work.exists() or work == source or source in work.parents or work in source.parents:
        parser.error('work directory must be new and separate from source game')
    if any((p / '.git').exists() for p in (work, *work.parents)):
        parser.error('private game and database must be outside Git')
    before = inventory(source)
    if before.get('DINOPARK.EXE') != EXPECTED_EXE:
        parser.error('unsupported game executable')
    if before.get('VARS.DAT') != EXPECTED_VARS:
        parser.error('unsupported bank configuration')
    library = (args.save_library or (args.load_save.parent if args.load_save else work / 'saves')).resolve()
    if (library == source or source in library.parents or library in source.parents or
            any((p / '.git').exists() for p in (library, *library.parents))):
        parser.error('save library must be private, outside Git and the source game')
    loaded, native = (None, None)
    if args.load_save:
        try:
            loaded, native = read_save_bundle(args.load_save, before)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error('cannot load saved park: ' + str(exc))
    if args.verify and loaded:
        parser.error('--verify requires the new-game bank route')
    patterns = json.loads(PATTERNS.read_text())['scenes']
    patterns['borrow_popup'] = BORROW_POPUP
    shop_patterns = json.loads(SHOP_PATTERNS.read_text())['scenes']
    patterns.update({('shop_street' if key == 'street' else key): value
                     for key, value in shop_patterns.items()})
    patterns.update(json.loads(SAVE_PATTERNS.read_text())['scenes'])
    patterns.update(json.loads(OPERATING_PATTERNS.read_text())['scenes'])
    patterns['park_view'] = park_static_pattern(patterns['park_view'])
    patterns.update(json.loads(CATALOGUE_PATTERNS.read_text())['scenes'])
    street_guard = json.loads(STREET_PATTERNS.read_text())['scenes']['street']
    street_guard['reject'] = [patterns[name] for name in
                              ('quarter_popup', 'parking_hint', 'game_menu', 'save_dialog', 'load_dialog')]
    patterns['shop_street'] = street_guard
    work.mkdir(parents=True)
    game = work / 'game'
    shutil.copytree(source, game, ignore=lambda _, names: [n for n in names if n.upper().startswith('DINOSG.')])
    copied = inventory(game)
    if native:
        shutil.copyfile(native, game / 'DINOSG.000')
        if digest(game / 'DINOSG.000') != loaded['native_sha256']:
            raise ValueError('Imported native save changed; guest launch withheld')
    receipt = {'format': 'dinopark-text-scene-1', 'source_exe_sha256': EXPECTED_EXE,
               'backend_sha256': digest(args.backend), 'patterns_sha256': digest(PATTERNS),
               'shop_patterns_sha256': digest(SHOP_PATTERNS),
               'save_patterns_sha256': digest(SAVE_PATTERNS),
               'street_patterns_sha256': digest(STREET_PATTERNS),
               'mart_patterns_sha256': digest(MART_PATTERNS),
               'operating_patterns_sha256': digest(OPERATING_PATTERNS),
               'park_observation_variant': 'occupied-first-pen-excluded-1',
               'park_observation_sha256': document_hash(patterns['park_view']),
               'catalogue_patterns_sha256': digest(CATALOGUE_PATTERNS),
               'script_sha256': digest(Path(__file__)), 'fdisbull_version': fdisbull.__version__,
               'e55_handoff_sha256': 'e6f9da13a3ab1d1de485a496f5d807121bcd929ba67bd87256b449870aa718ea',
               'source_inventory_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
               'working_copy_inventory_sha256': hashlib.sha256(json.dumps(copied, sort_keys=True).encode()).hexdigest(),
               'scope': 'original native new/load game; bounded setup and operation; native save persistence',
               'loaded_save': str(args.load_save.resolve()) if args.load_save else None, 'events': []}
    start = time.perf_counter()
    restart = None
    receipt.update(status='running', complete=False, ok=False)
    atomic_json(work/'receipt.json', receipt)
    try:
        with (work / 'events.jsonl').open('x', encoding='utf-8') as journal, Project.create(work / 'scene.fdb', game / 'DINOPARK.EXE', load_segment=0x1000) as project:
            def event(item):
                receipt['events'].append(item)
                if on_event is not None:
                    on_event(item)
                journal.write(json.dumps(item, sort_keys=True) + '\n')
                journal.flush()
                os.fsync(journal.fileno())
            with project.debugger(args.backend, game, version=1, _on_spawn=on_spawn) as debug:
                debug = BankInputSession(debug,event)
                receipt['run'] = debug.run_id
                # Previously researched NEW GAME setup; all mutations are on a private copy.
                if loaded:
                    event({'phase': 'intent', 'command': 'load park', 'native_sha256': loaded['native_sha256'],
                           'input': 'not_yet_sent', 'mechanism': 'original OLD GAME; fresh process'})
                    run_guest(debug, 35000)
                    for view, pos, ms in (('title_menu', (160, 160), 1500),
                                          ('load_dialog', (90, 60), 300),
                                          ('load_dialog', (250, 73), 3000)):
                        load_view(project, debug, patterns, view, event)
                        event({'phase': 'load_input_intent', 'point': pos, 'input': 'not_yet_sent'})
                        result = click(debug, *pos)
                        event({'phase': 'load_input_sent', 'point': pos, 'result': result})
                        run_guest(debug, ms)
                else:
                    for ms, pos in ((35000, (80, 160)), (2500, (160, 132)), (5000, (175, 140))):
                        run_guest(debug, ms)
                        click(debug, *pos)
                    run_guest(debug, 2500)
                office_frame = wait_for_office(project, debug, patterns)
                selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                                       'hex': debug.memory('4020:3c5c', length=2)['hex']}}
                office_pred, bank_pred = pixel_predicate(patterns['office']), pixel_predicate(patterns['bank'])
                # The current strict street profile avoids moving vehicles,
                # changing signs and the train, and rejects recognized modals.
                street_pattern = patterns['shop_street']
                patterns['street_view'] = street_pattern
                street_pred = pixel_predicate(street_pattern)
                office_doc = definition(office_frame, 'office', office_pred, selector,
                                        'office.bank', [51, 26], bank_pred)
                office_doc['objects'].append(definition(office_frame, 'office', office_pred, selector,
                                            'office.street', [201, 187], street_pred)['objects'][0])
                office = project.debug_save_scene('office', office_doc)
                receipt['office_revision'] = office['id']
                text = TextScene(debug, office['id'], None, project=project, patterns=patterns, event=event)
                text.save_library, text.game, text.source_files = library, game, before
                if loaded:
                    text.restore_qualifications(loaded)
                if on_ready is not None:
                    on_ready(text)
                say(text.describe(), flush=True)
                say('Travel: go office, go bank, go street, go dinomart, go store, go employment, go diner, go park.\n'
                      'Saved parks: save park NAME, list saves, load park NAME. Type help for details.', flush=True)
                commands = iter(('go bank', 'repay', 'borrow', 'go office', 'quit')) if args.verify else None
                bank = None
                street = None
                travel = deque()
                expected_hop = None
                while True:
                    command = None
                    try:
                        if expected_hop == 'park' and text.pending_park_entry:
                            event({'phase': 'travel_paused', 'expected_scene': 'park',
                                   'reason': 'qualified quarter notice', 'following_input': 'not_sent'})
                            travel.clear()
                            expected_hop = None
                        if expected_hop is not None and text.current != expected_hop:
                            event({'phase': 'travel_stopped', 'expected_scene': expected_hop,
                                   'actual_scene': text.current, 'following_input': 'not_sent'})
                            travel.clear()
                            say('Travel stopped before the next step. The last destination was not reached.', flush=True)
                        expected_hop = None
                        try:
                            if travel:
                                command, expected_hop = travel.popleft()
                            else:
                                command = (next(commands) if commands is not None else
                                           command_reader() if command_reader is not None else input('> ').strip().lower())
                                if command_reader is not None:
                                    bank = project.debug_scene_info(text.bank) if text.bank else None
                                    street = project.debug_scene_info(text.street) if text.street else None
                                if command.startswith('save park '):
                                    refusal = text.save_preflight(command.removeprefix('save park '))
                                    if refusal:
                                        event({'phase': 'refused', 'command': command, 'input': 'not_sent', 'reason': refusal})
                                        say(refusal, flush=True)
                                        continue
                                if command in ('go dinomart', 'go store', 'go employment', 'go diner') and not text.land_bought:
                                    event({'phase': 'refused', 'command': command, 'input': 'not_sent', 'reason': 'business closed before land'})
                                    say('That business is closed until you buy land. No input was sent.', flush=True)
                                    continue
                                route_command = 'go office' if command.startswith('save park ') else command
                                route = navigation_route(text.current, route_command, park_opened=text.park_opened)
                                if route == [] and command.startswith('go '):
                                    say('You are already there.', flush=True)
                                    continue
                                if route and (len(route) > 1 or command.startswith('save park ')):
                                    event({'phase': 'travel_intent', 'command': command, 'hops': route,
                                           'mechanism': 'original menu inputs; no memory writes'})
                                    travel.extend(route)
                                    if command.startswith('save park '):
                                        travel.append((command, 'office'))
                                    command, expected_hop = travel.popleft()
                        except EOFError:
                            break
                        if command == 'quit':
                            break
                        if (text.notice_outcome_unknown and command != 'status' or
                                text.pending_food_notice and command not in ('status', 'acknowledge notice')):
                            say(text.act(command), flush=True)
                            continue
                        if command == 'list saves':
                            say('Saved parks: ' + (', '.join(p.parent.name for p in sorted(library.glob('*/save.json'))) or 'none'), flush=True)
                            continue
                        if command == 'help':
                            say('Use go followed by a destination; connected scenes are crossed automatically.\n'
                                  'save park NAME saves a prepared running park, returning to the office if needed.\n'
                                  'list saves lists this session’s named parks. load park NAME resumes one in a fresh game session.\n'
                                  'To resume later, start with --load-save and the printed saved-park folder.\n'
                                  'Use status in the office, street or park, advance time in the street or park, and look for local actions.', flush=True)
                            continue
                        if command.startswith('load park '):
                            try:
                                bundle = library / save_name(command.removeprefix('load park '))
                                read_save_bundle(bundle, before)
                            except (OSError, ValueError, KeyError, TypeError) as exc:
                                event({'phase': 'refused', 'command': command, 'input': 'not_sent', 'reason': str(exc)})
                                say('Cannot load park: ' + str(exc) + ' No input was sent.', flush=True)
                                continue
                            number = 1
                            while (work / f'resume-{number:03d}').exists():
                                number += 1
                            resumed_work = work / f'resume-{number:03d}'
                            restart = ['--game-dir', str(source), '--backend', str(args.backend.resolve()),
                                       '--work-dir', str(resumed_work), '--load-save', str(bundle),
                                       '--save-library', str(library)]
                            event({'phase': 'restart_requested', 'command': command, 'bundle': str(bundle),
                                   'next_work_dir': str(resumed_work), 'mechanism': 'fresh guest; original OLD GAME loader'})
                            say('Loading saved park in a fresh game session. Evidence: ' + str(resumed_work), flush=True)
                            break
                        if command.startswith('save park '):
                            say(text.save_park(command.removeprefix('save park ')), flush=True)
                            continue
                        if command == 'look':
                            rendered = text.describe()
                            observed = {'phase': 'observation', 'command': 'look', 'scene': text.current,
                                        'persistence': 'unknown'}
                            if text.current == 'bank':
                                observed['observed_balances'] = balances(debug)
                            event(observed)
                            say(rendered, flush=True)
                            continue
                        local_result = dispatch_local_action(text, command)
                        if local_result is not None:
                            say(local_result, flush=True)
                            continue
                        if text.current == 'general_store' and command == 'go street':
                            say(text.act(command), flush=True)
                            continue
                        if text.current == 'street' and command in ('go dinomart', 'go store', 'go employment', 'go diner') and not text.land_bought:
                            say(text.act(command), flush=True)
                            continue
                        valid = (text.current, command) in {('office', 'go bank'), ('bank', 'go office'),
                                                           ('office', 'go street'), ('street', 'go office'),
                                                           ('street', 'go dinomart'), ('dinomart', 'go street'),
                                                           ('street', 'go employment'), ('employment', 'go street'),
                                                           ('street', 'go diner'), ('dino_diner', 'go street'),
                                                           ('street', 'go store'), ('general_store', 'go street'),
                                                           ('park', 'go street')}
                        if not valid:
                            say('That action is not available in this scene.', flush=True)
                            continue
                        event({'phase': 'intent', 'command': command, 'scene': text.current, 'input': 'not_yet_sent'})
                        if command == 'go bank' and bank is None:
                            action = debug.scene_click(office['id'], 'office.bank')
                            bank_frame, bank_image = take_frame(project, debug, 'bank-after')
                            if not matches(bank_image, patterns['bank']) or matches(bank_image, patterns['office']):
                                raise RuntimeError('bank not uniquely recognized after input')
                            bank_selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                                                        'hex': debug.memory('4020:3c5c', length=2)['hex']}}
                            bank_doc = definition(bank_frame, 'bank', bank_pred, bank_selector,
                                                  'bank.back', [173, 187], office_pred)
                            for object_name, point, popup in (('bank.payoff', [219, 187], 'paid_popup'),
                                                              ('bank.borrow', [50, 187], 'borrow_popup')):
                                item = definition(bank_frame, 'bank', bank_pred, bank_selector,
                                                  object_name, point, pixel_predicate(patterns[popup]))['objects'][0]
                                bank_doc['objects'].append(item)
                            bank = project.debug_save_scene('bank', bank_doc)
                            text.bank, text.current = bank['id'], 'bank'
                            rendered = text.describe()
                            receipt['bank_after'] = bank_frame
                        elif command == 'go street' and street is None:
                            action = debug.scene_click(office['id'], 'office.street')
                            street_frame, street_image = take_frame(project, debug, 'street-after')
                            if not matches(street_image, street_pattern) or matches(street_image, patterns['office']):
                                raise RuntimeError('street not uniquely recognized after input')
                            street_selector = {'memory': {'address': '4020:3c5c', 'length': 2,
                                                          'hex': debug.memory('4020:3c5c', length=2)['hex']}}
                            street_doc = definition(street_frame, 'street', street_pred, street_selector,
                                                    'street.office', [175, 140], office_pred)
                            street_doc['objects'].append(mart_entry_object(
                                street_frame, street_pred, street_selector, patterns))
                            for view in ('employment', 'dino_diner', 'general_store'):
                                street_doc['objects'].append(business_entry_object(
                                    street_frame, street_pred, street_selector, patterns, view))
                            street = project.debug_save_scene('street', street_doc)
                            text.street, text.current = street['id'], 'street'
                            event({'phase': 'street_guard_live_qualified', 'frame': street_frame,
                                   'scene_revision': street['id'], 'selector': street_selector,
                                   'profile_sha256': digest(STREET_PATTERNS)})
                            rendered = text.describe()
                            receipt['street_after'] = street_frame
                        elif command == 'go dinomart':
                            action = click_business(text, command, text.street, 'street.mart')
                            qualified = qualify_dinomart(text)
                            mart_frame, mart = qualified['frame'], qualified['scene']
                            text.vegasaurus_extinct = False
                            rendered = text.describe()
                            receipt['dinomart_before'] = mart_frame
                        elif command in ('go employment', 'go diner', 'go store'):
                            view, obj = {'go employment': ('employment', 'street.employment'),
                                         'go diner': ('dino_diner', 'street.diner'),
                                         'go store': ('general_store', 'street.store')}[command]
                            action = click_business(text, command, text.street, obj)
                            qualify_business(text, view)
                            rendered = text.describe()
                        else:
                            rendered = text.act(command)
                            action = text.last_action
                        result_event = {'phase': 'result', 'command': command, 'scene': text.current, 'result': action,
                                        'persistence': 'unknown', 'semantic_financial_effect': 'not assessed'}
                        if command in ('go bank', 'go office', 'repay', 'borrow'):
                            result_event['observed_balances'] = balances(debug)
                        event(result_event)
                        say(rendered, flush=True)
                        if args.verify and command == 'go office':
                            after, image = take_frame(project, debug, 'office-after')
                            if not matches(image, patterns['office']) or matches(image, patterns['bank']):
                                raise RuntimeError('office return not independently recognized')
                            receipt['office_after'] = after
                    except Exception as error:
                        if on_action_error is None or not on_action_error(error):
                            raise
                        travel.clear()
                        expected_hop = None
                        event({'phase':'action_recovery_required', 'command':command,
                               'error_type':type(error).__name__, 'following_input':'not_sent'})
                receipt['office_before'] = office_frame
                receipt['bank_revision'] = bank['id'] if bank else None
        if args.verify:
            with Project(work / 'scene.fdb') as reopened:
                saved = reopened.debug_scene_info(receipt['office_revision'], version=1)
                if saved['id'] != receipt['office_revision']:
                    raise ValueError('Scene revision changed across restart')
                overlay = reopened.debug_scene_overlay(saved['id'], version=1)
                reopened.debug_export(overlay['artifact'], work / 'office-overlay-after-restart.png')
                region = reopened.regions(1)[0]
                child = reopened.patch(address=hex(region.start), data=f'{region.data[0] ^ 1:02x}', version=1)
                try:
                    reopened.debug_scene_info(saved['id'], version=child['version'])
                except ValueError:
                    receipt['patched_child_scene_isolated'] = True
                else:
                    raise RuntimeError('scene unexpectedly visible in patched child')
                if reopened.debug_scene_info(saved['id'], version=1)['sha256'] != saved['sha256']:
                    raise ValueError('Parent scene changed after patch isolation check')
                receipt['restart_overlay'] = overlay
                receipt['patched_child_version'] = child['version']
        receipt['source_unchanged'] = inventory(source) == before
        receipt['elapsed_seconds'] = round(time.perf_counter() - start, 3)
        unresolved = bool(recovery_required and recovery_required())
        receipt['unresolved_recovery'] = unresolved
        receipt['ok'] = bool(not unresolved and receipt['source_unchanged'] and (not args.verify or
            [(e['phase'], e['command']) for e in receipt['events']] == [
                ('intent','go bank'), ('pointer_prepared','go bank'), ('result','go bank'),
                ('intent','repay'), ('pointer_prepared','repay'), ('modal','repay'), ('result','repay'),
                ('intent','borrow'), ('pointer_prepared','borrow'), ('modal','borrow'), ('result','borrow'),
                ('intent','go office'), ('pointer_prepared','go office'), ('result','go office')]))
        receipt.update(status='recovery-required' if unresolved else 'completed', complete=receipt['ok'])
        if not receipt['ok'] and not unresolved:
            raise RuntimeError('verification did not complete')
        return restart
    except BaseException as exc:
        receipt.update(status='interrupted' if isinstance(exc,(SceneInterrupted,KeyboardInterrupt,SystemExit)) else 'failed',
                       complete=False, ok=False, error_type=type(exc).__name__)
        confirmed_food = [e['result'] for e in receipt['events'] if e['phase'] == 'food_purchase_committed']
        confirmed_dinosaurs = [e['proof'] for e in receipt['events'] if e['phase'] == 'vegasaurus_purchase_confirmed']
        with (work / 'failure.json').open('x') as output:
            json.dump({'error_type': type(exc).__name__, 'error': str(exc), 'events': receipt['events'],
                       'outcome': ('followup_unknown_with_confirmed_food_purchases' if confirmed_food else
                                   'followup_unknown_with_confirmed_dinosaur_orders' if confirmed_dinosaurs else 'unknown'),
                       'confirmed_food_purchases': confirmed_food,
                       'confirmed_dinosaur_orders': confirmed_dinosaurs,
                       'do_not_retry_blindly': True}, output, indent=2, default=str)
        raise
    finally:
        receipt['elapsed_seconds'] = round(time.perf_counter() - start, 3)
        receipt['source_unchanged'] = inventory(source) == before
        atomic_json(work/'receipt.json',receipt)


def main():
    arguments = None
    while True:
        arguments = run_session(arguments)
        if arguments is None:
            return


if __name__ == '__main__':
    main()
