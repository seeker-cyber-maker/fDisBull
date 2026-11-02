// Browser services only: keys, pointer coordinates, clock and indexed presentation.
import {loadMemoryShell} from './memory-shell.mjs';
const status=document.getElementById('status'),canvas=document.getElementById('game');
const logic=document.getElementById('logic-backend'),render=document.getElementById('render-backend');
let api,plan,closed=false,timer=null,clockPending=false;
const listeners=[];
const captures=new Set();let pointerState={x:0,y:0,buttons:0};
let queuedMotion=null,motionTask=null;
const listen=(object,event,handler)=>{object.addEventListener(event,handler);listeners.push(()=>object.removeEventListener(event,handler));};
function paint(){
  const {words}=api.snapshot(),f=plan.frame,context=canvas.getContext('2d',{alpha:false});
  const image=context.createImageData(f.width,f.height);
  for(let n=0;n<f.width*f.height;n++){
    const color=f.palette[words[f.offset+n]];if(!color)throw Error('Pixel has no declared palette color');
    image.data[n*4]=color[0];image.data[n*4+1]=color[1];image.data[n*4+2]=color[2];image.data[n*4+3]=255;
  }
  context.putImageData(image,0,0);
}
const ticks=()=>Math.floor(performance.now()/plan.events.tick_ms)&65535;
async function stop(){
  if(closed)return;closed=true;queuedMotion=null;clearInterval(timer);for(const remove of listeners)remove();
  for(const id of captures){try{canvas.releasePointerCapture(id);}catch{}}captures.clear();
  canvas.tabIndex=-1;
  logic.disabled=render.disabled=true;await api?.dispose();
}
async function dispatch(patch,quiet=false){
  if(closed)return {status:'discarded',committed:false};
  const e=plan.events,owned={...patch,[e.clock]:ticks()};
  const result=await api.dispatch(e.function,owned);
  if(closed)return result;
  if(result.committed){
    paint();const words=api.snapshot().words;
    if(words[e.quit_index]){status.textContent='Exited. Reload to start again.';await stop();}
    else if(!quiet)status.textContent='Ready · input committed';
  }else if(result.status==='failed'||!quiet)status.textContent=result.status+': '+(result.reason||'input discarded');
  return result;
}
globalThis.fdisbullMemoryReady=(async()=>{
  api=await loadMemoryShell();plan=api.describe().plan;
  document.getElementById('title').textContent=plan.title;document.title=plan.title;document.getElementById('help').textContent=plan.help;
  canvas.width=plan.frame.width;canvas.height=plan.frame.height;
  const ready=await api.dispatch(plan.initialize,{});if(!ready.committed)throw Error(ready.reason||'Initialization failed');paint();
  const caps=api.capabilities();for(const select of [logic,render])select.querySelector('[value="webgpu"]').disabled=!caps.backends.webgpu;
  const choose=(select,functions)=>listen(select,'change',()=>{
    try{
      api.selectBackend(select.value,functions);status.textContent='Backend selected · pending inputs cancelled';
      // A committed press may have an old-epoch release queued behind it.
      // Explicitly end that gesture under the newly selected bindings.
      releasePointer().catch(error=>status.textContent=error.message);
    }
    catch(error){status.textContent=String(error.message);}
  });
  choose(logic,plan.logic_functions);choose(render,[plan.render.function]);
  listen(canvas,'keydown',event=>{
    if(event.ctrlKey||event.altKey||event.metaKey)return;
    const key=plan.keymap[event.code];if(!key||closed)return;event.preventDefault();
    const e=plan.events;dispatch({[e.kind]:e.keyboard_kind,[e.ascii]:key.ascii,[e.scan]:key.scan}).catch(error=>status.textContent=error.message);
  });
  function pointer(event){
    if(closed)return;const box=canvas.getBoundingClientRect(),e=plan.events;
    const scaleX=box.width/canvas.offsetWidth,scaleY=box.height/canvas.offsetHeight;
    const x=Math.max(0,Math.min(plan.frame.width-1,Math.floor((event.clientX-box.left-canvas.clientLeft*scaleX)*plan.frame.width/(canvas.clientWidth*scaleX))));
    const y=Math.max(0,Math.min(plan.frame.height-1,Math.floor((event.clientY-box.top-canvas.clientTop*scaleY)*plan.frame.height/(canvas.clientHeight*scaleY))));
    pointerState={x,y,buttons:event.buttons&7};
    const patch={[e.kind]:e.pointer_kind,[e.x]:x,[e.y]:y,[e.buttons]:event.buttons&7};
    if(event.type==='pointermove'){
      // Motion is a sampled device position, not a backlog of game turns.
      // Keep one pending sample while preserving press/release ordering.
      queuedMotion=patch;
      if(!motionTask)motionTask=(async()=>{while(queuedMotion&&!closed){const next=queuedMotion;queuedMotion=null;await dispatch(next,true);}})()
        .catch(error=>status.textContent=error.message).finally(()=>{motionTask=null;});
    }else{
      queuedMotion=null;
      (event.type==='pointerup'?releasePointer():dispatch(patch,true)).catch(error=>status.textContent=error.message);
    }
  }
  async function releasePointer(){
    const e=plan.events;pointerState={...pointerState,buttons:0};queuedMotion=null;
    const patch={[e.kind]:e.pointer_kind,[e.x]:pointerState.x,[e.y]:pointerState.y,[e.buttons]:0};
    try{return await dispatch(patch,true);}
    catch(error){
      if(error.message!=='Input queue full'||closed)throw error;
      // A release must never be dropped behind accepted held-button samples.
      // Discard the overloaded context explicitly, drain its physical job,
      // then deliver a fresh release under the current binding generation.
      status.textContent='Input backlog discarded to release the pointer';
      await api.discardPending();
      return dispatch(patch,true);
    }
  }
  listen(canvas,'pointerdown',event=>{event.preventDefault();canvas.focus();canvas.setPointerCapture(event.pointerId);captures.add(event.pointerId);pointer(event);});
  listen(canvas,'pointermove',pointer);listen(canvas,'pointerup',pointer);
  listen(canvas,'pointercancel',()=>{releasePointer().catch(error=>status.textContent=error.message);});
  listen(canvas,'lostpointercapture',event=>{captures.delete(event.pointerId);if(!closed)releasePointer().catch(error=>status.textContent=error.message);});
  listen(window,'blur',()=>{if(!closed)releasePointer().catch(error=>status.textContent=error.message);});
  timer=setInterval(()=>{
    if(clockPending||closed)return;clockPending=true;
    const e=plan.events;dispatch({[e.kind]:e.clock_kind},true).catch(error=>status.textContent=error.message).finally(()=>clockPending=false);
  },plan.events.tick_ms);
  listen(window,'pagehide',()=>{stop();});canvas.focus();status.textContent='Ready';
  globalThis.fdisbullMemory=api;
  return Object.freeze({api,paint,stop,clock:()=>ticks(),pauseClock:()=>{clearInterval(timer);timer=null;}});
})().catch(error=>{status.textContent='Could not start: '+error.message;stop();throw error;});
