'use strict';
/** Finite observations of authorized CJS targets through native Node providers.
 * Source is compiled unchanged in isolated children. This is not a sandbox or
 * a proof of equivalence. Keys enter children over stdin, never OS arguments.
 */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const digest=value=>sha(JSON.stringify(value));
const HASH=/^[0-9a-f]{64}$/;
const SCHEMA='bla-native-module-cli-v1';

function fingerprint() {
  return {node:process.version,openssl:process.versions.openssl,fips:crypto.getFips(),
    executable_sha256:sha(fs.readFileSync(process.execPath))};
}
function validateTarget(target) {
  if (!target || typeof target.source!=='string' || Buffer.byteLength(target.source)>1024*1024 ||
      typeof target.filename!=='string' || !path.isAbsolute(target.filename) ||
      (target.source_sha256!==undefined && target.source_sha256!==sha(target.source)))
    throw Error('Invalid native module source receipt');
  return {source:target.source,filename:target.filename,source_sha256:sha(target.source)};
}
function readWitness(witnessPath,commitment) {
  if (witnessPath===null || witnessPath===undefined)
    return {key:null,receipt:{status:'missing',real_valid_key_verified:false}};
  if (typeof witnessPath!=='string' || !path.isAbsolute(witnessPath))
    throw Error('Witness must be an explicit absolute external path');
  let bytes,key;
  try {
    if (fs.statSync(witnessPath).size>65536) throw Error('bound');
    bytes=fs.readFileSync(witnessPath);
    const text=bytes.toString('utf8');
    if (text.trimStart().startsWith('{')) {
      const value=JSON.parse(text);
      key=value.key===undefined?value.authorization_key:value.key;
    } else key=text.replace(/\r?\n$/,'');
  } catch (_) {throw Error('Cannot read bounded external key witness');}
  if (typeof key!=='string' || key.length<12 || key.length>96 || sha(key)!==commitment.keySha256)
    throw Error('External key witness does not match the pinned commitment');
  return {key,receipt:{status:'commitment_matched_pending_native_acceptance',
    real_valid_key_verified:false,path_sha256:sha(witnessPath),file_sha256:sha(bytes),
    key_sha256:sha(key)}};
}
function casesFor(key) {
  const cases=[
    {label:'missing',argv:[],has_argument:false},
    {label:'empty',argv:[''],value:''},
    {label:'short',argv:['x'.repeat(11)],value:'x'.repeat(11)},
    {label:'min_length_wrong_key',argv:['x'.repeat(12)],value:'x'.repeat(12)},
    {label:'max_length_wrong_key',argv:['x'.repeat(96)],value:'x'.repeat(96)},
    {label:'too_long',argv:['x'.repeat(97)],value:'x'.repeat(97)},
    {label:'unicode_wrong_key',argv:['λ☃😀'.repeat(5)],value:'λ☃😀'.repeat(5)},
    {label:'honeypot',argv:['/internal/v2/license/verify-entitlement'],value:'/internal/v2/license/verify-entitlement'},
    {label:'ordinary_wrong_key',argv:['authored-rejection-input-2026'],value:'authored-rejection-input-2026'},
  ];
  if (key!==null) {
    // Never label an incidental matching fixture as a rejection input.
    for (const row of cases) if (row.value===key) row.expected_acceptance=true;
    const changed=(key[0]==='A'?'B':'A')+key.slice(1);
    cases.push({label:'valid_key',argv:[key],value:key,expected_acceptance:true},
      {label:'valid_key_extra_argument',argv:[key,'ignored-authored-argument'],value:key,expected_acceptance:true},
      {label:'single_character_mutation',argv:[changed],value:changed});
  }
  return cases;
}
function keyReceipt(key) {
  return typeof key==='symbol'?{kind:'symbol',name_sha256:sha(String(key))}:
    {kind:'string',name_sha256:sha(key)};
}
function valueReceipt(value,depth=0,seen=new Set()) {
  if (value===null) return {type:'null'};
  const type=typeof value;
  if (type==='function') return {type,arity:value.length,name_sha256:sha(value.name)};
  if (type!=='object') return {type,value_sha256:sha(type==='bigint'?String(value):
    type==='symbol'?String(value):type==='undefined'?'undefined':
      type==='number'?(Object.is(value,-0)?'-0':String(value)):JSON.stringify(value))};
  if (seen.has(value)) return {type:'object',cycle:true};
  if (depth>=4) return {type:'object',depth_limit:true};
  seen.add(value);
  const keys=Reflect.ownKeys(value);
  if (keys.length>64) return {type:'object',property_count:keys.length,bound_exceeded:true};
  const properties=keys.map(key=>({key:keyReceipt(key),
    descriptor:descriptorReceipt(Object.getOwnPropertyDescriptor(value,key),depth+1,seen)}));
  return {type:'object',prototype:Object.getPrototypeOf(value)===Object.prototype?'Object':
    Object.getPrototypeOf(value)===null?'null':Array.isArray(value)?'Array':'other',
    extensible:Object.isExtensible(value),properties};
}
function descriptorReceipt(descriptor,depth=0,seen=new Set()) {
  if (!descriptor) return null;
  const common={enumerable:descriptor.enumerable,configurable:descriptor.configurable};
  if ('value' in descriptor) return {...common,kind:'data',writable:descriptor.writable,
    value:valueReceipt(descriptor.value,depth,seen)};
  return {...common,kind:'accessor',get:descriptor.get?valueReceipt(descriptor.get):null,
    set:descriptor.set?valueReceipt(descriptor.set):null};
}
function globalSnapshot() {
  return new Map(Reflect.ownKeys(globalThis).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
}
function measuredGlobalBaseline() {
  // V8 lazy global descriptors can initialize native facilities when their
  // descriptor is read. Separate those observer effects from target effects.
  const initialKeys=new Set(Reflect.ownKeys(globalThis));
  for (let attempt=0;attempt<4;attempt++) {
    const snapshot=globalSnapshot(),keys=Reflect.ownKeys(globalThis);
    if (keys.length===snapshot.size && keys.every(key=>snapshot.has(key)))
      return {snapshot,observer_bootstrap_global_additions:keys.filter(key=>!initialKeys.has(key)).map(key=>{
        const descriptor=snapshot.get(key);
        return {key:keyReceipt(key),enumerable:descriptor.enumerable,configurable:descriptor.configurable,
          kind:'value' in descriptor?'data':'accessor',value_type:'value' in descriptor?typeof descriptor.value:undefined};
      })};
  }
  throw Error('Native global descriptor enumeration did not stabilize');
}
function sameDescriptor(a,b) {
  if (!a || !b) return a===b;
  return ['enumerable','configurable','writable','value','get','set'].every(key=>
    Object.is(a[key],b[key]) && (key in a)===(key in b));
}
function globalDelta(before,after) {
  const keys=[...new Set([...before.keys(),...after.keys()])];
  return keys.filter(key=>!sameDescriptor(before.get(key),after.get(key))).map(key=>({
    key:keyReceipt(key),change:!before.has(key)?'added':!after.has(key)?'removed':'modified',
    before:descriptorReceipt(before.get(key)),after:descriptorReceipt(after.get(key)),
  }));
}
function execute(request) {
  const target=validateTarget(request);
  if (!['module','cli'].includes(request.mode) || !request.commitment ||
      !HASH.test(request.commitment.keySha256) || !HASH.test(request.commitment.flagSha256) ||
      !Array.isArray(request.cases) || request.cases.length>32)
    throw Error('Invalid native module probe request');
  const emit=value=>fs.writeSync(3,JSON.stringify(value)+'\n');
  emit({phase:'started',source_sha256:target.source_sha256,runtime:fingerprint()});
  const Module=require('node:module');
  const loaded=new Module(target.filename,module);
  loaded.filename=target.filename;
  loaded.paths=Module._nodeModulePaths(path.dirname(target.filename));
  if (request.mode==='cli') {
    if (!Array.isArray(request.argv) || request.argv.length>8 ||
        request.argv.some(value=>typeof value!=='string' || value.length>1024))
      throw Error('Invalid native CLI arguments');
    loaded.id='.';
    process.argv=[process.execPath,target.filename,...request.argv];
    process.mainModule=loaded;
    loaded._compile(target.source,target.filename);
    emit({phase:'cli_returned',source_sha256:target.source_sha256});
    return;
  }
  const baseline=measuredGlobalBaseline(),before=baseline.snapshot;
  loaded._compile(target.source,target.filename);
  const after=globalSnapshot();
  if (typeof loaded.exports.tryUnlock!=='function') throw Error('Missing native unlock export');
  const exportsBefore=valueReceipt(loaded.exports);
  const rows=request.cases.map(row=>{
    let value;
    try {
      value=loaded.exports.tryUnlock(row.has_argument===false?undefined:row.value);
      return {input_class:row.label,result_kind:'return',
        result_type:value===null?'null':typeof value,
        result_sha256:typeof value==='string'?sha(value):digest(valueReceipt(value)),
        flag_commitment_matches:typeof value==='string' && sha(value)===request.commitment.flagSha256};
    } catch(error) {return {input_class:row.label,result_kind:'throw',
      error_name_sha256:sha(String(error.name)),error_message_sha256:sha(String(error.message)),
      flag_commitment_matches:false};}
  });
  emit({phase:'module_completed',source_sha256:target.source_sha256,
    exports:exportsBefore,exports_after_calls:valueReceipt(loaded.exports),
    observer_bootstrap_global_additions:baseline.observer_bootstrap_global_additions,
    initialization_global_descriptor_delta:globalDelta(before,after),
    call_global_descriptor_delta:globalDelta(after,globalSnapshot()),rows});
}
function probe(target,mode,cases,commitment,argv,runtime) {
  const child=spawnSync(process.execPath,['--max-old-space-size=256',__filename,'--child'],{
    input:JSON.stringify({...target,mode,cases,commitment,argv}),
    timeout:10000,maxBuffer:1024*1024,env:{PATH:process.env.PATH||''},
    stdio:['pipe','pipe','pipe','pipe']});
  if (child.error || child.signal || child.status===null)
    throw Error('Bounded native module/CLI probe failed');
  let records;
  try {records=child.output[3].toString('utf8').trim().split('\n').filter(Boolean).map(JSON.parse);}
  catch (_) {throw Error('Invalid native module/CLI control receipt');}
  const started=records.shift();
  if (!started || started.phase!=='started' || started.source_sha256!==target.source_sha256 ||
      JSON.stringify(started.runtime)!==JSON.stringify(runtime))
    throw Error('Native module/CLI identity mismatch');
  const completed=records.find(row=>row.phase==='module_completed');
  if (mode==='module' && (!completed || child.status!==0 || completed.source_sha256!==target.source_sha256))
    throw Error('Native require probe did not complete');
  const stdout=child.stdout||Buffer.alloc(0),stderr=child.stderr||Buffer.alloc(0);
  let flagMatches=false;
  const prefix=Buffer.from('[+] Access Granted! Flag: ');
  if (mode==='cli' && stdout.subarray(0,prefix.length).equals(prefix) && stdout.at(-1)===10)
    flagMatches=sha(stdout.subarray(prefix.length,-1))===commitment.flagSha256;
  return {stdout,stderr,receipt:{exit_status:child.status,
    stdout_bytes:stdout.length,stdout_sha256:sha(stdout),stderr_bytes:stderr.length,stderr_sha256:sha(stderr),
    ...(mode==='module'?{observation:completed}:{
      native_cli_dispatch_returned:records.some(row=>row.phase==='cli_returned'),
      flag_commitment_matches:flagMatches})}};
}
function equalObservation(a,b) {
  const comparable=receipt=>{
    if (!receipt.observation) return receipt;
    const {source_sha256,phase,...observation}=receipt.observation;
    return {...receipt,observation};
  };
  return a.stdout.equals(b.stdout) && a.stderr.equals(b.stderr) &&
    JSON.stringify(comparable(a.receipt))===JSON.stringify(comparable(b.receipt));
}
function verifyModuleRuntime({reference,targets,commitment,witnessPath=null}) {
  if (!commitment || !HASH.test(commitment.keySha256) || !HASH.test(commitment.flagSha256) ||
      !Array.isArray(targets) || targets.length<1 || targets.length>8)
    throw Error('Invalid native module verification configuration');
  const clean=validateTarget(reference);
  const boundTargets=targets.map(target=>{
    if (typeof target.tier!=='string' || !/^[A-Za-z0-9_-]{1,32}$/.test(target.tier))
      throw Error('Invalid native target label');
    return {tier:target.tier,...validateTarget(target)};
  });
  const runtime=fingerprint(),witness=readWitness(witnessPath,commitment);
  const cases=casesFor(witness.key);
  const run=target=>{
    const nativeModule=probe(target,'module',cases,commitment,undefined,runtime);
    const cli=cases.map(row=>({label:row.label,expected_acceptance:row.expected_acceptance===true,
      result:probe(target,'cli',[],commitment,row.argv,runtime)}));
    const moduleRows=nativeModule.receipt.observation.rows;
    const valid=moduleRows.filter(row=>cases.find(item=>item.label===row.input_class).expected_acceptance===true);
    const rejected=moduleRows.filter(row=>!cases.find(item=>item.label===row.input_class).expected_acceptance);
    const rejectionVerified=rejected.every(row=>row.result_kind==='return' && row.result_type==='null') &&
      cli.filter(row=>!row.expected_acceptance).every(row=>row.result.receipt.exit_status===1 &&
        !row.result.receipt.flag_commitment_matches && !row.result.receipt.native_cli_dispatch_returned);
    const acceptanceVerified=witness.key!==null && valid.length>=2 && valid.every(row=>
      row.result_kind==='return' && row.result_type==='string' && row.flag_commitment_matches) &&
      cli.filter(row=>row.expected_acceptance).every(row=>row.result.receipt.exit_status===0 &&
        row.result.receipt.stderr_bytes===0 && row.result.receipt.flag_commitment_matches &&
        !row.result.receipt.native_cli_dispatch_returned);
    return {nativeModule,cli,rejectionVerified,acceptanceVerified};
  };
  const baseline=run(clean);
  const receipt=result=>({module:result.nativeModule.receipt,
    cli:result.cli.map(row=>({input_class:row.label,...row.result.receipt})),
    rejection_paths_verified:result.rejectionVerified,real_valid_key_acceptance_verified:result.acceptanceVerified});
  const observations=boundTargets.map(target=>{
    const bound=target,result=run(bound);
    const cleanObs=baseline.nativeModule.receipt.observation,targetObs=result.nativeModule.receipt.observation;
    const cliRows=result.cli.map((row,index)=>({...receipt(result).cli[index],
      equal_to_reference:equalObservation(baseline.cli[index].result,row.result)}));
    return {tier:target.tier,source_sha256:bound.source_sha256,...receipt(result),cli:cliRows,
      function_results_equal:JSON.stringify(cleanObs.rows)===JSON.stringify(targetObs.rows),
      export_reflection_equal:JSON.stringify(cleanObs.exports)===JSON.stringify(targetObs.exports),
      initialization_global_effects_equal:JSON.stringify(cleanObs.initialization_global_descriptor_delta)===
        JSON.stringify(targetObs.initialization_global_descriptor_delta),
      module_observations_equal:equalObservation(baseline.nativeModule,result.nativeModule),
      cli_observations_equal:cliRows.every(row=>row.equal_to_reference)};
  });
  const acceptance=baseline.acceptanceVerified && observations.every(row=>row.real_valid_key_acceptance_verified);
  const rejections=baseline.rejectionVerified && observations.every(row=>row.rejection_paths_verified);
  const witnessReceipt={...witness.receipt,real_valid_key_verified:acceptance,
    status:witness.key===null?'missing':acceptance?'verified_against_real_native_implementations':'native_acceptance_failed'};
  return {schema:SCHEMA,status:!rejections?'native_rejection_validation_failed':
    acceptance?'verified_finite_native_acceptance_and_rejection_observations':
    witness.key===null?'verified_finite_rejections_real_acceptance_pending':'native_acceptance_failed',runtime,
    loader_sha256:sha(fs.readFileSync(__filename)),reference_source_sha256:clean.source_sha256,
    loader:'Exact source via native CommonJS Module._compile; CLI process.mainModule and process.argv bridge; native process.exit',
    provider_substitutions:false,function_bodies_rewritten:false,target_observer_suffix:false,
    witness:witnessReceipt,reference:receipt(baseline),targets:observations,
    cases_per_cli:cases.length,real_valid_key_acceptance_verified:acceptance,
    rejection_paths_verified:rejections,
    all_cli_observations_equal:observations.every(row=>row.cli_observations_equal),
    all_module_observations_equal:observations.every(row=>row.module_observations_equal),
    limitations:[
      'Finite native observations do not prove whole-module or universal CLI equivalence.',
      'Global observations cover own descriptor changes; mutations inside pre-existing global objects are not traced.',
      'Descriptor enumeration initializes native lazy globals before measured import; observer bootstrap additions are recorded separately.',
      'Export reflection covers bounded own descriptors, function names and arity; function source and cross-run identity are excluded.',
      'Execution is an authorized-target probe, not a hostile-code sandbox.',
      ...(witness.key===null?['No external commitment-matching key witness: native valid-key acceptance remains unverified.']:[]),
    ]};
}
module.exports={verifyModuleRuntime,execute,readWitness,casesFor};
if (require.main===module) {
  try {
    const input=fs.readFileSync(0,'utf8');
    if (Buffer.byteLength(input)>1200000) throw Error('Native request exceeds bound');
    const request=JSON.parse(input);
    if (process.argv[2]==='--child') execute(request);
    else process.stdout.write(JSON.stringify(verifyModuleRuntime(request)));
  } catch (_) {process.stderr.write('Native module/CLI verification failed\n');process.exitCode=2;}
}
