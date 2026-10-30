"""Named terminal scenes over unchanged original DinoPark game code.

A scene change, park departure, and DOS process termination are separate
postconditions. Waiting never repeats a key or mouse-button action.
"""
from copy import deepcopy
import json
from pathlib import Path

from .dinopark_scenes import EXPECTED_EXE, matches, take_frame

PROFILES = Path(__file__).with_name('data') / 'dinopark-e55-terminal.json'
PATTERNS = json.loads(PROFILES.read_text())['scenes']
DESCRIPTIONS = {
    'menu': ('Game menu', 'A menu covers the office. Music and sound controls sit beside Load Game, Save Game and Quit Game. Resume your park or request to quit.'),
    'confirm': ('Quit confirmation', 'The original game asks whether you are sure you want to quit this park. Confirm to reach its save question, or cancel to keep playing.'),
    'save': ('Save before quitting', 'The original game asks whether to save first. Declining leaves this park without making a new save and returns to the title menu. Native saving remains available before requesting quit.'),
    'title': ('DinoPark title menu', 'The park has been left. New Game, Old Game and Exit to DOS stand against the animated park backdrop. Exit to DOS terminates the original program.'),
    'transition': ('Terminal transition', 'The last original input has been sent. The destination is still settling. Continue this transition without repeating that input.'),
    'exited': ('DOS — DinoPark exited', 'DinoPark has terminated. The original DOS kernel confirmed this program\'s exit. There are no further game actions in this session.'),
}
ACTIONS = {
    'menu': [('park', 'park', [], 'Return to this park or request to leave it.', {'resume':'resume', 'quit':'quit'})],
    'confirm': [('quit', 'quit', [], 'Confirm the request or cancel it.', {'confirm':'confirm', 'cancel':'cancel'})],
    'save': [('save', 'save', ['saving'], 'Decline making a new save and leave the current park.', {'decline':'decline'})],
    'title': [('dos', 'DOS', ['to dos', 'dos exit'], 'Leave DinoPark and return to DOS.', {'exit':'exit'})],
    'transition': [('transition', 'transition', [], 'Continue only the input-free wait already in progress.', {'continue':'continue'})],
    'exited': [],
}


