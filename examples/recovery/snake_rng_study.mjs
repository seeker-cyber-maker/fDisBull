// Finite original/intentional-variant comparisons through actual selected blocks.
import {sourceInitial,eventPatch,compareObservation} from './snake_browser_study.mjs';
const check=(ok,message)=>{if(!ok)throw Error(message);};
const names=['snake_length','direction','pending_direction','paused','game_status','score','rng_seed','tick_count','key_events','mouse_events','frame_count','mouse_present','food_cell','turn_queued'];
const same=(a,b,label)=>{check(a.length===b.length,label+' length');for(let i=0;i<a.length;i++)check(a[i]===b[i],label+' word '+i);};
const sha=async words=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',Uint32Array.from(words))),x=>x.toString(16).padStart(2,'0')).join('');

export async function exerciseRng(shell,manifest,study,initial){
  check(manifest.regions&&study.rng,'RNG study required');
  const state=study.layout.state,result={status:'passed',cases:{},probes:[],arms:[],outcomes:[],hot_swaps:[],checks:[]};
  const regions=receipt=>receipt.execution.filter(x=>x.function==='rng');
  for(const backend of ['wasm','webgpu']){
    shell.selectBackend(backend);shell.selectRegionImplementation('rng','lfsr16');
    let changed=0,calls=0;
    for(const item of study.rng.cases){
      const words=Uint32Array.from(initial);words.fill(0,0,621);words.set(item.initial.cells,0);
      for(const name of names)words[state[name]]=item.initial[name];
      shell.replace(words);const receipt=await shell.dispatch('step',{}, {render:false});
      check(receipt.committed,item.id+' alternate failed: '+receipt.reason);
      const actual=shell.snapshot().words;
      same(actual.subarray(0,600),item.alternate.all_cells,item.id+' all cells');
      for(const name of names)check(actual[state[name]]===item.alternate[name],item.id+' '+name);
      if(item.alternate.rng_seed!==item.original.rng_seed)changed++;
      for(const call of regions(receipt)){check(call.backend===backend&&call.implementation==='lfsr16'&&call.steps===1,'Wrong alternate provider');calls++;}
    }
    check(changed===84,'Expected intentional change control failed');
    result.cases[backend]={cases:study.rng.cases.length,changed,unchanged:study.rng.cases.length-changed,region_invocations:calls,mismatches:0};
    for(const choice of ['original','lfsr16']){
      shell.selectRegionImplementation('rng',choice);
      for(const item of study.rng.transitions){
        const words=Uint32Array.from(initial);words[state.rng_seed]=item.before;shell.replace(words);
        const receipt=await shell.dispatch('rng',{}, {render:false});check(receipt.committed,'Seed probe failed');
        const after=shell.snapshot().words,expected=choice==='original'?item.original_next:item.alternate_next;
        check(after[state.rng_seed]===expected,'Seed transition differs');
        const untouched=after.slice();untouched[state.rng_seed]=words[state.rng_seed];same(untouched,words,'Seed footprint');
        const call=regions(receipt)[0];check(call.implementation===choice&&call.backend===backend,'Probe selected wrong block');
        result.probes.push({backend,choice,before:item.before,after:expected,implementation_uil_sha256:call.implementation_uil_sha256});
      }
    }
  }
  for(const [owner,rng,draw] of [['wasm','wasm','wasm'],['wasm','webgpu','webgpu'],['webgpu','wasm','wasm'],['webgpu','webgpu','webgpu']]){
    shell.selectBackend(owner);shell.selectBackend(rng,['rng']);shell.selectBackend(draw,['render']);shell.selectRegionImplementation('rng','lfsr16');
    shell.replace(sourceInitial(initial,study));
    check((await shell.dispatch('reset',{[manifest.plan.events.clock]:study.initial_services.last_tick})).committed,'Alt reset failed');
    const arm={owner,rng,draw,observations:[],region_invocations:0};
    for(const row of study.rng.alternate_observations){
      if(row.intervention){const words=shell.snapshot().words;words.set(row.intervention.words,0);shell.replace(words);}
      for(const event of row.events){
        const receipt=await shell.dispatch('action',eventPatch(event,manifest.plan));check(receipt.committed,row.id+' variant action failed: '+receipt.reason);
        for(const call of regions(receipt)){check(call.implementation==='lfsr16'&&call.backend===rng,'Wrong carried RNG selection');arm.region_invocations++;}
      }
      arm.observations.push({id:row.id,...await compareObservation(shell.snapshot().words,row,manifest,study)});
    }
    result.arms.push(arm);
  }
  for(const backend of ['wasm','webgpu'])for(const choice of ['original','lfsr16']){
    shell.selectBackend(backend);shell.selectRegionImplementation('rng',choice);
    shell.replace(sourceInitial(initial,study));check((await shell.dispatch('reset',{[manifest.plan.events.clock]:100})).committed,'Outcome reset failed');
    const outcome={backend,choice,observations:[],region_invocations:0};
    for(const row of study.rng.outcome[choice]){
      for(const event of row.events){
        const receipt=await shell.dispatch('action',eventPatch(event,manifest.plan));check(receipt.committed,row.id+' outcome failed: '+receipt.reason);
        outcome.region_invocations+=regions(receipt).length;
      }
      const words=shell.snapshot().words;
      outcome.observations.push({id:row.id,...await compareObservation(words,row,manifest,study),
        head:words[0],length:words[state.snake_length],score:words[state.score],seed:words[state.rng_seed],food:words[state.food_cell],game_status:words[state.game_status]});
    }
    result.outcomes.push(outcome);
  }
  // An algorithm change preserves every current word. Its next invocation
  // consumes the current seed, including across opposite compute backends.
  for(const [from,to,seed,expected] of [['original','lfsr16',10589,41134],['lfsr16','original',2330,12219]]){
    const words=Uint32Array.from(initial);words[state.rng_seed]=seed;shell.replace(words);
    shell.selectBackend('wasm',['rng']);shell.selectRegionImplementation('rng',from);
    const before=shell.snapshot().words;shell.selectRegionImplementation('rng',to);same(shell.snapshot().words,before,'Choice reseeded state');
    shell.selectBackend('webgpu',['rng']);const receipt=await shell.dispatch('rng',{}, {render:false});check(receipt.committed,'Hot swap failed');
    check(shell.snapshot().words[state.rng_seed]===expected,'Hot swap did not carry seed');
    result.hot_swaps.push({from,to,seed,next:expected,backend:'webgpu',state_preserved_on_selection:true});
  }
  shell.selectRegionImplementation('rng','original');shell.selectBackend('wasm');
  result.checks.push('actual-original-and-alternate-region-artifacts','one-word-footprint','independent-algorithm-and-backend-choices','full-alternative-state-and-raster-replay','same-controls-different-game-outcomes','hot-swap-current-seed-without-reset');
  result.reference=study.rng.reference;
  return result;
}
