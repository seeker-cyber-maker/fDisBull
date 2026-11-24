/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qemu/cutils.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/boards.h"
#include "hw/loader.h"
#include "exec/address-spaces.h"
#include "system/reset.h"
#include "target/scumm/cpu.h"
#define TYPE_SCUMM_TEST_MACHINE MACHINE_TYPE_NAME("scumm-test")
OBJECT_DECLARE_SIMPLE_TYPE(ScummTestMachineState,SCUMM_TEST_MACHINE)
struct ScummTestMachineState {
 MachineState parent_obj;
 unsigned version;
 bool initialized,selected;
 char *resource_manifest;
 ScummCPU *cpu;
};
static char *get_version(Object *obj,Error **errp){return g_strdup_printf("%u",SCUMM_TEST_MACHINE(obj)->version);}
static void set_version(Object *obj,const char *v,Error **errp)
{
 ScummTestMachineState *m=SCUMM_TEST_MACHINE(obj);
 if(m->initialized||strlen(v)!=1||v[0]<'0'||v[0]>'2'){
  error_setg(errp,"SCUMM version must be startup-only 0, 1, or 2");return;}
 m->version=v[0]-'0';m->selected=true;
}
static char *get_resource_manifest(Object *obj,Error **errp)
{return g_strdup(SCUMM_TEST_MACHINE(obj)->resource_manifest);}
static void set_resource_manifest(Object *obj,const char *value,Error **errp)
{
 ScummTestMachineState *m=SCUMM_TEST_MACHINE(obj);
 if(m->initialized||!value||!*value){
  error_setg(errp,"SCUMM resource-manifest requires a nonempty startup-only path");return;
 }
 g_free(m->resource_manifest);m->resource_manifest=g_strdup(value);
}
static ram_addr_t fix_ram(ram_addr_t size){return SCUMM_CODE_MAX;}
static void machine_init(MachineState *m)
{
 ScummTestMachineState *sm=SCUMM_TEST_MACHINE(m);sm->initialized=true;
 if(!sm->selected||!m->kernel_filename||m->ram_size!=SCUMM_CODE_MAX){
  error_report("scumm-test requires version=0|1|2, raw -kernel and fixed RAM");exit(1);}
 if(sm->resource_manifest&&sm->version!=2){
  error_report("SCUMM resource-manifest requires version=2");exit(1);
 }
 memory_region_add_subregion(get_system_memory(),0,m->ram);
 ScummCPU *cpu=SCUMM_CPU(cpu_create(MACHINE_GET_CLASS(m)->default_cpu_type));
 sm->cpu=cpu;qemu_register_resettable(OBJECT(cpu));
 FILE *fp=fopen(m->kernel_filename,"rb");
 if(!fp){error_report("cannot open script: %s",strerror(errno));exit(1);}
 size_t size=fread(cpu->code,1,sizeof(cpu->code),fp);bool bad=ferror(fp);fclose(fp);
 if(bad||!size||size>SCUMM_CODE_MAX){error_report("raw script must be 1..65536 bytes");exit(1);}
 cpu->env.version=sm->version;cpu->env.code_size=size;
 g_autofree char *digest=g_compute_checksum_for_data(G_CHECKSUM_SHA256,cpu->code,size);
 pstrcpy(cpu->sha256,sizeof(cpu->sha256),digest);
 if(sm->resource_manifest){
  Error *err=NULL;
  if(!scumm_resource_bank_load(sm->resource_manifest,cpu->code,size,
                                &cpu->runtime,&cpu->bank,&err)){
   error_report_err(err);exit(1);
  }
 }
 rom_add_blob_fixed("scumm.script",cpu->code,size,0);memory_region_set_readonly(m->ram,true);
}
static void machine_class(ObjectClass *oc,void *data)
{
 MachineClass *mc=MACHINE_CLASS(oc);mc->desc="Bounded early SCUMM processor experiment";
 mc->init=machine_init;mc->default_cpu_type=TYPE_SCUMM_CPU;mc->default_ram_size=SCUMM_CODE_MAX;
 mc->default_ram_id="scumm.code";mc->fixup_ram_size=fix_ram;
 mc->no_cdrom=true;mc->no_floppy=true;mc->no_parallel=true;mc->max_cpus=1;
 object_class_property_add_str(oc,"version",get_version,set_version);
 object_class_property_add_str(oc,"resource-manifest",get_resource_manifest,set_resource_manifest);
}
static void machine_finalize(Object *obj)
{
 ScummTestMachineState *m=SCUMM_TEST_MACHINE(obj);
 if(m->cpu)qemu_unregister_resettable(OBJECT(m->cpu));
 g_free(m->resource_manifest);
}
static const TypeInfo machine_type={.name=TYPE_SCUMM_TEST_MACHINE,.parent=TYPE_MACHINE,
 .instance_size=sizeof(ScummTestMachineState),.class_init=machine_class,
 .instance_finalize=machine_finalize};
static void register_machine(void){type_register_static(&machine_type);}
type_init(register_machine)
