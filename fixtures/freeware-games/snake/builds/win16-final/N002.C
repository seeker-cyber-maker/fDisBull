#include "M16ABI.H"
#pragma code_seg("FDBN2")
FdbBlockResult fdb16_n2(Fdb16Arena *fdb_words) {
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
  FdbU32 fdb_t2;
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
  fdb_t0 = (FdbU32)(1UL & 65535UL);
  if (614UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,614UL,fdb_t0)) { fdb_failed = 2UL; goto fdb_done; }
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (636UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_read(fdb_words,636UL,&fdb_t1)) { fdb_failed = 2UL; goto fdb_done; }
  fdb_t2 = (FdbU32)(fdb_t1 & 65535UL);
  if (620UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,620UL,fdb_t2)) { fdb_failed = 2UL; goto fdb_done; }
fdb_done:
  fdb_result.status = fdb_failed;
  fdb_result.steps = 4000000UL-fdb_remaining;
  fdb_result.cut = fdb_failed ? 0UL : fdb_v0;
  return fdb_result;
}
