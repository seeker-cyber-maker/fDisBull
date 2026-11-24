/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SCUMM_CPU_QOM_H
#define SCUMM_CPU_QOM_H
#include "hw/core/cpu.h"
#define TYPE_SCUMM_CPU "scumm-cpu"
OBJECT_DECLARE_CPU_TYPE(ScummCPU, ScummCPUClass, SCUMM_CPU)
#endif
