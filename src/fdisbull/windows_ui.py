"""Guest-only Windows input, stopped frames, scenes and view-only dot-mode.

No operation in this module reads or injects host keyboard/mouse input. The
optional loopback viewer serves already retained captures and has no control
endpoint. Its lifetime belongs to the explicitly enabled debugger session.
"""
from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import secrets
import threading
import time
import uuid
import zlib

from .scenes import SceneSessionMixin


_SCANS = {
    'escape':(1,False),'esc':(1,False),'1':(2,False),'2':(3,False),'3':(4,False),
    '4':(5,False),'5':(6,False),'6':(7,False),'7':(8,False),'8':(9,False),
    '9':(10,False),'0':(11,False),'-':(12,False),'=':(13,False),
    'backspace':(14,False),'tab':(15,False),'q':(16,False),'w':(17,False),
    'e':(18,False),'r':(19,False),'t':(20,False),'y':(21,False),'u':(22,False),
    'i':(23,False),'o':(24,False),'p':(25,False),'[':(26,False),']':(27,False),
    'enter':(28,False),'ctrl':(29,False),'a':(30,False),'s':(31,False),
    'd':(32,False),'f':(33,False),'g':(34,False),'h':(35,False),'j':(36,False),
    'k':(37,False),'l':(38,False),';':(39,False),"'":(40,False),'`':(41,False),
    'shift':(42,False),'\\':(43,False),'z':(44,False),'x':(45,False),
    'c':(46,False),'v':(47,False),'b':(48,False),'n':(49,False),'m':(50,False),
    ',':(51,False),'.':(52,False),'/':(53,False),'alt':(56,False),'space':(57,False),
    **{f'f{i}':(58+i,False) for i in range(1,11)},
    'f11':(87,False),'f12':(88,False),'home':(71,True),'up':(72,True),
    'pageup':(73,True),'left':(75,True),'kp5':(76,False),'right':(77,True),
    'end':(79,True),'down':(80,True),'pagedown':(81,True),'insert':(82,True),
    'delete':(83,True),
}
_SHIFTED = dict(zip('!@#$%^&*()_+{}:"~|<>?', '1234567890-=[];\'`\\,./', strict=True))


def _events(*, key=None, text=None, modifiers=(), hold_ms=40, gap_ms=40):
    from .keyboard_input import validate_keyboard
    validate_keyboard(key=key,text=text,modifiers=modifiers,hold_ms=hold_ms,gap_ms=gap_ms)
    events=[]
    def add(name,down,delay):
        scan,extended=_SCANS[name]
        events.append(dict(scan_code=scan,extended=extended,down=down,delay_ms=delay))
    def press(name,mods,delay):
        for modifier in mods:add(modifier,True,delay)
        add(name,True,delay);add(name,False,delay+hold_ms)
        for modifier in reversed(mods):add(modifier,False,delay+hold_ms)
    if text is None:
        press(key,modifiers,0)
    else:
        delay=0
        for character in text:
            if character in '\r\n':name='enter';mods=()
            elif character=='\t':name='tab';mods=()
            elif character==' ':name='space';mods=()
            elif character.isupper():name=character.lower();mods=('shift',)
            elif character in _SHIFTED:name=_SHIFTED[character];mods=('shift',)
            else:name=character;mods=()
            press(name,mods,delay);delay+=hold_ms+gap_ms
    duration=(hold_ms+gap_ms)*(1 if text is None else len(text))
    if len(events)>1024 or duration>60000:
        raise ValueError('Windows keyboard batch exceeds 1024 events or 60000 execution milliseconds')
    return events


class WindowsInputError(RuntimeError):
    """An attempted input has an uncertain dispatch outcome and must not replay."""
    def __init__(self,receipt,error):
        self.input_receipt=receipt
        super().__init__('Windows input dispatch outcome unknown: '+str(error))


class WindowsCaptureUnavailable(ValueError):
    """A healthy stopped process has not presented a capturable client yet."""
    def __init__(self,result):
        self.capture_receipt=dict(result)
        super().__init__('Windows client capture unavailable: '+str(result.get('reason','not presented')))


