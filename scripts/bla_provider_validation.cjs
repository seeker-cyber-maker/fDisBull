'use strict';
/** Finite conformance of the actual Node SHA-256/Buffer leaves used by BLA.
 * The independent arithmetic/encoding oracles do not call these native leaves.
 * This receipt does not prove universal correctness or totality of native code.
 */
const fs = require('node:fs');
const crypto = require('node:crypto');
const {Buffer: NativeBuffer, constants: bufferConstants} = require('node:buffer');

const K = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
const hex = bytes => Array.from(bytes, x => x.toString(16).padStart(2,'0')).join('');
function pureSha256(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length > 2 ** 21) throw Error('unsupported_oracle_extent');
  const size = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(size); padded.set(bytes); padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer), bits = BigInt(bytes.length) * 8n;
  view.setUint32(size - 8, Number(bits >> 32n)); view.setUint32(size - 4, Number(bits & 0xffffffffn));
  const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const ror = (x,n) => (x >>> n) | (x << (32-n)), w = new Uint32Array(64);
  for (let offset = 0; offset < size; offset += 64) {
    for (let i=0;i<16;i++) w[i]=view.getUint32(offset+i*4);
    for (let i=16;i<64;i++) {
      const a=w[i-15],b=w[i-2];
      w[i]=(w[i-16]+(ror(a,7)^ror(a,18)^(a>>>3))+w[i-7]+(ror(b,17)^ror(b,19)^(b>>>10)))>>>0;
    }
    let [a,b,c,d,e,f,g,z]=h;
    for(let i=0;i<64;i++) {
      const t1=(z+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+K[i]+w[i])>>>0;
      const t2=((ror(a,2)^ror(a,13)^ror(a,22))+((a&b)^(a&c)^(b&c)))>>>0;
      z=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    const last=[a,b,c,d,e,f,g,z];for(let i=0;i<8;i++) h[i]=(h[i]+last[i])>>>0;
  }
  const result=new Uint8Array(32),out=new DataView(result.buffer);
  h.forEach((v,i)=>out.setUint32(i*4,v));return result;
}

function encodeUtf8(text) {
  if(typeof text!=='string'||text.length>2**20) throw Error('unsupported_utf8_extent');
  const bytes=[];
  for(let i=0;i<text.length;i++) {
    let c=text.charCodeAt(i);
    if(c>=0xd800&&c<=0xdbff) {
      const low=text.charCodeAt(i+1);
      if(low>=0xdc00&&low<=0xdfff){c=0x10000+((c-0xd800)<<10)+(low-0xdc00);i++;}else c=0xfffd;
    }else if(c>=0xdc00&&c<=0xdfff)c=0xfffd;
    if(c<0x80)bytes.push(c);
    else if(c<0x800)bytes.push(0xc0|(c>>6),0x80|(c&63));
    else if(c<0x10000)bytes.push(0xe0|(c>>12),0x80|((c>>6)&63),0x80|(c&63));
    else bytes.push(0xf0|(c>>18),0x80|((c>>12)&63),0x80|((c>>6)&63),0x80|(c&63));
  }
  return Uint8Array.from(bytes);
}
function decodeUtf8(bytes) {
  let result='';
  for(let i=0;i<bytes.length;) {
    const lead=bytes[i];if(lead<0x80){result+=String.fromCharCode(lead);i++;continue;}
    let count,code;
    if(lead>=0xc2&&lead<=0xdf){count=1;code=lead&31;}
    else if(lead>=0xe0&&lead<=0xef){count=2;code=lead&15;}
    else if(lead>=0xf0&&lead<=0xf4){count=3;code=lead&7;}
    else {result+='\ufffd';i++;continue;}
    let at=i+1,valid=true;
    for(let n=0;n<count;n++) {
      const b=bytes[at];let lower=0x80,upper=0xbf;
      if(n===0&&lead===0xe0)lower=0xa0;if(n===0&&lead===0xed)upper=0x9f;
      if(n===0&&lead===0xf0)lower=0x90;if(n===0&&lead===0xf4)upper=0x8f;
      if(b===undefined||b<lower||b>upper){valid=false;break;}
      code=(code<<6)|(b&63);at++;
    }
    result+=valid?String.fromCodePoint(code):'\ufffd';i=at;
  }
  return result;
}
function decodeHexPrefix(text) {
  const bytes=[];
  for(let i=0;i+1<text.length;i+=2) {
    const pair=text.slice(i,i+2);if(!/^[0-9a-fA-F]{2}$/.test(pair))break;bytes.push(parseInt(pair,16));
  }
  return Uint8Array.from(bytes);
}
const stable = value => {
  if(Array.isArray(value))return value.map(stable);
  if(!value||typeof value!=='object')return value;
  const out={};for(const key of Object.keys(value).sort())out[key]=stable(value[key]);return out;
};
const digest = value => hex(pureSha256(encodeUtf8(JSON.stringify(stable(value)))));
const same = (a,b,name) => {if(JSON.stringify(a)!==JSON.stringify(b))throw Error('provider_case_failed_'+name);};
const demand = (value,name) => {if(!value)throw Error('provider_case_failed_'+name);};
const observableError = fn => {
  try {fn();return null;}catch(error){return {name:error.name,code:typeof error.code==='string'?error.code:null,message_sha256:digest(error.message)};}
};
const byteViewsOverlap = (a,b) => a.length>0 && b.length>0 && a.buffer===b.buffer &&
  a.byteOffset<b.byteOffset+b.length && b.byteOffset<a.byteOffset+a.length;

