@group(0) @binding(0) var<storage,read> in_words:array<u32>;
@group(0) @binding(1) var<storage,read_write> out_words:array<u32>;
var<private> failed:bool = false;
var<private> remaining:u32 = 1u;
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
  if (!charge()) { return; }
  put_word(606u,(((word_shr(get_word(606u),1u) ^ (word_sub(0u,(get_word(606u) & 1u)) & 46080u)) | word_mul(select(0u,1u,(get_word(606u) == 0u)),44257u)) & 65535u));
  if (failed) { return; }
}
@compute @workgroup_size(1) fn main() {
  for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
  run();
  if (failed) {
    for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
    out_words[0]=1u;
  } else { out_words[0]=0u; }
  out_words[70001u]=1u-remaining;
}
