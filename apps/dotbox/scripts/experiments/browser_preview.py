"""Read-only browser presentation of original PNG frames; never advances a game.

An existing native owner publishes frames to FrameStore and owns the returned
HTTP server's serving thread and shutdown. The optional CLI observes an existing
DotBox service through its private descriptor; it never starts a guest.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import struct
import threading
import time
import zlib


MAX_PNG_BYTES = 16 * 1024 * 1024
STALE_SECONDS = 3


class FrameStore:
    """Keep immutable original PNG bytes and a small, credential-free status."""

    def __init__(self):
        self._lock = threading.Lock()
        self._png = None
        self._metadata = {}
        self._received = None
        self._count = 0
        self._status = 'waiting'
        self._message = 'Waiting for the original game screen.'
        self._finished = False

    def publish(self, png_bytes, metadata):
        """Validate native dimensions and SHA-256; retain bytes without resizing."""
        if not isinstance(png_bytes, bytes) or not 45 <= len(png_bytes) <= MAX_PNG_BYTES:
            raise ValueError('Expected bounded PNG bytes')
        if (png_bytes[:8] != b'\x89PNG\r\n\x1a\n' or png_bytes[8:16] != b'\0\0\0\rIHDR'
                or zlib.crc32(png_bytes[12:29]) != struct.unpack('>I', png_bytes[29:33])[0]
                or png_bytes[-12:] != b'\0\0\0\0IEND\xaeB`\x82'):
            raise ValueError('Invalid PNG header or terminator')
        width, height = struct.unpack('>II', png_bytes[16:24])
        if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height * 4 > MAX_PNG_BYTES:
            raise ValueError('PNG dimensions exceed the native frame bounds')
        digest = hashlib.sha256(png_bytes).hexdigest()
        if (not isinstance(metadata, dict) or type(metadata.get('width')) is not int
                or type(metadata.get('height')) is not int
                or (metadata['width'], metadata['height']) != (width, height)
                or metadata.get('sha256') != digest):
            raise ValueError('PNG dimensions or SHA-256 differ from native metadata')
        visible = {'width': width, 'height': height, 'sha256': digest}
        for key in ('frame_id', 'mode_id', 'captured_ticks'):
            value = metadata.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('Invalid native frame identity: ' + key)
            visible[key] = value
        with self._lock:
            if self._finished:
                raise ValueError('Cannot publish after the frame source finished')
            self._png, self._metadata = png_bytes, visible
            self._received = time.monotonic()
            self._count += 1
            self._status, self._message = 'live', ''

    def finish(self, status='finished', message=''):
        """Mark the source terminal while retaining its last original frame."""
        if (not isinstance(status, str) or not 1 <= len(status) <= 64
                or status in ('waiting', 'live') or not isinstance(message, str)
                or len(message) > 512):
            raise ValueError('Expected a short terminal status and message')
        with self._lock:
            self._finished = True
            self._status, self._message = status, message

    def _snapshot(self):
        with self._lock:
            age = None if self._received is None else max(0, time.monotonic() - self._received)
            status = {'status': self._status, 'message': self._message, 'view_only': True,
                      'received_count': self._count,
                      'age_ms': None if age is None else round(age * 1000),
                      'stale': not self._finished and age is not None and age > STALE_SECONDS,
                      **self._metadata}
            return self._png, status


PAGE = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DotBox game screen</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0b120f;color:#e9f5ed}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;height:100dvh;display:flex;flex-direction:column}
header,footer{padding:14px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header{border-bottom:1px solid #294334}h1{font-size:20px;margin:0;font-weight:650}
.badge{color:#adf0c5;border:1px solid #396d4c;border-radius:20px;padding:4px 10px;font-size:13px}
label{margin-left:auto;font-size:14px}select{margin-left:8px;padding:6px 10px;background:#18271f;color:inherit;border:1px solid #45614f;border-radius:6px}
#viewport{flex:1;min-height:0;overflow:auto;display:grid;padding:16px;background:#060a08}
#screen{display:block;margin:auto;image-rendering:pixelated;max-width:none}
#waiting{margin:auto;color:#a8bbb0}footer{border-top:1px solid #294334;font-size:13px;color:#acc2b4}
#connection{color:#adf0c5;font-weight:600}#detail{overflow-wrap:anywhere}
</style>
<header><h1>DotBox game screen</h1><span class="badge">View only</span>
<label for="scale">Display<select id="scale"><option value="fit">Fit</option><option value="1">1×</option><option value="2">2×</option><option value="3">3×</option><option value="4">4×</option></select></label></header>
<main id="viewport"><p id="waiting">Waiting for the original game screen…</p><img id="screen" alt="Original game screen" hidden></main>
<footer aria-live="polite"><span id="connection">Waiting</span><span id="detail">No frame received</span></footer>
<script>
const picture=document.getElementById('screen'), viewport=document.getElementById('viewport');
const scale=document.getElementById('scale'), connection=document.getElementById('connection');
const detail=document.getElementById('detail'), waiting=document.getElementById('waiting');
let width=0,height=0,lastHash='',objectURL=null,closed=false,timer=null,active=null;
function size(){
  if(!width||!height)return;
  const factor=scale.value==='fit'?Math.max(.01,Math.min((viewport.clientWidth-32)/width,(viewport.clientHeight-32)/height)):Number(scale.value);
  picture.style.width=(width*factor)+'px'; picture.style.height=(height*factor)+'px';
}
scale.addEventListener('change',size);new ResizeObserver(size).observe(viewport);
async function refresh(){
  if(closed)return;
  active=new AbortController();const timeout=setTimeout(()=>active.abort(),3000);
  try{
    const response=await fetch('/status',{cache:'no-store',credentials:'omit',signal:active.signal});
    if(!response.ok)throw new Error('Status unavailable');
    const state=await response.json();
    connection.textContent=state.stale?'Stale — waiting for fresh frames':state.status==='live'?'Live view':state.status==='waiting'?'Waiting':state.status;
    const age=state.age_ms===null?'':(state.age_ms/1000).toFixed(1)+' s since received';
    detail.textContent=[state.width?state.width+' × '+state.height+' native':'No frame received',state.frame_id!=null?'frame '+state.frame_id:'',state.mode_id!=null?'mode '+state.mode_id:'',state.received_count+' received',age,state.message].filter(Boolean).join(' · ');
    if(state.sha256 && state.sha256!==lastHash){
      const frame=await fetch('/frame.png',{cache:'no-store',credentials:'omit',signal:active.signal});
      if(!frame.ok)throw new Error('Frame unavailable');
      const blob=await frame.blob(),nextURL=URL.createObjectURL(blob),oldURL=objectURL;
      objectURL=nextURL;picture.src=nextURL;
      await picture.decode();
      width=picture.naturalWidth;height=picture.naturalHeight;
      picture.hidden=false;waiting.hidden=true;size();
      lastHash=frame.headers.get('X-Frame-SHA256')||state.sha256;
      if(oldURL)URL.revokeObjectURL(oldURL);
    }
  }catch(error){
    if(!closed){connection.textContent='Disconnected';detail.textContent='The frame source is unavailable. The last received image is retained.';}
  }finally{
    clearTimeout(timeout);active=null;
    if(!closed)timer=setTimeout(refresh,50);
  }
}
window.addEventListener('pagehide',()=>{closed=true;clearTimeout(timer);if(active)active.abort();if(objectURL)URL.revokeObjectURL(objectURL);});
refresh();
</script></html>'''.encode('utf-8')


def start_server(store, host='127.0.0.1', port=8766):
    """Bind loopback and return a server; the caller starts/stops serve_forever."""
    if not isinstance(store, FrameStore) or host not in ('127.0.0.1', 'localhost'):
        raise ValueError('Expected a FrameStore and a local loopback host')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('Expected a valid local port (0 selects an unused port)')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def _send(self, code, body, content_type='text/plain; charset=utf-8', headers=()):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; img-src 'self' blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'")
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _host_ok(self):
            actual_port = self.server.server_address[1]
            allowed = {f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'}
            if actual_port == 80:
                allowed.update(('127.0.0.1', 'localhost'))
            hosts = self.headers.get_all('Host', [])
            if len(hosts) == 1 and hosts[0].lower() in allowed:
                return True
            self.close_connection = True
            self._send(403, b'Unexpected Host\n')
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            if self.path == '/':
                self._send(200, PAGE, 'text/html; charset=utf-8')
            elif self.path == '/status':
                _, status = store._snapshot()
                self._send(200, json.dumps(status, allow_nan=False).encode(), 'application/json')
            elif self.path == '/frame.png':
                png, status = store._snapshot()
                if png is None:
                    self._send(503, b'No frame received\n')
                else:
                    self._send(200, png, 'image/png', [('X-Frame-SHA256', status['sha256'])])
            else:
                self._send(404, b'Not found\n')

        def _refuse_method(self):
            self.close_connection = True
            if self._host_ok():
                self._send(405, b'View only\n', headers=[('Allow', 'GET')])

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = _refuse_method

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.block_on_close = False
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True, help='Existing private DotBox session.json')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--fps', type=float, default=10, help='Observation rate, greater than 0 and at most 20')
    args = parser.parse_args(argv)
    if not math.isfinite(args.fps) or not 0 < args.fps <= 20:
        parser.error('--fps must be greater than 0 and at most 20')
    from dotbox.client import Client
    client = Client(args.session, timeout=3)
    store = FrameStore()
    server = start_server(store, port=args.port)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    print(f'View only: http://127.0.0.1:{server.server_address[1]}/', flush=True)
    try:
        while True:
            started = time.monotonic()
            reply = client.request('frame')
            if not reply.get('ok'):
                raise RuntimeError('Frame source refused observation')
            frame = reply['result']
            store.publish(base64.b64decode(frame['png_base64'], validate=True), frame)
            time.sleep(max(0, 1 / args.fps - (time.monotonic() - started)))
    except KeyboardInterrupt:
        store.finish('stopped', 'Preview stopped.')
        return 0
    except (OSError, ValueError, RuntimeError, KeyError):
        store.finish('disconnected', 'The original frame source is unavailable.')
        return 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=1)


if __name__ == '__main__':
    raise SystemExit(main())