class TerminalScenes:
    def __init__(self, text):
        self.text = text
        self.phase = 'live'
        self.pending = None
        self.exit = None
        self.status = None
        self.expected_psp = None
        metadata = text.debug.metadata
        if metadata.get('source_sha256') != EXPECTED_EXE:
            raise ValueError('Terminal scenes require the qualified original executable')
        try:
            segments = metadata['entry_registers']['segments']
            ds, es = int(segments['ds'], 16), int(segments['es'], 16)
            if ds == es == metadata['runtime_load_segment'] - 0x10:
                self.expected_psp = ds
        except (KeyError, TypeError, ValueError):
            pass

    def reset_after_restore(self):
        self.phase, self.pending, self.exit, self.status = 'live', None, None, None

    def objects(self):
        objects, bindings = [], {}
        for ident, label, aliases, description, actions in ACTIONS.get(self.phase, []):
            ident = 'terminal-' + ident
            objects.append({'id':ident,'label':label,'aliases':aliases,
                            'description':description,'verbs':list(actions)})
            bindings.update({(verb,ident):'terminal:'+action for verb,action in actions.items()})
        return objects, bindings

    def _frame(self):
        return take_frame(self.text.project, self.text.debug, 'terminal-observation')

    def _classify(self, image):
        specific = [name for name,key in (('confirm','quit_confirm'),('save','quit_save'))
                    if matches(image, PATTERNS[key])]
        if len(specific) > 1:
            raise RuntimeError('Ambiguous terminal prompts; outcome unknown')
        if specific:
            return specific[0]
        # Underlying menu text may remain visible behind an unrelated dialog.
        if any(matches(image,self.text.patterns[k]) for k in ('save_dialog','load_dialog')):
            return None
        if matches(image, self.text.patterns['game_menu']):
            return 'menu'
        if (matches(image, self.text.patterns['title_menu'])
                and matches(image, PATTERNS['title_exit'])):
            return 'title'
        if matches(image, self.text.patterns['office']):
            return 'live'
        return None

    def _native_status(self):
        native = self.text.debug.call('session.status')
        if native.get('state') != 'stopped':
            raise RuntimeError('Native terminal session is not stopped; outcome unknown')
        self.status = native
        return native

    def view(self):
        if self.phase == 'exited':
            return DESCRIPTIONS[self.phase], self.status['state_revision']
        native = self._native_status()
        if self.phase == 'transition' and native['state_revision'] != self.pending['revision']:
            raise RuntimeError('Terminal continuation state changed; no input sent')
        if self.phase != 'transition':
            frame, image = self._frame()
            actual = self._classify(image)
            self.text.event({'phase':'terminal_observation','expected':self.phase,
                             'actual':actual,'frame':frame})
            if actual != self.phase:
                raise RuntimeError('Terminal context changed; no input sent')
        return DESCRIPTIONS[self.phase], native['state_revision']

    def _exit_evidence(self, run):
        session = run.get('session', {})
        stop = session.get('stop_reason', {})
        evidence = stop.get('guest_exit', {})
        try: psp = int(evidence.get('psp'),16)
        except (TypeError,ValueError): psp = None
        if (run.get('outcome') == 'guest_exit' and session.get('state') == 'exited'
                and stop.get('kind') == 'guest_exit' and self.expected_psp is not None
                and psp == self.expected_psp and evidence.get('parent_psp') is not None
                and evidence.get('resident') is False and evidence.get('requested_exit_code') == 0
                and evidence.get('source') == 'DOS_Terminate'
                and evidence.get('stage') == 'after-process-cleanup'):
            self.exit = deepcopy(evidence)
            self.status = {'session_id':session['session_id'],'state':'exited',
                           'state_revision':session['state_revision'],'last_stop':deepcopy(stop)}
            return True
        return False

    def _run(self, ms):
        run = self.text.debug.run(guest_ms=ms,timeout_ms=15000,fast_forward=True)
        self.text.event({'phase':'terminal_run','command':'terminal:'+self.pending['action'],
                         'run':run,'input':'none'})
        if run.get('outcome') == 'guest_exit':
            if 'exited' not in self.pending['expected'] or not self._exit_evidence(run):
                raise RuntimeError('Unexpected or unqualified DOS exit; outcome unknown')
            return 'exited'
        if run.get('outcome') != 'guest_time' or run.get('hook_hits'):
            raise RuntimeError('Unexpected native stop during terminal transition; outcome unknown')
        return None

    def _wait(self):
        # Each public continuation gets at most four seconds; the original
        # transition has one shared twenty-second budget across every call.
        for _ in range(5):
            if self.exit:
                destination = 'exited'
            else:
                self._native_status()
                frame,image = self._frame()
                destination = self._classify(image)
                self.text.event({'phase':'terminal_observation','command':'terminal:'+self.pending['action'],
                                 'actual':destination,'frame':frame})
            if destination in self.pending['expected']:
                action = self.pending['action']
                self.phase, self.pending = destination, None
                self.text.event({'phase':'terminal_result','command':'terminal:'+action,'destination':destination})
                return self._result(action)
            if self.pending['guest_ms'] >= 20000:
                raise RuntimeError('Terminal transition budget exhausted; outcome unknown; do not retry input')
            if _ == 4:
                break
            self.pending['guest_ms'] += 1000
            reached = self._run(1000)
            if reached == 'exited':
                self.phase, action = 'exited', self.pending['action']
                self.pending = None
                return self._result(action)
        self.phase = 'transition'
        self.pending['revision'] = self.status['state_revision']
        return {'complete':True,'status':'accepted','effects':'partial','followup':'pending',
                'message':DESCRIPTIONS['transition'][1],
                'continuation':{'context':'terminal.transition','command':'continue transition'}}

    def _result(self, action):
        partial = self.phase in ('confirm','save')
        messages = {'open':'The original game menu is open.', 'resume':'You have returned to the park office.',
                    'quit':'The original quit confirmation is visible; the park has not been left yet.',
                    'cancel':'The quit request was cancelled.',
                    'confirm':'The quit request was confirmed; choose whether to save.',
                    'decline':'The park was left without creating a new save. The title menu is visible.',
                    'exit':'The original DOS kernel confirmed DinoPark has exited.'}
        result = {'complete':True,'status':'accepted' if partial else 'success',
                  'effects':'partial' if partial else 'applied-confirmed',
                  'message':messages[action]}
        if partial:
            result['followup'] = 'pending'
        if self.phase == 'exited': result['native_exit'] = deepcopy(self.exit)
        return result

    def perform(self, action):
        allowed = {'live':('open',), 'menu':('resume','quit'), 'confirm':('cancel','confirm'),
                   'save':('decline',), 'title':('exit',), 'transition':('continue',)}
        if action not in allowed.get(self.phase, ()):
            return {'complete':True,'status':'rejected','effects':'none-confirmed','message':'That terminal action is not available here; no input sent.'}
        if action == 'continue':
            self.view()
            return self._wait()
        if action == 'exit' and (self.expected_psp is None or
                self.text.debug.rpc.capabilities.get('lifecycle',{}).get('dos_guest_exit') is not True):
            return {'complete':True,'status':'rejected','effects':'none-confirmed',
                    'message':'This backend cannot qualify the original DOS exit; no input sent.'}
        if self.phase == 'live':
            if self.text.current != 'office':
                return {'complete':True,'status':'rejected','effects':'none-confirmed','message':'Go to the office before opening its game menu; no input sent.'}
            self.text.describe()
        else:
            self.view()
        origin = self.phase
        expected = {'open':('menu',), 'resume':('live',), 'quit':('confirm',),
                    'cancel':('menu','live'), 'confirm':('save','title'),
                    'decline':('title',), 'exit':('exited',)}[action]
        if action in ('open','resume'):
            control = ('key','escape')
        else:
            point = {'quit':(189,138),'cancel':(148,106),'confirm':(175,106),
                     'decline':(148,115),'exit':(221,160)}[action]
            moved = self.text.debug.call('input.mouse.move',{'x':point[0],'y':point[1]})
            if moved.get('accepted') is not True:
                raise RuntimeError('Terminal pointer preparation failed; no button input sent')
            # Readiness preparation advances execution but never queues a button.
            self.pending = {'action':action,'expected':expected,'guest_ms':0}
            reached = self._run(1000)
            if reached:
                raise RuntimeError('Original target exited before terminal button input')
            self.pending = None
            self._native_status()
            _,image = self._frame()
            if self._classify(image) != origin:
                raise RuntimeError('Terminal prompt changed during pointer preparation; no button input sent')
            control = ('click',point)
        # Install the shared wait before crossing the native input boundary.
        self.pending = {'action':action,'expected':expected,'guest_ms':0}
        self.phase = 'transition'
        self.text.event({'phase':'terminal_input','action':action,'control':control,'delivery':'attempted'})
        if control[0] == 'key': result = self.text.debug.keyboard_press(control[1],hold_ms=80)
        else: result = self.text.debug.click(*control[1],hold_ms=80)
        if result.get('accepted') is not True or result.get('delivery') != 'queued':
            raise RuntimeError('Terminal input delivery unknown; do not retry')
        return self._wait()
