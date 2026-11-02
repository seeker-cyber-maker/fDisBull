#include "M16ABI.H"
#pragma code_seg("FDBN4")
FdbBlockResult fdb16_n4(Fdb16Arena *fdb_words) {
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
  FdbU32 fdb_loop0;
  FdbU32 fdb_t0;
  FdbU32 fdb_t1;
  FdbU32 fdb_t2;
  FdbU32 fdb_t3;
  FdbU32 fdb_t4;
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
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_v14 = 0UL;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_loop0 = 0UL;
  for (;;) {
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t0 = (FdbU32)(fdb_v14 < 600UL);
    if (fdb_t0 == 0UL) break;
    if (fdb_loop0 == 600UL) { fdb_failed = 1UL; goto fdb_done; }
    ++fdb_loop0;
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    if (fdb_v14 >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
    if (fdb16_write(fdb_words,fdb_v14,0UL)) { fdb_failed = 2UL; goto fdb_done; }
    if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
    --fdb_remaining;
    fdb_t1 = (FdbU32)(fdb_v14 + 1UL);
    fdb_v14 = fdb_t1;
  }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (0UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,0UL,308UL)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (1UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,1UL,307UL)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (2UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,2UL,306UL)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t2 = (FdbU32)(3UL & 65535UL);
  if (600UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,600UL,fdb_t2)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t3 = (FdbU32)(1UL & 65535UL);
  if (601UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,601UL,fdb_t3)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t4 = (FdbU32)(1UL & 65535UL);
  if (602UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,602UL,fdb_t4)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t5 = (FdbU32)(1UL & 65535UL);
  if (603UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,603UL,fdb_t5)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t6 = (FdbU32)(0UL & 65535UL);
  if (604UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,604UL,fdb_t6)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t7 = (FdbU32)(0UL & 65535UL);
  if (605UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,605UL,fdb_t7)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t8 = (FdbU32)(4660UL & 65535UL);
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,606UL,fdb_t8)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t9 = (FdbU32)(312UL & 65535UL);
  if (612UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,612UL,fdb_t9)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t10 = (FdbU32)(0UL & 65535UL);
  if (607UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,607UL,fdb_t10)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t11 = (FdbU32)(0UL & 65535UL);
  if (608UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,608UL,fdb_t11)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t12 = (FdbU32)(0UL & 65535UL);
  if (609UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,609UL,fdb_t12)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t13 = (FdbU32)(0UL & 65535UL);
  if (610UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,610UL,fdb_t13)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t14 = (FdbU32)(0UL & 65535UL);
  if (613UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,613UL,fdb_t14)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t15 = (FdbU32)(0UL & 65535UL);
  if (615UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,615UL,fdb_t15)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  fdb_t16 = (FdbU32)(1UL & 65535UL);
  if (614UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,614UL,fdb_t16)) { fdb_failed = 2UL; goto fdb_done; }
fdb_done:
  fdb_result.status = fdb_failed;
  fdb_result.steps = 4000000UL-fdb_remaining;
  fdb_result.cut = 0UL;
  return fdb_result;
}
