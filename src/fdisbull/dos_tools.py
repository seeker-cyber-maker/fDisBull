"""DOS intake/RTLink commands and the existing owned debugger with launch options.

Installed as fdisbull-dos and available as python -m fdisbull.dos_tools. Native
sessions use the existing JSON methods and evidence store, not a shell shim.
"""
from __future__ import annotations

import argparse
import sys


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest='command', required=True)
    sub.add_parser('methods', help='Discover this additive DOS command surface')
    c = sub.add_parser('rtlink-inspect', help='Validate embedded-v2 overlays and original source ranges')
    c.add_argument('path')
    c = sub.add_parser('rtlink-export', help='Create a private, non-runnable banked analysis view')
    c.add_argument('path'); c.add_argument('output')
    c = sub.add_parser('rtlink-disasm', help='Decode backed bytes in one explicit overlay')
    c.add_argument('path'); c.add_argument('--overlay', required=True, type=int)
    c.add_argument('--offset', type=lambda s: int(s, 0), default=0)
    c.add_argument('--count', type=int, default=32)
    c = sub.add_parser('debug', help='Launch original DOS code and serve the normal debugger JSON protocol')
    c.add_argument('project'); c.add_argument('--executable', required=True)
    c.add_argument('--game-dir', required=True)
    c.add_argument('--argument', action='append', default=[], help='Repeatable token; use --argument=-p for a switch')
    c.add_argument('--cd-image', help='Explicit read-only D: .cue/.ins/.iso; no implicit media lookup')
    c.add_argument('--version', type=int)
    c.add_argument('--window', action='store_true')
    c.add_argument('--fair-play', action='store_true')
    return root


def serve(project, options):
    from .cli import respond, emit, load_request
    from .debugger import DebugWorkspace
    from .dos_launch_profile import open_dos_session
    from .project import Project

    class DOSWorkspace(DebugWorkspace):
        def invoke(self, method, project, params):
            if method != 'debug-launch':
                return super().invoke(method, project, params)
            db = Project(project)
            try:
                session = open_dos_session(db, **params)
            except BaseException:
                db.__exit__()
                raise
            self.sessions[session.run_id] = session
            return session.status()

    workspace = DOSWorkspace()
    try:
        result = respond({'id': 'launch', 'method': 'debug-launch', 'params': options}, project, workspace)
        emit(result)
        if not result['ok']:
            return 1
        while True:
            line = sys.stdin.buffer.readline(1024 * 1024 + 1)
            if not line:
                return 0
            if len(line) > 1024 * 1024:
                emit({'ok': False, 'error': {'type': 'ValueError', 'message': 'Request exceeds 1 MiB; closing'}})
                return 1
            try:
                request = load_request(line)
            except (ValueError, UnicodeDecodeError, RecursionError) as exc:
                emit({'ok': False, 'error': {'type': 'InvalidJSON', 'message': str(exc)}})
                continue
            emit(respond(request, project, workspace))
    finally:
        workspace.close()


def main(argv=None):
    from .cli import emit
    from .rtlink import inspect_rtlink, export_rtlink, disassemble_rtlink
    options = vars(parser().parse_args(argv))
    command = options.pop('command')
    try:
        if command == 'debug':
            project = options.pop('project')
            options['arguments'] = options.pop('argument')
            return serve(project, options)
        if command == 'methods':
            result = {'format': 'fdisbull-dos-tools-1',
                      'commands': ['rtlink-inspect', 'rtlink-export', 'rtlink-disasm', 'debug'],
                      'rtlink_profile': 'embedded-v2-only', 'flat_output_runnable': False,
                      'debug_options': ['arguments', 'cd_image', 'version', 'window', 'fair_play'],
                      'scope': 'Additive DOS entrypoint; ordinary fdisbull debug flags are unchanged'}
        else:
            operation = {'rtlink-inspect': inspect_rtlink, 'rtlink-export': export_rtlink,
                         'rtlink-disasm': disassemble_rtlink}[command]
            result = operation(**options)
        emit({'ok': True, 'result': result})
        return 0
    except (ValueError, OSError, TimeoutError) as exc:
        emit({'ok': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
