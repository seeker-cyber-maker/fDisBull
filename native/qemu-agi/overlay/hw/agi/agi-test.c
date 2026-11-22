/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Minimal authored raw-LOGIC machine; no DOS or complete AGI engine implied.
 */
#include "qemu/osdep.h"
#include "qemu/cutils.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/boards.h"
#include "hw/loader.h"
#include "exec/address-spaces.h"
#include "target/agi/cpu-qom.h"
#include "target/agi/cpu.h"
#include "target/agi/runtime_qom.h"

#define TYPE_AGI_TEST_MACHINE MACHINE_TYPE_NAME("agi-test")
OBJECT_DECLARE_SIMPLE_TYPE(AgiTestMachineState, AGI_TEST_MACHINE)
struct AgiTestMachineState {
    MachineState parent_obj;
    char *view_catalog;
    char *runtime_package;
    bool draw_intent;
    bool initialized;
};

static char *agi_get_runtime_package(Object *obj, Error **errp)
{
    const AgiTestMachineState *m = AGI_TEST_MACHINE(obj);
    return g_strdup(m->runtime_package ? m->runtime_package : "");
}
static void agi_set_runtime_package(Object *obj, const char *value, Error **errp)
{
    AgiTestMachineState *m = AGI_TEST_MACHINE(obj);
    if (m->initialized || !value[0] || strlen(value) > 4096) {
        error_setg(errp, "AGI_RUNTIME_PACKAGE: nonempty startup-only path required");
        return;
    }
    g_free(m->runtime_package);
    m->runtime_package = g_strdup(value);
}

static char *agi_get_catalog(Object *obj, Error **errp)
{
    AgiTestMachineState *machine = AGI_TEST_MACHINE(obj);
    return g_strdup(machine->view_catalog ? machine->view_catalog : "");
}

static void agi_set_catalog(Object *obj, const char *value, Error **errp)
{
    AgiTestMachineState *machine = AGI_TEST_MACHINE(obj);
    if (machine->initialized || !value[0] || strlen(value) > 4096) {
        error_setg(errp, "AGI_VIEW_CATALOG: nonempty startup-only path required");
        return;
    }
    g_free(machine->view_catalog);
    machine->view_catalog = g_strdup(value);
}

static bool agi_get_draw_intent(Object *obj, Error **errp)
{
    return AGI_TEST_MACHINE(obj)->draw_intent;
}

static void agi_set_draw_intent(Object *obj, bool value, Error **errp)
{
    AgiTestMachineState *machine = AGI_TEST_MACHINE(obj);
    if (machine->initialized) {
        error_setg(errp, "AGI_DRAW_INTENT: startup-only selection required");
        return;
    }
    machine->draw_intent = value;
}

static ram_addr_t agi_fixup_ram_size(ram_addr_t size)
{
    return AGI_CODE_MAX;
}

static void agi_test_init(MachineState *machine)
{
    MachineClass *mc = MACHINE_GET_CLASS(machine);
    AgiTestMachineState *ms = AGI_TEST_MACHINE(machine);
    AgiCPU *cpu;
    FILE *fp;
    size_t size;
    g_autofree char *digest = NULL;
    Error *error = NULL;

    ms->initialized = true;

    if ((!machine->kernel_filename && !ms->runtime_package) || machine->ram_size != AGI_CODE_MAX) {
        error_report("agi-test requires raw -kernel or runtime-package and fixed 64 KiB RAM");
        exit(1);
    }
    if (ms->runtime_package && (ms->view_catalog || ms->draw_intent)) {
        error_report("AGI_RUNTIME_PACKAGE: runtime-package cannot combine with a pilot profile");
        exit(1);
    }
    if (ms->draw_intent && !ms->view_catalog) {
        error_report("AGI_DRAW_INTENT: draw-intent requires view-catalog");
        exit(1);
    }
    memory_region_add_subregion(get_system_memory(), 0, machine->ram);
    cpu = AGI_CPU(cpu_create(mc->default_cpu_type));
    if (ms->runtime_package) {
        cpu->runtime = agi_runtime_load_package(ms->runtime_package, &error);
        if (!cpu->runtime) { error_report_err(error); exit(1); }
        cpu->env.runtime_profile = 1;
        cpu->decode_logic = cpu->runtime->resources->entry_logic;
        cpu->code[0] = 0;
        cpu->env.code_size = 1;
        pstrcpy(cpu->source_sha256, sizeof(cpu->source_sha256), cpu->runtime->resources->sha256);
        rom_add_blob_fixed("agi.runtime.trampoline", cpu->code, 1, 0);
        memory_region_set_readonly(machine->ram, true);
        return;
    }
    if (ms->view_catalog && !agi_load_view_catalog(cpu, ms->view_catalog, &error)) {
        error_report_err(error);
        exit(1);
    }
    cpu->draw_intent = ms->draw_intent;
    cpu->env.draw_intent = ms->draw_intent;
    fp = fopen(machine->kernel_filename, "rb");
    if (!fp) {
        error_report("cannot open AGI raw code: %s", strerror(errno));
        exit(1);
    }
    size = fread(cpu->code, 1, sizeof(cpu->code), fp);
    if (ferror(fp) || size == 0 || size > AGI_CODE_MAX) {
        error_report("AGI raw code must contain 1..65536 bytes");
        fclose(fp);
        exit(1);
    }
    fclose(fp);
    cpu->env.code_size = size;
    digest = g_compute_checksum_for_data(G_CHECKSUM_SHA256, cpu->code, size);
    pstrcpy(cpu->source_sha256, sizeof(cpu->source_sha256), digest);
    rom_add_blob_fixed("agi.logic", cpu->code, size, 0);
    memory_region_set_readonly(machine->ram, true);
}

static void agi_test_class_init(ObjectClass *oc, void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "Bounded AGI scalar/position observation experiment";
    mc->init = agi_test_init;
    mc->default_cpu_type = TYPE_AGI_CPU;
    mc->default_ram_size = AGI_CODE_MAX;
    mc->default_ram_id = "agi.code";
    mc->fixup_ram_size = agi_fixup_ram_size;
    mc->no_cdrom = true;
    mc->no_floppy = true;
    mc->no_parallel = true;
    object_class_property_add_str(oc, "view-catalog", agi_get_catalog, agi_set_catalog);
    object_class_property_set_description(oc, "view-catalog",
        "Immutable bounded FDBAGIV1 catalog; selects the view-binding profile");
    object_class_property_add_bool(oc, "draw-intent",
                                  agi_get_draw_intent, agi_set_draw_intent);
    object_class_property_set_description(oc, "draw-intent",
        "Startup-only draw-intent profile; requires an immutable VIEW catalog");
    object_class_property_add_str(oc, "runtime-package", agi_get_runtime_package, agi_set_runtime_package);
    object_class_property_set_description(oc, "runtime-package",
        "Immutable AGI runtime resource package; selects the native runtime profile");
}

static void agi_test_finalize(Object *obj)
{
    g_free(AGI_TEST_MACHINE(obj)->view_catalog);
    g_free(AGI_TEST_MACHINE(obj)->runtime_package);
}

static const TypeInfo agi_test_type = {
    .name = TYPE_AGI_TEST_MACHINE,
    .parent = TYPE_MACHINE,
    .instance_size = sizeof(AgiTestMachineState),
    .class_init = agi_test_class_init,
    .instance_finalize = agi_test_finalize,
};

static void agi_test_register_types(void)
{
    type_register_static(&agi_test_type);
}
type_init(agi_test_register_types)
