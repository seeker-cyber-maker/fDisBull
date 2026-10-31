"""Z protocol over existing original DinoPark scenes and the original DOS UDC.

UDC must actually emit the game before it is launched. No synthetic finance,
stock or scene rules are substituted for the original executable.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import signal
import sys
import traceback

HERE = Path(__file__).resolve().parent
LIMIT = 32768
NAVIGATION = {'office': 'office', 'bank': 'bank', 'street': 'street', 'dinomart': 'dinomart',
              'store': 'general_store', 'employment': 'employment', 'diner': 'dino_diner', 'park': 'park'}
TITLES = {'office': 'Park office', 'bank': 'Bank', 'street': 'Park street', 'dinomart': 'DinoMart',
          'general_store': 'General Store', 'employment': 'Employment office',
          'dino_diner': 'Dino Diner', 'park': 'Park'}
PURCHASE_COMMITS = ('food_purchase_committed', 'vegasaurus_purchase_confirmed',
                    'coelophysis_purchase_confirmed')
SNAPSHOT_FIELDS = ('office', 'bank', 'street', 'mart', 'park', 'locations', 'current',
                   'land_bought', 'dinosaur_bought', 'fence_bought', 'guide_hired',
                   'food_bought', 'park_opened', 'notice_outcome_unknown', 'transaction_count',
                   'pending_park_entry', 'pending_food_notice',
                   'pending_food_return',
                   'vegasaurus_attempted', 'vegasaurus_proof', 'vegasaurus_extinct', 'last_action',
                   'last_continuation', 'dinosaur_order')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def load_scenes():
    from fdisbull import dinopark_scenes
    return dinopark_scenes


def build_game(source, work):
    """Use the v0.23 candidate's actual UDC, then independently check its output."""
    try:
        from fdisbull.udc import capture_dos_definition, compile_dos
    except ImportError as exc:
        raise ValueError('Original-backed DOS UDC is required; select the v0.23 candidate core') from exc
    from fdisbull.project import Project
    import fdisbull.udc as compiler
    source = source.resolve(strict=True)
    before = files(source)
    scenes = load_scenes()
    if before.get('DINOPARK.EXE') != scenes.EXPECTED_EXE or before.get('VARS.DAT') != scenes.EXPECTED_VARS:
        raise ValueError('Unqualified original game identity')
    selected = {p: d for p, d in before.items() if not Path(p).name.upper().startswith('DINOSG.')}
    with Project.create(work / 'udc.fdb', source / 'DINOPARK.EXE', load_segment=0x1000) as project:
        resources = {}
        for index, path in enumerate(sorted(selected)):
            if (source/path).is_symlink() or not (source/path).resolve().is_relative_to(source):
                raise ValueError('Source resources must stay inside the selected game')
            if path == 'DINOPARK.EXE':
                continue
            name = 'game-resource-' + str(index)
            project.attach_file(source/path, name=name, kind='resource')
            resources[path] = name
        definition = capture_dos_definition(project, 'dinopark-z-original', resources=resources,
                                            version=1, author='DinoPark Z integration')
        built = compile_dos(project, definition['id'], work / 'udc-output')
    if built.get('format') != 'fdisbull-udc-compilation-1' or built.get('primary') != 'DINOPARK.EXE':
        raise ValueError('Unexpected UDC product')
    if built.get('qualification', {}).get('byte_identity') is not True:
        raise ValueError('Original-backed byte identity is not established')
    emitted = {a['path']: a['sha256'] for a in built['artifacts']}
    if len(emitted) != len(built['artifacts']) or emitted != selected:
        raise ValueError('UDC output resource closure differs from original inputs')
    runtime = work / 'compiled-game'; runtime.mkdir()
    for name, digest in emitted.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe UDC artifact path')
        original = work / 'udc-output' / name
        if original.is_symlink() or sha(original) != digest:
            raise ValueError('UDC artifact changed before native launch')
        target = runtime / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    if files(runtime) != selected or files(source) != before:
        raise ValueError('UDC deployment or original input changed')
    receipt = {'definition': definition, 'compiler': built, 'source_unchanged': True,
               'compiler_module_sha256': sha(compiler.__file__), 'runtime_artifacts': emitted,
               'scene_adapter_sha256': sha(scenes.__file__), 'z_adapter_sha256': sha(__file__),
               'recognition_profiles': scenes.pattern_hashes(),
               'scope': 'unchanged original-backed DOS; no generated semantic replacement'}
    (work/'udc-build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return runtime


class ZService:
    def __init__(self, work, reader, writer, *, slot='zpark', oracle=False):
        self.work, self.reader, self.writer, self.slot = work, reader, writer, slot
        self.text = None
        self.terminal = None
        self.epoch = secrets.token_hex(32)
        self.session_token = secrets.token_hex(32)
        self.checkpoint_failed = False
        self.recovery_required = False
        self.failures = []
        self.revision = 0
        self.pending = None
        self._action_budget_scope = None
        self.held_action = None
        self.snapshots = {}
        self.latest_native_save = None
        self.processes = []
        self.history = []
        self.restarted = False
        self.oracle_enabled, self.oracle_count = oracle, 0
        self.stop_reason = None
        from .z_replies import ZReplyJournal
        self.replies = ZReplyJournal(work)

    def receipt(self, status, *, complete=False):
        from fdisbull.dinopark_scenes import atomic_json
        processes=[{'pid':p.pid,'returncode':p.poll()} for p in self.processes]
        delivery_pending = self.reply_pending
        atomic_json(self.work/'z-session.json',{
            'status':status, 'complete':complete and not delivery_pending, 'stop_reason':self.stop_reason,
            'history':self.history, 'pending_command':self.pending['command'] if self.pending else None,
            'latest_native_save':self.latest_native_save,
            'checkpoint_recovery':'unqualified' if self.checkpoint_failed or self.recovery_required else 'qualified',
            'recovery_required':self.recovery_required, 'action_failures':self.failures,
            'held_command':self.held_action['pending']['command'] if self.held_action else None,
            'recovery_id':self.held_action['id'] if self.held_action else None,
            'reconciliation_available':self._reconcilable_navigation() or self._reconcilable_purchase(),
            'purchase_phase':(getattr(self.text,'dinosaur_order',None) or {}).get('phase'),
            'reply_delivery_pending':delivery_pending,
            'pending_effects':('applied-confirmed' if self.pending and any(e.get('phase') in
                PURCHASE_COMMITS for e in self.pending['events'])
                else 'unknown' if self.pending else self.held_action['effects'] if self.held_action else 'none-pending'),
            'processes':processes, 'cleanup_complete':all(p['returncode'] is not None for p in processes),
            'scope':'original-backed UDC with existing native scene actions'})

    def event(self, item):
        self.history.append(deepcopy(item))
        if item.get('phase') == 'result' and item.get('command', '').startswith('save park '):
            self.latest_native_save = item['command'].removeprefix('save park ')
        if self.pending is not None:
            self.pending['events'].append(deepcopy(item))
        if item.get('phase') == 'coelophysis_purchase_confirmed' and self._reconcilable_purchase():
            self.held_action['effects'] = 'applied-confirmed'
            self.failures[self.held_action['failure_index']]['effects'] = 'applied-confirmed'
        if item.get('phase') in (*PURCHASE_COMMITS, 'coelophysis_input_sent'):
            self.receipt('acting')
            # Retain delivery or commit evidence without optional native RPCs at an
            # instruction boundary; witness readback runs at command end.

    def ready(self, text):
        self.text = text
        text.bounded_purchases = True
        if not hasattr(text, 'dinosaur_order'):
            text.dinosaur_order = None
        self.terminal = None
        self.session_token = secrets.token_hex(32)
        self.checkpoint_failed = False
        self.recovery_required = False
        self.held_action = None
        if (self.pending and self.pending['command'].startswith('load park ') and any(
                e.get('phase') == 'result' and e.get('command') == 'load park'
                for e in self.pending['events'])):
            self.latest_native_save = self.pending['command'].removeprefix('load park ')
        self.revision += 1
        self.restarted = True
        self.snapshots.clear()
        self.receipt('ready')
        self.oracle('ready')

    def spawned(self, process):
        self.processes.append(process)
        self.receipt('running')

    def output(self, *values, sep=' ', end='\n', **kwargs):
        message = sep.join(map(str, values))
        if self.pending is not None and not message.startswith('Travel:'):
            self.pending['messages'].append(message)

    @property
    def reply_pending(self):
        return self.replies.blocked

    def reply_witness(self):
        # session.status observes the existing stopped native session. No scene
        # readback, run, input, checkpoint restore or new guest is permitted here.
        try:
            debug = self.text.debug
            native = debug.call('session.status')
            stop = native.get('last_stop', native.get('stop_reason'))
            if (not isinstance(stop, dict) or not isinstance(stop.get('kind'), str)
                    or not stop['kind'] or len(stop['kind']) > 64
                    or not isinstance(native.get('session_id'), str)
                    or native.get('state') not in ('stopped', 'exited')
                    or type(native.get('state_revision')) is not int or native['state_revision'] < 0):
                return None
            witness = {'epoch': self.epoch, 'session_token': self.session_token,
                       'run': debug.run_id,
                       'native': {**{k: native.get(k) for k in
                                      ('session_id', 'state', 'state_revision')},
                                  'stop_reason': stop}}
            from .z_replies import encoded
            return witness if len(encoded(witness)) <= 8192 else None
        except Exception:
            return None

    def reply_command(self, request):
        op = request.get('op')
        if op == 'reply_status' and set(request) == {'op'}:
            return self.replies.status()
        if op == 'read_reply' and {'op', 'reply_id'} <= set(request) <= {'op', 'reply_id', 'offset', 'length'}:
            return self.replies.read(request['reply_id'], request.get('offset', 0), request.get('length', 8192))
        if op == 'select_reply' and {'op', 'reply_id'} <= set(request) <= {'op', 'reply_id', 'pointer'}:
            return self.replies.select(request['reply_id'], request.get('pointer', ''))
        if op == 'accept_reply' and set(request) == {'op', 'reply_id', 'sha256'}:
            return self.replies.accept(request['reply_id'], request['sha256'], self.reply_witness())
        raise ValueError('Invalid reply request')

    def send(self, result):
        from .z_replies import encoded
        data = encoded(result) + b'\n'
        if len(data) > LIMIT:
            try:
                status = result.get('status')
                execution = {'returned': True,
                             'complete': result.get('complete') if type(result.get('complete')) is bool else None,
                             'status': status if isinstance(status, str) and len(status) <= 48 else None}
                result = self.replies.retain(data[:-1], self.reply_witness(), execution)
            except Exception:
                self.replies.unavailable()
                result = {
                    'complete': False, 'status': 'reply-unavailable', 'delivery_pending': True,
                    'retry_safe': False, 'message': 'Reply retention failed; do not replay the action.'}
            data = encoded(result) + b'\n'
        if len(data) > LIMIT:
            raise ValueError('Z reply exceeds delivery budget')
        text = data.decode('utf-8')
        with (self.work/'z-protocol.jsonl').open('a', encoding='utf-8') as journal:
            journal.write(text)
        self.writer.write(text); self.writer.flush()

    def public_message(self, text):
        # Legacy saved-park responses include local evidence paths. Keep them private.
        import re
        text = re.sub(r'Commands:[^\n]*', '', text)
        text = re.sub(r'/(?:Users|Volumes|private|var|tmp|home|workspace)/\S+', '[private evidence]', text)
        text = re.sub(r' Resume folder: [^\n]*| Evidence: [^\n]*', '', text)
        text = re.sub(r'Use load park ([a-z0-9][a-z0-9_-]{0,31}), or --load-save with that folder in a later session\.',
                      r'Use load \1 to restore this backup, or load park for the latest backup.', text)
        if len(text.encode('utf-8')) > 24000:
            return 'The command produced an oversized response; inspect private evidence before continuing.'
        return text

    def native_save_names(self):
        library = getattr(self.text, 'save_library', None)
        if library is None:
            return []
        names = []
        for path in sorted(library.glob('*/save.json')):
            name = path.parent.name
            try:
                load_scenes().save_name(name)
            except ValueError:
                continue
            names.append(name)
            if len(names) == 64:
                break
        return names

    def next_native_save_name(self):
        library = getattr(self.text, 'save_library', None)
        if library is None:
            return self.slot
        if len(self.native_save_names()) >= 64:
            return None
        for number in range(1, 1000):
            name = self.slot if number == 1 else f'{self.slot[:28]}-{number:03d}'
            if not (library / name).exists():
                return name
        return None

    def objects(self):
        if self.terminal is not None and self.terminal.phase != 'live':
            return self.terminal.objects()
        if self._reconcilable_purchase():
            if self.text.dinosaur_order.get('proof') and self.text.dinosaur_order['phase'] == 'committed':
                return [], {}
            return ([{'id':'dinosaur-order','label':'dinosaur order','aliases':['order','coelophysis order'],
                      'description':'Continue the remaining phases of the existing order; delivered inputs are not repeated.',
                      'verbs':['continue']}], {('continue','dinosaur-order'):'continue dinosaur order'})
        view = self.text.current
        objects = []
        bindings = {}
        def add(ident, label, aliases, description, actions):
            objects.append({'id': ident, 'label': label, 'aliases': aliases,
                            'description': description, 'verbs': list(actions)})
            for verb, command in actions.items():
                bindings[(verb, ident)] = command
        for name, target in NAVIGATION.items():
            actions = {'go': 'go '+name}
            if name == 'park':
                next_save = self.next_native_save_name()
                if next_save is not None:
                    actions['save'] = 'save park '+next_save
                actions['load'] = 'load park '+(self.latest_native_save or self.slot)
                if view == 'street': actions['open'] = 'open park'
            if target == view and name != 'park': continue
            add('route-'+name, name, [], 'Known route to '+TITLES[target]+'.', actions)
        local = {
            'bank': [('loan', 'loan', [], 'The original bank offers its full quote or full repayment.', {'borrow':'borrow','repay':'repay'})],
            'street': [('plot', 'desert plot', ['land'], 'A desert plot is listed for $500.', {'buy':'buy desert plot'}),
                       ('inventory', 'inventory screen', ['original inventory'] if getattr(self.text,'park_opened',False) else ['inventory'], 'Open the original count screen in its qualified pre-opening state.', {'check':'check inventory'})],
            'dinomart': [('coelophysis', 'coelophysis', [], 'A catalogue listing priced at $1,250.', {'buy':'buy coelophysis'}),
                         ('vegasaurus', 'vegasaurus', ['vegasosaurus'], 'A catalogue listing priced at $25,000, with an encyclopedia entry.', {'buy':'buy vegasaurus','read':'read vegasaurus'})],
            'general_store': [('wood-fence', 'wood fence', ['fence'], 'Wood fencing for the occupied pen, priced at $1,000.', {'buy':'buy wood fence'})],
            'employment': [('guide', 'tour guide', ['guide'], 'A tour guide position with a listed $900 monthly wage.', {'hire':'hire tour guide'})],
            'dino_diner': [('feeders', '20 small feeders', ['food','small feeders'], 'Twenty small feeders are listed for $500.', {'buy':'buy 20 small feeders'})],
        }
        for ident, label, aliases, description, actions in local.get(view, []):
            if ident == 'vegasaurus' and self.text.vegasaurus_extinct:
                description = 'The listing now reads NOW EXTINCT.'; actions = {}
            add(ident,label,aliases,description,actions)
        if view in ('office','street','park'):
            add('park-status','status',['finances','inventory','park inventory'] if getattr(self.text,'park_opened',False) else ['finances'], 'Read the operating park report: finances, inventory, food, staff and dinosaurs.', {'check':'status'})
        if view in ('street','park'):
            add('time','time',[], 'Advance one bounded original-game interval.', {'advance':'advance time'})
            add('notice','notice',[], 'Acknowledge a currently recognized notice.', {'acknowledge':'acknowledge notice'})
        if view == 'office':
            add('terminal-menu', 'game menu', ['menu'], 'Open the original menu to resume or leave this park.', {'open':'terminal:open'})
        add('saves','saves',[], 'List named native saves in this private session library.', {'list':'list saves'})
        for name in self.native_save_names():
            add('save-'+name, 'saved park '+name, [name],
                'A named native park save. Load it in a fresh original-game session.',
                {'load': 'load park '+name})
        return objects, bindings

    def oracle(self, phase):
        if not self.oracle_enabled or self.text is None or self.oracle_count >= 256:
            return
        self.oracle_count += 1
        spans = {'cash':('4020:5c3a',4),'loan':('4020:bfbb',4),
                 'working_cash':('4020:bad4',4),'food':('4020:6f94',18),
                 'staff':('4020:6f88',12),'pens':('4020:4384',200),
                 'species':('4020:bfe3',40),'year_month':('4020:ccfc',4),
                 'day':('4020:6fcb',2),'week':('4020:6fc9',2),'hunger':('4020:6fc0',4)}
        try:
            raw = {k:{'address':a,'length':n,'hex':self.text.debug.memory(a,length=n)['hex']}
                   for k,(a,n) in spans.items()}
            name = 'z-oracle-' + str(self.oracle_count).zfill(4) + '.png'
            frame = self.text.debug.screenshot(name)
            self.text.project.debug_export(frame['artifact'],self.work/name)
            item = {'phase':phase,'scene':self.text.current,'raw':raw,'frame':frame,
                    'command':self.pending['command'] if self.pending else None}
        except Exception as error:
            item = {'phase':phase,'oracle':'incomplete','error_type':type(error).__name__}
        with (self.work/'oracle.jsonl').open('a',encoding='utf-8') as journal:
            journal.write(json.dumps(item,sort_keys=True)+'\n')

    def observe(self, *, recovering=False):
        try:
            if (self.checkpoint_failed or self.recovery_required) and not recovering:
                if self._reconcilable_purchase():
                    from .dinopark_purchase import PurchaseBudget, recovery_view
                    with PurchaseBudget().bind(self.text.debug):
                        state = recovery_view(self.text)
                        registers = self.text.debug.registers()
                    order = self.text.dinosaur_order
                    context = 'dinomart.order-' + order['phase']
                    token = hashlib.sha256(json.dumps([self.epoch,self.session_token,self.revision,
                        order['id'],context,state,registers.get('state_revision')],sort_keys=True).encode()).hexdigest()
                    objects, _ = self.objects()
                    return {'complete':True,'session_token':self.session_token,
                            'context':{'id':context,'token':token,'title':'DinoMart order',
                                       'description':('The purchase effect is verified. Use reconcile to finish the order.'
                                                      if order.get('proof') else
                                                      'Your Coelophysis order is in progress. Continue dinosaur order to proceed.')},
                            'objects':objects,'inventory':[],'coverage':{'partial':True},
                            'recovery_required':True,'recovery_id':self.held_action['id'],
                            'reconciliation_available':True}
                raise ValueError('Checkpoint recovery is unqualified')
            if self.terminal is not None and self.terminal.phase != 'live':
                (title, description), revision = self.terminal.view()
                context = 'terminal.' + self.terminal.phase
                token = hashlib.sha256(json.dumps([self.epoch, self.session_token, self.revision,
                    context, revision, getattr(self.text.debug, '_runtime_epoch', None)]).encode()).hexdigest()
                objects, _ = self.objects()
                return {'complete':True,'session_token':self.session_token,
                        'context':{'id':context,'token':token,'title':title,'description':description},
                        'objects':objects,'inventory':[],'coverage':{'partial':True}}
            modal = False
            parking = getattr(self.text, 'pending_food_notice', False) and self.text.current == 'dino_diner'
            if parking:
                scenes = load_scenes()
                _, image = scenes.take_frame(self.text.project, self.text.debug, 'z-parking-observation')
                if (self.text.notice_outcome_unknown or
                        not scenes.matches(image, self.text.patterns['parking_hint']) or
                        scenes.matches(image, self.text.patterns['quarter_popup'])):
                    raise ValueError('Unqualified parking advice')
                modal = 'parking-notice'
                description = ('The adviser suggests another parking lot to increase attendance. '
                               'The food menu was interrupted before an order was submitted. Acknowledge the advice to continue.')
            else:
                try:
                    description = self.text.describe().split('Commands:')[0].strip()
                except Exception:
                    # Qualify the modal independently of its obscured parent.
                    scenes = load_scenes()
                    entering = getattr(self.text, 'pending_park_entry', False) and self.text.current == 'street'
                    returning = getattr(self.text, 'pending_food_return', False) and self.text.current == 'street'
                    if (self.text.current != 'park' and not entering and not returning or
                            not self.text.park_opened or self.text.notice_outcome_unknown):
                        raise
                    _,image = scenes.take_frame(self.text.project,self.text.debug,'z-modal-observation')
                    notices = [n for n in ('quarter_popup', 'parking_hint')
                               if scenes.matches(image, self.text.patterns[n])]
                    if len(notices) != 1:
                        raise ValueError('Unqualified modal')
                    modal = 'quarter-notice' if notices == ['quarter_popup'] else 'parking-notice'
                    description = ('A recognized quarter notice is visible.' if modal == 'quarter-notice' else
                                   'The adviser suggests another parking lot to increase attendance.') + ' Acknowledge it to continue.'
                    if returning:
                        description = 'The food purchase is already confirmed. ' + description
            registers = self.text.debug.registers()
            context = ('food-return.' + modal if modal and getattr(self.text, 'pending_food_return', False) else
                       'park-entry.' + modal if modal and getattr(self.text, 'pending_park_entry', False)
                       else self.text.current + ('.' + modal if modal else ''))
            opaque = [self.epoch, self.revision, context, description,
                      registers.get('state_revision'), getattr(self.text.debug, '_runtime_epoch', None)]
            token = hashlib.sha256(json.dumps(opaque, sort_keys=True).encode()).hexdigest()
            objects,_ = self.objects()
            if modal: objects = [o for o in objects if o['id'] == 'notice']
            return {'complete':True, 'session_token':self.session_token, 'context':{'id':context, 'token':token,
                    'title':'Parking advice' if modal == 'parking-notice' else 'Quarter notice' if modal else TITLES[self.text.current], 'description':description},
                    'objects':objects, 'inventory':[], 'coverage':{'partial':True}}
        except Exception:
            return {'complete':False, 'session_token':self.session_token,
                    'recovery_required':self.recovery_required or self.checkpoint_failed,
                    'recovery_id':self.held_action['id'] if self.held_action else None,
                    'reconciliation_available':self._reconcilable_navigation() or self._reconcilable_purchase()}

    def _reconcilable_purchase(self):
        held = self.held_action
        if not held or self.checkpoint_failed or not self.recovery_required:
            return False
        pending = held['pending']
        action = pending.get('action', {})
        order = held.get('dinosaur_order')
        current = getattr(self.text, 'dinosaur_order', None)
        if not isinstance(order, dict) or not isinstance(current, dict):
            return False
        ticket = order.get('last_input') or {}
        current_ticket = current.get('last_input') or {}
        return (held['session_token'] == pending.get('session_token') == self.session_token and
                pending.get('command') == 'buy coelophysis' and
                {k:action.get(k) for k in ('verb','target','item')} ==
                    {'verb':'buy','target':'coelophysis','item':None} and
                held['source'] == self.text.current == 'dinomart' and
                order.get('id') == current.get('id') and
                order.get('run') == current.get('run') == self.text.debug.run_id and
                order.get('source_revision') == current.get('source_revision') and
                ticket.get('accepted') is True and ticket.get('delivery') == 'queued' and
                current_ticket.get('accepted') is True and current_ticket.get('delivery') == 'queued')

    def _reconcilable_navigation(self):
        held = self.held_action
        if not held or self.checkpoint_failed or not self.recovery_required:
            return False
        pending, failure = held['pending'], held['scene_failure']
        action = pending.get('action', {})
        ticket = failure.get('input', {})
        return (held['session_token'] == self.session_token and
                pending.get('session_token') == self.session_token and
                pending.get('command') == 'go dinomart' and
                {k:action.get(k) for k in ('verb','target','item')} ==
                    {'verb':'go','target':'route-dinomart','item':None} and
                held['source'] == self.text.current == 'street' and
                failure.get('scene_revision') == getattr(self.text,'street',None) and
                failure.get('action_name') == 'street.mart' and
                failure.get('before_observation') is not None and
                ticket.get('accepted') is True and ticket.get('delivery') == 'queued' and
                (not getattr(self.text.debug,'run_id',None) or
                 failure.get('run') == self.text.debug.run_id))

    def reconcile(self, recovery_id=None):
        """Qualify the held original destination without execution or new input."""
        result = {'complete':False, 'status':'incomplete',
                  'effects':self.held_action['effects'] if self.held_action else 'unknown',
                  'read_only':True, 'recovery_required':self.recovery_required or self.checkpoint_failed,
                  'recovery_id':self.held_action['id'] if self.held_action else None,
                  'message':'Original outcome remains unresolved; no input sent.'}
        if not self.recovery_required and not self.checkpoint_failed:
            return {**result,'complete':True,'status':'not-needed','effects':'none-confirmed',
                    'message':'No held original action requires reconciliation.'}
        purchase = self._reconcilable_purchase()
        if not purchase and not self._reconcilable_navigation():
            return result
        held = self.held_action
        if recovery_id is not None and recovery_id != held['id']:
            return result
        previous = self.text.current, self.text.mart, self.revision
        previous_order = deepcopy(getattr(self.text,'dinosaur_order',None))
        previous_bought = getattr(self.text,'dinosaur_bought',False)
        try:
            from .dinopark_purchase import PurchaseBudget, qualify_purchase
            with PurchaseBudget().bind(self.text.debug):
                if self.text.debug.call('session.status').get('state') != 'stopped':
                    return result
                if purchase:
                    qualified = qualify_purchase(self.text)
                else:
                    qualified = load_scenes().qualify_dinomart(self.text)
                self.revision += 1
                observed = self.observe(recovering=True)
                witness = self.witness(observed)
                if witness is None or observed['context']['id'] != 'dinomart':
                    raise ValueError('Original destination is not qualified')
        except Exception:
            self.text.current, self.text.mart, self.revision = previous
            if purchase:
                proof = getattr(self.text,'dinosaur_order',{}).get('proof')
                self.text.dinosaur_order = previous_order
                if proof:
                    self.text.dinosaur_order['proof'] = proof
                self.text.dinosaur_bought = previous_bought
            return {**result, 'effects':held['effects']}
        self.recovery_required = False
        self.held_action = None
        action = {k:held['pending']['action'][k] for k in ('verb','target','item')}
        self.failures[held['failure_index']]['reconciliation'] = {
            'read_only':True,'witness':witness,'original_diagnostic_preserved':True}
        self.event({'phase':'purchase_reconciled' if purchase else 'navigation_reconciled',
                    'command':held['pending']['command'],
                    'read_only':True,'guest_execution':'not_requested','input':'not_sent',
                    'frame':qualified['frame'],'witness':witness})
        self.receipt('reconciled')
        return {**result,'complete':True,'status':'success','effects':'applied-confirmed',
                'recovery_required':False,'action':action,'witness':witness,
                'message':('Original Coelophysis purchase verified: one dinosaur placed, $1,250 charged. '
                           'Cash: $3,250. No input was replayed.' if purchase else
                           'Original DinoMart destination verified; navigation was not replayed.')}

    def witness(self, observation):
        context = observation.get('context', {})
        if (observation.get('complete') is True and isinstance(context, dict)
                and all(isinstance(context.get(k), str) and 1 <= len(context[k]) <= 128
                        for k in ('id', 'token'))):
            return {'session_token': self.session_token,
                    'context_id': context['id'], 'context_token': context['token']}
        return None

    def finish(self):
        self.oracle('command-complete')
        pending, self.pending = self.pending, None
        self.revision += 1
        if pending['command'] == 'continue dinosaur order' and self.held_action is not None:
            self.held_action['dinosaur_order'] = deepcopy(self.text.dinosaur_order)
            processed = (self.text.dinosaur_order['phase'] == 'committed' and
                         self.text.dinosaur_order.get('proof') and any(
                             e.get('phase') == 'coelophysis_continuation' and
                             e.get('order_id') == self.text.dinosaur_order['id'] for e in pending['events']))
            self.receipt('recovery-required')
            self.send({'status':'accepted' if processed else 'incomplete','complete':bool(processed),
                       'effects':self.held_action['effects'],
                       'recovery_required':True,'recovery_id':self.held_action['id'],
                       'message':('The remaining order phases have been processed. Use reconcile to verify the original purchase.'
                                  if processed else 'The continuation was not verified; the original order remains held.')})
            self._end_action_budget()
            return
        events = pending['events']
        messages = '\n'.join(pending['messages']).strip()
        refusal = any(e.get('phase') == 'refused' for e in events)
        text_refusal = any(x in messages.casefold() for x in ('no input was sent', 'not available in this scene', 'no input was sent.', 'not qualified'))
        uncertain = any(x in messages.casefold() for x in ('outcome unknown', 'do not retry', 'travel stopped'))
        sent = any(e.get('phase') in ('shop_input_sent','notice_input','save_key','load_input_sent') or
                   e.get('phase') == 'result' and str(e.get('command','')).startswith('go ')
                   for e in events)
        verified = any(e.get('phase') in ('result','park_status','notice') and
                       e.get('command') == pending['command'] for e in events)
        verified = verified or any(e.get('phase') in PURCHASE_COMMITS for e in events)
        verified = verified or pending['command'] == 'list saves'
        if pending['command'].startswith('go '):
            verified = self.text.current == NAVIGATION.get(pending['command'][3:])
        if pending['command'].startswith('load park '):
            verified = self.restarted and any(e.get('phase') == 'result' and e.get('command') == 'load park' for e in events)
        park_context = {'advance time': 'park', 'go park': 'park-entry'}
        kinds = {'quarter_popup': 'quarter-notice', 'parking_hint': 'parking-notice'}
        notices = {e['notices'][0] for e in events if e.get('phase') == 'interrupted' and
                   e.get('command') == pending['command'] and len(e.get('notices', [])) == 1 and
                   e['notices'][0] in kinds and e.get('run', {}).get('outcome') == 'guest_time'}
        park_pause = not uncertain and pending['command'] in park_context and len(notices) == 1
        if park_pause:
            observed = self.observe()
            expected = park_context[pending['command']] + '.' + kinds[next(iter(notices))]
            park_pause = (observed.get('complete') is True and
                          observed.get('context', {}).get('id') == expected)
        food_pause = (not uncertain and pending['command'] == 'buy 20 small feeders' and any(
            e.get('phase') == 'interrupted' and e.get('command') == pending['command'] and
            e.get('notices') == ['parking_hint'] and e.get('food_order_submitted') is False and
            e.get('run', {}).get('outcome') == 'guest_time' for e in events))
        if food_pause:
            observed = self.observe()
            food_pause = (observed.get('complete') is True and
                          observed.get('context', {}).get('id') == 'dino_diner.parking-notice')
        food_return = (not uncertain and pending['command'] == 'buy 20 small feeders' and
                       any(e.get('phase') == 'food_return_interrupted' and
                           e.get('purchase_outcome') == 'confirmed' for e in events))
        if food_return:
            observed = self.observe()
            food_return = (observed.get('complete') is True and observed.get('context', {}).get('id') in
                           ('food-return.quarter-notice', 'food-return.parking-notice'))
        if park_pause or food_pause or food_return:
            status = 'accepted'
        elif uncertain or (refusal or text_refusal) and sent or not verified and not (refusal or text_refusal):
            status = 'incomplete'
        else:
            status = 'rejected' if refusal or text_refusal else 'success'
        effects = ('applied-confirmed' if food_return else
                   'partial' if park_pause or food_pause or (refusal or text_refusal) and sent else
                   'none-confirmed' if status == 'rejected' or pending['command'] in ('status','list saves') else
                   'unknown' if status == 'incomplete' else 'applied-confirmed')
        extra = {}
        if food_return:
            extra['followup'] = 'pending'
        if park_pause or food_pause or food_return:
            extra['continuation'] = {'context': observed['context']['id'], 'command': 'acknowledge notice',
                                     'original_intent': pending['command']}
        previous_session = pending.get('session_token', self.session_token)
        if previous_session != self.session_token and status == 'success' and pending['command'].startswith('load park '):
            extra['session_transition'] = {'from': previous_session, 'to': self.session_token, 'reason': 'native-load'}
        if status != 'incomplete':
            observed = self.observe()
            witness = self.witness(observed)
            if witness is not None:
                extra['witness'] = witness
            elif pending['command'] == 'buy coelophysis' and not (refusal or text_refusal):
                self.pending = pending
                if self.action_error(RuntimeError('Coelophysis following observation incomplete')):
                    return
                raise RuntimeError('Original purchase follow-up is unavailable')
        self.send({'status':status, 'complete':status != 'incomplete',
                   'message':self.public_message(messages or 'No verified completion was recorded.'),
                   'effects':effects, **extra})
        self._end_action_budget()

    def _start_action_budget(self):
        from .dinopark_purchase import PurchaseBudget
        self._end_action_budget()
        scope = PurchaseBudget().bind(self.text.debug)
        scope.__enter__()
        self._action_budget_scope = scope

    def _end_action_budget(self):
        scope, self._action_budget_scope = self._action_budget_scope, None
        if scope is not None:
            scope.__exit__(None, None, None)

    def checkpoint(self, request):
        op = request['op']; name = request.get('slot' if op == 'save' else 'checkpoint', 'live')
        if not isinstance(name,str) or not 1 <= len(name) <= 64:
            return {'complete':False,'status':'incomplete'}
        try:
            if op == 'save':
                if self.terminal is not None and self.terminal.phase != 'live':
                    raise ValueError('Live checkpoints require a qualified park scene')
                if self.checkpoint_failed or self.recovery_required:
                    raise ValueError('Prior checkpoint restore incomplete')
                if len(self.snapshots) >= 64 and name not in self.snapshots:
                    raise ValueError('Snapshot slot budget')
                observation = self.observe()
                if observation.get('complete') is not True:
                    raise ValueError('Checkpoint requires a qualified scene')
                fields = load_scenes().live_saved_fields(self.text.debug)
                state = self.text.debug.save_state('z-'+secrets.token_hex(8)+'.sav')
                self.snapshots[name] = {'artifact':state['artifact'],
                    'text':{k:deepcopy(getattr(self.text,k)) for k in SNAPSHOT_FIELDS},
                    'fields':fields, 'context':observation['context']['id'], 'session_token':self.session_token,
                    'latest_native_save':self.latest_native_save}
                self.event({'phase':'checkpoint_saved', 'checkpoint':name,
                            'context':observation['context']['id'], 'field_count':len(fields)})
                result = 'saved'
            elif name not in self.snapshots:
                result = 'missing'
            else:
                snapshot = self.snapshots[name]
                if snapshot['session_token'] != self.session_token:
                    raise ValueError('Checkpoint belongs to another original guest')
                self.checkpoint_failed = True
                self.revision += 1
                self.text.debug.load_state(snapshot['artifact'])
                if self.terminal is not None:
                    self.terminal.reset_after_restore()
                for key,value in snapshot['text'].items(): setattr(self.text,key,deepcopy(value))
                self.latest_native_save = snapshot['latest_native_save']
                restored_fields = load_scenes().live_saved_fields(self.text.debug)
                if restored_fields != snapshot['fields']:
                    raise ValueError('Restored native fields differ before presentation preparation')
                # state.load deliberately invalidates the framebuffer. Advance
                # original execution without mouse/keyboard input, then qualify
                # a completed frame and the restored public scene.
                prepared_ms = 0
                for _ in range(12):
                    load_scenes().run_guest(self.text.debug, 100)
                    prepared_ms += 100
                    observation = self.observe(recovering=True)
                    if observation.get('complete') is True and observation['context']['id'] == snapshot['context']:
                        break
                else:
                    raise ValueError('Restored scene did not requalify')
                self.checkpoint_failed = False
                self.recovery_required = False
                self.held_action = None
                for failure in self.failures:
                    if failure.get('restored_by') is None:
                        failure['restored_by'] = name
                self.event({'phase':'checkpoint_restored', 'checkpoint':name, 'native_fields_equal':True,
                            'saved_fields':snapshot['fields'], 'restored_fields':restored_fields,
                            'field_count':len(snapshot['fields']), 'preparation_guest_ms':prepared_ms,
                            'context':observation['context']['id'], 'following_input':'not_sent'})
                result = 'restored'
            self.receipt('checkpoint-' + result)
            reply = {'complete':True,'status':result,'checkpoint':name,'replay_safe':result in ('saved', 'restored'),
                     'persistence':'owned live-session snapshot; mounted files must remain unchanged; not a native park disk save'}
            if result == 'restored':
                witness = self.witness(observation)
                if witness is not None:
                    reply['witness'] = witness
            return reply
        except Exception as error:
            self.event({'phase':'checkpoint_incomplete', 'operation':op, 'error_type':type(error).__name__, 'error':str(error)})
            self.receipt('checkpoint-incomplete')
            return {'complete':False,'status':'incomplete','message':'Checkpoint unavailable; inspect private evidence.'}

    def command(self):
        if self.pending is not None and not self.reply_pending:
            self.finish()
        while True:
            line = self.reader.readline(65537)
            if not line: raise EOFError
            if not line.endswith('\n') or len(line.encode('utf-8')) > 65536:
                raise ValueError('Invalid Z request size')
            try:
                request = json.loads(line)
                if not isinstance(request,dict): raise ValueError('Expected request')
                op = request.get('op')
                if op in ('reply_status', 'read_reply', 'select_reply', 'accept_reply'):
                    try:
                        self.send(self.reply_command(request))
                    except (OSError, ValueError, KeyError):
                        self.send({'complete': False, 'status': 'unresolved', 'delivery_pending': self.reply_pending,
                                   'retry_safe': False, 'message': 'Reply unavailable or invalid; no input sent.'})
                    continue
                if self.reply_pending:
                    try: self.send(self.replies.status())
                    except (OSError, ValueError, KeyError):
                        self.send({'complete': False, 'status': 'reply-unavailable', 'delivery_pending': True, 'retry_safe': False})
                    continue
                if op == 'observe' and set(request) == {'op'}:
                    self.send(self.observe()); continue
                if op == 'reconcile' and set(request) <= {'op','recovery_id'}:
                    ident = request.get('recovery_id')
                    if ident is not None and (not isinstance(ident,str) or not 1 <= len(ident) <= 128):
                        raise ValueError('Invalid recovery identity')
                    self.send(self.reconcile(ident)); continue
                if op in ('save','load') and set(request) <= {'op','slot' if op == 'save' else 'checkpoint'}:
                    self.send(self.checkpoint(request)); continue
                if op != 'act' or set(request) != {'op','action'}:
                    raise ValueError('Unsupported request')
                candidate = request.get('action')
                continuing = (isinstance(candidate,dict) and candidate.get('verb') == 'continue' and
                              candidate.get('target') == 'dinosaur-order' and self._reconcilable_purchase())
                if (self.recovery_required or self.checkpoint_failed) and not continuing:
                    self.send({'complete':True,'status':'rejected','effects':'none-confirmed',
                               'recovery_required':True,
                               'message':'Reconciliation or checkpoint recovery is required; no action input was sent.'});continue
                action = request['action']
                if (not isinstance(action,dict) or set(action) != {'verb','target','item','context_token'}
                        or not all(isinstance(action[k],str) for k in ('verb','target','context_token')) or action['item'] is not None):
                    raise ValueError('Invalid action')
                bounded_purchase = action['verb'] == 'buy' and action['target'] == 'coelophysis' or continuing
                if bounded_purchase:
                    self._start_action_budget()
                observation = self.observe()
                if not observation['complete']:
                    self._end_action_budget()
                    self.send({'complete':bounded_purchase,
                               'status':'rejected' if bounded_purchase else 'incomplete',
                               'effects':'none-confirmed' if bounded_purchase else 'unknown',
                               'message':'Original scene observation incomplete; no input sent.'});continue
                if action['context_token'] != observation['context']['token']:
                    self._end_action_budget()
                    self.send({'complete':True,'status':'rejected','message':'Context changed; no input sent.'});continue
                visible = {o['id'] for o in observation['objects'] + observation['inventory']}
                _,bindings = self.objects()
                command = bindings.get((action['verb'],action['target'])) if action['target'] in visible else None
                if command is None:
                    self._end_action_budget()
                    self.send({'complete':True,'status':'rejected','message':'Action unavailable; no input sent.'});continue
                self.pending = {'command':command,'messages':[],'events':[],
                                'session_token':self.session_token,'action':deepcopy(action)}
                self.restarted = False
                self.receipt('acting')
                if command.startswith('terminal:'):
                    self.terminal_command(command.removeprefix('terminal:'))
                    continue
                return command
            except (ValueError,TypeError,KeyError):
                self._end_action_budget()
                self.send({'complete':False,'status':'incomplete','message':'Invalid Z request; no input sent.'})

    def terminal_command(self, action):
        from .dinopark_terminal import TerminalScenes
        try:
            if self.terminal is None:
                self.terminal = TerminalScenes(self.text)
            result = self.terminal.perform(action)
            self.revision += 1
            if result.get('complete'):
                observed = self.observe()
                witness = self.witness(observed)
                if witness is None:
                    raise RuntimeError('Terminal result observation incomplete; outcome unknown')
                result['witness'] = witness
            if self.terminal.phase in ('live','menu','confirm','save'):
                self.oracle('terminal-complete')
            self.pending = None
            self.receipt('terminal-' + self.terminal.phase)
            self.send(result)
        except Exception as error:
            # Delivery failures after pending was cleared must never rerun the
            # input or be turned into a second producer result.
            if self.pending is None:
                raise
            if not self.action_error(error):
                command = self.pending['command']
                self.pending = None
                self.recovery_required = True
                self.failures.append({'command':command,'effects':'unknown',
                                      'diagnostic':'terminal action failure','restored_by':None})
                self.receipt('recovery-required')
                self.send({'complete':False,'status':'incomplete','effects':'unknown',
                           'recovery_required':True,'message':'Terminal outcome unknown; no input will be replayed.'})

    def action_error(self, error):
        """Keep only a reachable, paused native guest for explicit recovery."""
        self._end_action_budget()
        if self.pending is None:
            return False
        try:
            if self.pending['command'] in ('buy coelophysis', 'continue dinosaur order'):
                from .dinopark_purchase import recovery_budget
                with recovery_budget(self.text):
                    if self.text.debug.call('session.status').get('state') != 'stopped':
                        return False
            elif self.text.debug.call('session.status').get('state') != 'stopped':
                return False
        except Exception:
            return False
        self.recovery_required = True
        self.revision += 1
        self.failure(error, recoverable=True)
        return True

    def failure(self, error, *, recoverable=False):
        if self.pending is None:
            self.send({'complete':False,'status':'stopped','message':'Original-backed service stopped; inspect private evidence.'})
            return
        root = (self.held_action if self.pending['command'] == 'continue dinosaur order' else None)
        confirmed = [e for e in self.pending['events'] if e.get('phase') in PURCHASE_COMMITS]
        effects = 'applied-confirmed' if confirmed else root['effects'] if root else 'unknown'
        message = ('The purchase is confirmed; its follow-up failed. Do not repeat the purchase.' if effects == 'applied-confirmed' else
                   'The original action did not reach a verified outcome. Do not retry blindly.')
        if recoverable:
            message += ' The provider is retained for reconciliation or checkpoint recovery; further action input is blocked.'
            if self.pending['command'] in ('buy coelophysis','continue dinosaur order'):
                message += ' Use look for the guarded order continuation, or reconcile to check completion; do not repeat the purchase.'
        path = self.work/('z-failure.json' if not self.failures else f'z-failure-{len(self.failures)+1:03d}.json')
        load_scenes().atomic_json(path, {'error_type':type(error).__name__, 'error':str(error),
            'pending':self.pending,'confirmed_effects':confirmed,'recovery_required':recoverable})
        index = len(self.failures)
        self.failures.append({'command':self.pending['command'],'effects':effects,
                              'diagnostic':path.name,'restored_by':None})
        if recoverable:
            scene_failure = getattr(error,'result',{})
            if root is not None:
                root.update(effects=effects, dinosaur_order=deepcopy(self.text.dinosaur_order),
                            last_failure_index=index)
                self.held_action = root
            else:
                self.held_action = {'id':secrets.token_hex(16),'pending':deepcopy(self.pending),'effects':effects,
                    'session_token':self.session_token,'source':getattr(self.text,'current',None),
                    'scene_failure':deepcopy(scene_failure) if isinstance(scene_failure,dict) else {},
                    'dinosaur_order':deepcopy(getattr(self.text,'dinosaur_order',None)),
                    'failure_index':index}
            self.pending = None  # Exactly one reply; the next read must not finish it again.
            self.receipt('recovery-required')
        self.send({'complete':False,'status':'incomplete','message':message,
                   'effects':effects,'followup':'failed','recovery_required':recoverable,
                   'recovery_id':self.held_action['id'] if recoverable else None})

    def stop(self, signum, _frame=None):
        self._end_action_budget()
        self.stop_reason=signal.Signals(signum).name
        # Prevent a second termination signal from interrupting receipt finalization.
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        self.receipt('interrupted')
        for process in self.processes:
            if process.poll() is None:
                try: process.terminate()
                except OSError: pass
        raise load_scenes().SceneInterrupted(self.stop_reason)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,required=True)
    parser.add_argument('--backend',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--load-save',type=Path)
    parser.add_argument('--slot',default='zpark')
    parser.add_argument('--oracle',action='store_true',help='write private raw native readback for independent tests')
    args = parser.parse_args(argv)
    work = args.work_dir.resolve(); source=args.game_dir.resolve(strict=True)
    scenes = load_scenes(); scenes.save_name(args.slot)
    if work.exists() or work == source or work.is_relative_to(source) or source.is_relative_to(work) or any((p/'.git').exists() for p in (work,*work.parents)):
        parser.error('Work directory must be new, private and outside the source/Git')
    work.mkdir(parents=True,mode=0o700)
    service = ZService(work,sys.stdin,sys.stdout,slot=args.slot,oracle=args.oracle)
    signal.signal(signal.SIGTERM,service.stop)
    signal.signal(signal.SIGINT,service.stop)
    status='failed'
    service.receipt('starting')
    try:
        game = build_game(source,work)
        # Import only the selected native bundle into this owned library. Keep
        # the original bundle unchanged and make later public loads usable.
        selected_save = None
        if args.load_save:
            original = args.load_save.resolve(strict=True)
            scenes.read_save_bundle(original, scenes.inventory(game))
            try:
                selected_name = scenes.save_name(original.name)
            except ValueError:
                selected_name = args.slot
            selected_save = work/'saves'/selected_name
            selected_save.mkdir(parents=True)
            for name in ('save.json', 'DINOSG.000'):
                shutil.copyfile(original/name, selected_save/name)
            scenes.read_save_bundle(selected_save, scenes.inventory(game))
            service.latest_native_save = selected_name
        next_args = ['--game-dir',str(game),'--backend',str(args.backend.resolve()),
                     '--work-dir',str(work/'native'),'--save-library',str(work/'saves')]
        if selected_save: next_args += ['--load-save',str(selected_save)]
        while next_args is not None:
            next_args = scenes.run_session(next_args,command_reader=service.command,output=service.output,
                        on_ready=service.ready,on_event=service.event,on_spawn=service.spawned,
                        on_action_error=service.action_error,
                        recovery_required=lambda:service.recovery_required or service.checkpoint_failed)
        status='recovery-required' if service.recovery_required or service.checkpoint_failed or service.reply_pending else 'completed'
        return 0 if status == 'completed' else 1
    except scenes.SceneInterrupted:
        status='interrupted'
        return 130 if service.stop_reason=='SIGINT' else 143
    except Exception as error:
        (work/'z-service-error.log').write_text(traceback.format_exc())
        service.failure(error)
        return 1
    finally:
        for process in service.processes:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=.5)
                except Exception:
                    process.kill()
                    try: process.wait(timeout=.5)
                    except Exception: pass
        service.receipt(status, complete=status=='completed' and all(p.poll() is not None for p in service.processes))


if __name__ == '__main__':
    raise SystemExit(main())
