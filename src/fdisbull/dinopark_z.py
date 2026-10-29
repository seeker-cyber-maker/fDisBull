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
SNAPSHOT_FIELDS = ('office', 'bank', 'street', 'mart', 'park', 'locations', 'current',
                   'land_bought', 'dinosaur_bought', 'fence_bought', 'guide_hired',
                   'food_bought', 'park_opened', 'notice_outcome_unknown', 'transaction_count',
                   'pending_park_entry',
                   'vegasaurus_attempted', 'vegasaurus_proof', 'vegasaurus_extinct', 'last_action')


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
        self.epoch = secrets.token_hex(32)
        self.revision = 0
        self.pending = None
        self.snapshots = {}
        self.latest_native_save = None
        self.processes = []
        self.history = []
        self.restarted = False
        self.oracle_enabled, self.oracle_count = oracle, 0
        self.stop_reason = None

    def receipt(self, status, *, complete=False):
        from fdisbull.dinopark_scenes import atomic_json
        processes=[{'pid':p.pid,'returncode':p.poll()} for p in self.processes]
        atomic_json(self.work/'z-session.json',{
            'status':status, 'complete':complete, 'stop_reason':self.stop_reason,
            'history':self.history, 'pending_command':self.pending['command'] if self.pending else None,
            'latest_native_save':self.latest_native_save,
            'pending_effects':('applied-confirmed' if self.pending and any(e.get('phase') in
                ('food_purchase_committed','vegasaurus_purchase_confirmed') for e in self.pending['events'])
                else 'unknown' if self.pending else 'none-pending'),
            'processes':processes, 'cleanup_complete':all(p['returncode'] is not None for p in processes),
            'scope':'original-backed UDC with existing native scene actions'})

    def event(self, item):
        self.history.append(deepcopy(item))
        if item.get('phase') == 'result' and item.get('command', '').startswith('save park '):
            self.latest_native_save = item['command'].removeprefix('save park ')
        if self.pending is not None:
            self.pending['events'].append(deepcopy(item))
        if item.get('phase') in ('food_purchase_committed','vegasaurus_purchase_confirmed'):
            self.receipt('acting')
            self.oracle(item['phase'])

    def ready(self, text):
        self.text = text
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

    def send(self, result):
        data = json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n'
        if len(data.encode()) > LIMIT:
            data = '{"complete":false,"status":"incomplete","message":"Response exceeds the Z budget; inspect private evidence."}\n'
        with (self.work/'z-protocol.jsonl').open('a',encoding='utf-8') as journal:
            journal.write(data)
        self.writer.write(data); self.writer.flush()

    def public_message(self, text):
        # Legacy saved-park responses include local evidence paths. Keep them private.
        import re
        text = re.sub(r'Commands:[^\n]*', '', text)
        text = re.sub(r'/(?:Users|Volumes|private|var|tmp|home|workspace)/\S+', '[private evidence]', text)
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

    def observe(self):
        try:
            modal = False
            try:
                description = self.text.describe().split('Commands:')[0].strip()
            except Exception:
                # A known modal is itself an observable context. Do not require
                # the obscured background scene before offering its handler.
                scenes = load_scenes()
                entering = getattr(self.text, 'pending_park_entry', False) and self.text.current == 'street'
                if (self.text.current != 'park' and not entering or
                        not self.text.park_opened or self.text.notice_outcome_unknown):
                    raise
                _,image = scenes.take_frame(self.text.project,self.text.debug,'z-modal-observation')
                if (not scenes.matches(image,self.text.patterns['quarter_popup']) or
                        scenes.matches(image,self.text.patterns['parking_hint'])):
                    raise ValueError('Unqualified modal')
                modal = True
                description = 'A recognized quarter notice is visible. Acknowledge it to continue.'
            registers = self.text.debug.registers()
            context = ('park-entry.quarter-notice' if modal and getattr(self.text, 'pending_park_entry', False)
                       else self.text.current + ('.quarter-notice' if modal else ''))
            opaque = [self.epoch, self.revision, context, description,
                      registers.get('state_revision'), getattr(self.text.debug, '_runtime_epoch', None)]
            token = hashlib.sha256(json.dumps(opaque, sort_keys=True).encode()).hexdigest()
            objects,_ = self.objects()
            if modal: objects = [o for o in objects if o['id'] == 'notice']
            return {'complete':True, 'context':{'id':context, 'token':token,
                    'title':'Quarter notice' if modal else TITLES[self.text.current], 'description':description},
                    'objects':objects, 'inventory':[], 'coverage':{'partial':True}}
        except Exception:
            return {'complete':False}

    def finish(self):
        self.oracle('command-complete')
        pending, self.pending = self.pending, None
        self.revision += 1
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
        verified = verified or any(e.get('phase') in ('food_purchase_committed','vegasaurus_purchase_confirmed') for e in events)
        verified = verified or pending['command'] == 'list saves'
        if pending['command'].startswith('go '):
            verified = self.text.current == NAVIGATION.get(pending['command'][3:])
        if pending['command'].startswith('load park '):
            verified = self.restarted and any(e.get('phase') == 'result' and e.get('command') == 'load park' for e in events)
        quarter_context = {'advance time': 'park.quarter-notice', 'go park': 'park-entry.quarter-notice'}
        quarter_pause = (not uncertain and pending['command'] in quarter_context and any(
            e.get('phase') == 'interrupted' and e.get('command') == pending['command'] and
            e.get('notices') == ['quarter_popup'] and e.get('run', {}).get('outcome') == 'guest_time'
            for e in events))
        if quarter_pause:
            observed = self.observe()
            quarter_pause = (observed.get('complete') is True and
                             observed.get('context', {}).get('id') == quarter_context[pending['command']])
        if quarter_pause:
            status = 'accepted'
        elif uncertain or (refusal or text_refusal) and sent or not verified and not (refusal or text_refusal):
            status = 'incomplete'
        else:
            status = 'rejected' if refusal or text_refusal else 'success'
        effects = ('partial' if quarter_pause or (refusal or text_refusal) and sent else
                   'none-confirmed' if status == 'rejected' or pending['command'] in ('status','list saves') else
                   'unknown' if status == 'incomplete' else 'applied-confirmed')
        self.send({'status':status, 'complete':status != 'incomplete',
                   'message':self.public_message(messages or 'No verified completion was recorded.'),
                   'effects':effects})

    def checkpoint(self, request):
        op = request['op']; name = request.get('slot' if op == 'save' else 'checkpoint', 'live')
        if not isinstance(name,str) or not 1 <= len(name) <= 64:
            return {'complete':False,'status':'incomplete'}
        try:
            if op == 'save':
                if len(self.snapshots) >= 64 and name not in self.snapshots:
                    raise ValueError('Snapshot slot budget')
                state = self.text.debug.save_state('z-'+secrets.token_hex(8)+'.sav')
                self.snapshots[name] = {'artifact':state['artifact'],
                    'text':{k:deepcopy(getattr(self.text,k)) for k in SNAPSHOT_FIELDS}}
                result = 'saved'
            elif name not in self.snapshots:
                result = 'missing'
            else:
                snapshot = self.snapshots[name]
                self.text.debug.load_state(snapshot['artifact'])
                for key,value in snapshot['text'].items(): setattr(self.text,key,deepcopy(value))
                self.revision += 1; result = 'restored'
            return {'complete':True,'status':result,'checkpoint':name,'persistence':'owned live-session snapshot; not a native park disk save'}
        except Exception:
            return {'complete':False,'status':'incomplete','message':'Checkpoint unavailable; inspect private evidence.'}

    def command(self):
        if self.pending is not None:
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
                if op == 'observe' and set(request) == {'op'}:
                    self.send(self.observe()); continue
                if op in ('save','load') and set(request) <= {'op','slot' if op == 'save' else 'checkpoint'}:
                    self.send(self.checkpoint(request)); continue
                if op != 'act' or set(request) != {'op','action'}:
                    raise ValueError('Unsupported request')
                action = request['action']
                if (not isinstance(action,dict) or set(action) != {'verb','target','item','context_token'}
                        or not all(isinstance(action[k],str) for k in ('verb','target','context_token')) or action['item'] is not None):
                    raise ValueError('Invalid action')
                observation = self.observe()
                if not observation['complete']:
                    self.send({'complete':False,'status':'incomplete','message':'Original scene observation incomplete.'});continue
                if action['context_token'] != observation['context']['token']:
                    self.send({'complete':True,'status':'rejected','message':'Context changed; no input sent.'});continue
                visible = {o['id'] for o in observation['objects'] + observation['inventory']}
                _,bindings = self.objects()
                command = bindings.get((action['verb'],action['target'])) if action['target'] in visible else None
                if command is None:
                    self.send({'complete':True,'status':'rejected','message':'Action unavailable; no input sent.'});continue
                self.pending = {'command':command,'messages':[],'events':[]}
                self.restarted = False
                self.receipt('acting')
                return command
            except (ValueError,TypeError,KeyError):
                self.send({'complete':False,'status':'incomplete','message':'Invalid Z request; no input sent.'})

    def failure(self, error):
        if self.pending is None:
            self.send({'complete':False,'status':'stopped','message':'Original-backed service stopped; inspect private evidence.'})
            return
        confirmed = [e for e in self.pending['events'] if e.get('phase') in
                     ('food_purchase_committed','vegasaurus_purchase_confirmed')]
        message = ('The purchase is confirmed; its follow-up failed. Do not repeat the purchase.' if confirmed else
                   'The original action did not reach a verified outcome. Do not retry blindly.')
        self.send({'complete':False,'status':'incomplete','message':message,
                   'effects':'applied-confirmed' if confirmed else 'unknown','followup':'failed'})
        (self.work/'z-failure.json').write_text(json.dumps({'error_type':type(error).__name__,
            'error':str(error),'pending':self.pending,'confirmed_effects':confirmed},indent=2,default=str)+'\n')

    def stop(self, signum, _frame=None):
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
                        on_ready=service.ready,on_event=service.event,on_spawn=service.spawned)
        status='completed'
        return 0
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
