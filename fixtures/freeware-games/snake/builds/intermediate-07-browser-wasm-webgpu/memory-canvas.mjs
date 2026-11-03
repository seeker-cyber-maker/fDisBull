// Browser services only: keys, pointer coordinates, clock and indexed presentation.
import {loadMemoryShell} from './memory-shell.mjs';
const status=document.getElementById('status'),canvas=document.getElementById('game');
const logic=document.getElementById('logic-backend'),render=document.getElementById('render-backend');
let api,plan,closed=false,timer=null,clockPending=false;
const listeners=[];
const listen=(object,event,handler)=>{object.addEventListener(event,handler);listeners.push(()=>object.removeEventListener(event,handler));};
function paint(){
  const {words}=api.snapshot(),f=plan.frame,context=canvas.getContext('2d',{alpha:false});
  const image=context.createImageData(f.width,f.height);
  for(let n=0;n<f.width*f.height;n++){
    const color=f.palette[words[f.offset+n]];if(!color)throw Error('Pixel has no declared palette color');
    image.data.set([...color,255],n*4);
  }
  context.putImageData(image,0,0);
}
const ticks=()=>Math.floor(performance.now()/plan.events.tick_ms)&65535;
async function stop(){
  if(closed)return;closed=true;clearInterval(timer);for(const remove of listeners)remove();
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
    try{api.selectBackend(select.value,functions);status.textContent='Backend selected · pending inputs cancelled';}
    catch(error){status.textContent=String(error.message);}
  });
  choose(logic,plan.logic_functions);choose(render,[plan.render.function]);
  listen(canvas,'keydown',event=>{
    const key=plan.keymap[event.code];if(!key||closed)return;event.preventDefault();
    const e=plan.events;dispatch({[e.kind]:e.keyboard_kind,[e.ascii]:key.ascii,[e.scan]:key.scan}).catch(error=>status.textContent=error.message);
  });
  function pointer(event){
    if(closed)return;const box=canvas.getBoundingClientRect(),e=plan.events;
    const x=Math.max(0,Math.min(plan.frame.width-1,Math.floor((event.clientX-box.left)*plan.frame.width/box.width)));
    const y=Math.max(0,Math.min(plan.frame.height-1,Math.floor((event.clientY-box.top)*plan.frame.height/box.height)));
    dispatch({[e.kind]:e.pointer_kind,[e.x]:x,[e.y]:y,[e.buttons]:event.buttons&7},true).catch(error=>status.textContent=error.message);
  }
  listen(canvas,'pointerdown',event=>{event.preventDefault();canvas.focus();canvas.setPointerCapture(event.pointerId);pointer(event);});
  listen(canvas,'pointermove',pointer);listen(canvas,'pointerup',pointer);
  listen(canvas,'pointercancel',event=>pointer({...event,buttons:0,clientX:event.clientX,clientY:event.clientY}));
  timer=setInterval(()=>{
    if(clockPending||closed)return;clockPending=true;
    const e=plan.events;dispatch({[e.kind]:e.clock_kind},true).catch(error=>status.textContent=error.message).finally(()=>clockPending=false);
  },plan.events.tick_ms);
  listen(window,'pagehide',()=>{stop();});canvas.focus();status.textContent='Ready';
  globalThis.fdisbullMemory=api;
  return Object.freeze({api,paint,stop,clock:()=>ticks(),pauseClock:()=>{clearInterval(timer);timer=null;}});
})().catch(error=>{status.textContent='Could not start: '+error.message;stop();throw error;});