function runtimeFingerprint() {
  const sourceHash = fn => hex(pureSha256(encodeUtf8(Function.prototype.toString.call(fn))));
  const file=fs.realpathSync(process.execPath),stat=fs.statSync(file),fd=fs.openSync(file,'r');
  const hash=crypto.createHash('sha256'),chunk=NativeBuffer.alloc(65536);
  try {for(;;){const n=fs.readSync(fd,chunk,0,chunk.length,null);if(!n)break;hash.update(chunk.subarray(0,n));}}finally{fs.closeSync(fd);}
  const prototype=Object.getPrototypeOf(crypto.createHash('sha256'));
  return {node:process.version,openssl:process.versions.openssl,platform:process.platform,arch:process.arch,
    executable_sha256:hash.digest('hex'),executable_bytes:stat.size,fips:crypto.getFips(),
    openssl_shared_linkage:Boolean(process.config.variables.node_shared_openssl),
    builtin_source_sha256:{createHash:sourceHash(crypto.createHash),hash_update:sourceHash(prototype.update),hash_digest:sourceHash(prototype.digest),
      Buffer_from:sourceHash(NativeBuffer.from),Buffer_alloc:sourceHash(NativeBuffer.alloc),Buffer_toString:sourceHash(NativeBuffer.prototype.toString)},
    identity_scope:'Executable and selected public JS builtin wrappers; OpenSSL version/mode recorded, not a complete dynamic-library closure'};
}

