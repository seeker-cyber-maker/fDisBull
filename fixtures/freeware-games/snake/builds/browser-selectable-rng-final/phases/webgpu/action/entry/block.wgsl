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
var<private> captured_0:u32 = 0u;
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
  var v37:u32 = 0u;
  if (!charge()) { return; }
  v8 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  let c0 = select(0u,1u,(get_word(630u) == 1u));
  if (failed) { return; }
  if (c0 != 0u) {
    if (!charge()) { return; }
    put_word(608u,(word_add(get_word(608u),1u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    v1 = get_word(631u);
    if (failed) { return; }
    if (!charge()) { return; }
    let c1 = (select(0u,1u,(v1 >= 65u)) & select(0u,1u,(v1 <= 90u)));
    if (failed) { return; }
    if (c1 != 0u) {
      if (!charge()) { return; }
      v1 = word_add(v1,32u);
      if (failed) { return; }
    } else {
    }
    if (failed) { return; }
    if (!charge()) { return; }
    let c2 = select(0u,1u,(v1 == 27u));
    if (failed) { return; }
    if (c2 != 0u) {
      if (!charge()) { return; }
      v8 = 8u;
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      let c3 = select(0u,1u,(v1 == 32u));
      if (failed) { return; }
      if (c3 != 0u) {
        if (!charge()) { return; }
        v8 = 5u;
        if (failed) { return; }
      } else {
        if (!charge()) { return; }
        let c4 = select(0u,1u,(v1 == 112u));
        if (failed) { return; }
        if (c4 != 0u) {
          if (!charge()) { return; }
          v8 = 5u;
          if (failed) { return; }
        } else {
          if (!charge()) { return; }
          let c5 = select(0u,1u,(v1 == 110u));
          if (failed) { return; }
          if (c5 != 0u) {
            if (!charge()) { return; }
            v8 = 6u;
            if (failed) { return; }
          } else {
            if (!charge()) { return; }
            let c6 = select(0u,1u,(v1 == 114u));
            if (failed) { return; }
            if (c6 != 0u) {
              if (!charge()) { return; }
              v8 = 7u;
              if (failed) { return; }
            } else {
              if (!charge()) { return; }
              let c7 = (select(0u,1u,(v1 == 119u)) | select(0u,1u,(get_word(632u) == 72u)));
              if (failed) { return; }
              if (c7 != 0u) {
                if (!charge()) { return; }
                v8 = 1u;
                if (failed) { return; }
              } else {
                if (!charge()) { return; }
                let c8 = (select(0u,1u,(v1 == 100u)) | select(0u,1u,(get_word(632u) == 77u)));
                if (failed) { return; }
                if (c8 != 0u) {
                  if (!charge()) { return; }
                  v8 = 2u;
                  if (failed) { return; }
                } else {
                  if (!charge()) { return; }
                  let c9 = (select(0u,1u,(v1 == 115u)) | select(0u,1u,(get_word(632u) == 80u)));
                  if (failed) { return; }
                  if (c9 != 0u) {
                    if (!charge()) { return; }
                    v8 = 3u;
                    if (failed) { return; }
                  } else {
                    if (!charge()) { return; }
                    let c10 = (select(0u,1u,(v1 == 97u)) | select(0u,1u,(get_word(632u) == 75u)));
                    if (failed) { return; }
                    if (c10 != 0u) {
                      if (!charge()) { return; }
                      v8 = 4u;
                      if (failed) { return; }
                    } else {
                    }
                    if (failed) { return; }
                  }
                  if (failed) { return; }
                }
                if (failed) { return; }
              }
              if (failed) { return; }
            }
            if (failed) { return; }
          }
          if (failed) { return; }
        }
        if (failed) { return; }
      }
      if (failed) { return; }
    }
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c11 = (select(0u,1u,(get_word(630u) == 2u)) & select(0u,1u,(get_word(611u) != 0u)));
  if (failed) { return; }
  if (c11 != 0u) {
    if (!charge()) { return; }
    v22 = get_word(617u);
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(617u,(get_word(635u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(618u,(get_word(633u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(619u,(get_word(634u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    let c12 = (select(0u,1u,((get_word(635u) & 1u) != 0u)) & select(0u,1u,((v22 & 1u) == 0u)));
    if (failed) { return; }
    if (c12 != 0u) {
      if (!charge()) { return; }
      put_word(609u,(word_add(get_word(609u),1u) & 65535u));
      if (failed) { return; }
      if (!charge()) { return; }
      let c13 = ((select(0u,1u,(get_word(633u) >= 280u)) & select(0u,1u,(get_word(633u) < 304u))) & (select(0u,1u,(get_word(634u) >= 40u)) & select(0u,1u,(get_word(634u) < 60u))));
      if (failed) { return; }
      if (c13 != 0u) {
        if (!charge()) { return; }
        v8 = 1u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c14 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 280u))) & (select(0u,1u,(get_word(634u) >= 64u)) & select(0u,1u,(get_word(634u) < 84u))));
      if (failed) { return; }
      if (c14 != 0u) {
        if (!charge()) { return; }
        v8 = 4u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c15 = ((select(0u,1u,(get_word(633u) >= 288u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 64u)) & select(0u,1u,(get_word(634u) < 84u))));
      if (failed) { return; }
      if (c15 != 0u) {
        if (!charge()) { return; }
        v8 = 2u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c16 = ((select(0u,1u,(get_word(633u) >= 280u)) & select(0u,1u,(get_word(633u) < 304u))) & (select(0u,1u,(get_word(634u) >= 88u)) & select(0u,1u,(get_word(634u) < 108u))));
      if (failed) { return; }
      if (c16 != 0u) {
        if (!charge()) { return; }
        v8 = 3u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c17 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 120u)) & select(0u,1u,(get_word(634u) < 140u))));
      if (failed) { return; }
      if (c17 != 0u) {
        if (!charge()) { return; }
        v8 = 5u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c18 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 144u)) & select(0u,1u,(get_word(634u) < 164u))));
      if (failed) { return; }
      if (c18 != 0u) {
        if (!charge()) { return; }
        v8 = 6u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c19 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 168u)) & select(0u,1u,(get_word(634u) < 188u))));
      if (failed) { return; }
      if (c19 != 0u) {
        if (!charge()) { return; }
        v8 = 7u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
    } else {
    }
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c20 = (select(0u,1u,(v8 >= 1u)) & select(0u,1u,(v8 <= 4u)));
  if (failed) { return; }
  if (c20 != 0u) {
    if (!charge()) { return; }
    let c21 = ((select(0u,1u,(get_word(604u) == 0u)) & select(0u,1u,(get_word(613u) == 0u))) & (select(0u,1u,(word_sub(v8,1u) != get_word(601u))) & select(0u,1u,(word_sub(v8,1u) != (word_add(get_word(601u),2u) & 3u)))));
    if (failed) { return; }
    if (c21 != 0u) {
      if (!charge()) { return; }
      put_word(602u,(word_sub(v8,1u) & 65535u));
      if (failed) { return; }
      if (!charge()) { return; }
      put_word(613u,(1u & 65535u));
      if (failed) { return; }
      if (!charge()) { return; }
      put_word(614u,(1u & 65535u));
      if (failed) { return; }
    } else {
    }
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c22 = (select(0u,1u,(v8 == 5u)) & select(0u,1u,(get_word(604u) == 0u)));
  if (failed) { return; }
  if (c22 != 0u) {
    if (!charge()) { return; }
    put_word(603u,((get_word(603u) ^ 1u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(614u,(1u & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(620u,(get_word(636u) & 65535u));
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c23 = ((select(0u,1u,(v8 == 6u)) & select(0u,1u,(get_word(604u) == 0u))) & select(0u,1u,(get_word(603u) == 1u)));
  if (failed) { return; }
  if (c23 != 0u) {
    if (!charge()) { return; }
    put_word(615u,(1u & 65535u));
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c24 = select(0u,1u,(v8 == 7u));
  if (failed) { return; }
  if (c24 != 0u) {
    if (!charge()) { return; }
    v15 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    {
      var loop25:u32 = 0u;
      loop {
        if (!charge()) { return; }
        let test = select(0u,1u,(v15 < 600u));
        if (failed) { return; }
        if (test == 0u) { break; }
        if (loop25 >= 600u) { failed=true; return; }
        loop25 += 1u;
        if (!charge()) { return; }
        put_word(v15,0u);
        if (failed) { return; }
        if (!charge()) { return; }
        v15 = word_add(v15,1u);
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
    if (!charge()) { return; }
    put_word(620u,(get_word(636u) & 65535u));
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c26 = select(0u,1u,(v8 == 8u));
  if (failed) { return; }
  if (c26 != 0u) {
    if (!charge()) { return; }
    put_word(616u,(1u & 65535u));
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c27 = select(0u,1u,(get_word(616u) == 0u));
  if (failed) { return; }
  if (c27 != 0u) {
    if (!charge()) { return; }
    let c28 = select(0u,1u,(get_word(615u) != 0u));
    if (failed) { return; }
    if (c28 != 0u) {
      if (!charge()) { return; }
      put_word(615u,(0u & 65535u));
      if (failed) { return; }
      if (!charge()) { return; }
      let c29 = select(0u,1u,(get_word(603u) == 1u));
      if (failed) { return; }
      if (c29 != 0u) {
        if (!charge()) { return; }
        v0 = 1u;
        if (failed) { return; }
        if (!charge()) { return; }
        captured_0 = v0;
        return;
        if (!charge()) { return; }
        put_word(614u,(1u & 65535u));
        if (failed) { return; }
        if (!charge()) { return; }
        put_word(620u,(get_word(636u) & 65535u));
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      let c30 = ((select(0u,1u,(get_word(603u) == 0u)) & select(0u,1u,(get_word(604u) == 0u))) & select(0u,1u,((word_sub(get_word(636u),get_word(620u)) & 65535u) >= 4u)));
      if (failed) { return; }
      if (c30 != 0u) {
        if (!charge()) { return; }
        v0 = 2u;
        if (failed) { return; }
        if (!charge()) { return; }
        captured_0 = v0;
        return;
        if (!charge()) { return; }
        put_word(614u,(1u & 65535u));
        if (failed) { return; }
        if (!charge()) { return; }
        put_word(620u,(get_word(636u) & 65535u));
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
    }
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  captured_0 = v0;
}
@compute @workgroup_size(1) fn main() {
  for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
  run();
  if (failed) {
    for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
    out_words[0]=1u;
  } else { out_words[0]=0u; }
  out_words[70001u]=4000000u-remaining;
  out_words[70002u]=captured_0;
}
