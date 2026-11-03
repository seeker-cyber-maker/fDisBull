// Focused natural-play switch through the production loader, real Wasm/Metal,
// native loopback fetch, and unchanged source-derived input/renderer adapters.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {sourceInitial,eventPatch,compareObservation} from './snake_browser_study.mjs';
const [bundleArg,studyArg,npmArg,outputArg]=process.argv.slice(2);
const check=(ok,message)=>{if(!ok)throw Error(message);};
check(outputArg,'BUNDLE STUDY PRIVATE_NPM_ROOT NEW_OUTPUT');
const bundle=path.resolve(bundleArg),output=path.resolve(outputArg),study=JSON.parse(await fs.readFile(studyArg));
const bytes=await fs.readFile(path.join(bundle,'memory-shell.json')),manifest=JSON.parse(bytes);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const prefix='/'+crypto.randomBytes(20).toString('hex')+'/',allowed=new Map([[prefix+'memory-shell.json',bytes]]);
for(const [name,hash] of Object.entries(manifest.artifacts)){
  const data=await fs.readFile(path.join(bundle,name));check(sha(data)===hash,'Asset identity differs');allowed.set(prefix+name,data);
}
const server=http.createServer((req,res)=>{
  const data=allowed.get(new URL(req.url,'http://127.0.0.1').pathname);
  if(req.method!=='GET'||!data){res.writeHead(404);res.end();return;}res.end(data);
});
const require=createRequire(path.join(path.resolve(npmArg),'package.json'));
const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));Object.assign(globalThis,globals);
let gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND||'metal')]),shell;
const adapters=[],requestAdapter=gpu.requestAdapter;
gpu.requestAdapter=async function(...args){
  const adapter=await Reflect.apply(requestAdapter,this,args);
  check(adapter&&adapter.info.isFallbackAdapter===false,'Hardware adapter required');
  adapters.push({vendor:adapter.info.vendor,architecture:adapter.info.architecture,isFallbackAdapter:adapter.info.isFallbackAdapter});
  return adapter;
};
Object.defineProperty(navigator,'gpu',{configurable:true,value:gpu});
try{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  globalThis.location=new URL(`http://127.0.0.1:${server.address().port}${prefix}index.html`);
  const {loadMemoryShell}=await import(pathToFileURL(path.join(bundle,'memory-shell.mjs')));
  const initial=JSON.parse(allowed.get(prefix+'initial.json'));
  const result={status:'passed',module_uil_sha256:manifest.module_uil_sha256,arms:[],
    manifest_sha256:sha(bytes),study_sha256:sha(await fs.readFile(studyArg)),
    scope:'Natural game-input route; switch after first meal without board or seed edits; production loader over finite loopback allowlist'};
  for(const [owner,rng] of [['wasm','webgpu'],['webgpu','wasm']]){
    shell=await loadMemoryShell();check(shell.capabilities().backends.webgpu,'Real GPU required');
    shell.selectBackend(owner);shell.selectBackend(rng,['rng']);shell.replace(sourceInitial(initial,study));
    check((await shell.dispatch('reset',{[manifest.plan.events.clock]:100})).committed,'Reset failed');
    const arm={owner,rng,observations:[],region_invocations:[]};let index=0;
    for(const row of study.rng.outcome.hot_swap){
      index++;
      if(index===5){
        const before=shell.snapshot();check(before.words[606]===10589&&before.words[612]===389,'First original meal differs');
        shell.selectRegionImplementation('rng','lfsr16');const after=shell.snapshot();
        check(before.words.every((value,n)=>value===after.words[n]),'Algorithm selection changed state');
        arm.selection={after_step:4,seed:after.words[606],food:after.words[612],state_unchanged:true};
      }
      for(const event of row.events){
        const receipt=await shell.dispatch('action',eventPatch(event,manifest.plan));check(receipt.committed,row.id+' failed');
        arm.region_invocations.push(...receipt.execution.filter(x=>x.function==='rng').map(x=>({...x,step:index})));
      }
      const words=shell.snapshot().words;arm.observations.push({id:row.id,...await compareObservation(words,row,manifest,study),seed:words[606],food:words[612],length:words[600],score:words[605],game_status:words[604]});
    }
    check(arm.region_invocations.length===2&&arm.region_invocations[0].implementation==='original'&&arm.region_invocations[0].step===4&&arm.region_invocations[1].implementation==='lfsr16'&&arm.region_invocations[1].step===23,'Future meal did not use selected algorithm');
    check(arm.observations[22].seed===41134&&arm.observations[22].food===334,'New algorithm did not inherit current seed');
    await shell.dispose();shell=null;result.arms.push(arm);
  }
  result.adapters=adapters;
  await fs.writeFile(output,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:result.status,arms:result.arms.length,steps_per_arm:26,seed_after_second_meal:41134,food_after_second_meal:334}));
}finally{
  await shell?.dispose();server.closeAllConnections();if(server.listening)await new Promise(r=>server.close(r));delete navigator.gpu;gpu=null;
}
