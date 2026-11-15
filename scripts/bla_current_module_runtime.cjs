'use strict';
/** Finite native observations of original and independently reduced CJS trees.
 * This executes authorized targets, not hostile code in a security sandbox.
 */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const digest=value=>sha(JSON.stringify(value));
const HASH=/^[0-9a-f]{64}$/;
const fingerprint=()=>({node:process.version,openssl:process.versions.openssl,fips:crypto.getFips(),
  executable_sha256:sha(fs.readFileSync(process.execPath))});

function relativeFilename(root,name) {
  if(typeof name!=='string'||!name||path.isAbsolute(name)||name.split(/[\\/]/).some(x=>x==='..'||x===''))
    throw Error('Invalid tree-relative source path');
  const filename=path.resolve(root,name);
  if(fs.realpathSync(filename)!==filename||!filename.startsWith(root+path.sep))
    throw Error('Source must remain within its own independent tree');
  return filename;
}
function validateTree(tree,edition) {
  if(!tree||typeof tree.root!=='string'||!path.isAbsolute(tree.root)||
      !Array.isArray(tree.pins)||tree.pins.length<1||tree.pins.length>128)
    throw Error('Pinned independent tree required');
  const root=fs.realpathSync(tree.root),seen=new Set();
  let total=0;
  const pins=tree.pins.map(pin=>{
    if(!pin||!HASH.test(pin.sha256)||seen.has(pin.path))throw Error('Invalid or duplicate tree pin');
    seen.add(pin.path);
    const filename=relativeFilename(root,pin.path),size=fs.statSync(filename).size;
    total+=size;
    if(size>8*1024*1024||total>32*1024*1024||sha(fs.readFileSync(filename))!==pin.sha256)
      throw Error('Changed or oversized pinned artifact');
    return {path:pin.path,sha256:pin.sha256};
  }).sort((a,b)=>a.path.localeCompare(b.path));
  const inventory=[];
  function visit(directory,depth=0){
    if(depth>16)throw Error('Source tree directory depth exceeds bound');
    for(const entry of fs.readdirSync(directory,{withFileTypes:true})){
      const filename=path.join(directory,entry.name);
      if(entry.isSymbolicLink())throw Error('Source trees cannot contain symlinks');
      if(entry.isDirectory())visit(filename,depth+1);
      else if(entry.isFile()){
        inventory.push(path.relative(root,filename));
        if(inventory.length>128)throw Error('Source tree inventory exceeds bound');
      }else throw Error('Source tree contains a non-regular artifact');
    }
  }
  visit(root);
  if(JSON.stringify(inventory.sort())!==JSON.stringify([...seen].sort()))
    throw Error('Every regular source-tree artifact must be pinned');
  const cliEntry=tree.cliEntry||(edition==='v6'?'vault.cjs':'cli/meridian.cjs');
  const moduleEntries=tree.moduleEntries||(edition==='v6'?[{label:'vault',path:cliEntry}]:
    ['expr','units','stats','license'].map(label=>({label,path:`core/${label}.cjs`})));
  if(!Array.isArray(moduleEntries)||moduleEntries.length>12)throw Error('Bounded module entries required');
  for(const entry of [{path:cliEntry},...moduleEntries]){
    if(!seen.has(entry.path))throw Error('Every executed entry must be pinned');
    relativeFilename(root,entry.path);
  }
  const labels=new Set();
  for(const entry of moduleEntries){
    if(typeof entry.label!=='string'||!/^[A-Za-z0-9_-]{1,40}$/.test(entry.label)||labels.has(entry.label))
      throw Error('Invalid or duplicate public module label');
    labels.add(entry.label);
  }
  return {root,pins,cliEntry,moduleEntries,tree_sha256:digest(pins),root_path_sha256:sha(root)};
}
function witnessAt(filename,commitment) {
  if(typeof filename!=='string'||!path.isAbsolute(filename)||fs.statSync(filename).size>65536)
    throw Error('Explicit bounded private witness required');
  const bytes=fs.readFileSync(filename),value=JSON.parse(bytes.toString('utf8'));
  const key=value.key===undefined?value.authorization_key:value.key;
  if(typeof key!=='string'||key.length>1024||sha(key)!==commitment.keySha256)
    throw Error('Private witness does not match edition commitment');
  return {key,receipt:{file_sha256:sha(bytes),path_sha256:sha(filename),key_sha256:sha(key)}};
}
function keyReceipt(key){return {kind:typeof key==='symbol'?'symbol':'string',name_sha256:sha(String(key))};}
function valueReceipt(value,depth=0,seen=new Set()) {
  if(value===null)return {type:'null'};
  const type=typeof value;
  if(type==='function')return {type,arity:value.length,name_sha256:sha(String(value.name))};
  if(type!=='object')return {type,value_sha256:sha(type==='string'?value:
    type==='number'&&Object.is(value,-0)?'-0':String(value))};
  if(seen.has(value))return {type,shared_or_cycle:true};
  if(depth>=4)return {type,depth_limit:true};
  seen.add(value);const keys=Reflect.ownKeys(value);
  if(keys.length>64)return {type,property_count:keys.length,bound_exceeded:true};
  return {type,extensible:Object.isExtensible(value),prototype:Object.getPrototypeOf(value)===null?'null':
    Object.getPrototypeOf(value)===Object.prototype?'Object':Array.isArray(value)?'Array':'other',
    properties:keys.map(key=>({key:keyReceipt(key),descriptor:descriptorReceipt(Object.getOwnPropertyDescriptor(value,key),depth+1,seen)}))};
}
function descriptorReceipt(d,depth=0,seen=new Set()) {
  if(!d)return null;
  const common={enumerable:d.enumerable,configurable:d.configurable};
  return 'value'in d?{...common,kind:'data',writable:d.writable,value:valueReceipt(d.value,depth,seen)}:
    {...common,kind:'accessor',get:d.get?valueReceipt(d.get):null,set:d.set?valueReceipt(d.set):null};
}
function globalSnapshot(){return new Map(Reflect.ownKeys(globalThis).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));}
function stableBaseline() {
  const original=new Set(Reflect.ownKeys(globalThis));
  for(let i=0;i<4;i++){
    const snapshot=globalSnapshot(),keys=Reflect.ownKeys(globalThis);
    if(keys.length===snapshot.size&&keys.every(key=>snapshot.has(key)))return {snapshot,
      bootstrap_additions:keys.filter(key=>!original.has(key)).map(keyReceipt)};
  }
  throw Error('Native descriptor baseline did not stabilize');
}
function descriptorEqual(a,b){return a&&b?['enumerable','configurable','writable','value','get','set'].every(key=>
  (key in a)===(key in b)&&Object.is(a[key],b[key])):a===b;}
