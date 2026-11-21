"""Local JSON-lines transport for an explicitly supplied DOSBox agent build."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from fdisbull_core.pipe_rpc import PipeRPC


class DebuggerError(ValueError):
    """A debugger operation failed; uncertain requests are never replayed."""


class DOSBoxRPC(PipeRPC):
    rpc_error_type = DebuggerError
    request_prefix = 'fdisbull'
    limit = 8 * 1024 * 1024

    def __init__(self, executable, game_dir, *, window=False, on_spawn=None):
        if type(window) is not bool:
            raise ValueError('window must be boolean')
        if window:
            driver = os.environ.get('SDL_VIDEODRIVER', '').strip().lower()
            if any(item.strip() in ('dummy', 'offscreen') for item in driver.split(',')):
                raise DebuggerError('Window requires a visible SDL video driver; SDL_VIDEODRIVER is '+driver)
            if sys.platform.startswith('linux') and not driver and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
                raise DebuggerError('Window requires an available display (DISPLAY or WAYLAND_DISPLAY)')
        if os.name != 'posix':
            raise DebuggerError('Inherited-pipe debugger currently requires macOS or Linux')
        executable = Path(executable).expanduser().resolve(strict=True)
        game_dir = Path(game_dir).expanduser().resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK) or not game_dir.is_dir():
            raise DebuggerError('Expected an executable DOSBox agent and a game directory')
        if any(c in str(executable) + str(game_dir) for c in '\r\n\0'):
            raise DebuggerError('Paths cannot contain configuration line breaks or NUL')
        self.process = None
        self.reader = self.writer = None
        self.sequence = 0
        self.lock = threading.Lock()
        self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-dosbox-')
        directory = Path(self.temporary.name)
        descriptors = []
        try:
            child_read, self.writer = os.pipe()
            descriptors.append(child_read)
            self.reader, child_write = os.pipe()
            descriptors.append(child_write)
            config = directory / 'agent.env'
            config.write_text(
                f'transport=pipe\nendpoint=fd:{child_read}:{child_write}\n'
                f'dosbox_executable={executable}\ndosbox_workdir={game_dir}\n'
                'profile=production\nrequest_timeout_ms=15000\n'
                f'max_message_bytes={self.limit}\nmax_memory_read_bytes=65536\nmax_trace_events=10000\n')
            config.chmod(0o600)
            environment = {k:v for k,v in os.environ.items() if not k.upper().startswith('DOSBOX_')}
            environment['XDG_CONFIG_HOME'] = str(directory / 'config')
            arguments = [str(executable), '--defaultconf', '--noautoexec', '--noconfig',
                         '-set', 'render doublescan=false', '-set', 'cpu core=normal', '--agent-config', str(config)]
            if window:
                arguments.append('-agent-window')
            else:
                # Owned headless sessions must never wait for a host quit dialog.
                arguments.extend(['-set', 'dosbox quit warning=false'])
                # MIDI can bypass SDL's audio driver on macOS. Disable both
                # host output paths while retaining the emulated sound devices.
                environment['SDL_AUDIODRIVER'] = 'dummy'
                arguments.extend(['-set', 'mixer nosound=true', '-set', 'midi mididevice=none'])
            with (directory / 'emulator.log').open('wb') as log:
                self.process = subprocess.Popen(
                    arguments,
                    cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, pass_fds=(child_read,child_write))
            if on_spawn is not None:on_spawn(self.process)
            os.close(child_read); descriptors.remove(child_read)
            os.close(child_write); descriptors.remove(child_write)
            os.set_blocking(self.reader, False)
            os.set_blocking(self.writer, False)
            self.capabilities = self.call('agent.capabilities')
            video = self.capabilities.get('video')
            if window and (not isinstance(video, dict) or video.get('headless') is not False or
                           video.get('controlled_window') is not True):
                raise DebuggerError('Backend does not advertise a safe controlled window; rebuild with a compatible agent backend')
        except BaseException:
            for fd in descriptors:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                self.close()
            except Exception:
                pass  # Preserve the original startup error while attempting cleanup.
            raise

    def _close_pipes(self):
        failure = None
        for name in ('reader','writer'):
            fd = getattr(self,name,None)
            if fd is not None:
                setattr(self,name,None)
                try:
                    os.close(fd)
                except BaseException as error:
                    if failure is None:
                        failure = error
        if failure is not None:
            raise failure

    def close(self):
        failure = None
        try:
            self._close_pipes()
        except BaseException as error:
            failure = error
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                self.process.wait(timeout=2)
        except BaseException as error:
            if failure is None:
                failure = error
        finally:
            if self.temporary is not None:
                try:
                    self.temporary.cleanup()
                except BaseException as error:
                    if failure is None:
                        failure = error
                else:
                    self.temporary = None
        if failure is not None:
            raise failure
