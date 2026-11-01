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
  v7 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  let c0 = select(0u,1u,(get_word(630u) == 1u));
  if (failed) { return; }
  if (c0 != 0u) {
    if (!charge()) { return; }
    put_word(608u,(word_add(get_word(608u),1u) & 65535u));
    if (failed) { return; }
    if (!charge()) { return; }
    v0 = get_word(631u);
    if (failed) { return; }
    if (!charge()) { return; }
    let c1 = (select(0u,1u,(v0 >= 65u)) & select(0u,1u,(v0 <= 90u)));
    if (failed) { return; }
    if (c1 != 0u) {
      if (!charge()) { return; }
      v0 = word_add(v0,32u);
      if (failed) { return; }
    } else {
    }
    if (failed) { return; }
    if (!charge()) { return; }
    let c2 = select(0u,1u,(v0 == 27u));
    if (failed) { return; }
    if (c2 != 0u) {
      if (!charge()) { return; }
      v7 = 8u;
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      let c3 = select(0u,1u,(v0 == 32u));
      if (failed) { return; }
      if (c3 != 0u) {
        if (!charge()) { return; }
        v7 = 5u;
        if (failed) { return; }
      } else {
        if (!charge()) { return; }
        let c4 = select(0u,1u,(v0 == 112u));
        if (failed) { return; }
        if (c4 != 0u) {
          if (!charge()) { return; }
          v7 = 5u;
          if (failed) { return; }
        } else {
          if (!charge()) { return; }
          let c5 = select(0u,1u,(v0 == 110u));
          if (failed) { return; }
          if (c5 != 0u) {
            if (!charge()) { return; }
            v7 = 6u;
            if (failed) { return; }
          } else {
            if (!charge()) { return; }
            let c6 = select(0u,1u,(v0 == 114u));
            if (failed) { return; }
            if (c6 != 0u) {
              if (!charge()) { return; }
              v7 = 7u;
              if (failed) { return; }
            } else {
              if (!charge()) { return; }
              let c7 = (select(0u,1u,(v0 == 119u)) | select(0u,1u,(get_word(632u) == 72u)));
              if (failed) { return; }
              if (c7 != 0u) {
                if (!charge()) { return; }
                v7 = 1u;
                if (failed) { return; }
              } else {
                if (!charge()) { return; }
                let c8 = (select(0u,1u,(v0 == 100u)) | select(0u,1u,(get_word(632u) == 77u)));
                if (failed) { return; }
                if (c8 != 0u) {
                  if (!charge()) { return; }
                  v7 = 2u;
                  if (failed) { return; }
                } else {
                  if (!charge()) { return; }
                  let c9 = (select(0u,1u,(v0 == 115u)) | select(0u,1u,(get_word(632u) == 80u)));
                  if (failed) { return; }
                  if (c9 != 0u) {
                    if (!charge()) { return; }
                    v7 = 3u;
                    if (failed) { return; }
                  } else {
                    if (!charge()) { return; }
                    let c10 = (select(0u,1u,(v0 == 97u)) | select(0u,1u,(get_word(632u) == 75u)));
                    if (failed) { return; }
                    if (c10 != 0u) {
                      if (!charge()) { return; }
                      v7 = 4u;
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
    v21 = get_word(617u);
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
    let c12 = (select(0u,1u,((get_word(635u) & 1u) != 0u)) & select(0u,1u,((v21 & 1u) == 0u)));
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
        v7 = 1u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c14 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 280u))) & (select(0u,1u,(get_word(634u) >= 64u)) & select(0u,1u,(get_word(634u) < 84u))));
      if (failed) { return; }
      if (c14 != 0u) {
        if (!charge()) { return; }
        v7 = 4u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c15 = ((select(0u,1u,(get_word(633u) >= 288u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 64u)) & select(0u,1u,(get_word(634u) < 84u))));
      if (failed) { return; }
      if (c15 != 0u) {
        if (!charge()) { return; }
        v7 = 2u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c16 = ((select(0u,1u,(get_word(633u) >= 280u)) & select(0u,1u,(get_word(633u) < 304u))) & (select(0u,1u,(get_word(634u) >= 88u)) & select(0u,1u,(get_word(634u) < 108u))));
      if (failed) { return; }
      if (c16 != 0u) {
        if (!charge()) { return; }
        v7 = 3u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c17 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 120u)) & select(0u,1u,(get_word(634u) < 140u))));
      if (failed) { return; }
      if (c17 != 0u) {
        if (!charge()) { return; }
        v7 = 5u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c18 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 144u)) & select(0u,1u,(get_word(634u) < 164u))));
      if (failed) { return; }
      if (c18 != 0u) {
        if (!charge()) { return; }
        v7 = 6u;
        if (failed) { return; }
      } else {
      }
      if (failed) { return; }
      if (!charge()) { return; }
      let c19 = ((select(0u,1u,(get_word(633u) >= 256u)) & select(0u,1u,(get_word(633u) < 312u))) & (select(0u,1u,(get_word(634u) >= 168u)) & select(0u,1u,(get_word(634u) < 188u))));
      if (failed) { return; }
      if (c19 != 0u) {
        if (!charge()) { return; }
        v7 = 7u;
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
  let c20 = (select(0u,1u,(v7 >= 1u)) & select(0u,1u,(v7 <= 4u)));
  if (failed) { return; }
  if (c20 != 0u) {
    if (!charge()) { return; }
    let c21 = ((select(0u,1u,(get_word(604u) == 0u)) & select(0u,1u,(get_word(613u) == 0u))) & (select(0u,1u,(word_sub(v7,1u) != get_word(601u))) & select(0u,1u,(word_sub(v7,1u) != (word_add(get_word(601u),2u) & 3u)))));
    if (failed) { return; }
    if (c21 != 0u) {
      if (!charge()) { return; }
      put_word(602u,(word_sub(v7,1u) & 65535u));
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
  let c22 = (select(0u,1u,(v7 == 5u)) & select(0u,1u,(get_word(604u) == 0u)));
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
  let c23 = ((select(0u,1u,(v7 == 6u)) & select(0u,1u,(get_word(604u) == 0u))) & select(0u,1u,(get_word(603u) == 1u)));
  if (failed) { return; }
  if (c23 != 0u) {
    if (!charge()) { return; }
    put_word(615u,(1u & 65535u));
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c24 = select(0u,1u,(v7 == 7u));
  if (failed) { return; }
  if (c24 != 0u) {
    if (!charge()) { return; }
    v14 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    {
      var loop25:u32 = 0u;
      loop {
        if (!charge()) { return; }
        let test = select(0u,1u,(v14 < 600u));
        if (failed) { return; }
        if (test == 0u) { break; }
        if (loop25 >= 600u) { failed=true; return; }
        loop25 += 1u;
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
    if (!charge()) { return; }
    put_word(620u,(get_word(636u) & 65535u));
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c26 = select(0u,1u,(v7 == 8u));
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
        let c30 = select(0u,1u,(get_word(604u) == 0u));
        if (failed) { return; }
        if (c30 != 0u) {
          if (!charge()) { return; }
          put_word(607u,(word_add(get_word(607u),1u) & 65535u));
          if (failed) { return; }
          if (!charge()) { return; }
          let c31 = select(0u,1u,(get_word(602u) != (word_add(get_word(601u),2u) & 3u)));
          if (failed) { return; }
          if (c31 != 0u) {
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
          let c32 = select(0u,1u,(get_word(601u) == 0u));
          if (failed) { return; }
          if (c32 != 0u) {
            if (!charge()) { return; }
            v36 = word_sub(v36,1u);
            if (failed) { return; }
          } else {
            if (!charge()) { return; }
            let c33 = select(0u,1u,(get_word(601u) == 1u));
            if (failed) { return; }
            if (c33 != 0u) {
              if (!charge()) { return; }
              v35 = word_add(v35,1u);
              if (failed) { return; }
            } else {
              if (!charge()) { return; }
              let c34 = select(0u,1u,(get_word(601u) == 2u));
              if (failed) { return; }
              if (c34 != 0u) {
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
          let c35 = (select(0u,1u,(v35 >= 30u)) | select(0u,1u,(v36 >= 20u)));
          if (failed) { return; }
          if (c35 != 0u) {
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
              var loop36:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = (select(0u,1u,(v14 < v17)) & select(0u,1u,(v4 == 0u)));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop36 >= 600u) { failed=true; return; }
                loop36 += 1u;
                if (!charge()) { return; }
                let c37 = select(0u,1u,(v18 == get_word(v14)));
                if (failed) { return; }
                if (c37 != 0u) {
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
            let c38 = v4;
            if (failed) { return; }
            if (c38 != 0u) {
              if (!charge()) { return; }
              put_word(604u,(1u & 65535u));
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(603u,(1u & 65535u));
              if (failed) { return; }
            } else {
              if (!charge()) { return; }
              let c39 = v11;
              if (failed) { return; }
              if (c39 != 0u) {
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
                var loop40:u32 = 0u;
                loop {
                  if (!charge()) { return; }
                  let test = select(0u,1u,(v14 != 0u));
                  if (failed) { return; }
                  if (test == 0u) { break; }
                  if (loop40 >= 599u) { failed=true; return; }
                  loop40 += 1u;
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
              let c41 = v11;
              if (failed) { return; }
              if (c41 != 0u) {
                if (!charge()) { return; }
                let c42 = select(0u,1u,(get_word(600u) == 600u));
                if (failed) { return; }
                if (c42 != 0u) {
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
                    var loop43:u32 = 0u;
                    loop {
                      if (!charge()) { return; }
                      let test = (select(0u,1u,(v10 == 0u)) & select(0u,1u,(v34 < 600u)));
                      if (failed) { return; }
                      if (test == 0u) { break; }
                      if (loop43 >= 600u) { failed=true; return; }
                      loop43 += 1u;
                      if (!charge()) { return; }
                      v20 = 0u;
                      if (failed) { return; }
                      if (!charge()) { return; }
                      v16 = 0u;
                      if (failed) { return; }
                      if (!charge()) { return; }
                      {
                        var loop44:u32 = 0u;
                        loop {
                          if (!charge()) { return; }
                          let test = (select(0u,1u,(v16 < get_word(600u))) & select(0u,1u,(v20 == 0u)));
                          if (failed) { return; }
                          if (test == 0u) { break; }
                          if (loop44 >= 600u) { failed=true; return; }
                          loop44 += 1u;
                          if (!charge()) { return; }
                          let c45 = select(0u,1u,(v2 == get_word(v16)));
                          if (failed) { return; }
                          if (c45 != 0u) {
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
                      let c46 = select(0u,1u,(v20 == 0u));
                      if (failed) { return; }
                      if (c46 != 0u) {
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
                  let c47 = select(0u,1u,(v10 == 0u));
                  if (failed) { return; }
                  if (c47 != 0u) {
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
      let c48 = ((select(0u,1u,(get_word(603u) == 0u)) & select(0u,1u,(get_word(604u) == 0u))) & select(0u,1u,((word_sub(get_word(636u),get_word(620u)) & 65535u) >= 4u)));
      if (failed) { return; }
      if (c48 != 0u) {
        if (!charge()) { return; }
        let c49 = select(0u,1u,(get_word(604u) == 0u));
        if (failed) { return; }
        if (c49 != 0u) {
          if (!charge()) { return; }
          put_word(607u,(word_add(get_word(607u),1u) & 65535u));
          if (failed) { return; }
          if (!charge()) { return; }
          let c50 = select(0u,1u,(get_word(602u) != (word_add(get_word(601u),2u) & 3u)));
          if (failed) { return; }
          if (c50 != 0u) {
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
          let c51 = select(0u,1u,(get_word(601u) == 0u));
          if (failed) { return; }
          if (c51 != 0u) {
            if (!charge()) { return; }
            v36 = word_sub(v36,1u);
            if (failed) { return; }
          } else {
            if (!charge()) { return; }
            let c52 = select(0u,1u,(get_word(601u) == 1u));
            if (failed) { return; }
            if (c52 != 0u) {
              if (!charge()) { return; }
              v35 = word_add(v35,1u);
              if (failed) { return; }
            } else {
              if (!charge()) { return; }
              let c53 = select(0u,1u,(get_word(601u) == 2u));
              if (failed) { return; }
              if (c53 != 0u) {
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
          let c54 = (select(0u,1u,(v35 >= 30u)) | select(0u,1u,(v36 >= 20u)));
          if (failed) { return; }
          if (c54 != 0u) {
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
              var loop55:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = (select(0u,1u,(v14 < v17)) & select(0u,1u,(v4 == 0u)));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop55 >= 600u) { failed=true; return; }
                loop55 += 1u;
                if (!charge()) { return; }
                let c56 = select(0u,1u,(v18 == get_word(v14)));
                if (failed) { return; }
                if (c56 != 0u) {
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
            let c57 = v4;
            if (failed) { return; }
            if (c57 != 0u) {
              if (!charge()) { return; }
              put_word(604u,(1u & 65535u));
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(603u,(1u & 65535u));
              if (failed) { return; }
            } else {
              if (!charge()) { return; }
              let c58 = v11;
              if (failed) { return; }
              if (c58 != 0u) {
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
                var loop59:u32 = 0u;
                loop {
                  if (!charge()) { return; }
                  let test = select(0u,1u,(v14 != 0u));
                  if (failed) { return; }
                  if (test == 0u) { break; }
                  if (loop59 >= 599u) { failed=true; return; }
                  loop59 += 1u;
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
              let c60 = v11;
              if (failed) { return; }
              if (c60 != 0u) {
                if (!charge()) { return; }
                let c61 = select(0u,1u,(get_word(600u) == 600u));
                if (failed) { return; }
                if (c61 != 0u) {
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
                    var loop62:u32 = 0u;
                    loop {
                      if (!charge()) { return; }
                      let test = (select(0u,1u,(v10 == 0u)) & select(0u,1u,(v34 < 600u)));
                      if (failed) { return; }
                      if (test == 0u) { break; }
                      if (loop62 >= 600u) { failed=true; return; }
                      loop62 += 1u;
                      if (!charge()) { return; }
                      v20 = 0u;
                      if (failed) { return; }
                      if (!charge()) { return; }
                      v16 = 0u;
                      if (failed) { return; }
                      if (!charge()) { return; }
                      {
                        var loop63:u32 = 0u;
                        loop {
                          if (!charge()) { return; }
                          let test = (select(0u,1u,(v16 < get_word(600u))) & select(0u,1u,(v20 == 0u)));
                          if (failed) { return; }
                          if (test == 0u) { break; }
                          if (loop63 >= 600u) { failed=true; return; }
                          loop63 += 1u;
                          if (!charge()) { return; }
                          let c64 = select(0u,1u,(v2 == get_word(v16)));
                          if (failed) { return; }
                          if (c64 != 0u) {
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
                      let c65 = select(0u,1u,(v20 == 0u));
                      if (failed) { return; }
                      if (c65 != 0u) {
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
                  let c66 = select(0u,1u,(v10 == 0u));
                  if (failed) { return; }
                  if (c66 != 0u) {
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
}
@compute @workgroup_size(1) fn main() {
  for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
  run();
  if (failed) {
    for (var i=0u;i<70000u;i+=1u) { out_words[i+1u]=in_words[i]; }
    out_words[0]=1u;
  } else { out_words[0]=0u; }
}
