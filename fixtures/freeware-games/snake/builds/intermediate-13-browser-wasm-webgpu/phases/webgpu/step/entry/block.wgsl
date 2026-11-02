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
    v36 = remainder(get_word(0u),30u);
    if (failed) { return; }
    if (!charge()) { return; }
    v37 = divide(get_word(0u),30u);
    if (failed) { return; }
    if (!charge()) { return; }
    let c2 = select(0u,1u,(get_word(601u) == 0u));
    if (failed) { return; }
    if (c2 != 0u) {
      if (!charge()) { return; }
      v37 = word_sub(v37,1u);
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      let c3 = select(0u,1u,(get_word(601u) == 1u));
      if (failed) { return; }
      if (c3 != 0u) {
        if (!charge()) { return; }
        v36 = word_add(v36,1u);
        if (failed) { return; }
      } else {
        if (!charge()) { return; }
        let c4 = select(0u,1u,(get_word(601u) == 2u));
        if (failed) { return; }
        if (c4 != 0u) {
          if (!charge()) { return; }
          v37 = word_add(v37,1u);
          if (failed) { return; }
        } else {
          if (!charge()) { return; }
          v36 = word_sub(v36,1u);
          if (failed) { return; }
        }
        if (failed) { return; }
      }
      if (failed) { return; }
    }
    if (failed) { return; }
    if (!charge()) { return; }
    let c5 = (select(0u,1u,(v36 >= 30u)) | select(0u,1u,(v37 >= 20u)));
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
      v19 = word_add(word_mul(v37,30u),v36);
      if (failed) { return; }
      if (!charge()) { return; }
      v12 = select(0u,1u,(v19 == get_word(612u)));
      if (failed) { return; }
      if (!charge()) { return; }
      v18 = word_sub(get_word(600u),word_sub(1u,v12));
      if (failed) { return; }
      if (!charge()) { return; }
      v15 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      v5 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop6:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = (select(0u,1u,(v15 < v18)) & select(0u,1u,(v5 == 0u)));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop6 >= 600u) { failed=true; return; }
          loop6 += 1u;
          if (!charge()) { return; }
          let c7 = select(0u,1u,(v19 == get_word(v15)));
          if (failed) { return; }
          if (c7 != 0u) {
            if (!charge()) { return; }
            v5 = 1u;
            if (failed) { return; }
          } else {
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v15 = word_add(v15,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c8 = v5;
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
        let c9 = v12;
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
        v15 = word_sub(get_word(600u),1u);
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop10:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v15 != 0u));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop10 >= 599u) { failed=true; return; }
            loop10 += 1u;
            if (!charge()) { return; }
            put_word(v15,get_word(word_sub(v15,1u)));
            if (failed) { return; }
            if (!charge()) { return; }
            v15 = word_sub(v15,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
        if (!charge()) { return; }
        put_word(0u,v19);
        if (failed) { return; }
        if (!charge()) { return; }
        let c11 = v12;
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
            v0 = 1u;
            if (failed) { return; }
            if (!charge()) { return; }
            captured_0 = v0;
            return;
            if (!charge()) { return; }
            v3 = remainder(get_word(606u),600u);
            if (failed) { return; }
            if (!charge()) { return; }
            v11 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            v35 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop13:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = (select(0u,1u,(v11 == 0u)) & select(0u,1u,(v35 < 600u)));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop13 >= 600u) { failed=true; return; }
                loop13 += 1u;
                if (!charge()) { return; }
                v21 = 0u;
                if (failed) { return; }
                if (!charge()) { return; }
                v17 = 0u;
                if (failed) { return; }
                if (!charge()) { return; }
                {
                  var loop14:u32 = 0u;
                  loop {
                    if (!charge()) { return; }
                    let test = (select(0u,1u,(v17 < get_word(600u))) & select(0u,1u,(v21 == 0u)));
                    if (failed) { return; }
                    if (test == 0u) { break; }
                    if (loop14 >= 600u) { failed=true; return; }
                    loop14 += 1u;
                    if (!charge()) { return; }
                    let c15 = select(0u,1u,(v3 == get_word(v17)));
                    if (failed) { return; }
                    if (c15 != 0u) {
                      if (!charge()) { return; }
                      v21 = 1u;
                      if (failed) { return; }
                    } else {
                    }
                    if (failed) { return; }
                    if (!charge()) { return; }
                    v17 = word_add(v17,1u);
                    if (failed) { return; }
                  }
                }
                if (failed) { return; }
                if (!charge()) { return; }
                let c16 = select(0u,1u,(v21 == 0u));
                if (failed) { return; }
                if (c16 != 0u) {
                  if (!charge()) { return; }
                  put_word(612u,(v3 & 65535u));
                  if (failed) { return; }
                  if (!charge()) { return; }
                  v11 = 1u;
                  if (failed) { return; }
                } else {
                  if (!charge()) { return; }
                  v3 = remainder(word_add(v3,1u),600u);
                  if (failed) { return; }
                }
                if (failed) { return; }
                if (!charge()) { return; }
                v35 = word_add(v35,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            let c17 = select(0u,1u,(v11 == 0u));
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
