/* SPDX-License-Identifier: GPL-2.0-or-later */
DEF_HELPER_2(scumm_step, void, env, i32)
DEF_HELPER_1(scumm_observe, void, env)
DEF_HELPER_1(scumm_fetch_fault, noreturn, env)