def _decode_bgra(result,expected):
    """Decode one exact, bounded stopped-frame payload without caching it."""
    fields=[name for name in ('bgra_base64','bgra_zlib_base64') if name in result]
    if len(fields)!=1:raise ValueError('Windows capture requires exactly one pixel payload')
    field=fields[0];encoded=result.pop(field)
    maximum=expected-1 if field=='bgra_zlib_base64' else expected
    if not isinstance(encoded,str) or len(encoded)>4*((maximum+2)//3):
        raise ValueError('Windows pixel payload exceeds its encoded byte budget')
    try:data=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError) as error:raise ValueError('Invalid Windows pixel payload base64') from error
    if field=='bgra_zlib_base64':
        # The broker uses compression only when strictly smaller. This bounds
        # both the compressed input allocation and the decompressor's output.
        if not 0<len(data)<expected:raise ValueError('Invalid Windows compressed pixel length')
        decoder=zlib.decompressobj()
        try:pixels=decoder.decompress(data,expected+1)
        except zlib.error as error:raise ValueError('Invalid Windows compressed pixel stream') from error
        if len(pixels)!=expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
            raise ValueError('Incomplete or oversized Windows compressed pixel capture')
    else:pixels=data
    if len(pixels)!=expected:raise ValueError('Incomplete Windows client capture')
    return pixels


class _Spectator:
    """A capability URL with read-only HTTP access to an owned PNG buffer."""
    def __init__(self,session):
        self.session=session;self.token=secrets.token_hex(24);self.lock=threading.Lock()
        self.png=None;self.frame=None;self.closed=False;self.capture_available=False;self.capture_reason='not captured yet'
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(2)
                super().setup()
            def log_message(self,*args):pass
            def _send(self,status,kind,data):
                self.send_response(status)
                self.send_header('Content-Type',kind)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'none'")
                self.end_headers();self.wfile.write(data)
            def do_GET(self):
                host='127.0.0.1:'+str(owner.server.server_port)
                if self.headers.get('Host')!=host or self.headers.get('Origin') not in (None,'http://'+host):
                    return self._send(403,'text/plain',b'Forbidden')
                prefix='/'+owner.token+'/'
                if self.path==prefix:
                    page=("<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=1>"
                          "<title>fDisBull dot-mode spectator</title>"
                          "<style>body{background:#15191f;color:#e7edf5;font:16px system-ui;margin:24px}"
                          "img{max-width:100%;image-rendering:pixelated;border:1px solid #637083}</style>"
                          "<h1>Dot-mode spectator</h1><p>View only. Host keyboard and mouse are never forwarded. "
                          "Images update from retained debugger captures at native stops; no live frame rate is promised.</p>"
                          "<img alt='No retained frame yet; run or capture the guest first.' src='frame.png'>")
                    return self._send(200,'text/html; charset=utf-8',page.encode())
                if self.path==prefix+'frame.png':
                    with owner.lock:data=owner.png
                    return self._send(200 if data is not None else 204,'image/png',data or b'')
                if self.path==prefix+'state.json':
                    return self._send(200,'application/json',json.dumps(owner.state()).encode())
                return self._send(404,'text/plain',b'Not found')
            def do_POST(self):self._send(405,'text/plain',b'View only')
            do_PUT=do_DELETE=do_PATCH=do_POST
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,name='fdisbull-dot-spectator',daemon=True)
        self.thread.start()

    def state(self):
        with self.lock:frame=self.frame;available=self.capture_available;reason=self.capture_reason
        return dict(mode='dot-mode',enabled=not self.closed,view_only=True,
                    viewer_url=f'http://127.0.0.1:{self.server.server_port}/{self.token}/',
                    host_input_capture=False,host_keyboard_forwarded=False,host_mouse_forwarded=False,
                    source='retained stopped-frame captures',frame=frame,
                    capture_available=available,capture_reason=reason)

    def update(self,png,frame):
        with self.lock:
            self.png=png;self.frame=dict(frame);self.capture_available=True;self.capture_reason=None

    def unavailable(self,reason):
        with self.lock:
            self.png=None;self.frame=None;self.capture_available=False;self.capture_reason=reason

    def close(self):
        if self.closed:return
        self.closed=True;self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)


