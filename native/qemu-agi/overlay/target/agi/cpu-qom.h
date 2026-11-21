/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef AGI_CPU_QOM_H
#define AGI_CPU_QOM_H
#include "hw/core/cpu.h"
#define TYPE_AGI_CPU "agi-cpu"
OBJECT_DECLARE_CPU_TYPE(AgiCPU, AgiCPUClass, AGI_CPU)
#endif
