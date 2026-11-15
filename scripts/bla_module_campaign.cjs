'use strict';
/** Source-bound module/CLI coordinator. Original targets and witnesses remain external. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {analyze}=require('./bla_function_analysis.cjs');
const {proveModuleEquivalence}=require('./bla_module_equivalence.cjs');
const {verifyModuleRuntime}=require('./bla_module_runtime.cjs');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');

function run(config) {
  if (!config || !path.isAbsolute(config.root||'') || !path.isAbsolute(config.babelRoot||'') ||
      !Array.isArray(config.targets) || config.targets.length!==3 ||
      JSON.stringify(config.targets.map(x=>x.tier))!==JSON.stringify(['L1','L2','L3']))
    throw Error('Bounded source configuration required');
  function readSource(item) {
    if (!item || typeof item.path!=='string' || path.isAbsolute(item.path) ||
        item.path.split(/[\\/]/).includes('..') || !/^[a-f0-9]{64}$/.test(item.sha256))
      throw Error('Invalid source identity');
    const filename=path.resolve(config.root,item.path);
    if (fs.statSync(filename).size>2*1024*1024) throw Error('Oversized source');
    const raw=fs.readFileSync(filename);
    if (raw.length>2*1024*1024 || sha(raw)!==item.sha256) throw Error('Changed source identity');
    const source=raw.toString('utf8');
    if (!Buffer.from(source).equals(raw)) throw Error('Invalid UTF-8 source');
    return {source,filename};
  }
  const template=readSource(config.template);
  const targets=config.targets.map(item=>({...readSource(item),tier:item.tier}));
  let reference;
  const proofs=targets.map(target=>{
    const analysis=analyze(template.source,target.source,{babelRoot:config.babelRoot});
    if (!analysis.runtime.staticQualified) throw Error('Core source relation is unqualified');
    const candidate=analysis.runtime.materializedCleanSource;
    if (reference!==undefined && reference!==candidate) throw Error('Reference constants differ');
    reference=candidate;
    return {tier:target.tier,proof:proveModuleEquivalence({templateSource:template.source,
      targetSource:target.source,babelRoot:config.babelRoot})};
  });
  const runtime=verifyModuleRuntime({reference:{source:reference,
      filename:path.join(config.root,'challenge/archive/v6-tiered-protect/clean/materialized-reference.cjs')},
    targets,commitment:config.commitment,witnessPath:config.witnessPath||null});
  return {format:'fdisbull-bla-module-driver-1',template_sha256:sha(template.source),
    reference_sha256:sha(reference),proofs,runtime};
}
module.exports={run};
if (require.main===module) {
  try {
    const input=fs.readFileSync(0,'utf8');
    if (Buffer.byteLength(input)>65536) throw Error('Oversized configuration');
    process.stdout.write(JSON.stringify(run(JSON.parse(input))));
  } catch (_) {process.stderr.write('BLA module campaign failed; no verified receipt\n');process.exitCode=2;}
}
