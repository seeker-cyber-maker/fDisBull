"""One bounded, loopback-only connection to a live text projection."""
import socket

from .project import Project
from .text_projection import serve_stream


def _config(config):
    required = {'format', 'project', 'backend', 'game_dir', 'projection'}
    allowed = required | {'version', 'state', 'bindings', 'port', 'timeout_ms', 'prepare_guest_ms', 'checkpoint_prepare_guest_ms', 'fair_play', 'spatial_mode'}
    if not isinstance(config, dict) or not required <= set(config) <= allowed or config['format'] != 'fdisbull-text-host-1':
        raise ValueError('Invalid text host configuration')
    for key in ('project', 'backend', 'game_dir', 'projection'):
        if not isinstance(config[key], str) or not config[key]: raise ValueError('Invalid text host '+key)
    if 'state' in config and (not isinstance(config['state'], str) or not config['state']): raise ValueError('Invalid state artifact')
    if type(config.get('fair_play', False)) is not bool: raise ValueError('Invalid fair play policy')
    from .spatial import validate_mode
    validate_mode(config.get('spatial_mode', 'physical' if config.get('fair_play') else 'assisted'), config.get('fair_play', False))
    port = config.get('port', 0); timeout = config.get('timeout_ms', 60000)
    if type(port) is not int or not 0 <= port <= 65535: raise ValueError('Invalid port')
    if type(timeout) is not int or not 1 <= timeout <= 600000: raise ValueError('Invalid timeout')
    prepare = config.get('prepare_guest_ms', 0)
    if type(prepare) is not int or not 0 <= prepare <= 10000: raise ValueError('Invalid guest preparation duration')
    checkpoint_prepare = config.get('checkpoint_prepare_guest_ms', 100)
    if type(checkpoint_prepare) is not int or not 1 <= checkpoint_prepare <= 10000: raise ValueError('Invalid checkpoint preparation duration')
    bindings = config.get('bindings', [])
    if not isinstance(bindings, list) or len(bindings) > 256: raise ValueError('Invalid bindings')
    names = set()
    for binding in bindings:
        if (not isinstance(binding, dict) or not {'name','address','length','expected_hex','provenance'} <= set(binding)
                or not set(binding) <= {'name','address','length','expected_hex','mask_hex','provenance'}
                or not isinstance(binding.get('name'), str) or not binding['name'] or binding['name'] in names):
            raise ValueError('Invalid runtime binding')
        names.add(binding['name'])
    return port, timeout


def host(config, *, on_listen=None):
    """Open one live backend, serve one client, then close session and project.

    The callback executes on the owning thread and receives a public endpoint
    dictionary. Timeout applies separately to accept and each socket read.
    """
    port, timeout = _config(config)
    if on_listen is not None and not callable(on_listen): raise ValueError('on_listen must be callable')
    with Project(config['project']) as project:
        with project.debugger(config['backend'], config['game_dir'], version=config.get('version')) as session:
            session.spatial_policy(config.get('spatial_mode', 'physical' if config.get('fair_play') else 'assisted'),
                                   fair_play=config.get('fair_play', False))
            if hasattr(session, '_event'):
                session._event('run-policy', {'assisted_travel': session._allow_assisted_travel,
                                              'source': 'text-host startup', 'voluntary': True})
            if config.get('state') is not None:
                session.load_state(config['state'])
            for binding in config.get('bindings', []):
                session.bind_runtime_memory(binding['name'], binding['address'], length=binding['length'],
                                            expected_hex=binding['expected_hex'], mask_hex=binding.get('mask_hex'),
                                            provenance=binding['provenance'])
            preparation = None
            if config.get('prepare_guest_ms', 0):
                requested = config['prepare_guest_ms']
                run = session.run(guest_ms=requested, timeout_ms=min(timeout, 30000),
                                  fast_forward=True, stop_on_hook=True)
                if (not isinstance(run, dict) or run.get('outcome') != 'guest_time'
                        or run.get('hook_hits') != [] or type(run.get('guest_elapsed_ms')) is not int
                        or run['guest_elapsed_ms'] < requested):
                    raise ValueError('Guest preparation stopped before its declared boundary')
                preparation = {'requested_guest_ms': requested, 'guest_elapsed_ms': run['guest_elapsed_ms'],
                               'outcome': 'guest_time'}
            backend = session.text_projection(config['projection'], config['game_dir'])
            backend.checkpoint_prepare_guest_ms = config.get('checkpoint_prepare_guest_ms', 100)
            backend.checkpoint_timeout_ms = min(timeout, 30000)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1', port))
                listener.listen(1)
                listener.settimeout(timeout / 1000)
                address = {'host':'127.0.0.1', 'port':listener.getsockname()[1],
                           'policy': {'assisted_travel': session._allow_assisted_travel,
                                      'spatial_mode':session._spatial_mode, 'fair_play':session._fair_play}}
                if preparation is not None: address['preparation'] = preparation
                if on_listen: on_listen(address)
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    return {'status':'accept_timeout', 'endpoint':address}
                with connection:
                    connection.settimeout(timeout / 1000)
                    with connection.makefile('r', encoding='utf-8') as reader, connection.makefile('w', encoding='utf-8') as writer:
                        try:
                            serve_stream(backend, reader, writer)
                        except (TimeoutError, ConnectionError, UnicodeError):
                            return {'status':'disconnected', 'endpoint':address}
                return {'status':'disconnected', 'endpoint':address}
