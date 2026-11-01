#include "M16ABI.H"
#pragma code_seg("FDBN5")
FdbBlockResult fdb16_n5(Fdb16Arena *fdb_words) {
  FdbU32 fdb_remaining;
  FdbU32 fdb_failed;
  FdbBlockResult fdb_result;
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
  fdb_remaining = 1UL;
  fdb_failed = 0UL;
  fdb_result.status = 1UL; fdb_result.steps = 0UL; fdb_result.cut = 0UL;
  if (!fdb_words || fdb16_word_count(fdb_words) != 70000UL) return fdb_result;
  if (fdb_remaining == 0UL) { fdb_failed = 1UL; goto fdb_done; }
  --fdb_remaining;
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_read(fdb_words,606UL,&fdb_t0)) { fdb_failed = 2UL; goto fdb_done; }
  fdb_t1 = (FdbU32)(fdb_t0 >> (1UL & 31UL));
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_read(fdb_words,606UL,&fdb_t2)) { fdb_failed = 2UL; goto fdb_done; }
  fdb_t3 = (FdbU32)(fdb_t2 & 1UL);
  fdb_t4 = (FdbU32)(0UL - fdb_t3);
  fdb_t5 = (FdbU32)(fdb_t4 & 46080UL);
  fdb_t6 = (FdbU32)(fdb_t1 ^ fdb_t5);
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_read(fdb_words,606UL,&fdb_t7)) { fdb_failed = 2UL; goto fdb_done; }
  fdb_t8 = (FdbU32)(fdb_t7 == 0UL);
  fdb_t9 = (FdbU32)(fdb_t8 * 44257UL);
  fdb_t10 = (FdbU32)(fdb_t6 | fdb_t9);
  fdb_t11 = (FdbU32)(fdb_t10 & 65535UL);
  if (606UL >= 70000UL) { fdb_failed = 1UL; goto fdb_done; }
  if (fdb16_write(fdb_words,606UL,fdb_t11)) { fdb_failed = 2UL; goto fdb_done; }
fdb_done:
  fdb_result.status = fdb_failed;
  fdb_result.steps = 1UL-fdb_remaining;
  fdb_result.cut = 0UL;
  return fdb_result;
}
