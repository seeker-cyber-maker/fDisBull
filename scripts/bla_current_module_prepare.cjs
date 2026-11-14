'use strict';
/** Prepare independent original/reduced trees. Never executes target code. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const zlib=require('node:zlib');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function canonical(value) {
  if(Array.isArray(value))return value.map(canonical);
  if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));
  return value;
}
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
function inventory(root) {
  const rows=[];
  function walk(dir) {
    for(const entry of fs.readdirSync(dir,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))) {
      const filename=path.join(dir,entry.name);
      if(entry.isDirectory())walk(filename);
      else if(entry.isFile()) {
        const size=fs.statSync(filename).size;
        if(size>16*1024*1024)throw Error('Source file exceeds preparation bound');
        const raw=fs.readFileSync(filename);
        rows.push({path:path.relative(root,filename).split(path.sep).join('/'),bytes:raw.length,sha256:sha(raw)});
      } else throw Error('Nonregular preparation entry');
    }
  }
  walk(root);return rows;
}
async function prepare(config) {
  if(!config||!path.isAbsolute(config.outputRoot||'')||!path.isAbsolute(config.lasikRoot||'')||
     !Array.isArray(config.editions)||JSON.stringify(config.editions.map(x=>x.edition))!==JSON.stringify(['v6','v7']))
    throw Error('Invalid preparation configuration');
  const dist=path.join(config.lasikRoot,'dist'),entry=path.join(dist,'engine/run.js');
  const distribution=inventory(dist),metadata=JSON.parse(fs.readFileSync(path.join(config.lasikRoot,'package.json')));
  const {run}=await import(pathToFileURL(entry).href);
  fs.mkdirSync(config.outputRoot); // Refuse replacement or reuse of any earlier preparation.
  const editions=[];
  for(const item of config.editions) {
    if(!path.isAbsolute(item.sourceRoot||'')||!Array.isArray(item.pins))throw Error('Invalid source descriptor');
    const before=inventory(item.sourceRoot);
    if(!same(before,item.pins))throw Error('Source pins changed before preparation');
    const base=path.join(config.outputRoot,item.edition),original=path.join(base,'original'),reduced=path.join(base,'reduced');
    fs.mkdirSync(original,{recursive:true});
    for(const pin of before) {
      const target=path.join(original,pin.path);fs.mkdirSync(path.dirname(target),{recursive:true});
      fs.copyFileSync(path.join(item.sourceRoot,pin.path),target,fs.constants.COPYFILE_EXCL);
    }
    const report=run(item.sourceRoot,'heal',{outDir:reduced,firewall:false,maxBytes:16*1024*1024});
    if(!same(before,inventory(item.sourceRoot)))throw Error('Original changed during reduction');
    if(item.edition==='v6') {
      for(const root of [original,reduced]) {
        const raw=zlib.gunzipSync(fs.readFileSync(path.join(root,'core.wasm.gz')),{maxOutputLength:16*1024*1024});
        fs.writeFileSync(path.join(root,'core.wasm'),raw,{flag:'wx'});
      }
    }
    const originalPins=inventory(original),reducedPins=inventory(reduced);
    editions.push({edition:item.edition,source_root:item.sourceRoot,source_pins:before,
      original:{root:original,pins:originalPins},reduced:{root:reduced,pins:reducedPins},
      transformation:{target_executed:false,firewall:false,aggressive:false,rename:true,
        files:report.files.map(f=>({path:f.file,format:f.format,bytes_before:f.bytesBefore,bytes_after:f.bytesAfter,
          changed:f.healed,warnings:f.warnings,techniques:f.findings.map(x=>({layer:x.layer,technique:x.technique,count:x.count}))}))}});
  }
  if(!same(distribution,inventory(dist)))throw Error('LASIK distribution changed');
  const result={format:'fdisbull-bla-current-preparation-1',source_commit:config.sourceCommit,
    lasik:{package:metadata.name,version:metadata.version,root:config.lasikRoot,entry_sha256:sha(fs.readFileSync(entry)),
      distribution_sha256:sha(JSON.stringify(distribution)),distribution,build_provenance_verified:false},
    editions,source_executed_during_preparation:false,independent_filesystem_trees:true};
  result.manifest_sha256=sha(JSON.stringify(result));
  fs.writeFileSync(path.join(config.outputRoot,'preparation.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
  return result;
}
async function verifyPrepared(config) {
  if(fs.statSync(config.manifestPath).size>1024*1024)throw Error('Oversized manifest');
  const manifest=JSON.parse(fs.readFileSync(config.manifestPath,'utf8'));
  const {manifest_sha256,...payload}=manifest;
  if(sha(JSON.stringify(payload))!==manifest_sha256)throw Error('Preparation manifest digest changed');
  if(manifest.format!=='fdisbull-bla-current-preparation-1'||manifest.source_commit!==config.sourceCommit||
     manifest.lasik.root!==config.lasikRoot||manifest.editions.length!==2)throw Error('Unbound preparation');
  const dist=inventory(path.join(config.lasikRoot,'dist'));
  const metadata=JSON.parse(fs.readFileSync(path.join(config.lasikRoot,'package.json')));
  if(manifest.lasik.package!==metadata.name||manifest.lasik.version!==metadata.version||
     manifest.lasik.entry_sha256!==sha(fs.readFileSync(path.join(config.lasikRoot,'dist/engine/run.js'))))
    throw Error('LASIK entry identity changed');
  if(!same(dist,manifest.lasik.distribution)||sha(JSON.stringify(dist))!==manifest.lasik.distribution_sha256)
    throw Error('LASIK distribution changed');
  const [{healJs},{healHtml},{healWasm}]=await Promise.all([
    import(pathToFileURL(path.join(config.lasikRoot,'dist/js/heal.js')).href),
    import(pathToFileURL(path.join(config.lasikRoot,'dist/js/html.js')).href),
    import(pathToFileURL(path.join(config.lasikRoot,'dist/formats/wasm.js')).href)]);
  const seenInodes=new Set(),roots=new Set();
  for(let i=0;i<2;i++) {
    const actual=manifest.editions[i],expected=config.editions[i];
    if(actual.edition!==expected.edition||actual.source_root!==expected.sourceRoot||
       !same(inventory(expected.sourceRoot),expected.pins)||
       !same(actual.source_pins,expected.pins))throw Error('Source preparation pin changed');
    for(const tree of [actual.original,actual.reduced]) {
      const real=fs.realpathSync(tree.root);if(roots.has(real))throw Error('Shared original/candidate root');roots.add(real);
      if(!same(inventory(tree.root),tree.pins))throw Error('Prepared tree changed');
      for(const pin of tree.pins) {
        const stat=fs.statSync(path.join(tree.root,pin.path)),id=`${stat.dev}:${stat.ino}`;
        if(seenInodes.has(id))throw Error('Original/candidate files share an inode');seenInodes.add(id);
      }
    }
    const expectedPaths=expected.pins.map(x=>x.path).concat(actual.edition==='v6'?['core.wasm']:[]).sort();
    for(const tree of [actual.original,actual.reduced])
      if(JSON.stringify(tree.pins.map(x=>x.path).sort())!==JSON.stringify(expectedPaths))throw Error('Unreviewed prepared file');
    for(const pin of expected.pins) {
      const filename=path.join(expected.sourceRoot,pin.path),input=fs.readFileSync(filename);
      if(!fs.readFileSync(path.join(actual.original.root,pin.path)).equals(input))throw Error('Original copy differs');
      let output;
      if(pin.path.endsWith('.cjs')) {
        const r=healJs(input.toString('utf8'),{filename,firewall:false,rename:true});output=r.changed?Buffer.from(r.code):input;
      } else if(pin.path.endsWith('.html')) {
        const r=healHtml(input.toString('utf8'),{firewall:false,rename:true});output=r.changed?Buffer.from(r.code):input;
      } else if(pin.path.endsWith('.wasm.gz'))output=healWasm(input,filename,{}).output;
      else if(pin.path.endsWith('.json'))output=input;
      else throw Error('Unsupported pinned file type');
      if(!fs.readFileSync(path.join(actual.reduced.root,pin.path)).equals(output))throw Error('LASIK reduction replay differs');
    }
    if(actual.edition==='v6')for(const tree of [actual.original,actual.reduced])
      if(!zlib.gunzipSync(fs.readFileSync(path.join(tree.root,'core.wasm.gz')),{maxOutputLength:16*1024*1024})
        .equals(fs.readFileSync(path.join(tree.root,'core.wasm'))))throw Error('Wasm decompression differs');
  }
  return {...manifest,verification:{source_pins_checked:true,original_copies_equal:true,
    exact_reduction_replayed:true,independent_roots_and_inodes:true,raw_wasm_decompression_checked:true}};
}
module.exports={prepare,verifyPrepared,inventory};
if(require.main===module) {
  (async()=>{try {
    const input=fs.readFileSync(0,'utf8');if(Buffer.byteLength(input)>65536)throw Error('Oversized configuration');
    const config=JSON.parse(input);
    const result=config.manifestPath?await verifyPrepared(config):await prepare(config);
    process.stdout.write(JSON.stringify(config.manifestPath?result:
      {manifest:path.join(config.outputRoot,'preparation.json'),manifest_sha256:result.manifest_sha256}));
  }catch(_){process.stderr.write('Current BLA preparation failed; preserve partial output for inspection\n');process.exitCode=2;}})();
}
