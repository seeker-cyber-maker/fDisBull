'use strict';
/** Native/source comparison of independent current BLA original/LASIK trees. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {analyzeCurrentModules,extractCurrentV6RuntimeMetadata}=require('./bla_current_module_analysis.cjs');
const {verifyCurrentModuleRuntime}=require('./bla_current_module_runtime.cjs');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function sourceModules(tree) {
  const modules=tree.pins.filter(x=>x.path.endsWith('.cjs')).map(pin=>({path:pin.path,
    source:fs.readFileSync(path.join(tree.root,pin.path),'utf8')}));
  const html=tree.pins.find(x=>x.path==='panel.html');
  if(html) {
    const source=fs.readFileSync(path.join(tree.root,html.path),'utf8');
    const pattern=/<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi;
    let match,index=0;
    while((match=pattern.exec(source))) {
      const attrs=match[1]||'';
      if(/\bsrc\s*=/.test(attrs)||/\btype\s*=\s*["']?(?!text\/javascript|module|application\/javascript)/i.test(attrs))continue;
      modules.push({path:`panel.html#script:${index++}`,source:match[2]});
    }
  }
  return modules;
}
function wasmSurface(root) {
  const raw=fs.readFileSync(path.join(root,'core.wasm')),module=new WebAssembly.Module(raw);
  const exports=WebAssembly.Module.exports(module),imports=WebAssembly.Module.imports(module);
  return {source_sha256:sha(raw),bytes:raw.length,export_count:exports.length,import_count:imports.length,
    exports:exports.map(x=>({name_sha256:sha(x.name),kind:x.kind,
      ...(['mix','seal'].includes(x.name)?{admitted_name:x.name}:{})})),
    imports_sha256:sha(JSON.stringify(imports)),name_custom_section_count:WebAssembly.Module.customSections(module,'name').length,
    target_functions_executed:false};
}
function apiProjection(runtime) {
  const result=[];
  for(let i=0;i<runtime.original.modules.length;i++) {
    const a=runtime.original.modules[i],b=runtime.reduced.modules[i];
    const calls=row=>row.controls.find(x=>x.phase==='native_exit_observed')?.calls||[];
    const left=calls(a),right=calls(b);
    if(a.label!==b.label||left.length!==right.length)throw Error('Public call coverage mismatch');
    for(let j=0;j<left.length;j++) {
      const project=row=>Object.fromEntries(Object.entries(row).filter(([key])=>
        !['global_descriptor_delta','process_event_listener_delta','exports_before','exports_after'].includes(key)));
      const original=project(left[j]),reduced=project(right[j]);
      result.push({module:a.label,export:original.export,input_class:original.input_class,
        original,reduced,equal:JSON.stringify(original)===JSON.stringify(reduced)});
    }
  }
  return {scope:'Finite synchronous result/throw descriptor projection; global/listener/export reflection remains separately observed',rows:result};
}
function run(config) {
  if(!config||!Array.isArray(config.editions)||config.editions.length!==2||!config.babelRoot)
    throw Error('Bounded verified configuration required');
  const editions=config.editions.map(item=>{
    const originalModules=sourceModules(item.original),reducedModules=sourceModules(item.reduced);
    const analysis=analyzeCurrentModules({originalModules,reducedModules,babelRoot:config.babelRoot,
      entryPaths:[item.edition==='v6'?'vault.cjs':'cli/meridian.cjs']});
    let honeypotInputs=[];
    if(item.edition==='v6') {
      const metadata=extractCurrentV6RuntimeMetadata({source:reducedModules.find(x=>x.path==='vault.cjs').source,babelRoot:config.babelRoot});
      if(metadata.status!=='source_qualified_literal_candidates')throw Error('Retired key branch not source-qualified');
      honeypotInputs=metadata.honeypotInputs;
    }
    const runtime=verifyCurrentModuleRuntime({...item,honeypotInputs});
    return {edition:item.edition,analysis,runtime,api_comparison:apiProjection(runtime),...(item.edition==='v6'?{wasm:{
      original:wasmSurface(item.original.root),reduced:wasmSurface(item.reduced.root)}}:{})};
  });
  return {format:'fdisbull-bla-current-module-driver-1',editions};
}
module.exports={run,sourceModules,wasmSurface,apiProjection};
if(require.main===module) {
  try {
    const input=fs.readFileSync(0,'utf8');if(Buffer.byteLength(input)>262144)throw Error('Oversized configuration');
    process.stdout.write(JSON.stringify(run(JSON.parse(input))));
  }catch(_){process.stderr.write('Current BLA module campaign failed; no qualified receipt\n');process.exitCode=2;}
}