class WindowsUIMixin(SceneSessionMixin):
    native_hooks_available=False
    scene_time_basis='host'

    def _windows_ui_initialize(self, *, window=False):
        if type(window) is not bool:raise ValueError('window must be boolean')
        self._windows_epoch=0;self._windows_revision=0;self._windows_frame_id=0
        self._windows_last_revision=None;self._windows_last_frame=None
        self._windows_spectator=None;self._windows_last_png=None;self._windows_last_metadata=None
        self._keyboard_leases={}
        self.metadata['window_requested']=window
        if window:self.dot_mode(True)

    def _windows_ui_ready(self):
        if not hasattr(self,'_windows_epoch'):self._windows_ui_initialize()

    def _windows_state_changed(self):
        self._windows_ui_ready();self._windows_epoch+=1
        self._windows_last_frame=None;self._windows_last_revision=None

    def _windows_invalidate_input_leases(self):
        self._windows_ui_ready();self._keyboard_leases.clear()
        self._windows_state_changed()

    def _windows_ui_close(self):
        spectator=getattr(self,'_windows_spectator',None)
        if spectator is not None:spectator.close();self._windows_spectator=None

    def dot_mode(self, enabled=None):
        self._windows_ui_ready()
        if enabled is not None and type(enabled) is not bool:raise ValueError('dot-mode requires a boolean')
        if enabled is True and self._windows_spectator is None:self._windows_spectator=_Spectator(self)
        if enabled is False:self._windows_ui_close()
        if self._windows_spectator is None:
            result=dict(mode='dot-mode',enabled=False,view_only=True,host_input_capture=False,
                        host_keyboard_forwarded=False,host_mouse_forwarded=False,viewer_url=None)
        else:result=self._windows_spectator.state()
        self.metadata['dot_mode']=result
        return result

    spectator_state=dot_mode

    def spectator_frame(self):
        """Explicitly capture one stopped frame and refresh the view-only buffer."""
        return self.screenshot('dot-mode.png',hooks=False)

    def _windows_refresh_spectator(self):
        """Replace one bounded in-memory viewer frame without growing artifacts."""
        if getattr(self,'_windows_spectator',None) is None:return None
        image,metadata=self._windows_capture();output=io.BytesIO();image.save(output,format='PNG')
        data=output.getvalue();metadata['sha256']=hashlib.sha256(data).hexdigest()
        metadata['retention']='latest owned spectator buffer; use screenshot for a persistent artifact'
        self._windows_last_png=data;self._windows_last_metadata=metadata
        self._windows_spectator.update(data,metadata)
        return metadata

    def scene_memory_key(self,address,length,cs=None):
        if cs is not None:raise ValueError('Windows PE scene addresses are flat project addresses')
        value=self._address(address,length)
        return f'pe/{self.version["id"]}/{value:x}/{length}'

    def scene_memory_address(self,address,length,cs=None):
        if cs is not None:raise ValueError('Windows PE scene addresses are flat project addresses')
        return hex(self._address(address,length))

    def _windows_submit_input(self,operation,params):
        receipt=dict(input_id=uuid.uuid4().hex,kind=operation,attempted=True,
                     dispatch_outcome='unknown',application_consumption_verified=False,
                     host_input_capture=False)
        self._event('input-attempt',receipt)
        try:
            result=self.call(operation,params)
            queued=result.get('queued') if isinstance(result,dict) else None
            if type(queued) is not int or not 1<=queued<=1024:
                raise ValueError('Windows input acknowledgment lacks a bounded queued-event count')
        except Exception as error:
            receipt.update(error_type=type(error).__name__,error=str(error))
            self._windows_state_changed();self._event('input-unknown',receipt)
            raise WindowsInputError(receipt,error) from error
        self._windows_state_changed()
        return {**result,**receipt,'dispatch_outcome':'queued'}

    def _windows_capture(self):
        from PIL import Image
        from .debugger import bounded
        self._windows_ui_ready()
        result=dict(self.call('screenshot'))
        if result.get('available') is False:
            self._windows_last_frame=None
            if self._windows_spectator is not None:
                self._windows_spectator.unavailable(str(result.get('reason','not presented')))
            raise WindowsCaptureUnavailable(result)
        width=bounded(result.get('width'),'width',1,1920);height=bounded(result.get('height'),'height',1,1080)
        pixels=_decode_bgra(result,width*height*4)
        native=result.get('state_revision',result.get('frame_revision'))
        if type(native) is not int or native<0:raise ValueError('Windows frame lacks a native state revision; prepare the current runtime')
        if 'window' not in result:raise ValueError('Windows capture lacks its owned window identity')
        mode=(result['window'],width,height)
        if mode!=getattr(self,'_frame',None):self.mode_id=getattr(self,'mode_id',0)+1;self._frame=mode
        revision=(self._windows_epoch,native)
        if revision!=self._windows_last_revision:self._windows_revision+=1;self._windows_last_revision=revision
        image=Image.frombytes('RGB',(width,height),pixels,'raw','BGRX')
        digest=hashlib.sha256(image.tobytes()).hexdigest()
        identity=(mode,revision,digest)
        if identity!=self._windows_last_frame:self._windows_frame_id+=1;self._windows_last_frame=identity
        metadata={**result,'width':width,'height':height,'mode_id':self.mode_id,
                  'frame_id':self._windows_frame_id,'state_revision':self._windows_revision,
                  'native_state_revision':native,'capture_sha256':digest,
                  'source_bpp':32,'double_width':False,'double_height':False,
                  'backend':self.backend_name,'source_sha256':self.metadata['source_sha256'],
                  'runtime_profile':self.metadata.get('runtime_profile','windows-debugger'),
                  'coordinate_space':'client-native-pixels','capture':'owned stopped Windows client BitBlt',
                  'host_input_capture':False}
        inputs=self.metadata.get('runtime_inputs',{})
        runtime=dict(inputs={name:{k:v for k,v in value.items() if k!='path'}
                             for name,value in inputs.items()},guest=self.metadata.get('guest_runtime',{}))
        metadata['runtime_identity_sha256']=hashlib.sha256(json.dumps(runtime,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        files=self.metadata.get('files',[])
        metadata['resource_manifest_sha256']=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return image,metadata

    def frame_probe(self,points):
        from .debugger import bounded
        if not isinstance(points,list) or len(points)>4096:raise ValueError('Probe requires at most 4096 native points')
        for point in points:
            if not isinstance(point,(list,tuple)) or len(point)!=2:raise ValueError('Invalid probe point')
            bounded(point[0],'x',0,1919);bounded(point[1],'y',0,1079)
        image,metadata=self._windows_capture()
        if any(x>=image.width or y>=image.height for x,y in points):raise ValueError('Probe point outside Windows client frame')
        result={**metadata,'format':'rgb-samples','samples':[dict(x=x,y=y,rgb=list(image.getpixel((x,y)))) for x,y in points]}
        self._event('frame-probe',result)
        return result

    def screenshot(self,name='screenshot.png',*,grid=False,grid_step=32,hooks=False):
        from .external_files import _file_name
        from .screenshot_grid import validate_step
        _file_name(name);validate_step(grid_step)
        if type(grid) is not bool or type(hooks) is not bool:raise ValueError('grid and hooks must be boolean')
        if hooks:raise ValueError('Windows screenshots do not support DOS native screenshot hooks')
        image,metadata=self._windows_capture();output=io.BytesIO();image.save(output,format='PNG');data=output.getvalue()
        metadata['sha256']=hashlib.sha256(data).hexdigest()
        raw=self._artifact(name if not grid else name[:248]+'.raw.png','screenshot',data,metadata)
        self._windows_last_png=data;self._windows_last_metadata=metadata
        if self._windows_spectator is not None:self._windows_spectator.update(data,metadata)
        return self.project.debug_grid(raw['artifact'],name=name,step=grid_step) if grid else raw

    def click(self,x,y,*,button='left',hold_ms=80,mode_id=None,frame_id=None):
        from .debugger import bounded
        bounded(x,'x',0,1919);bounded(y,'y',0,1079);bounded(hold_ms,'hold_ms',1,1000)
        if button not in ('left','right','middle'):raise ValueError('Invalid mouse button')
        _,frame=self._windows_capture()
        if mode_id is not None and (type(mode_id) is not int or mode_id!=frame['mode_id']):raise ValueError('Stale Windows frame mode')
        if frame_id is not None and (type(frame_id) is not int or frame_id!=frame['frame_id']):raise ValueError('Stale Windows frame identity')
        if x>=frame['width'] or y>=frame['height']:raise ValueError('Click outside Windows client frame')
        result=self._windows_submit_input('click',dict(x=x,y=y,button=button,hold_ms=hold_ms))
        result.update(x=x,y=y,button=button,mode_id=frame['mode_id'],frame_id=frame['frame_id'],
                      delivery='queued guest-only SendInput; execution-clock hold/release',
                      application_consumption_verified=False,host_input_capture=False)
        self._event('click',result)
        return result

    @property
    def keyboard(self):
        from .keyboard_input import GuestKeyboard
        return GuestKeyboard(self)

    def _windows_keyboard(self,*,key=None,text=None,modifiers=(),hold_ms=40,gap_ms=40):
        events=_events(key=key,text=text,modifiers=modifiers,hold_ms=hold_ms,gap_ms=gap_ms)
        self._windows_ui_ready()
        held={_SCANS[k] for k in self._keyboard_leases.values()}
        touched={(e['scan_code'],e['extended']) for e in events}
        if held and (text is not None or held&touched or held&{_SCANS[k] for k in ('ctrl','alt','shift')}):
            raise ValueError('Release the owned key lease before this keyboard batch')
        duration_ms=(hold_ms+gap_ms)*(1 if text is None else len(text))
        result=self._windows_submit_input('keyboard',dict(events=events,duration_ms=duration_ms))
        result.update(delivery='queued guest-only physical scan codes',application_consumption_verified=False,
                      host_input_capture=False,requested_events=len(events))
        self._event('keyboard-input',result)
        return result

    def keyboard_press(self,key,*,modifiers=(),hold_ms=40,gap_ms=40):
        return self._windows_keyboard(key=key,modifiers=modifiers,hold_ms=hold_ms,gap_ms=gap_ms)

    def keyboard_type(self,text,*,hold_ms=40,gap_ms=40):
        return self._windows_keyboard(text=text,hold_ms=hold_ms,gap_ms=gap_ms)

    def keyboard_state(self):
        self._windows_ui_ready()
        result=self.call('keyboard-state')
        result.update(application_consumption_verified=False,host_input_capture=False,
                      owned_leases=[dict(lease=lease,key=key) for lease,key in self._keyboard_leases.items()])
        return result

    def keyboard_key_down(self,key):
        self._windows_ui_ready()
        events=_events(key=key)
        scan=_SCANS[key]
        if scan in {_SCANS[k] for k in self._keyboard_leases.values()}:
            raise ValueError('Physical key already has an owned lease')
        token=uuid.uuid4().hex
        result=self._windows_submit_input('keyboard',dict(events=[events[0]],duration_ms=0))
        self._keyboard_leases[token]=key
        result.update(lease=token,key=key,run=self.run_id,delivery='queued guest-only physical key down')
        self._event('keyboard-down',result)
        return result

    def keyboard_key_up(self,lease):
        self._windows_ui_ready()
        if not isinstance(lease,str) or lease not in self._keyboard_leases:
            raise ValueError('Unknown, consumed or unrelated input lease')
        key=self._keyboard_leases[lease];scan,extended=_SCANS[key]
        event=dict(scan_code=scan,extended=extended,down=False,delay_ms=0)
        result=self._windows_submit_input('keyboard',dict(events=[event],duration_ms=0))
        del self._keyboard_leases[lease]
        result.update(lease=lease,key=key,consumed=True,delivery='queued guest-only physical key up')
        self._event('keyboard-up',result)
        return result

    def scene_advance(self,*,slice_ms,timeout_ms):
        from .debugger import bounded
        bounded(slice_ms,'slice_ms',1,10000);bounded(timeout_ms,'timeout_ms',1,600000)
        start=time.monotonic();budget=min(slice_ms,timeout_ms)
        slicer=getattr(self,'_scene_slice',None)
        result=(slicer(budget,timeout_ms) if callable(slicer) else
                self.call('slice',{'timeout_ms':budget},timeout_ms=timeout_ms))
        stop=result.get('stop_reason',result.get('session',{}).get('stop_reason',{}))
        outcome=result.get('outcome',stop.get('kind','incomplete'))
        elapsed=(time.monotonic()-start)*1000
        self._windows_state_changed()
        result={'run':self.run_id,'outcome':outcome,'session':result,'time_basis':'host',
                'scene_elapsed_ms':elapsed,'host_elapsed_ms':elapsed,'hook_hits':[]}
        if self._windows_spectator is not None:
            try:self._windows_refresh_spectator()
            except Exception as error:result['spectator_capture_error']=str(error)
        self._event('scene-advance',result)
        return result

    def wait(self,observations,until,*,guest_ms=None,active_ms=None,slice_ms=50,timeout_ms=10000,
             fast_forward=False,max_polls=1000,timeout_screenshot='wait-timeout.png'):
        from .debug_wait import validate_wait,_matches,_integer
        if guest_ms is not None and active_ms is not None:raise ValueError('Choose active_ms or legacy guest_ms, not both')
        budget=active_ms if active_ms is not None else guest_ms
        if budget is None:raise ValueError('Windows observation wait requires active_ms')
        if fast_forward is not False:raise ValueError('Windows waits use host execution slices, without DOS fast-forward')
        validate_wait(observations,until,guest_ms=budget,slice_ms=slice_ms,timeout_ms=timeout_ms,
                      fast_forward=False,max_polls=max_polls,timeout_screenshot=timeout_screenshot)
        start=time.monotonic();elapsed=0;initial=None
        result=dict(format='fdisbull-wait-result-1',complete=False,matched=False,outcome='incomplete',
                    time_basis='host',requested_active_ms=budget,active_elapsed_ms=0,polls=[],runs=[])
        try:
            while len(result['polls'])<max_polls:
                values={};captures={}
                for name,spec in observations.items():
                    if spec['kind']=='memory':
                        capture=self.memory(**{k:v for k,v in spec.items() if k!='kind'});value=capture['hex']
                        if len(bytes.fromhex(value))!=spec['length']:raise ValueError('Incomplete wait memory capture')
                    else:
                        capture=self.registers() if spec['kind']=='register' else self.status();value=capture
                        for part in spec['path'].split('.'):value=value[part]
                        value=_integer(value)
                    captures[name]=capture;values[name]=value
                result['polls'].append(dict(values=dict(values),captures=captures,active_elapsed_ms=elapsed))
                if initial is None:initial=dict(values)
                result.update(last_observation=values,initial_observation=initial)
                remaining=timeout_ms-int((time.monotonic()-start)*1000)
                if remaining<=0:result['outcome']='timeout';break
                if _matches(until,values,initial,observations):result.update(complete=True,matched=True,outcome='predicate');break
                if elapsed>=budget:result['outcome']='active_budget';break
                advance=self.scene_advance(slice_ms=max(1,int(min(slice_ms,budget-elapsed))),timeout_ms=max(1,remaining))
                result['runs'].append(advance);elapsed+=advance['scene_elapsed_ms']
                if advance['outcome']!='slice':result.update(outcome=advance['outcome'],stop=advance);break
            else:result['outcome']='poll_budget'
        except Exception as error:result.update(outcome='incomplete',error=dict(type=type(error).__name__,message=str(error)))
        result.update(active_elapsed_ms=elapsed,host_elapsed_ms=(time.monotonic()-start)*1000)
        if not result['complete'] and timeout_screenshot is not None:
            try:result['diagnostic_frame']=self.screenshot(timeout_screenshot,hooks=False)
            except Exception as error:result['capture_error']=str(error)
        self._event('wait',result)
        return result