function validateProviders() {
  const rows=[];
  const record=(category,name,evidence)=>rows.push({category,name,passed:true,evidence_sha256:digest(evidence)});
  const vectors=[['empty','', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
    ['abc','abc','ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
    ['multiblock','abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq','248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1'],
    ['million_a','a'.repeat(1000000),'cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0']];
  for(const [name,text,expected] of vectors) {
    const independent=hex(pureSha256(encodeUtf8(text))),native=crypto.createHash('sha256').update(text,'utf8').digest('hex');
    same(independent,expected,name+'_oracle_vector');same(native,expected,name+'_native_vector');record('sha256_known_vector',name,{independent,native});
  }
  for(const length of [0,1,55,56,63,64,65,119,120,127,128,4096]) {
    const bytes=Uint8Array.from({length},(_,i)=>(i*73+19)&255),expected=hex(pureSha256(bytes));
    const h=crypto.createHash('sha256');let at=0;
    for(const width of [1,7,31,64]){const end=Math.min(length,at+width);demand(h.update(bytes.subarray(at,end))===h,'update_identity');at=end;}
    h.update(bytes.subarray(at));same(h.digest('hex'),expected,'chunked_'+length);
    const raw=crypto.createHash('sha256').update(bytes).digest();demand(NativeBuffer.isBuffer(raw)&&raw.length===32,'digest_bytes_type');
    same(Array.from(raw),Array.from(pureSha256(bytes)),'raw_digest_'+length);record('sha256_chunk_and_typestate','bytes_'+length,{expected,raw:Array.from(raw)});
  }
  const primitives=[['undefined',undefined,'undefined'],['null',null,'null'],['false',false,'false'],['true',true,'true'],
    ['number',17,'17'],['negative_zero',-0,'0'],['nan',NaN,'NaN'],['positive_infinity',Infinity,'Infinity'],['negative_infinity',-Infinity,'-Infinity'],
    ['bigint',12345678901234567890n,'12345678901234567890'],['symbol',Symbol('authored'),'Symbol(authored)'],
    ['unicode','λ☃😀','λ☃😀'],['nul','a\u0000b','a\u0000b'],['unpaired_high','\ud800','\ud800'],['unpaired_low','\udfff','\udfff'],
    ['mixed_surrogates','\ud800x\udc00😀','\ud800x\udc00😀']];
  for(const [name,value,expectedText] of primitives) {
    const text=String(value);same(text,expectedText,'primitive_'+name);
    const expected=encodeUtf8(text);same(Array.from(NativeBuffer.from(text,'utf8')),Array.from(expected),'utf8_'+name);
    const h=crypto.createHash('sha256');demand(h.update(text,'utf8')===h,'string_update_identity');
    const actual=h.digest('hex');demand(/^[0-9a-f]{64}$/.test(actual),'hex_digest_type');same(actual,hex(pureSha256(expected)),'string_digest_'+name);
    record('primitive_string_utf8_sha256',name,{expected:Array.from(expected),actual});
  }
  for(const text of ['', '00','0123456789abcdef','ABCDEF','a','abc','abzzcd','ab cd','zz','00λ','00\u0000ff']) {
    const actual=NativeBuffer.from(text,'hex'),expected=decodeHexPrefix(text);same(Array.from(actual),Array.from(expected),'hex_decode');
    record('buffer_hex_prefix','case_'+rows.filter(r=>r.category==='buffer_hex_prefix').length,{actual:Array.from(actual)});
  }
  const byteCases=[[],[0],[0x61,0,0x62],[0xce,0xbb,0xe2,0x98,0x83,0xf0,0x9f,0x98,0x80],
    [0xc0,0xaf],[0xe1,0x80,0x41],[0xe0,0x80,0x80],[0xed,0xa0,0x80],[0xf0,0x90,0x80],[0xf4,0x90,0x80,0x80],
    Array.from({length:256},(_,i)=>i)];
  for(const bytes of byteCases) {
    const expected=decodeUtf8(bytes),actual=NativeBuffer.from(bytes).toString('utf8');same(actual,expected,'utf8_decode');
    record('buffer_utf8_decode','case_'+rows.filter(r=>r.category==='buffer_utf8_decode').length,{expected,actual});
  }
  for(const length of [0,1,2,31,32,63,64,4096]) {
    const a=NativeBuffer.alloc(length),b=NativeBuffer.alloc(length);same(Array.from(a),Array(length).fill(0),'zero_initialization');
    demand(!byteViewsOverlap(a,b),'alloc_logical_freshness');if(length){a[0]=513;demand(a[0]===1&&b[0]===0,'byte_write_isolation');a[length-1]=-1;demand(a[length-1]===255,'byte_coercion');}
    const first=NativeBuffer.from('a5'.repeat(length),'hex'),second=NativeBuffer.from('a5'.repeat(length),'hex');
    demand(!byteViewsOverlap(first,second),'from_logical_freshness');
    if(length){first[0]=0;demand(second[0]===0xa5,'from_write_isolation');}
    const copy=NativeBuffer.from(second);demand(!byteViewsOverlap(second,copy),'copy_logical_freshness');
    if(length){copy[0]=0;demand(second[0]===0xa5,'copy_write_isolation');}
    const destination=NativeBuffer.alloc(length);same(second.copy(destination),length,'copy_extent');same(Array.from(destination),Array.from(second),'copy_bytes');
    same(a[-1],undefined,'negative_index_read');same(a[length],undefined,'past_end_read');
    a[length]=17;demand(a.length===length,'past_end_write_no_growth');
    demand(Object.getOwnPropertyDescriptor(a,'length')===undefined,'admitted_ops_leave_length_metadata');
    record('buffer_freshness_index_copy','length_'+length,{logical_views_disjoint:true,
      zero_initialized:true,copy:Array.from(destination),length:a.length});
  }
  let sharedBackingObserved=false;
  for(let attempt=0;attempt<32&&!sharedBackingObserved;attempt++) {
    const a=NativeBuffer.from('01','hex'),b=NativeBuffer.from('02','hex');
    demand(!byteViewsOverlap(a,b),'pooled_views_remain_disjoint');sharedBackingObserved=a.buffer===b.buffer;
  }
  // These native capabilities explain observer restrictions; they are not
  // admitted by the selected BLA call closure or by the byte-view relation.
  const backing=NativeBuffer.from([1,2,3,4]),narrow=backing.subarray(0,1);
  demand(new Uint8Array(narrow.buffer)[narrow.byteOffset+1]===2,'outside_view_backing_observer');
  record('contract_boundary_counterexample','outside_logical_byte_view',{outside_view_read_possible:true,excluded:true});
  const metadataMutable=NativeBuffer.alloc(4);
  Object.defineProperty(metadataMutable,'length',{value:2});
  demand(metadataMutable.length===2&&metadataMutable.byteLength===4,'length_property_shadow');
  record('contract_boundary_counterexample','metadata_length_shadow',{length_property_can_be_shadowed:true,excluded:true});
  const failedUpdate=()=>{const h=crypto.createHash('sha256');h.update('authored-left','utf8');const error=observableError(()=>h.update({}));
    demand(error?.name==='TypeError'&&error.code==='ERR_INVALID_ARG_TYPE','invalid_update_error');return {error,digest:h.digest('hex')};};
  const a=failedUpdate(),b=failedUpdate();same(a,b,'paired_invalid_update_state');
  same(a.digest,hex(pureSha256(encodeUtf8('authored-left'))),'failed_update_preserves_hash');record('native_error_and_recovery','invalid_update',a);
  const finalized=()=>{const h=crypto.createHash('sha256');h.update('authored-final','utf8');const result=h.digest('hex');
    const update=observableError(()=>h.update('later','utf8')),digestAgain=observableError(()=>h.digest());
    demand(update?.code==='ERR_CRYPTO_HASH_FINALIZED'&&digestAgain?.code==='ERR_CRYPTO_HASH_FINALIZED','finalized_error');
    return {result,update,digestAgain,fresh:crypto.createHash('sha256').update('fresh','utf8').digest('hex')};};
  const fa=finalized(),fb=finalized();same(fa,fb,'paired_finalized_state');same(fa.fresh,hex(pureSha256(encodeUtf8('fresh'))),'fresh_after_throw');
  record('native_error_and_recovery','finalized_hash',fa);
  for(const [name,fn,expectedName] of [['negative_alloc',()=>NativeBuffer.alloc(-1),'RangeError'],
      ['nonnumeric_alloc',()=>NativeBuffer.alloc('2'),'TypeError'],['invalid_from',()=>NativeBuffer.from({}),'TypeError'],
      ['invalid_algorithm',()=>crypto.createHash('authored-unsupported-algorithm'),'Error']]) {
    const first=observableError(fn),second=observableError(fn);same(first,second,'paired_error_'+name);demand(first?.name===expectedName,'native_error_type_'+name);
    same(Array.from(NativeBuffer.alloc(2)),[0,0],'fresh_buffer_after_throw');record('native_error_and_recovery',name,{error:first,recovery:true});
  }
  for(const [name,text,prefix,suffix] of [['ascii','authored{data}','authored{','}'],['unicode','λ😀☃','λ','☃'],['empty','','','']]) {
    demand(text.startsWith(prefix)&&text.endsWith(suffix),'string_predicates');record('string_predicates',name,{prefix:true,suffix:true});
  }
  const counts={};for(const row of rows)counts[row.category]=(counts[row.category]||0)+1;
  const receipt={format:'fdisbull-real-provider-conformance-1',status:'verified_finite_conformance',runtime:runtimeFingerprint(),
    receipt_digest_encoding:'SHA-256 of UTF-8 recursively sorted-key JSON without receipt_sha256',
    providers:'Actual node:crypto and node:buffer implementations in this process; no modeled digest or Buffer replacement',
    oracle:'Independent pure JavaScript SHA-256 arithmetic, UTF-8 encoder/decoder and hex-prefix decoder, anchored by four fixed SHA-256 vectors',
    coverage:['crypto.createHash(sha256)','hash.update(string,utf8)','hash.digest(hex)','hash.digest()','String(primitives)',
      'Buffer.from(hex)','Buffer.alloc','Buffer indexed reads/writes and copy','Buffer.toString(utf8)','string.startsWith/endsWith'],
    categories:counts,cases:rows.length,rows,rows_sha256:digest(rows),
    buffer_freshness:{logical_byte_views_nonoverlapping:true,shared_backing_observed:sharedBackingObserved,
      distinct_ArrayBuffer_not_required:true,
      extent_stability:'Lengths remain stable under the admitted native operations; arbitrary metadata mutation is excluded',
      excluded_observers:['Buffer.buffer/parent backing identity or contents outside the logical view','byteOffset/allocation pool identity',
        'Object.defineProperty or other Buffer metadata/prototype mutation']},
    buffer_limits:{max_length:bufferConstants.MAX_LENGTH,max_string_length:bufferConstants.MAX_STRING_LENGTH},
    limitations:['Finite implementation conformance is not a universal native-code correctness or termination proof',
      'The whole-function theorem still requires stable standard implementations and its stated relational provider/observer contract',
      'Resource exhaustion, native faults, host tampering, callbacks/reentry and timing are outside these bounded checks',
      'The executable/OpenSSL/wrapper fingerprints identify the tested runtime, not an authenticated implementation proof']};
  receipt.receipt_sha256=digest(receipt);return receipt;
}

module.exports={validateProviders,pureSha256,encodeUtf8,decodeUtf8,decodeHexPrefix,byteViewsOverlap};
if(require.main===module) {
  try {process.stdout.write(JSON.stringify(validateProviders())+'\n');}
  catch (_) {console.error('Real provider conformance failed; no verified receipt');process.exitCode=2;}
}
