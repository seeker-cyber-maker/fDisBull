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
  let c0 = select(0u,1u,(get_word(604u) == 0u));
  if (failed) { return; }
  if (c0 != 0u) {
    if (!charge()) { return; }
    put_word(607u,(word_add(get_word(607u),1u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    let c1 = select(0u,1u,(get_word(602u) != (word_add(get_word(601u),2u) & 3u)));
    if (failed) { return; }
    if (c1 != 0u) {
      if (!charge()) { return; }
      put_word(601u,(get_word(602u) & 65535u));
      if (failed) { return; }
    } else {
    }
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(602u,(get_word(601u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    put_word(613u,(0u & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    v35 = remainder(get_word(0u),30u);
    if (failed) { return; }
    if (!charge()) { return; }
    v36 = divide(get_word(0u),30u);
    if (failed) { return; }
    if (!charge()) { return; }
    let c2 = select(0u,1u,(get_word(601u) == 0u));
    if (failed) { return; }
    if (c2 != 0u) {
      if (!charge()) { return; }
      v36 = word_sub(v36,1u);
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      let c3 = select(0u,1u,(get_word(601u) == 1u));
      if (failed) { return; }
      if (c3 != 0u) {
        if (!charge()) { return; }
        v35 = word_add(v35,1u);
        if (failed) { return; }
      } else {
        if (!charge()) { return; }
        let c4 = select(0u,1u,(get_word(601u) == 2u));
        if (failed) { return; }
        if (c4 != 0u) {
          if (!charge()) { return; }
          v36 = word_add(v36,1u);
          if (failed) { return; }
        } else {
          if (!charge()) { return; }
          v35 = word_sub(v35,1u);
          if (failed) { return; }
        }
        if (failed) { return; }
      }
      if (failed) { return; }
    }
    if (failed) { return; }
    if (!charge()) { return; }
    let c5 = (select(0u,1u,(v35 >= 30u)) | select(0u,1u,(v36 >= 20u)));
    if (failed) { return; }
    if (c5 != 0u) {
      if (!charge()) { return; }
      put_word(604u,(1u & 65535u));
      if (failed) { return; }
      if (!charge()) { return; }
      put_word(603u,(1u & 65535u));
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      v18 = word_add(word_mul(v36,30u),v35);
      if (failed) { return; }
      if (!charge()) { return; }
      v11 = select(0u,1u,(v18 == get_word(612u)));
      if (failed) { return; }
      if (!charge()) { return; }
      v17 = word_sub(get_word(600u),word_sub(1u,v11));
      if (failed) { return; }
      if (!charge()) { return; }
      v14 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      v4 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop6:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = (select(0u,1u,(v14 < v17)) & select(0u,1u,(v4 == 0u)));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop6 >= 600u) { failed=true; return; }
          loop6 += 1u;
          if (!charge()) { return; }
          let c7 = select(0u,1u,(v18 == get_word(v14)));
          if (failed) { return; }
          if (c7 != 0u) {
            if (!charge()) { return; }
            v4 = 1u;
            if (failed) { return; }
          } else {
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v14 = word_add(v14,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c8 = v4;
      if (failed) { return; }
      if (c8 != 0u) {
        if (!charge()) { return; }
        put_word(604u,(1u & 65535u));
        if (failed) { return; }
        if (!charge()) { return; }
        put_word(603u,(1u & 65535u));
        if (failed) { return; }
      } else {
        if (!charge()) { return; }
        let c9 = v11;
        if (failed) { return; }
        if (c9 != 0u) {
          if (!charge()) { return; }
          put_word(600u,(word_add(get_word(600u),1u) & 65535u));
          if (failed) { return; }
          if (!charge()) { return; }
          put_word(605u,(word_add(get_word(605u),1u) & 65535u));
          if (failed) { return; }
        } else {
        }
        if (failed) { return; }
        if (!charge()) { return; }
        v14 = word_sub(get_word(600u),1u);
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop10:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v14 != 0u));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop10 >= 599u) { failed=true; return; }
            loop10 += 1u;
            if (!charge()) { return; }
            put_word(v14,get_word(word_sub(v14,1u)));
            if (failed) { return; }
            if (!charge()) { return; }
            v14 = word_sub(v14,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
        if (!charge()) { return; }
        put_word(0u,v18);
        if (failed) { return; }
        if (!charge()) { return; }
        let c11 = v11;
        if (failed) { return; }
        if (c11 != 0u) {
          if (!charge()) { return; }
          let c12 = select(0u,1u,(get_word(600u) == 600u));
          if (failed) { return; }
          if (c12 != 0u) {
            if (!charge()) { return; }
            put_word(604u,(2u & 65535u));
            if (failed) { return; }
            if (!charge()) { return; }
            put_word(603u,(1u & 65535u));
            if (failed) { return; }
            if (!charge()) { return; }
            put_word(612u,(65535u & 65535u));
            if (failed) { return; }
          } else {
            if (!charge()) { return; }
            put_word(606u,((word_add(word_mul(get_word(606u),25173u),13849u) & 65535u) & 65535u));
            if (failed) { return; }
            if (!charge()) { return; }
            v2 = remainder(get_word(606u),600u);
            if (failed) { return; }
            if (!charge()) { return; }
            v10 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            v34 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop13:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = (select(0u,1u,(v10 == 0u)) & select(0u,1u,(v34 < 600u)));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop13 >= 600u) { failed=true; return; }
                loop13 += 1u;
                if (!charge()) { return; }
                v20 = 0u;
                if (failed) { return; }
                if (!charge()) { return; }
                v16 = 0u;
                if (failed) { return; }
                if (!charge()) { return; }
                {
                  var loop14:u32 = 0u;
                  loop {
                    if (!charge()) { return; }
                    let test = (select(0u,1u,(v16 < get_word(600u))) & select(0u,1u,(v20 == 0u)));
                    if (failed) { return; }
                    if (test == 0u) { break; }
                    if (loop14 >= 600u) { failed=true; return; }
                    loop14 += 1u;
                    if (!charge()) { return; }
                    let c15 = select(0u,1u,(v2 == get_word(v16)));
                    if (failed) { return; }
                    if (c15 != 0u) {
                      if (!charge()) { return; }
                      v20 = 1u;
                      if (failed) { return; }
                    } else {
                    }
                    if (failed) { return; }
                    if (!charge()) { return; }
                    v16 = word_add(v16,1u);
                    if (failed) { return; }
                  }
                }
                if (failed) { return; }
                if (!charge()) { return; }
                let c16 = select(0u,1u,(v20 == 0u));
                if (failed) { return; }
                if (c16 != 0u) {
                  if (!charge()) { return; }
                  put_word(612u,(v2 & 65535u));
                  if (failed) { return; }
                  if (!charge()) { return; }
                  v10 = 1u;
                  if (failed) { return; }
                } else {
                  if (!charge()) { return; }
                  v2 = remainder(word_add(v2,1u),600u);
                  if (failed) { return; }
                }
                if (failed) { return; }
                if (!charge()) { return; }
                v34 = word_add(v34,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            let c17 = select(0u,1u,(v10 == 0u));
            if (failed) { return; }
            if (c17 != 0u) {
              if (!charge()) { return; }
              put_word(604u,(2u & 65535u));
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(603u,(1u & 65535u));
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(612u,(65535u & 65535u));
              if (failed) { return; }
            } else {
            }
            if (failed) { return; }
          }
          if (failed) { return; }
        } else {
        }
        if (failed) { return; }
      }
      if (failed) { return; }
    }
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
}
@compute @workgroup_size(1) fn main() {
  for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
  run();
  if (failed) {
    for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
    out_words[0]=1u;
  } else { out_words[0]=0u; }
  out_words[70001u]=4000000u-remaining;
}
