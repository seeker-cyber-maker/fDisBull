#!/usr/bin/env python3
"""Castles II original-DOS GUI smoke harness for isolated, owner-supplied copies.

This is a narrow P01/P04 *test orchestrator*, not a new game implementation.
It drives the unmodified original C2CDTOOL.EXE in DOSBox-X by actual mouse/key
input, observes actual screenshots, and checks a real .GAM file. The only
startup variation is a BAT firsttime->startagain replacement in an already
private working copy. No game bytes are included with this script.

Prerequisites: Linux Xvfb, libX11, libXtst, scrot, Pillow and a tested DOSBox-X
binary. The Xvfb DISPLAY is owned by this process. Game dir must be private.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from PIL import Image

# Verified from original game clicks, at a 640x400 game surface.
# Coordinates are *game-surface pixels*, not host desktop positions.
ACTIONS = {
    'main.reference': (95, 55), # First picture: Reference.
    'main.designs': (234, 55),  # Second picture: Designs.
    'main.game': (517, 55),       # Fourth picture: "Game" options.
    'main.tutorial': (376, 55),   # Third picture: "Game Tutorial" options.
    'main.options': (72, 226),   # Audio controls at the top menu.
    'game.play': (226, 313),      # PLAY in Game configuration.
    'game.load': (295, 313),      # LOAD in Game configuration.
    'map.opts': (603, 213),      # OPTS tab beside STOCK/ARMY/RELAT.
    'opts.save': (458, 340),     # SAVE on the options tab.
    'opts.load': (509, 340),     # LOAD on the options tab.
    'save.ok': (536, 385),       # Confirm entered DOS save basename.
    'load.ok': (536, 385),       # Confirm selected .GAM slot.
    'load.first': (475, 277),    # First save slot in load screen.
}

# Encoded non-game evidence. This fixed scoring function only distinguishes
# the maroon title surface from the dominant-green in-game map. It does NOT
# read text, identify every dialog or prove a game-state transition by itself.
MAP_RECT = (10, 75, 410, 388)
# Exact executable from owner-supplied Castles II 1.0 GOG Inno 5.6.2 package.
# Coordinates are not valid for a different edition without new qualification.
EXPECTED_EXE_SHA256 = '512efad4a4d771f6c975702cad9a688aeef10f8d81798b8c7260e37c74e87d43'


def validate_slot(text: str) -> str:
    if not re.fullmatch('[A-Z0-9]{1,8}', text):
        raise ValueError('DOS save basename must be 1..8 A-Z/0-9')
    return text



def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def green_fraction(frame: Image.Image) -> float:
    p = frame.convert('RGB').crop(MAP_RECT).resize((80, 80))
    pixels = list(p.get_flattened_data())
    return sum(g > r * 1.4 and g > b * 1.3 and g > 45 for r, g, b in pixels) / len(pixels)


@dataclass(frozen=True)
class Stage:
    name: str
    wall_seconds: float
    evidence: dict


class XTest:
    def __init__(self, display):
        self.x = ctypes.CDLL('libX11.so.6')
        self.xt = ctypes.CDLL('libXtst.so.6')
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XKeysymToKeycode.restype = ctypes.c_ubyte
        self.x.XFlush.argtypes = [ctypes.c_void_p]
        self.xt.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.xt.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.xt.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.d = self.x.XOpenDisplay(display.encode())
        if not self.d:
            raise RuntimeError(f'Cannot open X display {display}')

    def click(self, xx, yy):
        self.xt.XTestFakeMotionEvent(self.d, -1, int(xx), int(yy), 0)
        self.x.XFlush(self.d)
        time.sleep(.12)
        self.xt.XTestFakeButtonEvent(self.d, 1, 1, 0)
        self.x.XFlush(self.d)
        time.sleep(.10)
        self.xt.XTestFakeButtonEvent(self.d, 1, 0, 0)
        self.x.XFlush(self.d)
        time.sleep(.25)

    def type_ascii(self, text):
        validate_slot(text)
        # XKeysymToKeycode maps ASCII to the appropriate physical key. DOSBox's
        # recorded default layout supplies uppercase Latin letters on input.
        for ch in text.lower():
            code = self.x.XKeysymToKeycode(self.d, ord(ch))
            if not code:
                raise RuntimeError(f'Missing X keycode for {ch!r}')
            self.xt.XTestFakeKeyEvent(self.d, code, 1, 0)
            self.x.XFlush(self.d)
            time.sleep(.12)
            self.xt.XTestFakeKeyEvent(self.d, code, 0, 0)
            self.x.XFlush(self.d)
            time.sleep(.07)


class Harness:
    def __init__(self, *, game_dir: Path, backend: Path, out: Path, display=':102'):
        self.game = game_dir.resolve(strict=True)
        self.backend = backend.resolve(strict=True)
        self.out = out
        if self.out.exists() and list(self.out.iterdir()):
            raise ValueError('Output must be a new or empty private directory')
        self.out.mkdir(parents=True, exist_ok=True)
        for filename in ('C2CDTOOL.EXE', 'C2CD.BAT', 'C2CD.gog', 'C2CD.ins'):
            if not (self.game / filename).is_file():
                raise ValueError(f'Missing original runtime input {filename}')
        bat = (self.game / 'C2CD.BAT').read_bytes()
        if b'c2cdtool quickfades startagain' not in bat.splitlines()[1:4]:
            # Refuse silently changing original startup. Prepare a separate
            # working copy as documented, retaining the original installer.
            raise ValueError('Working BAT must explicitly start with startagain')
        if sha256(self.game / 'C2CDTOOL.EXE') != EXPECTED_EXE_SHA256:
            raise ValueError('Executable hash differs from admitted Castles II edition')
        if 'TRACK 02 AUDIO' not in (self.game / 'C2CD.ins').read_text():
            raise ValueError('Expected qualified two-track CUE profile')
        self.display = display
        self.env = dict(os.environ, DISPLAY=display, SDL_AUDIODRIVER='dummy')
        self.xvfb = self.dosbox = None
        self.xinput = None
        self.t0 = time.monotonic()
        self.events = []
        self.x = self.y = None
        self.known_hashes = {
            k: sha256(self.game / k)
            for k in ('C2CDTOOL.EXE', 'C2CD.BAT', 'C2CD.ins')
        }

    def event(self, event_type, **evidence):
        event = {'event':event_type, 'elapsed_s':round(time.monotonic()-self.t0, 3),**evidence}
        self.events.append(event)
        print(json.dumps(event,sort_keys=True),flush=True)

    def start_x(self):
        if self.xvfb:
            return
        self.xvfb = subprocess.Popen(['Xvfb',self.display,'-screen','0','1024x768x24','-nolisten','tcp'],
                                     stdout=(self.out/'xvfb.log').open('wb'),stderr=subprocess.STDOUT)
        time.sleep(.7)
        self.xinput=XTest(self.display)
        self.event('xvfb_started', display=self.display)

    def _get_window(self):
        text = subprocess.check_output(['xwininfo','-root','-tree'],env=self.env,text=True)
        # On an isolated X display, the only DOSBox window is ours.
        for line in text.splitlines():
            if '"DOSBox-X ' in line:
                m = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)',line)
                if m and tuple(map(int,m.groups()[:2])) == (640,417):
                    return int(m.group(3)),int(m.group(4))
        return None

    def start_game(self):
        self.start_x()
        config=self.out/'dosbox.conf'
        config.write_text('[sdl]\nfullscreen=false\noutput=surface\n'
                          '[dosbox]\nmachine=svga_s3\nmemsize=16\n'
                          '[cpu]\ncore=normal\ncycles=max\n'
                          '[render]\nscaler=none\n'
                          '[autoexec]\n@echo off\n'
                          f'mount c "{self.game}"\n'
                          f'imgmount d "{self.game/"C2CD.ins"}" -t iso -fs iso\n'
                          'c:\nc2cd\n')
        self.dosbox = subprocess.Popen([str(self.backend),'-fastlaunch','-conf',str(config)],
            env=self.env,stdin=subprocess.DEVNULL,
            stdout=(self.out/'dosbox.log').open('ab'),stderr=subprocess.STDOUT)
        self.event('original_program_launched',pid=self.dosbox.pid)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if self.dosbox.poll() is not None:
                raise RuntimeError('DOSBox exited before a controllable window appeared')
            win=self._get_window()
            if win:
                self.x,self.y=win
                frame=self.screenshot('launch-observed')
                fraction=green_fraction(frame)
                logo=frame.crop((447,328,612,387)).convert('RGB')
                menu_gold=sum(r>130 and g>90 and bb<120 and r>g*1.1
                              for r,g,bb in logo.get_flattened_data())
                # Black startup frames also have a zero green fraction.
                # Only admit the game's real visible title + menu surface.
                if fraction<.12 and menu_gold>500:
                    log=(self.out/'dosbox.log').read_text(errors='replace')
                    if 'CD-ROM image mounted to drive D' not in log:
                        time.sleep(.5)
                        continue
                    self.event('main_menu_ready',green_fraction=round(fraction,3),menu_gold_pixels=menu_gold)
                    return
            time.sleep(.5)
        raise RuntimeError('Timed out acquiring main menu and qualified CD mount')

    def screenshot(self, name):
        if self.x is None:
            raise RuntimeError('No DOSBox window has been observed')
        dst=self.out/f'{name}.png'
        # scrot auto-suffixes an existing filename instead of overwriting it.
        # Without unlinking, polling repeatedly reads a stale first black frame.
        dst.unlink(missing_ok=True)
        subprocess.check_call(['scrot','-z',str(dst)],env=self.env,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        im=Image.open(dst).convert('RGB').crop((self.x,self.y+17,self.x+640,self.y+417))
        im.save(dst)
        return im

    def click(self, name):
        if name not in ACTIONS:raise ValueError('Undefined action '+name)
        dx,dy=ACTIONS[name]
        self.xinput.click(self.x+dx,self.y+17+dy)
        self.event('action',action_name=name)

    def assert_map(self, label):
        deadline=time.monotonic()+12
        while True:
            frame=self.screenshot(label)
            ratio=green_fraction(frame)
            if ratio>=.50:
                self.event('scene_observed',label=label,green_fraction=round(ratio,3))
                return frame
            if time.monotonic()>=deadline:
                self.event('scene_observed',label=label,green_fraction=round(ratio,3))
                raise AssertionError(f'Expected in-game map, observed green ratio {ratio:.3f}')
            time.sleep(.4)

    def from_main_play(self):
        self.click('main.game')
        self.screenshot('game-configuration')
        self.click('game.play')
        self.assert_map('new-game-map')

    def save(self, slot):
        slot=validate_slot(slot.upper())
        file=self.game/(slot+'.GAM')
        if file.exists():raise ValueError('Refuse to overwrite existing user save '+str(file))
        self.click('map.opts')
        self.screenshot('in-game-opts')
        self.click('opts.save')
        self.screenshot('save-entry-blank')
        self.xinput.type_ascii(slot)
        self.screenshot('save-entry-filled')
        self.click('save.ok')
        for _ in range(15):
            if file.exists() and file.stat().st_size:
                break
            time.sleep(.2)
        if not file.is_file() or file.stat().st_size<1000:
            raise AssertionError('Original game did not produce a nonempty .GAM file')
        self.event('save_materialized',basename=file.name,bytes=file.stat().st_size,sha256=sha256(file))
        self.assert_map('after-save-map')
        return file

    def load(self, slot, from_main=False):
        slot=validate_slot(slot.upper())
        file=self.game/(slot+'.GAM')
        if not file.exists():raise ValueError('Cannot test load without pinned save')
        before=sha256(file)
        if from_main:
            self.click('main.game')
            self.screenshot('fresh-game-config')
            self.click('game.load')
        else:
            self.click('map.opts')
            self.screenshot('opts-before-load')
            self.click('opts.load')
        self.screenshot('load-choice')
        # Single-save test directory: first row is the pinned user-provided slot.
        saves=list(self.game.glob('*.GAM'))
        if len(saves)!=1 or saves[0].name.upper()!=file.name.upper():
            raise ValueError('Load selection only admitted for one .GAM file in isolated workdir')
        self.click('load.first')
        self.click('load.ok')
        self.assert_map('restored-map-fresh' if from_main else 'restored-map-in-session')
        after=sha256(file)
        if before != after:
            raise AssertionError('Saving changed during a read-only load route')
        self.event('load_accepted',basename=file.name,sha256=after,fresh_process=from_main)

    def stop_game(self):
        if self.dosbox:
            # Never claim a graceful DOS guest quit. Stop only our process after
            # the completed Save/Load acceptance, avoiding the game's quit-save
            # path which has separate known issues.
            p=self.dosbox
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)
            self.event('owned_emulator_reaped',pid=p.pid,shutdown='host-forced-no-guest-exit-claim')
            self.dosbox=None
        self.x=self.y=None

    def stop(self):
        self.stop_game()
        if self.xvfb:
            p=self.xvfb
            if p.poll() is None:p.terminate()
            p.wait(timeout=5)
            self.xvfb=None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,required=True,help='private writable clone, never a repo checkout')
    parser.add_argument('--backend',type=Path,required=True,help='exact tested DOSBox-X wrapper executable')
    parser.add_argument('--output',type=Path,required=True,help='empty private result directory')
    parser.add_argument('--display',default=':102')
    parser.add_argument('--slot',default='BENCH1')
    parser.add_argument('--plan',choices=['menu','save_load'],default='save_load')
    a=parser.parse_args()
    h=Harness(game_dir=a.game_dir,backend=a.backend,out=a.output,display=a.display)
    status='failed'
    try:
        h.start_game()
        if a.plan=='save_load':
            h.from_main_play()
            h.save(a.slot)
            h.load(a.slot)
            h.stop_game()
            h.start_game()
            h.load(a.slot,from_main=True)
        status='passed'
    except Exception as e:
        h.event('failure',type=type(e).__name__,message=str(e))
        raise
    finally:
        h.stop()
        h.event('complete',status=status,elapsed_seconds=round(time.monotonic()-h.t0,3))
        receipt={'format':'castles2-original-menu-save-load-1','status':status,
                 'target_exe_sha256':h.known_hashes['C2CDTOOL.EXE'],
                 'bat_working_copy_sha256':h.known_hashes['C2CD.BAT'],
                 'cue_sha256':h.known_hashes['C2CD.ins'],
                 'plan':a.plan,'display':a.display,'events':h.events,
                 'claims':['Original guest was launched and observed through DOSBox video',
                           'Source game was controlled by XTest mouse and keyboard',
                           'Full game-state equivalence not established',
                           'GUI route is a test harness, not a recovered UIL or UDC program']}
        (h.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