function globalDelta(before,after){return [...new Set([...before.keys(),...after.keys()])]
  .filter(key=>!descriptorEqual(before.get(key),after.get(key))).map(key=>({key:keyReceipt(key),
    change:!before.has(key)?'added':!after.has(key)?'removed':'modified',
    before:descriptorReceipt(before.get(key)),after:descriptorReceipt(after.get(key))}));}
function listenerSnapshot(){return new Map(process.eventNames().map(name=>[name,process.rawListeners(name)]));}
function listenerDelta(before,after){return [...new Set([...before.keys(),...after.keys()])].map(name=>{
  const a=before.get(name)||[],b=after.get(name)||[];
  return {event:keyReceipt(name),before_count:a.length,after_count:b.length,
    added:b.filter(fn=>!a.includes(fn)).map(fn=>valueReceipt(fn)),removed:a.filter(fn=>!b.includes(fn)).map(fn=>valueReceipt(fn))};
}).filter(row=>row.added.length||row.removed.length||row.before_count!==row.after_count);}
function exportsReceipt(value){return {public_export_names:value&&(typeof value==='object'||typeof value==='function')?
  Object.getOwnPropertyNames(value).filter(key=>/^[A-Za-z_$][A-Za-z0-9_$]{0,63}$/.test(key)):[],shape:valueReceipt(value)};}
