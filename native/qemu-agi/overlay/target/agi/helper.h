/* SPDX-License-Identifier: GPL-2.0-or-later */
DEF_HELPER_4(agi_fault, noreturn, env, i32, i32, i32)
DEF_HELPER_2(agi_retire, void, env, i32)
DEF_HELPER_5(agi_binding, void, env, i32, i32, i32, i32)
DEF_HELPER_3(agi_draw, noreturn, env, i32, i32)
DEF_HELPER_5(agi_observe, void, env, i32, i32, i32, i32)
