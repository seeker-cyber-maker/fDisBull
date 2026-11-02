#include "M16ABI.H"
#pragma code_seg("FDBN8")
FdbBlockResult fdb16_n8(Fdb16Arena *fdb_words) {
  FdbU32 fdb_remaining;
  FdbU32 fdb_failed;
  FdbBlockResult fdb_result;
  FdbU32 fdb_v0;
  FdbU32 fdb_v1;
  FdbU32 fdb_v2;
  FdbU32 fdb_v3;
  FdbU32 fdb_v4;
  FdbU32 fdb_v5;
  FdbU32 fdb_v6;
  FdbU32 fdb_v7;
  FdbU32 fdb_v8;
  FdbU32 fdb_v9;
  FdbU32 fdb_v10;
  FdbU32 fdb_v11;
  FdbU32 fdb_v12;
  FdbU32 fdb_v13;
  FdbU32 fdb_v14;
  FdbU32 fdb_v15;
  FdbU32 fdb_v16;
  FdbU32 fdb_v17;
  FdbU32 fdb_v18;
  FdbU32 fdb_v19;
  FdbU32 fdb_v20;
  FdbU32 fdb_v21;
  FdbU32 fdb_v22;
  FdbU32 fdb_v23;
  FdbU32 fdb_v24;
  FdbU32 fdb_v25;
  FdbU32 fdb_v26;
  FdbU32 fdb_v27;
  FdbU32 fdb_v28;
  FdbU32 fdb_v29;
  FdbU32 fdb_v30;
  FdbU32 fdb_v31;
  FdbU32 fdb_v32;
  FdbU32 fdb_v33;
  FdbU32 fdb_v34;
  FdbU32 fdb_v35;
  FdbU32 fdb_v36;
  FdbU32 fdb_v37;
  FdbU32 fdb_t0;
  FdbU32 fdb_t1;
  FdbU32 fdb_loop0;
  FdbU32 fdb_t2;
  FdbU32 fdb_t3;
  FdbU32 fdb_t4;
  FdbU32 fdb_loop1;
  FdbU32 fdb_t5;
  FdbU32 fdb_t6;
  FdbU32 fdb_t7;
  FdbU32 fdb_t8;
  FdbU32 fdb_t9;
  FdbU32 fdb_t10;
  FdbU32 fdb_t11;
  FdbU32 fdb_t12;
  FdbU32 fdb_t13;
  FdbU32 fdb_t14;
  FdbU32 fdb_t15;
  FdbU32 fdb_t16;
  FdbU32 fdb_t17;
  FdbU32 fdb_t18;
  FdbU32 fdb_t19;
  FdbU32 fdb_t20;
  fdb_remaining = 4000000UL;
  fdb_failed = 0UL;
  fdb_result.status = 1UL; fdb_result.steps = 0UL; fdb_result.cut = 0UL;
  if (!fdb_words || fdb16_word_count(fdb_words) != 70000UL) return fdb_result;
  fdb_v0 = 0UL;
  fdb_v1 = 0UL;
  fdb_v2 = 0UL;
  fdb_v3 = 0UL;
  fdb_v4 = 0UL;
  fdb_v5 = 0UL;
  fdb_v6 = 0UL;
  fdb_v7 = 0UL;
  fdb_v8 = 0UL;
  fdb_v9 = 0UL;
  fdb_v10 = 0UL;
  fdb_v11 = 0UL;
  fdb_v12 = 0UL;
  fdb_v13 = 0UL;
  fdb_v14 = 0UL;
  fdb_v15 = 0UL;
  fdb_v16 = 0UL;
  fdb_v17 = 0UL;
  fdb_v18 = 0UL;
  fdb_v19 = 0UL;
  fdb_v20 = 0UL;
  fdb_v21 = 0UL;
  fdb_v22 = 0UL;
  fdb_v23 = 0UL;
  fdb_v24 = 0UL;
  fdb_v25 = 0UL;
  fdb_v26 = 0UL;
  fdb_v27 = 0UL;
  fdb_v28 = 0UL;
  fdb_v29 = 0UL;
  fdb_v30 = 0UL;
  fdb_v31 = 0UL;
  fdb_v32 = 0UL;
  fdb_v33 = 0UL;
  fdb_v34 = 0UL;
  fdb_v35 = 0UL;
  fdb_v36 = 0UL;
  fdb_v37 = 0UL;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_read(fdb_words,606UL,&fdb_t0)) { fdb_failed = 2UL; goto fdb_done; }
  if (600UL == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  fdb_t1 = (FdbU32)(fdb_t0 % 600UL);
  fdb_v3 = fdb_t1;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_v11 = 0UL;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_v35 = 0UL;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_loop0 = 0UL;
  for (;;) {
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t2 = (FdbU32)(fdb_v11 == 0UL);
    fdb_t3 = (FdbU32)(fdb_v35 < 600UL);
    fdb_t4 = (FdbU32)(fdb_t2 & fdb_t3);
    if (fdb_t4 == 0UL) break;
    if (fdb_loop0 == 600UL) { fdb_failed = 1UL; goto fdb_done; }
    ++fdb_loop0;
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_v21 = 0UL;
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_v17 = 0UL;
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_loop1 = 0UL;
    for (;;) {
      if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      --fdb_remaining;
      if (600UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
      if (fdb16_read(fdb_words,600UL,&fdb_t5)) { fdb_failed = 2UL; goto fdb_done; }
      fdb_t6 = (FdbU32)(fdb_v17 < fdb_t5);
      fdb_t7 = (FdbU32)(fdb_v21 == 0UL);
      fdb_t8 = (FdbU32)(fdb_t6 & fdb_t7);
      if (fdb_t8 == 0UL) break;
      if (fdb_loop1 == 600UL) { fdb_failed = 1UL; goto fdb_done; }
      ++fdb_loop1;
      if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      --fdb_remaining;
      if (fdb_v17 >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
      if (fdb16_read(fdb_words,fdb_v17,&fdb_t9)) { fdb_failed = 2UL; goto fdb_done; }
      fdb_t10 = (FdbU32)(fdb_v3 == fdb_t9);
      if (fdb_t10 != 0UL) {
        if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
        --fdb_remaining;
        fdb_v21 = 1UL;
      } else {
      }
      if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      --fdb_remaining;
      fdb_t11 = (FdbU32)(fdb_v17 + 1UL);
      fdb_v17 = fdb_t11;
    }
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t12 = (FdbU32)(fdb_v21 == 0UL);
    if (fdb_t12 != 0UL) {
      if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      --fdb_remaining;
      fdb_t13 = (FdbU32)(fdb_v3 & 65535UL);
      if (612UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
      if (fdb16_write(fdb_words,612UL,fdb_t13)) { fdb_failed = 2UL; goto fdb_done; }
      if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      --fdb_remaining;
      fdb_v11 = 1UL;
    } else {
      if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      --fdb_remaining;
      fdb_t14 = (FdbU32)(fdb_v3 + 1UL);
      if (600UL == 0UL) { fdb_failed = 1UL; goto fdb_done; }
      fdb_t15 = (FdbU32)(fdb_t14 % 600UL);
      fdb_v3 = fdb_t15;
    }
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t16 = (FdbU32)(fdb_v35 + 1UL);
    fdb_v35 = fdb_t16;
  }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t17 = (FdbU32)(fdb_v11 == 0UL);
  if (fdb_t17 != 0UL) {
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t18 = (FdbU32)(2UL & 65535UL);
    if (604UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
    if (fdb16_write(fdb_words,604UL,fdb_t18)) { fdb_failed = 2UL; goto fdb_done; }
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t19 = (FdbU32)(1UL & 65535UL);
    if (603UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
    if (fdb16_write(fdb_words,603UL,fdb_t19)) { fdb_failed = 2UL; goto fdb_done; }
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t20 = (FdbU32)(65535UL & 65535UL);
    if (612UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
    if (fdb16_write(fdb_words,612UL,fdb_t20)) { fdb_failed = 2UL; goto fdb_done; }
  } else {
  }
fdb_done:
  fdb_result.status = fdb_failed;
  fdb_result.steps = 4000000UL-fdb_remaining;
  fdb_result.cut = fdb_failed ? 0UL : fdb_v0;
  return fdb_result;
}
