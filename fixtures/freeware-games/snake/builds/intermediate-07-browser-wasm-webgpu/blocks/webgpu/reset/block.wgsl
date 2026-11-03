@group(0) @binding(0) var<storage,read> in_words:array<u32>;
@group(0) @binding(1) var<storage,read_write> out_words:array<u32>;
var<private> failed:bool = false;
var<private> remaining:u32 = 4000000u;
fn charge()->bool { if (remaining==0u) { failed=true; return false; } remaining-=1u; return true; }
fn get_word(i:u32)->u32 { if (i>=70000u) { failed=true; return 0u; } return out_words[i+1u]; }
fn put_word(i:u32,v:u32) { if (i>=70000u) { failed=true; return; } out_words[i+1u]=v; }
fn divide(a:u32,b:u32)->u32 { if (b==0u) { failed=true; return 0u; } return a/b; }
fn remainder(a:u32,b:u32)->u32 { if (b==0u) { failed=true; return 0u; } return a%b; }
fn word_add(a:u32,b:u32)->u32 { return a+b; }
fn word_sub(a:u32,b:u32)->u32 { return a-b; }
fn word_mul(a:u32,b:u32)->u32 { return a*b; }
fn word_shl(a:u32,b:u32)->u32 { return a << (b & 31u); }
fn word_shr(a:u32,b:u32)->u32 { return a >> (b & 31u); }
fn run() {
  var v0:u32 = 0u;
  var v1:u32 = 0u;
  var v2:u32 = 0u;
  var v3:u32 = 0u;
  var v4:u32 = 0u;
  var v5:u32 = 0u;
  var v6:u32 = 0u;
  var v7:u32 = 0u;
  var v8:u32 = 0u;
  var v9:u32 = 0u;
  var v10:u32 = 0u;
  var v11:u32 = 0u;
  var v12:u32 = 0u;
  var v13:u32 = 0u;
  var v14:u32 = 0u;
  var v15:u32 = 0u;
  var v16:u32 = 0u;
  var v17:u32 = 0u;
  var v18:u32 = 0u;
  var v19:u32 = 0u;
  var v20:u32 = 0u;
  var v21:u32 = 0u;
  var v22:u32 = 0u;
  var v23:u32 = 0u;
  var v24:u32 = 0u;
  var v25:u32 = 0u;
  var v26:u32 = 0u;
  var v27:u32 = 0u;
  var v28:u32 = 0u;
  var v29:u32 = 0u;
  var v30:u32 = 0u;
  var v31:u32 = 0u;
  var v32:u32 = 0u;
  var v33:u32 = 0u;
  var v34:u32 = 0u;
  var v35:u32 = 0u;
  var v36:u32 = 0u;
  if (!charge()) { return; }
  v14 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop0:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v14 < 600u));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop0 >= 600u) { failed=true; return; }
      loop0 += 1u;
      if (!charge()) { return; }
      put_word(v14,0u);
      if (failed) { return; }
      if (!charge()) { return; }
      v14 = word_add(v14,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(0u,308u);
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(1u,307u);
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(2u,306u);
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(600u,(3u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(601u,(1u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(602u,(1u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(603u,(1u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(604u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(605u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(606u,(4660u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(612u,(312u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(607u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(608u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(609u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(610u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(613u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(615u,(0u & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(614u,(1u & 65535u));
  if (failed) { return; }
}
@compute @workgroup_size(1) fn main() {
  for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
  run();
  if (failed) {
    for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
    out_words[0]=1u;
  } else { out_words[0]=0u; }
}
