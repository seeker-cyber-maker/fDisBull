// Original-derived expectations only; no Snake transition or drawing algorithm.
const check=(ok,message)=>{if(!ok)throw Error(message);};
const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
const same=(a,b,label)=>{check(a.length===b.length,label+': length');for(let i=0;i<a.length;i++)check(a[i]===b[i],label+': word '+i+' '+a[i]+' != '+b[i]);};
const scalarNames=['snake_length','direction','pending_direction','paused','game_status','score','rng_seed','tick_count','key_events','mouse_events','frame_count','mouse_present','food_cell','turn_queued'];
const bytes=words=>{const b=new Uint8Array(words.length*4),v=new DataView(b.buffer);words.forEach((x,i)=>v.setUint32(i*4,x,true));return b;};
const decoded=text=>Uint8Array.from(atob(text),x=>x.charCodeAt(0));

export function sourceInitial(initial,study){
 const words=Uint32Array.from(initial),s=study.layout.state;
 for(const[name,value]of Object.entries(study.initial_services))words[s[name]]=value;
 return words;
}
export function eventPatch(event,plan){
 const e=plan.events;return Object.fromEntries(['kind','ascii','scan','x','y','buttons','clock'].map(k=>[e[k],event[k]||0]));
}
export async function compareObservation(words,observation,manifest,study){
 same(words.subarray(0,observation.expected_state.length),observation.expected_state,observation.id+' state');
 const f=manifest.plan.frame,frame=Uint8Array.from(words.subarray(f.offset,f.offset+f.width*f.height));
 const expected=decoded(study.raster_data[observation.frame.sha256]);
 same(frame,expected,observation.id+' full indexed frame');
 check(await sha(frame)===observation.frame.sha256,observation.id+' frame identity');
 return{state_sha256:await sha(bytes(Array.from(words.subarray(0,observation.expected_state.length)))),frame_sha256:observation.frame.sha256};
}

export async function exerciseSnake(shell,manifest,study,initial){
 check(study.uil_sha256===manifest.module_uil_sha256,'Study and selected UIL differ');
 const result={status:'passed',uil_sha256:study.uil_sha256,cpu:{},arms:[],checks:[],
  scope:'342 constructed original-code states plus original-carried input/render sequences; no reset to expected answers between ordinary events'};
 for(const backend of ['wasm','webgpu']){
  shell.selectBackend(backend);const observed=[];
  for(const item of study.cases){
   const words=Uint32Array.from(initial);words.fill(0,0,621);words.set(item.initial.cells,0);
   for(const name of scalarNames)words[study.layout.state[name]]=item.initial[name];
   shell.replace(words);const receipt=await shell.dispatch('step',{}, {render:false});
   check(receipt.committed,item.id+' '+backend+' step failed: '+receipt.reason);
   const actual=shell.snapshot().words;
   same(actual.subarray(0,600),item.original.all_cells,item.id+' all600 cells');
   for(const name of scalarNames)check(actual[study.layout.state[name]]===item.original[name],item.id+' '+name);
   observed.push(await sha(bytes(Array.from(actual.subarray(0,614)))));
  }
  result.cpu[backend]={cases:observed.length,mismatches:0,projection_sha256:await sha(new TextEncoder().encode(JSON.stringify(observed)))};
 }
 for(const mode of [['wasm','wasm'],['wasm','webgpu'],['webgpu','wasm'],['webgpu','webgpu'],['alternating','alternating']]){
  const arm={logic:mode[0],render:mode[1],observations:[],events:0,interventions:0};
  shell.selectBackend('wasm');shell.replace(sourceInitial(initial,study));
  shell.selectBackend(mode[0]==='alternating'?'wasm':mode[0],manifest.plan.logic_functions);
  shell.selectBackend(mode[1]==='alternating'?'webgpu':mode[1],[manifest.plan.render.function]);
  let receipt=await shell.dispatch(manifest.plan.initialize,{[manifest.plan.events.clock]:study.initial_services.last_tick});
  check(receipt.committed,'Initial source reset failed');
  for(const observation of study.observations){
   if(observation.intervention){
    check(observation.intervention.kind==='declared-original-ram-state','Undeclared intervention');
    const next=shell.snapshot().words;next.set(observation.intervention.words,0);shell.replace(next);arm.interventions++;
   }
   for(const event of observation.events){
    if(mode[0]==='alternating'){
     shell.selectBackend(arm.events%2?'webgpu':'wasm',manifest.plan.logic_functions);
     shell.selectBackend(arm.events%2?'wasm':'webgpu',[manifest.plan.render.function]);
    }
    receipt=await shell.dispatch(manifest.plan.events.function,eventPatch(event,manifest.plan));
    check(receipt.committed,observation.id+' '+mode+' event failed: '+receipt.reason);arm.events++;
   }
   arm.observations.push({id:observation.id,...await compareObservation(shell.snapshot().words,observation,manifest,study)});
  }
  result.arms.push(arm);
 }
 result.checks.push('all-original-step-cases-both-backends','all-native-sequences-four-logic-render-combinations','alternating-carried-state-without-answer-resets','exact-full-indexed-frames');
 return result;
}
