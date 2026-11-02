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
  v22 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop0:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v22 < 64000u));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop0 >= 64000u) { failed=true; return; }
      loop0 += 1u;
      if (!charge()) { return; }
      put_word(word_add(4096u,v22),0u);
      if (failed) { return; }
      if (!charge()) { return; }
      v22 = word_add(v22,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 6u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 22u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 244u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 164u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 8u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop1:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop1 >= 200u) { failed=true; return; }
      loop1 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop2:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop2 >= 320u) { failed=true; return; }
          loop2 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 8u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 24u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 240u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 160u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop3:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop3 >= 200u) { failed=true; return; }
      loop3 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop4:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop4 >= 320u) { failed=true; return; }
          loop4 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v28 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop5:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v28 < get_word(600u)));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop5 >= 600u) { failed=true; return; }
      loop5 += 1u;
      if (!charge()) { return; }
      v26 = word_add(8u,word_mul(remainder(get_word(v28),30u),8u));
      if (failed) { return; }
      if (!charge()) { return; }
      v27 = word_add(24u,word_mul(divide(get_word(v28),30u),8u));
      if (failed) { return; }
      if (!charge()) { return; }
      v25 = 7u;
      if (failed) { return; }
      if (!charge()) { return; }
      v23 = 7u;
      if (failed) { return; }
      if (!charge()) { return; }
      v5 = 2u;
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop6:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v24 < v23));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop6 >= 200u) { failed=true; return; }
          loop6 += 1u;
          if (!charge()) { return; }
          v6 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop7:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v6 < v25));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop7 >= 320u) { failed=true; return; }
              loop7 += 1u;
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
              if (failed) { return; }
              if (!charge()) { return; }
              v6 = word_add(v6,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v24 = word_add(v24,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v28 = word_add(v28,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = word_add(8u,word_mul(remainder(get_word(0u),30u),8u));
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = word_add(24u,word_mul(divide(get_word(0u),30u),8u));
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 7u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 7u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 10u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop8:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop8 >= 200u) { failed=true; return; }
      loop8 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop9:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop9 >= 320u) { failed=true; return; }
          loop9 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c10 = select(0u,1u,(get_word(612u) < 600u));
  if (failed) { return; }
  if (c10 != 0u) {
    if (!charge()) { return; }
    v26 = word_add(8u,word_mul(remainder(get_word(612u),30u),8u));
    if (failed) { return; }
    if (!charge()) { return; }
    v27 = word_add(24u,word_mul(divide(get_word(612u),30u),8u));
    if (failed) { return; }
    if (!charge()) { return; }
    v25 = 7u;
    if (failed) { return; }
    if (!charge()) { return; }
    v23 = 7u;
    if (failed) { return; }
    if (!charge()) { return; }
    v5 = 12u;
    if (failed) { return; }
    if (!charge()) { return; }
    v24 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    {
      var loop11:u32 = 0u;
      loop {
        if (!charge()) { return; }
        let test = select(0u,1u,(v24 < v23));
        if (failed) { return; }
        if (test == 0u) { break; }
        if (loop11 >= 200u) { failed=true; return; }
        loop11 += 1u;
        if (!charge()) { return; }
        v6 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop12:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v6 < v25));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop12 >= 320u) { failed=true; return; }
            loop12 += 1u;
            if (!charge()) { return; }
            put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
            if (failed) { return; }
            if (!charge()) { return; }
            v6 = word_add(v6,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
        if (!charge()) { return; }
        v24 = word_add(v24,1u);
        if (failed) { return; }
      }
    }
    if (failed) { return; }
  } else {
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 280u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 40u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 24u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop13:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop13 >= 200u) { failed=true; return; }
      loop13 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop14:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop14 >= 320u) { failed=true; return; }
          loop14 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 64u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 24u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop15:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop15 >= 200u) { failed=true; return; }
      loop15 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop16:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop16 >= 320u) { failed=true; return; }
          loop16 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 288u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 64u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 24u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop17:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop17 >= 200u) { failed=true; return; }
      loop17 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop18:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop18 >= 320u) { failed=true; return; }
          loop18 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 280u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 88u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 24u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop19:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop19 >= 200u) { failed=true; return; }
      loop19 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop20:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop20 >= 320u) { failed=true; return; }
          loop20 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 120u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 56u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop21:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop21 >= 200u) { failed=true; return; }
      loop21 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop22:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop22 >= 320u) { failed=true; return; }
          loop22 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 144u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 56u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop23:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop23 >= 200u) { failed=true; return; }
      loop23 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop24:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop24 >= 320u) { failed=true; return; }
          loop24 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v26 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v27 = 168u;
  if (failed) { return; }
  if (!charge()) { return; }
  v25 = 56u;
  if (failed) { return; }
  if (!charge()) { return; }
  v23 = 20u;
  if (failed) { return; }
  if (!charge()) { return; }
  v5 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v24 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop25:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v24 < v23));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop25 >= 200u) { failed=true; return; }
      loop25 += 1u;
      if (!charge()) { return; }
      v6 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop26:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v6 < v25));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop26 >= 320u) { failed=true; return; }
          loop26 += 1u;
          if (!charge()) { return; }
          put_word(word_add(4096u,word_add(word_mul(word_add(v27,v24),320u),word_add(v26,v6))),v5);
          if (failed) { return; }
          if (!charge()) { return; }
          v6 = word_add(v6,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v24 = word_add(v24,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3072u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 16u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop27:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop27 >= 80u) { failed=true; return; }
      loop27 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop28:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop28 >= 8u) { failed=true; return; }
          loop28 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop29:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop29 >= 8u) { failed=true; return; }
              loop29 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v19 = get_word(605u);
  if (failed) { return; }
  if (!charge()) { return; }
  v9 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop30:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = (select(0u,1u,(v19 != 0u)) | select(0u,1u,(v9 == 0u)));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop30 >= 5u) { failed=true; return; }
      loop30 += 1u;
      if (!charge()) { return; }
      put_word(word_add(760u,v9),word_add(48u,remainder(v19,10u)));
      if (failed) { return; }
      if (!charge()) { return; }
      v9 = word_add(v9,1u);
      if (failed) { return; }
      if (!charge()) { return; }
      v19 = divide(v19,10u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v8 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop31:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v8 < v9));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop31 >= 5u) { failed=true; return; }
      loop31 += 1u;
      if (!charge()) { return; }
      put_word(word_add(768u,v8),get_word(word_add(760u,word_sub(word_sub(v9,1u),v8))));
      if (failed) { return; }
      if (!charge()) { return; }
      v8 = word_add(v8,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 768u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = v9;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 128u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop32:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop32 >= 80u) { failed=true; return; }
      loop32 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop33:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop33 >= 8u) { failed=true; return; }
          loop33 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop34:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop34 >= 8u) { failed=true; return; }
              loop34 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c35 = select(0u,1u,(get_word(604u) == 1u));
  if (failed) { return; }
  if (c35 != 0u) {
    if (!charge()) { return; }
    v30 = 3102u;
    if (failed) { return; }
    if (!charge()) { return; }
    v29 = 7u;
    if (failed) { return; }
    if (!charge()) { return; }
    v31 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    v32 = 8u;
    if (failed) { return; }
    if (!charge()) { return; }
    v33 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    {
      var loop36:u32 = 0u;
      loop {
        if (!charge()) { return; }
        let test = select(0u,1u,(v33 < v29));
        if (failed) { return; }
        if (test == 0u) { break; }
        if (loop36 >= 80u) { failed=true; return; }
        loop36 += 1u;
        if (!charge()) { return; }
        v3 = get_word(word_add(v30,v33));
        if (failed) { return; }
        if (!charge()) { return; }
        v13 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop37:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v13 < 8u));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop37 >= 8u) { failed=true; return; }
            loop37 += 1u;
            if (!charge()) { return; }
            v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
            if (failed) { return; }
            if (!charge()) { return; }
            v12 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop38:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = select(0u,1u,(v12 < 8u));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop38 >= 8u) { failed=true; return; }
                loop38 += 1u;
                if (!charge()) { return; }
                v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
                if (failed) { return; }
                if (!charge()) { return; }
                put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
                if (failed) { return; }
                if (!charge()) { return; }
                v12 = word_add(v12,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            v13 = word_add(v13,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
        if (!charge()) { return; }
        v33 = word_add(v33,1u);
        if (failed) { return; }
      }
    }
    if (failed) { return; }
  } else {
    if (!charge()) { return; }
    let c39 = select(0u,1u,(get_word(604u) == 2u));
    if (failed) { return; }
    if (c39 != 0u) {
      if (!charge()) { return; }
      v30 = 3109u;
      if (failed) { return; }
      if (!charge()) { return; }
      v29 = 7u;
      if (failed) { return; }
      if (!charge()) { return; }
      v31 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      v32 = 8u;
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop40:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v33 < v29));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop40 >= 80u) { failed=true; return; }
          loop40 += 1u;
          if (!charge()) { return; }
          v3 = get_word(word_add(v30,v33));
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop41:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v13 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop41 >= 8u) { failed=true; return; }
              loop41 += 1u;
              if (!charge()) { return; }
              v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = 0u;
              if (failed) { return; }
              if (!charge()) { return; }
              {
                var loop42:u32 = 0u;
                loop {
                  if (!charge()) { return; }
                  let test = select(0u,1u,(v12 < 8u));
                  if (failed) { return; }
                  if (test == 0u) { break; }
                  if (loop42 >= 8u) { failed=true; return; }
                  loop42 += 1u;
                  if (!charge()) { return; }
                  v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
                  if (failed) { return; }
                  if (!charge()) { return; }
                  put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
                  if (failed) { return; }
                  if (!charge()) { return; }
                  v12 = word_add(v12,1u);
                  if (failed) { return; }
                }
              }
              if (failed) { return; }
              if (!charge()) { return; }
              v13 = word_add(v13,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v33 = word_add(v33,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
    } else {
      if (!charge()) { return; }
      let c43 = select(0u,1u,(get_word(603u) == 0u));
      if (failed) { return; }
      if (c43 != 0u) {
        if (!charge()) { return; }
        v30 = 3095u;
        if (failed) { return; }
        if (!charge()) { return; }
        v29 = 7u;
        if (failed) { return; }
        if (!charge()) { return; }
        v31 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        v32 = 8u;
        if (failed) { return; }
        if (!charge()) { return; }
        v33 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop44:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v33 < v29));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop44 >= 80u) { failed=true; return; }
            loop44 += 1u;
            if (!charge()) { return; }
            v3 = get_word(word_add(v30,v33));
            if (failed) { return; }
            if (!charge()) { return; }
            v13 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop45:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = select(0u,1u,(v13 < 8u));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop45 >= 8u) { failed=true; return; }
                loop45 += 1u;
                if (!charge()) { return; }
                v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
                if (failed) { return; }
                if (!charge()) { return; }
                v12 = 0u;
                if (failed) { return; }
                if (!charge()) { return; }
                {
                  var loop46:u32 = 0u;
                  loop {
                    if (!charge()) { return; }
                    let test = select(0u,1u,(v12 < 8u));
                    if (failed) { return; }
                    if (test == 0u) { break; }
                    if (loop46 >= 8u) { failed=true; return; }
                    loop46 += 1u;
                    if (!charge()) { return; }
                    v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
                    if (failed) { return; }
                    if (!charge()) { return; }
                    put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
                    if (failed) { return; }
                    if (!charge()) { return; }
                    v12 = word_add(v12,1u);
                    if (failed) { return; }
                  }
                }
                if (failed) { return; }
                if (!charge()) { return; }
                v13 = word_add(v13,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            v33 = word_add(v33,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
      } else {
        if (!charge()) { return; }
        v30 = 3088u;
        if (failed) { return; }
        if (!charge()) { return; }
        v29 = 7u;
        if (failed) { return; }
        if (!charge()) { return; }
        v31 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        v32 = 8u;
        if (failed) { return; }
        if (!charge()) { return; }
        v33 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop47:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v33 < v29));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop47 >= 80u) { failed=true; return; }
            loop47 += 1u;
            if (!charge()) { return; }
            v3 = get_word(word_add(v30,v33));
            if (failed) { return; }
            if (!charge()) { return; }
            v13 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop48:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = select(0u,1u,(v13 < 8u));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop48 >= 8u) { failed=true; return; }
                loop48 += 1u;
                if (!charge()) { return; }
                v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
                if (failed) { return; }
                if (!charge()) { return; }
                v12 = 0u;
                if (failed) { return; }
                if (!charge()) { return; }
                {
                  var loop49:u32 = 0u;
                  loop {
                    if (!charge()) { return; }
                    let test = select(0u,1u,(v12 < 8u));
                    if (failed) { return; }
                    if (test == 0u) { break; }
                    if (loop49 >= 8u) { failed=true; return; }
                    loop49 += 1u;
                    if (!charge()) { return; }
                    v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
                    if (failed) { return; }
                    if (!charge()) { return; }
                    put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
                    if (failed) { return; }
                    if (!charge()) { return; }
                    v12 = word_add(v12,1u);
                    if (failed) { return; }
                  }
                }
                if (failed) { return; }
                if (!charge()) { return; }
                v13 = word_add(v13,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            v33 = word_add(v33,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
      }
      if (failed) { return; }
    }
    if (failed) { return; }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  let c50 = select(0u,1u,(get_word(611u) == 0u));
  if (failed) { return; }
  if (c50 != 0u) {
    if (!charge()) { return; }
    v30 = 3180u;
    if (failed) { return; }
    if (!charge()) { return; }
    v29 = 5u;
    if (failed) { return; }
    if (!charge()) { return; }
    v31 = 256u;
    if (failed) { return; }
    if (!charge()) { return; }
    v32 = 8u;
    if (failed) { return; }
    if (!charge()) { return; }
    v33 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    {
      var loop51:u32 = 0u;
      loop {
        if (!charge()) { return; }
        let test = select(0u,1u,(v33 < v29));
        if (failed) { return; }
        if (test == 0u) { break; }
        if (loop51 >= 80u) { failed=true; return; }
        loop51 += 1u;
        if (!charge()) { return; }
        v3 = get_word(word_add(v30,v33));
        if (failed) { return; }
        if (!charge()) { return; }
        v13 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop52:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v13 < 8u));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop52 >= 8u) { failed=true; return; }
            loop52 += 1u;
            if (!charge()) { return; }
            v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
            if (failed) { return; }
            if (!charge()) { return; }
            v12 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop53:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = select(0u,1u,(v12 < 8u));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop53 >= 8u) { failed=true; return; }
                loop53 += 1u;
                if (!charge()) { return; }
                v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
                if (failed) { return; }
                if (!charge()) { return; }
                put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
                if (failed) { return; }
                if (!charge()) { return; }
                v12 = word_add(v12,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            v13 = word_add(v13,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
        if (!charge()) { return; }
        v33 = word_add(v33,1u);
        if (failed) { return; }
      }
    }
    if (failed) { return; }
  } else {
    if (!charge()) { return; }
    v30 = 3175u;
    if (failed) { return; }
    if (!charge()) { return; }
    v29 = 5u;
    if (failed) { return; }
    if (!charge()) { return; }
    v31 = 256u;
    if (failed) { return; }
    if (!charge()) { return; }
    v32 = 8u;
    if (failed) { return; }
    if (!charge()) { return; }
    v33 = 0u;
    if (failed) { return; }
    if (!charge()) { return; }
    {
      var loop54:u32 = 0u;
      loop {
        if (!charge()) { return; }
        let test = select(0u,1u,(v33 < v29));
        if (failed) { return; }
        if (test == 0u) { break; }
        if (loop54 >= 80u) { failed=true; return; }
        loop54 += 1u;
        if (!charge()) { return; }
        v3 = get_word(word_add(v30,v33));
        if (failed) { return; }
        if (!charge()) { return; }
        v13 = 0u;
        if (failed) { return; }
        if (!charge()) { return; }
        {
          var loop55:u32 = 0u;
          loop {
            if (!charge()) { return; }
            let test = select(0u,1u,(v13 < 8u));
            if (failed) { return; }
            if (test == 0u) { break; }
            if (loop55 >= 8u) { failed=true; return; }
            loop55 += 1u;
            if (!charge()) { return; }
            v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
            if (failed) { return; }
            if (!charge()) { return; }
            v12 = 0u;
            if (failed) { return; }
            if (!charge()) { return; }
            {
              var loop56:u32 = 0u;
              loop {
                if (!charge()) { return; }
                let test = select(0u,1u,(v12 < 8u));
                if (failed) { return; }
                if (test == 0u) { break; }
                if (loop56 >= 8u) { failed=true; return; }
                loop56 += 1u;
                if (!charge()) { return; }
                v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
                if (failed) { return; }
                if (!charge()) { return; }
                put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
                if (failed) { return; }
                if (!charge()) { return; }
                v12 = word_add(v12,1u);
                if (failed) { return; }
              }
            }
            if (failed) { return; }
            if (!charge()) { return; }
            v13 = word_add(v13,1u);
            if (failed) { return; }
          }
        }
        if (failed) { return; }
        if (!charge()) { return; }
        v33 = word_add(v33,1u);
        if (failed) { return; }
      }
    }
    if (failed) { return; }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3155u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 2u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 280u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 40u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop57:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop57 >= 80u) { failed=true; return; }
      loop57 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop58:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop58 >= 8u) { failed=true; return; }
          loop58 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop59:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop59 >= 8u) { failed=true; return; }
              loop59 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3157u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 64u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop60:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop60 >= 80u) { failed=true; return; }
      loop60 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop61:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop61 >= 8u) { failed=true; return; }
          loop61 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop62:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop62 >= 8u) { failed=true; return; }
              loop62 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3158u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 1u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 288u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 64u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop63:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop63 >= 80u) { failed=true; return; }
      loop63 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop64:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop64 >= 8u) { failed=true; return; }
          loop64 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop65:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop65 >= 8u) { failed=true; return; }
              loop65 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3159u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 2u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 280u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 88u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop66:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop66 >= 80u) { failed=true; return; }
      loop66 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop67:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop67 >= 8u) { failed=true; return; }
          loop67 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop68:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop68 >= 8u) { failed=true; return; }
              loop68 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3161u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 5u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 120u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop69:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop69 >= 80u) { failed=true; return; }
      loop69 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop70:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop70 >= 8u) { failed=true; return; }
          loop70 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop71:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop71 >= 8u) { failed=true; return; }
              loop71 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3166u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 4u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 144u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop72:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop72 >= 80u) { failed=true; return; }
      loop72 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop73:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop73 >= 8u) { failed=true; return; }
          loop73 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop74:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop74 >= 8u) { failed=true; return; }
              loop74 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3170u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 5u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 256u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 168u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop75:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop75 >= 80u) { failed=true; return; }
      loop75 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop76:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop76 >= 8u) { failed=true; return; }
          loop76 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop77:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop77 >= 8u) { failed=true; return; }
              loop77 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  v30 = 3116u;
  if (failed) { return; }
  if (!charge()) { return; }
  v29 = 39u;
  if (failed) { return; }
  if (!charge()) { return; }
  v31 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  v32 = 192u;
  if (failed) { return; }
  if (!charge()) { return; }
  v33 = 0u;
  if (failed) { return; }
  if (!charge()) { return; }
  {
    var loop78:u32 = 0u;
    loop {
      if (!charge()) { return; }
      let test = select(0u,1u,(v33 < v29));
      if (failed) { return; }
      if (test == 0u) { break; }
      if (loop78 >= 80u) { failed=true; return; }
      loop78 += 1u;
      if (!charge()) { return; }
      v3 = get_word(word_add(v30,v33));
      if (failed) { return; }
      if (!charge()) { return; }
      v13 = 0u;
      if (failed) { return; }
      if (!charge()) { return; }
      {
        var loop79:u32 = 0u;
        loop {
          if (!charge()) { return; }
          let test = select(0u,1u,(v13 < 8u));
          if (failed) { return; }
          if (test == 0u) { break; }
          if (loop79 >= 8u) { failed=true; return; }
          loop79 += 1u;
          if (!charge()) { return; }
          v1 = get_word(word_add(1024u,word_add(word_mul(v3,8u),v13)));
          if (failed) { return; }
          if (!charge()) { return; }
          v12 = 0u;
          if (failed) { return; }
          if (!charge()) { return; }
          {
            var loop80:u32 = 0u;
            loop {
              if (!charge()) { return; }
              let test = select(0u,1u,(v12 < 8u));
              if (failed) { return; }
              if (test == 0u) { break; }
              if (loop80 >= 8u) { failed=true; return; }
              loop80 += 1u;
              if (!charge()) { return; }
              v15 = (word_shr(v1,word_sub(7u,v12)) & 1u);
              if (failed) { return; }
              if (!charge()) { return; }
              put_word(word_add(4096u,word_add(word_mul(word_add(v32,v13),320u),word_add(v31,word_add(word_mul(v33,8u),v12)))),word_mul(v15,15u));
              if (failed) { return; }
              if (!charge()) { return; }
              v12 = word_add(v12,1u);
              if (failed) { return; }
            }
          }
          if (failed) { return; }
          if (!charge()) { return; }
          v13 = word_add(v13,1u);
          if (failed) { return; }
        }
      }
      if (failed) { return; }
      if (!charge()) { return; }
      v33 = word_add(v33,1u);
      if (failed) { return; }
    }
  }
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(610u,(word_add(get_word(610u),1u) & 65535u));
  if (failed) { return; }
  if (!charge()) { return; }
  put_word(614u,(0u & 65535u));
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
