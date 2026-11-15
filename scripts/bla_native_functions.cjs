'use strict';
/** Execute hash-bound CJS exports through Node's ordinary loader in a fresh
 * bounded child. This is an authorized-target probe, not a hostile-code sandbox.
 * No target observer, crypto substitute or Buffer substitute is installed.
 */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const digest=value=>sha(JSON.stringify(value));
const INPUTS=Object.freeze([
  ['empty','""'],['short','"x".repeat(11)'],['min_length','"x".repeat(12)'],
  ['max_length','"x".repeat(96)'],['too_long','"x".repeat(97)'],['unicode','"λ☃😀".repeat(5)'],
  ['null','null'],['undefined','undefined'],['number','17'],['boolean','true'],
  ['symbol','Symbol("authored")'],['honeypot','"/internal/v2/license/verify-entitlement"'],
  ['nan','NaN'],['positive_infinity','Infinity'],['negative_infinity','-Infinity'],
  ['negative_zero','-0'],['bigint','12345678901234567890n'],
]);
function inputValue(name) {
  const values={empty:()=>'',short:()=>'x'.repeat(11),min_length:()=>'x'.repeat(12),
    max_length:()=>'x'.repeat(96),too_long:()=>'x'.repeat(97),unicode:()=>'λ☃😀'.repeat(5),
    null:()=>null,undefined:()=>undefined,number:()=>17,boolean:()=>true,
    symbol:()=>Symbol('authored'),honeypot:()=>'/internal/v2/license/verify-entitlement',
    nan:()=>NaN,positive_infinity:()=>Infinity,negative_infinity:()=>-Infinity,
    negative_zero:()=>-0,bigint:()=>12345678901234567890n};
  if (!Object.hasOwn(values,name)) throw Error('Unknown native input class');
  return values[name]();
}
function fingerprint() {
  return {node:process.version,openssl:process.versions.openssl,fips:crypto.getFips(),
    executable_sha256:sha(fs.readFileSync(process.execPath))};
}
function execute(request) {
  if (!request || typeof request.source!=='string' || Buffer.byteLength(request.source)>1024*1024 ||
      !/^[0-9a-f]{64}$/.test(request.source_sha256) || sha(request.source)!==request.source_sha256 ||
      typeof request.filename!=='string' || !path.isAbsolute(request.filename)) throw Error('Invalid native source receipt');
  const Module=require('node:module');
  const loaded=new Module(request.filename,module);
  loaded.filename=request.filename;
  loaded.paths=Module._nodeModulePaths(path.dirname(request.filename));
  loaded._compile(request.source,request.filename);
  if (typeof loaded.exports.sha256Hex!=='function' || typeof loaded.exports.tryUnlock!=='function')
    throw Error('Missing native export boundary');
  const rows=[];
  for (const fn of ['sha256Hex','tryUnlock']) for (const [label] of INPUTS) {
    let result;
    try {result={kind:'return',value:loaded.exports[fn](inputValue(label)),input_effects:[]};}
    catch(error) {result={kind:'throw',name:error.name,message:error.message,input_effects:[]};}
    rows.push({function:fn,input_class:label,result_kind:result.kind,
      result_type:result.kind==='throw'?result.name:result.value===null?'null':typeof result.value,
      result_sha256:digest(result)});
  }
  return {status:'verified_native_cjs_observations',source_sha256:request.source_sha256,
    runtime:fingerprint(),loader:'Unmodified source via native CommonJS Module._compile; CLI entry not invoked',
    function_bodies_rewritten:false,provider_substitutions:false,target_observer_suffix:false,
    cases:rows.length,rows,rows_sha256:digest(rows),
    limitation:'Finite native export observations; no native implementation proof or valid-key acceptance claim'};
}
function probeNativeFunctions({source,filename}) {
  const request={source,filename,source_sha256:sha(source)};
  const child=spawnSync(process.execPath,['--max-old-space-size=256',__filename],{
    input:JSON.stringify(request),encoding:'utf8',timeout:10000,maxBuffer:1024*1024,
    env:{PATH:process.env.PATH||''}});
  if (child.error || child.status!==0) throw Error('Bounded native CJS probe failed');
  const receipt=JSON.parse(child.stdout);
  if (receipt.source_sha256!==request.source_sha256 || receipt.cases!==34 ||
      JSON.stringify(receipt.runtime)!==JSON.stringify(fingerprint())) throw Error('Native CJS probe identity mismatch');
  return receipt;
}
module.exports={probeNativeFunctions,execute,INPUTS};
if (require.main===module) {
  try {
    const input=fs.readFileSync(0,'utf8');
    if (Buffer.byteLength(input)>1200000) throw Error('Native request exceeds bound');
    process.stdout.write(JSON.stringify(execute(JSON.parse(input))));
  } catch (_) {process.stderr.write('Native CJS probe failed\n');process.exitCode=2;}
}
