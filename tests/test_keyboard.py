"""Guest controller input contracts, including real BIOS consumption."""
import pytest

from fdisbull.debug_script import validate_script
from fdisbull.project import Project
from test_debugger import emulator
from test_dos_loader import mz_file
from fdisbull.keyboard_input import validate_keyboard


@pytest.mark.parametrize('options',[
    {'text':''},{'text':'x'*65},{'text':'nul\0'}, {'text':'\u00e9'},
    {'key':'ENTER'}, {'key':'made-up'}, {'key':'enter','hold_ms':True},
    {'key':'enter','gap_ms':0},{'key':'enter','modifiers':['ctrl','ctrl']},
    {'key':'shift','modifiers':['shift']},{'key':'enter','modifiers':'ctrl'},
])
def test_keyboard_validation(options):
    with pytest.raises(ValueError):validate_keyboard(**options)


def test_keyboard_script_rejects_bad_later_input_before_execution():
    script={'format':'fdisbull-script-1','steps':[
        {'op':'keyboard.press','key':'enter'},
        {'op':'keyboard.type','text':'name\u2603'}]}
    with pytest.raises(ValueError,match='ASCII'):
        validate_script(script)
    validate_script({'format':'fdisbull-script-1','steps':[
        {'op':'keyboard.press','key':'left','modifiers':['ctrl']},
        {'op':'keyboard.type','text':'Agent 16!'}]})


@pytest.fixture
def keyboard_game(tmp_path):
    # Read BIOS ASCII/scan-code pairs until Enter; keep results at DS:0100.
    # push cs; pop ds; push cs; pop es; mov di,0100; xor ah,ah; int16; stosw;
    # cmp al,0d; jne read; jmp $ (stop at offset 10h).
    binary=tmp_path/'KEYS.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('0e1f0e07bf000130e4cd16ab3c0d75f7ebfe')+bytes(1024),ss=0,sp=0x400))
    path=tmp_path/'keys.fdb'
    with Project.create(path,binary) as db:
        db.analyze(max_instructions=20)
    return path,binary


def test_real_keyboard_press_type_script_and_restore(keyboard_game,emulator,tmp_path):
    path,binary=keyboard_game
    with Project(path) as db, db.debugger(emulator,binary.parent) as debug:
        checkpoint=debug.save_state('before-input.sav')
        bp=debug.breakpoint('1000:0010')
        result=debug.keyboard.type('Az 19!?',hold_ms=20,gap_ms=20)
        assert result['accepted'] and result['delivery']=='queued'
        with pytest.raises(ValueError,match='keyboard'):
            debug.save_state('pending.sav')
        with pytest.raises(Exception,match='pending keyboard'):
            debug.call('state.save',{'path':str(tmp_path/'pending-native.sav')})
        assert not (tmp_path/'pending-native.sav').exists()
        with pytest.raises(Exception,match='pending'):
            debug.keyboard.press('enter')
        debug.run(guest_ms=1200,timeout_ms=5000,fast_forward=True)
        assert debug.keyboard.state()['keyboard']==dict(pending_events=0,owned_keys=0,queued_guest_ms=0)
        script={'format':'fdisbull-script-1','steps':[
            {'op':'keyboard.press','key':'backspace'},
            {'op':'run','guest_ms':200,'timeout_ms':3000},
            {'op':'keyboard.press','key':'enter'},
            {'op':'run','timeout_ms':3000,'expect':'breakpoint'},
            {'op':'screenshot','name':'keyboard.png'}]}
        report=debug.script(script)
        assert report['ok'],report
        data=debug.memory('1000:0100',length=18)['hex']
        assert bytes.fromhex(data)[::2]==b'Az 19!?\x08\r'
        # Finish Enter's release before saving, even though the BP stopped us.
        debug.delete_breakpoint(bp['breakpoint_id'])
        debug.run(guest_ms=150,timeout_ms=3000,fast_forward=True)
        debug.save_state('completed.sav')
        debug.load_state(checkpoint['artifact'])
        assert debug.keyboard.state()['keyboard']['pending_events']==0
        bp=debug.breakpoint('1000:0010')
        report=debug.script({'format':'fdisbull-script-1','steps':[
            {'op':'keyboard.type','text':'Restored\n'},
            {'op':'run','timeout_ms':5000,'expect':'breakpoint'}]})
        assert report['ok'],report
        assert bytes.fromhex(debug.memory('1000:0100',length=18)['hex'])[::2]==b'Restored\r'
        debug.project.debug_export(report['artifact'],tmp_path/'keyboard-script.json')
        assert (tmp_path/'keyboard-script.json').is_file()


def test_real_keyboard_chords_atomic_rejection_and_pending_restore(keyboard_game,emulator):
    path,binary=keyboard_game
    with Project(path) as db, db.debugger(emulator,binary.parent) as debug:
        checkpoint=debug.save_state('clean.sav')
        with pytest.raises(Exception,match='ASCII'):
            debug.call('input.keyboard.type',{'text':'valid\u2603'})
        assert debug.keyboard.state()['keyboard']['pending_events']==0
        debug.keyboard.press('shift',hold_ms=1000)
        debug.run(guest_ms=10,timeout_ms=3000,fast_forward=True)
        assert debug.keyboard.state()['keyboard']['owned_keys']==1
        debug.load_state(checkpoint['artifact'])
        assert debug.keyboard.state()['keyboard']['pending_events']==0
        debug.keyboard.press('a',modifiers=['shift'])
        debug.run(guest_ms=200,timeout_ms=3000,fast_forward=True)
        debug.keyboard.press('left')
        debug.run(guest_ms=200,timeout_ms=3000,fast_forward=True)
        debug.keyboard.press('f1')
        debug.run(guest_ms=200,timeout_ms=3000,fast_forward=True)
        assert debug.memory('1000:0100',length=6)['hex']=='411e004b003b'
        assert debug.keyboard.state()['keyboard']['owned_keys']==0


def test_real_keyboard_mid_dialog_checkpoint_restore(keyboard_game,emulator):
    path,binary=keyboard_game
    with Project(path) as db, db.debugger(emulator,binary.parent) as debug:
        wait=debug.breakpoint('1000:0009')
        assert debug.run(timeout_ms=5000,fast_forward=True)['outcome']=='breakpoint'
        debug.delete_breakpoint(wait['breakpoint_id'])
        debug.run(guest_ms=20,timeout_ms=3000,fast_forward=True)
        checkpoint=debug.save_state('waiting-for-name.sav')

        end=debug.breakpoint('1000:0010')
        debug.keyboard.type('TIGA16\n')
        assert debug.run(timeout_ms=5000,fast_forward=True)['outcome']=='breakpoint'
        assert bytes.fromhex(debug.memory('1000:0100',length=14)['hex'])[::2]==b'TIGA16\r'
        debug.delete_breakpoint(end['breakpoint_id'])

        restored=debug.load_state(checkpoint['artifact'])
        assert restored['framebuffer']=='invalidated_until_next_completed_frame'
        assert debug.keyboard.state()['keyboard']==dict(
            pending_events=0,owned_keys=0,queued_guest_ms=0)
        debug.run(guest_ms=50,timeout_ms=3000,fast_forward=True)
        assert debug.screenshot('restored-dialog.png')['artifact']

        end=debug.breakpoint('1000:0010')
        debug.keyboard.type('TIGA16\n')
        assert debug.run(timeout_ms=5000,fast_forward=True)['outcome']=='breakpoint'
        assert bytes.fromhex(debug.memory('1000:0100',length=14)['hex'])[::2]==b'TIGA16\r'