function outputMatches(bytes,expected){
  // CLI products prefix certificates differently; the committed output must
  // occur as an exact line suffix, with no candidate plaintext in the receipt.
  for(const raw of bytes.toString('utf8').split('\n')){
    const line=raw.replace(/\r$/,'');
    for(let i=0;i<Math.min(line.length,1024);i++)if(sha(line.slice(i))===expected)return true;
  }
  return false;
}
function defaultCases(edition,key,honeypotInputs=[]) {
  const changed=(key[0]==='A'?'B':'A')+key.slice(1);
  const cases=edition==='v6'?[['missing',[]],['empty',['']],['short',['x']],['too_long',['x'.repeat(key.length+1)]],
    ['help',['--help']],['valid_key',[key]],['single_character_mutation',[changed]]]:[
    ['missing',[]],['help',['--help']],['version',['version']],['calc',['calc','2+3*4']],
    ['convert',['convert','1','mi','km']],['units',['units']],['stats',['stats','4','8','15','16','23','42']],
    ['license_missing',['license']],['license_bad_format',['license','activate','bad']],
    ['valid_key',['license','activate',key]],['single_character_mutation',['license','activate',changed]],
    ['license_extra_argument',['license','activate',key,'extra']]];
  if(!Array.isArray(honeypotInputs)||honeypotInputs.length>12)throw Error('Bounded honeypot input list required');
  honeypotInputs.forEach((value,index)=>{
    if(typeof value!=='string'||value.length>1024)throw Error('Invalid honeypot input');
    cases.push([`honeypot_${index+1}`,edition==='v6'?[value]:['license','activate',value]]);
  });
  return cases.map(([label,args])=>({label,args,args_sha256:digest(args)}));
}
function callsFor(entry,key) {
  const changed=(key[0]==='A'?'B':'A')+key.slice(1);
  const calls=entry.calls===undefined&&entry.label==='license'?
    [{export:'activate',inputClass:'valid_key'},{export:'activate',inputClass:'single_character_mutation'}]:entry.calls||[];
  if(!Array.isArray(calls)||calls.length>16)throw Error('Bounded public call list required');
  return calls.map(call=>{
    if(!call||typeof call.export!=='string'||!/^[A-Za-z_$][A-Za-z0-9_$]{0,63}$/.test(call.export)||
      typeof call.inputClass!=='string'||!/^[A-Za-z0-9_-]{1,40}$/.test(call.inputClass))throw Error('Invalid public call');
    const args=call.inputClass==='valid_key'?[key]:call.inputClass==='single_character_mutation'?[changed]:call.args||[];
    if(!Array.isArray(args)||args.length>8||Buffer.byteLength(JSON.stringify(args))>8192)throw Error('Invalid public call arguments');
    return {export:call.export,input_class:call.inputClass,args,args_sha256:digest(args)};
  });
}
function execute(request) {
  if(!request||!['cli','observed_cli','module'].includes(request.mode)||!path.isAbsolute(request.filename||'')||
    !HASH.test(request.source_sha256)||!HASH.test(request.output_sha256)||!Array.isArray(request.args)||request.args.length>16)
    throw Error('Invalid native child request');
  const source=fs.readFileSync(request.filename,'utf8');
  if(Buffer.byteLength(source)>8*1024*1024||sha(source)!==request.source_sha256)throw Error('Changed native entry');
  const emit=value=>fs.writeSync(3,JSON.stringify(value)+'\n');
  emit({phase:'started',source_sha256:request.source_sha256,runtime:fingerprint()});
  const Module=require('node:module'),loaded=new Module(request.filename,module);
  loaded.filename=request.filename;loaded.paths=Module._nodeModulePaths(path.dirname(request.filename));
  process.argv=[process.execPath,request.filename,...request.args];
  if(request.mode!=='module'){loaded.id='.';process.mainModule=loaded;}
  if(request.mode==='cli'){
    loaded._compile(source,request.filename);
    emit({phase:'synchronous_compile_returned'});
    return;
  }
  let baseline,listeners,synchronous=false;
  const calls=[];
  function snapshot(){return {global_descriptor_delta:globalDelta(baseline.snapshot,globalSnapshot()),
    process_event_listener_delta:listenerDelta(listeners,listenerSnapshot()),exports:exportsReceipt(loaded.exports)};}
  process.on('exit',code=>{
    try{emit({phase:'native_exit_observed',exit_code:code,synchronous_compile_returned:synchronous,
      final:snapshot(),calls});}
    catch(_){emit({phase:'observer_failed'});}
  });
  baseline=stableBaseline();listeners=listenerSnapshot();
  emit({phase:'observer_installed',exit_listener_installed:true,global_descriptor_priming:true,
    observer_bootstrap_global_additions:baseline.bootstrap_additions,
    native_global_add_event_listener:typeof globalThis.addEventListener,
    process_exit_observer_order:'Registered before target listeners; observes state at its native exit callback'});
  loaded._compile(source,request.filename);synchronous=true;
  emit({phase:'synchronous_return',observation:snapshot()});
  for(const call of request.calls||[]){
    const before=globalSnapshot(),beforeListeners=listenerSnapshot(),exportsBefore=exportsReceipt(loaded.exports);
    let row;
    try{
      const descriptor=Object.getOwnPropertyDescriptor(loaded.exports,call.export);
      if(!descriptor||typeof descriptor.value!=='function')throw Error('Missing public callable');
      const value=Reflect.apply(descriptor.value,loaded.exports,call.args);
      const cert=value&&typeof value==='object'?Object.getOwnPropertyDescriptor(value,'certificate'):null;
      const ok=value&&typeof value==='object'?Object.getOwnPropertyDescriptor(value,'ok'):null;
      const committed=typeof value==='string'?sha(value)===request.output_sha256:
        !!(cert&&typeof cert.value==='string'&&sha(cert.value)===request.output_sha256);
      row={result_kind:'return',result:valueReceipt(value),accepted:!!(ok&&ok.value===true),
        output_commitment_matches:committed};
    }catch(error){row={result_kind:'throw',error_name_sha256:sha(String(error.name)),
      error_message_sha256:sha(String(error.message)),accepted:false,output_commitment_matches:false};}
    calls.push({export:call.export,input_class:call.input_class,args_sha256:call.args_sha256,...row,
      global_descriptor_delta:globalDelta(before,globalSnapshot()),
      process_event_listener_delta:listenerDelta(beforeListeners,listenerSnapshot()),
      exports_before:exportsBefore,exports_after:exportsReceipt(loaded.exports)});
  }
}
function runChild(tree,entry,mode,row,calls,runtime,outputSha) {
  const filename=relativeFilename(tree.root,entry),sourceSha=tree.pins.find(pin=>pin.path===entry).sha256;
  const result=spawnSync(process.execPath,['--max-old-space-size=256',__filename,'--child'],{
    input:JSON.stringify({mode,filename,source_sha256:sourceSha,output_sha256:outputSha,args:row.args,calls}),
    stdio:['pipe','pipe','pipe','pipe'],env:{PATH:process.env.PATH||''},timeout:15000,maxBuffer:2*1024*1024});
  const stdout=result.stdout||Buffer.alloc(0),stderr=result.stderr||Buffer.alloc(0);
  let controls=[];
  try{controls=(result.output&&result.output[3]||Buffer.alloc(0)).toString('utf8').trim().split('\n').filter(Boolean).map(JSON.parse);}
  catch(_){throw Error('Invalid native control receipt');}
  const started=controls.shift();
  if(!started||started.phase!=='started'||started.source_sha256!==sourceSha||
      JSON.stringify(started.runtime)!==JSON.stringify(runtime))throw Error('Native entry identity mismatch');
  const observedExit=controls.find(value=>value.phase==='native_exit_observed');
  const completed=!result.error&&!result.signal&&result.status!==null&&
    (mode==='cli'||!!observedExit)&&!controls.some(value=>value.phase==='observer_failed');
  const receipt={input_class:row.label,args_sha256:row.args_sha256,mode,source_sha256:sourceSha,
    completed,exit_status:result.status,signal:result.signal||null,
    stdout_bytes:stdout.length,stdout_sha256:sha(stdout),stderr_bytes:stderr.length,stderr_sha256:sha(stderr),
    output_commitment_matches:outputMatches(stdout,outputSha),controls};
  return {stdout,stderr,receipt};
}
function same(a,b){
  const comparable=receipt=>{const {source_sha256,...result}=receipt;return result;};
  return a.receipt.completed&&b.receipt.completed&&a.stdout.equals(b.stdout)&&a.stderr.equals(b.stderr)&&
    JSON.stringify(comparable(a.receipt))===JSON.stringify(comparable(b.receipt));
}
function verifyCurrentModuleRuntime(config) {
  if(!config||!['v6','v7'].includes(config.edition)||!config.commitment||
    !HASH.test(config.commitment.keySha256)||!HASH.test(config.commitment.outputSha256))
    throw Error('Invalid current-edition verification configuration');
  const original=validateTree(config.original,config.edition),reduced=validateTree(config.reduced,config.edition);
  if(original.root===reduced.root)throw Error('Original and reduced require independent roots');
  const originalInodes=new Set(original.pins.map(pin=>{
    const stat=fs.statSync(relativeFilename(original.root,pin.path));return `${stat.dev}:${stat.ino}`;
  }));
  if(reduced.pins.some(pin=>{
    const stat=fs.statSync(relativeFilename(reduced.root,pin.path));return originalInodes.has(`${stat.dev}:${stat.ino}`);
  }))throw Error('Original and reduced source files cannot share inodes');
  if(original.cliEntry!==reduced.cliEntry||JSON.stringify(original.moduleEntries)!==JSON.stringify(reduced.moduleEntries))
    throw Error('Original and reduced public entry descriptions differ');
  const witness=witnessAt(config.witnessPath,config.commitment),runtime=fingerprint();
  const cases=defaultCases(config.edition,witness.key,config.honeypotInputs),outputSha=config.commitment.outputSha256;
  const observe=cases.filter(row=>['missing','valid_key','single_character_mutation'].includes(row.label));
  const run=tree=>({
    cli:cases.map(row=>runChild(tree,tree.cliEntry,'cli',row,[],runtime,outputSha)),
    measured_cli:observe.map(row=>runChild(tree,tree.cliEntry,'observed_cli',row,[],runtime,outputSha)),
    modules:tree.moduleEntries.flatMap(entry=>(config.edition==='v6'?observe:[{label:'import_and_calls',args:[],args_sha256:digest([])}])
      .map(row=>({label:entry.label,result:runChild(tree,entry.path,'module',row,callsFor(entry,witness.key),runtime,outputSha)}))),
  });
  const baseline=run(original),candidate=run(reduced);
  // Native original self-integrity reads and reduced self-integrity reads stay
  // rooted in their respective trees; no filename overlay or FS shim exists.
  for(const tree of [original,reduced])if(validateTree(tree,config.edition).tree_sha256!==tree.tree_sha256)
    throw Error('Pinned source tree changed during native observations');
  const cli=candidate.cli.map((result,index)=>({...result.receipt,equal_to_original:same(baseline.cli[index],result)}));
  const measured=candidate.measured_cli.map((result,index)=>({...result.receipt,equal_to_original:same(baseline.measured_cli[index],result)}));
  const modules=candidate.modules.map((row,index)=>({label:row.label,...row.result.receipt,
    equal_to_original:same(baseline.modules[index].result,row.result)}));
  const allResults=[...baseline.cli,...candidate.cli,...baseline.measured_cli,...candidate.measured_cli,
    ...baseline.modules.map(row=>row.result),...candidate.modules.map(row=>row.result)];
  const acceptance=result=>result.cli.find(row=>row.receipt.input_class==='valid_key').receipt;
  const originalValid=acceptance(baseline),reducedValid=acceptance(candidate);
  const originalAcceptance=originalValid.completed&&originalValid.exit_status===0&&originalValid.output_commitment_matches;
  const reducedAcceptance=reducedValid.completed&&reducedValid.exit_status===0&&reducedValid.output_commitment_matches;
  const complete=allResults.every(row=>row.receipt.completed);
  return {schema:'bla-current-native-module-comparison-1',edition:config.edition,
    status:!complete?'native_observations_incomplete':!originalAcceptance?'original_witness_acceptance_failed':
      cli.every(row=>row.equal_to_original)&&measured.every(row=>row.equal_to_original)&&modules.every(row=>row.equal_to_original)?
        'finite_observations_equal':'finite_observations_differ',runtime,
    loader_sha256:sha(fs.readFileSync(__filename)),witness:witness.receipt,
    original_tree_sha256:original.tree_sha256,reduced_tree_sha256:reduced.tree_sha256,
    original_root_path_sha256:original.root_path_sha256,reduced_root_path_sha256:reduced.root_path_sha256,
    original_real_acceptance_verified:originalAcceptance,reduced_real_acceptance_verified:reducedAcceptance,
    provider_substitutions:false,function_bodies_rewritten:false,filesystem_substitutions:false,
    target_observer_suffix:false,native_exit_replaced:false,
    original:{cli:baseline.cli.map(row=>row.receipt),measured_cli:baseline.measured_cli.map(row=>row.receipt),
      modules:baseline.modules.map(row=>({label:row.label,...row.result.receipt}))},
    reduced:{cli,measured_cli:measured,modules},all_cli_observations_equal:cli.every(row=>row.equal_to_original),
    all_measured_cli_observations_equal:measured.every(row=>row.equal_to_original),
    all_module_observations_equal:modules.every(row=>row.equal_to_original),
    observation_context:{plain_cli:{exit_listener_installed:false,global_descriptor_priming:false},
      measured_cli_and_modules:{exit_listener_installed:true,global_descriptor_priming:true,
        process_events:'Native process listener additions/removals observed; no listener wrapper installed',
        browser_events:'Native Node has no addEventListener; browser event registrations remain untested'}},
    limitations:[
      'Finite observations are not a proof of whole-module or universal CLI equivalence.',
      'Measured runs install a native exit observer and prime lazy global descriptors; plain CLI runs do neither.',
      'The exit observer runs in registration order before later target exit listeners; it cannot describe later listeners effects.',
      'Global own descriptors and bounded exported data are observed; pre-existing object internals, arbitrary memory and file writes are not traced.',
      'Export reflection includes names and arity but excludes function source strings and cross-run object identity.',
      'Calls are synchronous public export probes; pending async export results are not resolved by the call observer.',
      'Candidate self-integrity reads its own reduced siblings; no original-tree filename overlay or integrity rebinding is used.',
      'Source is compiled unchanged with native CommonJS providers; private keys enter over stdin into process.argv, never OS arguments.',
    ]};
}
module.exports={verifyCurrentModuleRuntime,execute,defaultCases};
if(require.main===module){
  if(process.argv[2]==='--child'){
    // Preserve native target exceptions and native child stderr/exit behavior.
    // The parent captures these privately and publishes only stream digests.
    execute(JSON.parse(fs.readFileSync(0,'utf8')));
  }else try{
    const text=fs.readFileSync(0,'utf8');if(Buffer.byteLength(text)>262144)throw Error('Oversized private configuration');
    const request=JSON.parse(text);
    process.stdout.write(JSON.stringify(verifyCurrentModuleRuntime(request)));
  }catch(_){process.stderr.write('Current module comparison failed\n');process.exitCode=2;}
}
