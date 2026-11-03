#ifndef FDISBULL_NATIVE_MEMORY_ABI_1
#define FDISBULL_NATIVE_MEMORY_ABI_1
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef struct { uint32_t status, steps, cut; } FdbBlockResult;
#endif

#include "memory-runtime.h"
#include <pthread.h>
static pthread_t fdb_owner_id; __attribute__((constructor)) static void fdb_capture_owner(void) { fdb_owner_id=pthread_self(); }
static int fdb_owner_thread(void) { return pthread_equal(pthread_self(),fdb_owner_id); }
typedef struct { uint32_t start,count; } FdbRange;
enum { FDB_WORDS=70000, FDB_FUNCTIONS=5, FDB_REGIONS=1 };
static uint32_t g_words[FDB_WORDS] = {308u,307u,306u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,3u,1u,1u,1u,0u,0u,4660u,0u,0u,0u,0u,1u,312u,0u,1u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,126u,129u,165u,129u,189u,153u,129u,126u,126u,255u,219u,255u,195u,231u,255u,126u,108u,254u,254u,254u,124u,56u,16u,0u,16u,56u,124u,254u,124u,56u,16u,0u,56u,124u,56u,254u,254u,124u,56u,124u,16u,16u,56u,124u,254u,124u,56u,124u,0u,0u,24u,60u,60u,24u,0u,0u,255u,255u,231u,195u,195u,231u,255u,255u,0u,60u,102u,66u,66u,102u,60u,0u,255u,195u,153u,189u,189u,153u,195u,255u,15u,7u,15u,125u,204u,204u,204u,120u,60u,102u,102u,102u,60u,24u,126u,24u,63u,51u,63u,48u,48u,112u,240u,224u,127u,99u,127u,99u,99u,103u,230u,192u,153u,90u,60u,231u,231u,60u,90u,153u,128u,224u,248u,254u,248u,224u,128u,0u,2u,14u,62u,254u,62u,14u,2u,0u,24u,60u,126u,24u,24u,126u,60u,24u,102u,102u,102u,102u,102u,0u,102u,0u,127u,219u,219u,123u,27u,27u,27u,0u,62u,99u,56u,108u,108u,56u,204u,120u,0u,0u,0u,0u,126u,126u,126u,0u,24u,60u,126u,24u,126u,60u,24u,255u,24u,60u,126u,24u,24u,24u,24u,0u,24u,24u,24u,24u,126u,60u,24u,0u,0u,24u,12u,254u,12u,24u,0u,0u,0u,48u,96u,254u,96u,48u,0u,0u,0u,0u,192u,192u,192u,254u,0u,0u,0u,36u,102u,255u,102u,36u,0u,0u,0u,24u,60u,126u,255u,255u,0u,0u,0u,255u,255u,126u,60u,24u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,48u,120u,120u,48u,48u,0u,48u,0u,108u,108u,108u,0u,0u,0u,0u,0u,108u,108u,254u,108u,254u,108u,108u,0u,48u,124u,192u,120u,12u,248u,48u,0u,0u,198u,204u,24u,48u,102u,198u,0u,56u,108u,56u,118u,220u,204u,118u,0u,96u,96u,192u,0u,0u,0u,0u,0u,24u,48u,96u,96u,96u,48u,24u,0u,96u,48u,24u,24u,24u,48u,96u,0u,0u,102u,60u,255u,60u,102u,0u,0u,0u,48u,48u,252u,48u,48u,0u,0u,0u,0u,0u,0u,0u,48u,48u,96u,0u,0u,0u,252u,0u,0u,0u,0u,0u,0u,0u,0u,0u,48u,48u,0u,6u,12u,24u,48u,96u,192u,128u,0u,124u,198u,206u,222u,246u,230u,124u,0u,48u,112u,48u,48u,48u,48u,252u,0u,120u,204u,12u,56u,96u,204u,252u,0u,120u,204u,12u,56u,12u,204u,120u,0u,28u,60u,108u,204u,254u,12u,30u,0u,252u,192u,248u,12u,12u,204u,120u,0u,56u,96u,192u,248u,204u,204u,120u,0u,252u,204u,12u,24u,48u,48u,48u,0u,120u,204u,204u,120u,204u,204u,120u,0u,120u,204u,204u,124u,12u,24u,112u,0u,0u,48u,48u,0u,0u,48u,48u,0u,0u,48u,48u,0u,0u,48u,48u,96u,24u,48u,96u,192u,96u,48u,24u,0u,0u,0u,252u,0u,0u,252u,0u,0u,96u,48u,24u,12u,24u,48u,96u,0u,120u,204u,12u,24u,48u,0u,48u,0u,124u,198u,222u,222u,222u,192u,120u,0u,48u,120u,204u,204u,252u,204u,204u,0u,252u,102u,102u,124u,102u,102u,252u,0u,60u,102u,192u,192u,192u,102u,60u,0u,248u,108u,102u,102u,102u,108u,248u,0u,254u,98u,104u,120u,104u,98u,254u,0u,254u,98u,104u,120u,104u,96u,240u,0u,60u,102u,192u,192u,206u,102u,62u,0u,204u,204u,204u,252u,204u,204u,204u,0u,120u,48u,48u,48u,48u,48u,120u,0u,30u,12u,12u,12u,204u,204u,120u,0u,230u,102u,108u,120u,108u,102u,230u,0u,240u,96u,96u,96u,98u,102u,254u,0u,198u,238u,254u,254u,214u,198u,198u,0u,198u,230u,246u,222u,206u,198u,198u,0u,56u,108u,198u,198u,198u,108u,56u,0u,252u,102u,102u,124u,96u,96u,240u,0u,120u,204u,204u,204u,220u,120u,28u,0u,252u,102u,102u,124u,108u,102u,230u,0u,120u,204u,224u,112u,28u,204u,120u,0u,252u,180u,48u,48u,48u,48u,120u,0u,204u,204u,204u,204u,204u,204u,252u,0u,204u,204u,204u,204u,204u,120u,48u,0u,198u,198u,198u,214u,254u,238u,198u,0u,198u,198u,108u,56u,56u,108u,198u,0u,204u,204u,204u,120u,48u,48u,120u,0u,254u,198u,140u,24u,50u,102u,254u,0u,120u,96u,96u,96u,96u,96u,120u,0u,192u,96u,48u,24u,12u,6u,2u,0u,120u,24u,24u,24u,24u,24u,120u,0u,16u,56u,108u,198u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,255u,48u,48u,24u,0u,0u,0u,0u,0u,0u,0u,120u,12u,124u,204u,118u,0u,224u,96u,96u,124u,102u,102u,220u,0u,0u,0u,120u,204u,192u,204u,120u,0u,28u,12u,12u,124u,204u,204u,118u,0u,0u,0u,120u,204u,252u,192u,120u,0u,56u,108u,96u,240u,96u,96u,240u,0u,0u,0u,118u,204u,204u,124u,12u,248u,224u,96u,108u,118u,102u,102u,230u,0u,48u,0u,112u,48u,48u,48u,120u,0u,12u,0u,12u,12u,12u,204u,204u,120u,224u,96u,102u,108u,120u,108u,230u,0u,112u,48u,48u,48u,48u,48u,120u,0u,0u,0u,204u,254u,254u,214u,198u,0u,0u,0u,248u,204u,204u,204u,204u,0u,0u,0u,120u,204u,204u,204u,120u,0u,0u,0u,220u,102u,102u,124u,96u,240u,0u,0u,118u,204u,204u,124u,12u,30u,0u,0u,220u,118u,102u,96u,240u,0u,0u,0u,124u,192u,120u,12u,248u,0u,16u,48u,124u,48u,48u,52u,24u,0u,0u,0u,204u,204u,204u,204u,118u,0u,0u,0u,204u,204u,204u,120u,48u,0u,0u,0u,198u,214u,254u,254u,108u,0u,0u,0u,198u,108u,56u,108u,198u,0u,0u,0u,204u,204u,204u,124u,12u,248u,0u,0u,252u,152u,48u,100u,252u,0u,28u,48u,48u,224u,48u,48u,28u,0u,24u,24u,24u,0u,24u,24u,24u,0u,224u,48u,48u,28u,48u,48u,224u,0u,118u,220u,0u,0u,0u,0u,0u,0u,0u,16u,56u,108u,198u,198u,254u,0u,120u,204u,192u,204u,120u,24u,12u,120u,0u,204u,0u,204u,204u,204u,126u,0u,28u,0u,120u,204u,252u,192u,120u,0u,126u,195u,60u,6u,62u,102u,63u,0u,204u,0u,120u,12u,124u,204u,126u,0u,224u,0u,120u,12u,124u,204u,126u,0u,48u,48u,120u,12u,124u,204u,126u,0u,0u,0u,120u,192u,192u,120u,12u,56u,126u,195u,60u,102u,126u,96u,60u,0u,204u,0u,120u,204u,252u,192u,120u,0u,224u,0u,120u,204u,252u,192u,120u,0u,204u,0u,112u,48u,48u,48u,120u,0u,124u,198u,56u,24u,24u,24u,60u,0u,224u,0u,112u,48u,48u,48u,120u,0u,198u,56u,108u,198u,254u,198u,198u,0u,48u,48u,0u,120u,204u,252u,204u,0u,28u,0u,252u,96u,120u,96u,252u,0u,0u,0u,127u,12u,127u,204u,127u,0u,62u,108u,204u,254u,204u,204u,206u,0u,120u,204u,0u,120u,204u,204u,120u,0u,0u,204u,0u,120u,204u,204u,120u,0u,0u,224u,0u,120u,204u,204u,120u,0u,120u,204u,0u,204u,204u,204u,126u,0u,0u,224u,0u,204u,204u,204u,126u,0u,0u,204u,0u,204u,204u,124u,12u,248u,195u,24u,60u,102u,102u,60u,24u,0u,204u,0u,204u,204u,204u,204u,120u,0u,24u,24u,126u,192u,192u,126u,24u,24u,56u,108u,100u,240u,96u,230u,252u,0u,204u,204u,120u,252u,48u,252u,48u,48u,248u,204u,204u,250u,198u,207u,198u,199u,14u,27u,24u,60u,24u,24u,216u,112u,28u,0u,120u,12u,124u,204u,126u,0u,56u,0u,112u,48u,48u,48u,120u,0u,0u,28u,0u,120u,204u,204u,120u,0u,0u,28u,0u,204u,204u,204u,126u,0u,0u,248u,0u,248u,204u,204u,204u,0u,252u,0u,204u,236u,252u,220u,204u,0u,60u,108u,108u,62u,0u,126u,0u,0u,56u,108u,108u,56u,0u,124u,0u,0u,48u,0u,48u,96u,192u,204u,120u,0u,0u,0u,0u,252u,192u,192u,0u,0u,0u,0u,0u,252u,12u,12u,0u,0u,195u,198u,204u,222u,51u,102u,204u,15u,195u,198u,204u,219u,55u,111u,207u,3u,24u,24u,0u,24u,24u,24u,24u,0u,0u,51u,102u,204u,102u,51u,0u,0u,0u,204u,102u,51u,102u,204u,0u,0u,34u,136u,34u,136u,34u,136u,34u,136u,85u,170u,85u,170u,85u,170u,85u,170u,219u,119u,219u,238u,219u,119u,219u,238u,24u,24u,24u,24u,24u,24u,24u,24u,24u,24u,24u,24u,248u,24u,24u,24u,24u,24u,248u,24u,248u,24u,24u,24u,54u,54u,54u,54u,246u,54u,54u,54u,0u,0u,0u,0u,254u,54u,54u,54u,0u,0u,248u,24u,248u,24u,24u,24u,54u,54u,246u,6u,246u,54u,54u,54u,54u,54u,54u,54u,54u,54u,54u,54u,0u,0u,254u,6u,246u,54u,54u,54u,54u,54u,246u,6u,254u,0u,0u,0u,54u,54u,54u,54u,254u,0u,0u,0u,24u,24u,248u,24u,248u,0u,0u,0u,0u,0u,0u,0u,248u,24u,24u,24u,24u,24u,24u,24u,31u,0u,0u,0u,24u,24u,24u,24u,255u,0u,0u,0u,0u,0u,0u,0u,255u,24u,24u,24u,24u,24u,24u,24u,31u,24u,24u,24u,0u,0u,0u,0u,255u,0u,0u,0u,24u,24u,24u,24u,255u,24u,24u,24u,24u,24u,31u,24u,31u,24u,24u,24u,54u,54u,54u,54u,55u,54u,54u,54u,54u,54u,55u,48u,63u,0u,0u,0u,0u,0u,63u,48u,55u,54u,54u,54u,54u,54u,247u,0u,255u,0u,0u,0u,0u,0u,255u,0u,247u,54u,54u,54u,54u,54u,55u,48u,55u,54u,54u,54u,0u,0u,255u,0u,255u,0u,0u,0u,54u,54u,247u,0u,247u,54u,54u,54u,24u,24u,255u,0u,255u,0u,0u,0u,54u,54u,54u,54u,255u,0u,0u,0u,0u,0u,255u,0u,255u,24u,24u,24u,0u,0u,0u,0u,255u,54u,54u,54u,54u,54u,54u,54u,63u,0u,0u,0u,24u,24u,31u,24u,31u,0u,0u,0u,0u,0u,31u,24u,31u,24u,24u,24u,0u,0u,0u,0u,63u,54u,54u,54u,54u,54u,54u,54u,255u,54u,54u,54u,24u,24u,255u,24u,255u,24u,24u,24u,24u,24u,24u,24u,248u,0u,0u,0u,0u,0u,0u,0u,31u,24u,24u,24u,255u,255u,255u,255u,255u,255u,255u,255u,0u,0u,0u,0u,255u,255u,255u,255u,240u,240u,240u,240u,240u,240u,240u,240u,15u,15u,15u,15u,15u,15u,15u,15u,255u,255u,255u,255u,0u,0u,0u,0u,0u,0u,118u,220u,200u,220u,118u,0u,0u,120u,204u,248u,204u,248u,192u,192u,0u,252u,204u,192u,192u,192u,192u,0u,0u,254u,108u,108u,108u,108u,108u,0u,252u,204u,96u,48u,96u,204u,252u,0u,0u,0u,126u,216u,216u,216u,112u,0u,0u,102u,102u,102u,102u,124u,96u,192u,0u,118u,220u,24u,24u,24u,24u,0u,252u,48u,120u,204u,204u,120u,48u,252u,56u,108u,198u,254u,198u,108u,56u,0u,56u,108u,198u,198u,108u,108u,238u,0u,28u,48u,24u,124u,204u,204u,120u,0u,0u,0u,126u,219u,219u,126u,0u,0u,6u,12u,126u,219u,219u,126u,96u,192u,56u,96u,192u,248u,192u,96u,56u,0u,120u,204u,204u,204u,204u,204u,204u,0u,0u,252u,0u,252u,0u,252u,0u,0u,48u,48u,252u,48u,48u,0u,252u,0u,96u,48u,24u,48u,96u,0u,252u,0u,24u,48u,96u,48u,24u,0u,252u,0u,14u,27u,27u,24u,24u,24u,24u,24u,24u,24u,24u,24u,24u,216u,216u,112u,48u,48u,0u,252u,0u,48u,48u,0u,0u,118u,220u,0u,118u,220u,0u,0u,56u,108u,108u,56u,0u,0u,0u,0u,0u,0u,0u,24u,24u,0u,0u,0u,0u,0u,0u,0u,24u,0u,0u,0u,15u,12u,12u,12u,236u,108u,60u,28u,120u,108u,108u,108u,108u,0u,0u,0u,112u,24u,48u,96u,120u,0u,0u,0u,0u,0u,60u,60u,60u,60u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,83u,78u,65u,75u,69u,32u,118u,49u,32u,32u,83u,67u,79u,82u,69u,32u,80u,65u,85u,83u,69u,68u,32u,82u,85u,78u,78u,73u,78u,71u,68u,69u,65u,68u,32u,32u,32u,87u,79u,78u,32u,32u,32u,32u,65u,114u,114u,111u,119u,115u,47u,87u,65u,83u,68u,32u,32u,80u,58u,112u,97u,117u,115u,101u,32u,78u,58u,115u,116u,101u,112u,32u,82u,58u,114u,101u,115u,101u,116u,32u,69u,115u,99u,85u,80u,76u,82u,68u,78u,80u,65u,85u,83u,69u,83u,84u,69u,80u,82u,69u,83u,69u,84u,77u,79u,85u,83u,69u,75u,69u,89u,83u,32u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u,0u};
static uint64_t g_revision=0,g_epoch=0,g_calls[FDB_FUNCTIONS];
static int g_closed=0,g_busy=0; static uint32_t g_last_steps=0;
static _Thread_local const char *g_error="";
static const char *g_names[] = {"action","render","reset","rng","step"};
static int fail(const char *message) { g_error=message; return 1; }
static int admit(void) { if(!fdb_owner_thread()) return fail("Main-thread owner required"); if(g_closed) return fail("Shell closed"); if(g_busy) return fail("Reentrant shell operation"); return 0; }
static int inside(uint32_t i,const FdbRange *r,size_t n) { for(size_t j=0;j<n;j++) if(i>=r[j].start && i-r[j].start<r[j].count) return 1; return 0; }
static int compare_words(const void *a,const void *b) { uint32_t x=*(const uint32_t*)a,y=*(const uint32_t*)b; return (x>y)-(x<y); }
static const FdbRange commit_ranges[] = {{0u,621u},{4096u,64000u}};
static const FdbRange replace_ranges[] = {{0u,621u},{4096u,64000u}};
static const uint32_t input_indices[] = {630u,631u,632u,633u,634u,635u,636u};
static const FdbRange outputs_0[] = {{0u,621u}};
static const FdbRange outputs_1[] = {{610u,1u},{614u,1u},{760u,13u},{4096u,64000u}};
static const FdbRange outputs_2[] = {{0u,621u}};
static const FdbRange outputs_3[] = {{606u,1u}};
static const FdbRange outputs_4[] = {{0u,621u}};
static uint32_t g_choice_0=1u; static uint64_t g_region_calls_0[2];
static int validate(const uint32_t *w) {
if(w[600]<1u || w[600]>600u) return fail("State guard refused");
if(w[601]<0u || w[601]>3u) return fail("State guard refused");
if(w[602]<0u || w[602]>3u) return fail("State guard refused");
if(w[603]<0u || w[603]>1u) return fail("State guard refused");
if(w[604]<0u || w[604]>2u) return fail("State guard refused");
if(w[605]<0u || w[605]>65535u) return fail("State guard refused");
if(w[606]<0u || w[606]>65535u) return fail("State guard refused");
if(w[607]<0u || w[607]>65535u) return fail("State guard refused");
if(w[608]<0u || w[608]>65535u) return fail("State guard refused");
if(w[609]<0u || w[609]>65535u) return fail("State guard refused");
if(w[610]<0u || w[610]>65535u) return fail("State guard refused");
if(w[611]<0u || w[611]>1u) return fail("State guard refused");
if(w[612]<0u || w[612]>65535u) return fail("State guard refused");
if(w[613]<0u || w[613]>1u) return fail("State guard refused");
if(w[614]<0u || w[614]>1u) return fail("State guard refused");
if(w[615]<0u || w[615]>1u) return fail("State guard refused");
if(w[616]<0u || w[616]>1u) return fail("State guard refused");
if(w[617]<0u || w[617]>7u) return fail("State guard refused");
if(w[618]<0u || w[618]>319u) return fail("State guard refused");
if(w[619]<0u || w[619]>199u) return fail("State guard refused");
if(w[620]<0u || w[620]>65535u) return fail("State guard refused");
if(w[0]<0u || w[0]>599u) return fail("State guard refused");
if(w[1]<0u || w[1]>599u) return fail("State guard refused");
if(w[2]<0u || w[2]>599u) return fail("State guard refused");
if(w[3]<0u || w[3]>599u) return fail("State guard refused");
if(w[4]<0u || w[4]>599u) return fail("State guard refused");
if(w[5]<0u || w[5]>599u) return fail("State guard refused");
if(w[6]<0u || w[6]>599u) return fail("State guard refused");
if(w[7]<0u || w[7]>599u) return fail("State guard refused");
if(w[8]<0u || w[8]>599u) return fail("State guard refused");
if(w[9]<0u || w[9]>599u) return fail("State guard refused");
if(w[10]<0u || w[10]>599u) return fail("State guard refused");
if(w[11]<0u || w[11]>599u) return fail("State guard refused");
if(w[12]<0u || w[12]>599u) return fail("State guard refused");
if(w[13]<0u || w[13]>599u) return fail("State guard refused");
if(w[14]<0u || w[14]>599u) return fail("State guard refused");
if(w[15]<0u || w[15]>599u) return fail("State guard refused");
if(w[16]<0u || w[16]>599u) return fail("State guard refused");
if(w[17]<0u || w[17]>599u) return fail("State guard refused");
if(w[18]<0u || w[18]>599u) return fail("State guard refused");
if(w[19]<0u || w[19]>599u) return fail("State guard refused");
if(w[20]<0u || w[20]>599u) return fail("State guard refused");
if(w[21]<0u || w[21]>599u) return fail("State guard refused");
if(w[22]<0u || w[22]>599u) return fail("State guard refused");
if(w[23]<0u || w[23]>599u) return fail("State guard refused");
if(w[24]<0u || w[24]>599u) return fail("State guard refused");
if(w[25]<0u || w[25]>599u) return fail("State guard refused");
if(w[26]<0u || w[26]>599u) return fail("State guard refused");
if(w[27]<0u || w[27]>599u) return fail("State guard refused");
if(w[28]<0u || w[28]>599u) return fail("State guard refused");
if(w[29]<0u || w[29]>599u) return fail("State guard refused");
if(w[30]<0u || w[30]>599u) return fail("State guard refused");
if(w[31]<0u || w[31]>599u) return fail("State guard refused");
if(w[32]<0u || w[32]>599u) return fail("State guard refused");
if(w[33]<0u || w[33]>599u) return fail("State guard refused");
if(w[34]<0u || w[34]>599u) return fail("State guard refused");
if(w[35]<0u || w[35]>599u) return fail("State guard refused");
if(w[36]<0u || w[36]>599u) return fail("State guard refused");
if(w[37]<0u || w[37]>599u) return fail("State guard refused");
if(w[38]<0u || w[38]>599u) return fail("State guard refused");
if(w[39]<0u || w[39]>599u) return fail("State guard refused");
if(w[40]<0u || w[40]>599u) return fail("State guard refused");
if(w[41]<0u || w[41]>599u) return fail("State guard refused");
if(w[42]<0u || w[42]>599u) return fail("State guard refused");
if(w[43]<0u || w[43]>599u) return fail("State guard refused");
if(w[44]<0u || w[44]>599u) return fail("State guard refused");
if(w[45]<0u || w[45]>599u) return fail("State guard refused");
if(w[46]<0u || w[46]>599u) return fail("State guard refused");
if(w[47]<0u || w[47]>599u) return fail("State guard refused");
if(w[48]<0u || w[48]>599u) return fail("State guard refused");
if(w[49]<0u || w[49]>599u) return fail("State guard refused");
if(w[50]<0u || w[50]>599u) return fail("State guard refused");
if(w[51]<0u || w[51]>599u) return fail("State guard refused");
if(w[52]<0u || w[52]>599u) return fail("State guard refused");
if(w[53]<0u || w[53]>599u) return fail("State guard refused");
if(w[54]<0u || w[54]>599u) return fail("State guard refused");
if(w[55]<0u || w[55]>599u) return fail("State guard refused");
if(w[56]<0u || w[56]>599u) return fail("State guard refused");
if(w[57]<0u || w[57]>599u) return fail("State guard refused");
if(w[58]<0u || w[58]>599u) return fail("State guard refused");
if(w[59]<0u || w[59]>599u) return fail("State guard refused");
if(w[60]<0u || w[60]>599u) return fail("State guard refused");
if(w[61]<0u || w[61]>599u) return fail("State guard refused");
if(w[62]<0u || w[62]>599u) return fail("State guard refused");
if(w[63]<0u || w[63]>599u) return fail("State guard refused");
if(w[64]<0u || w[64]>599u) return fail("State guard refused");
if(w[65]<0u || w[65]>599u) return fail("State guard refused");
if(w[66]<0u || w[66]>599u) return fail("State guard refused");
if(w[67]<0u || w[67]>599u) return fail("State guard refused");
if(w[68]<0u || w[68]>599u) return fail("State guard refused");
if(w[69]<0u || w[69]>599u) return fail("State guard refused");
if(w[70]<0u || w[70]>599u) return fail("State guard refused");
if(w[71]<0u || w[71]>599u) return fail("State guard refused");
if(w[72]<0u || w[72]>599u) return fail("State guard refused");
if(w[73]<0u || w[73]>599u) return fail("State guard refused");
if(w[74]<0u || w[74]>599u) return fail("State guard refused");
if(w[75]<0u || w[75]>599u) return fail("State guard refused");
if(w[76]<0u || w[76]>599u) return fail("State guard refused");
if(w[77]<0u || w[77]>599u) return fail("State guard refused");
if(w[78]<0u || w[78]>599u) return fail("State guard refused");
if(w[79]<0u || w[79]>599u) return fail("State guard refused");
if(w[80]<0u || w[80]>599u) return fail("State guard refused");
if(w[81]<0u || w[81]>599u) return fail("State guard refused");
if(w[82]<0u || w[82]>599u) return fail("State guard refused");
if(w[83]<0u || w[83]>599u) return fail("State guard refused");
if(w[84]<0u || w[84]>599u) return fail("State guard refused");
if(w[85]<0u || w[85]>599u) return fail("State guard refused");
if(w[86]<0u || w[86]>599u) return fail("State guard refused");
if(w[87]<0u || w[87]>599u) return fail("State guard refused");
if(w[88]<0u || w[88]>599u) return fail("State guard refused");
if(w[89]<0u || w[89]>599u) return fail("State guard refused");
if(w[90]<0u || w[90]>599u) return fail("State guard refused");
if(w[91]<0u || w[91]>599u) return fail("State guard refused");
if(w[92]<0u || w[92]>599u) return fail("State guard refused");
if(w[93]<0u || w[93]>599u) return fail("State guard refused");
if(w[94]<0u || w[94]>599u) return fail("State guard refused");
if(w[95]<0u || w[95]>599u) return fail("State guard refused");
if(w[96]<0u || w[96]>599u) return fail("State guard refused");
if(w[97]<0u || w[97]>599u) return fail("State guard refused");
if(w[98]<0u || w[98]>599u) return fail("State guard refused");
if(w[99]<0u || w[99]>599u) return fail("State guard refused");
if(w[100]<0u || w[100]>599u) return fail("State guard refused");
if(w[101]<0u || w[101]>599u) return fail("State guard refused");
if(w[102]<0u || w[102]>599u) return fail("State guard refused");
if(w[103]<0u || w[103]>599u) return fail("State guard refused");
if(w[104]<0u || w[104]>599u) return fail("State guard refused");
if(w[105]<0u || w[105]>599u) return fail("State guard refused");
if(w[106]<0u || w[106]>599u) return fail("State guard refused");
if(w[107]<0u || w[107]>599u) return fail("State guard refused");
if(w[108]<0u || w[108]>599u) return fail("State guard refused");
if(w[109]<0u || w[109]>599u) return fail("State guard refused");
if(w[110]<0u || w[110]>599u) return fail("State guard refused");
if(w[111]<0u || w[111]>599u) return fail("State guard refused");
if(w[112]<0u || w[112]>599u) return fail("State guard refused");
if(w[113]<0u || w[113]>599u) return fail("State guard refused");
if(w[114]<0u || w[114]>599u) return fail("State guard refused");
if(w[115]<0u || w[115]>599u) return fail("State guard refused");
if(w[116]<0u || w[116]>599u) return fail("State guard refused");
if(w[117]<0u || w[117]>599u) return fail("State guard refused");
if(w[118]<0u || w[118]>599u) return fail("State guard refused");
if(w[119]<0u || w[119]>599u) return fail("State guard refused");
if(w[120]<0u || w[120]>599u) return fail("State guard refused");
if(w[121]<0u || w[121]>599u) return fail("State guard refused");
if(w[122]<0u || w[122]>599u) return fail("State guard refused");
if(w[123]<0u || w[123]>599u) return fail("State guard refused");
if(w[124]<0u || w[124]>599u) return fail("State guard refused");
if(w[125]<0u || w[125]>599u) return fail("State guard refused");
if(w[126]<0u || w[126]>599u) return fail("State guard refused");
if(w[127]<0u || w[127]>599u) return fail("State guard refused");
if(w[128]<0u || w[128]>599u) return fail("State guard refused");
if(w[129]<0u || w[129]>599u) return fail("State guard refused");
if(w[130]<0u || w[130]>599u) return fail("State guard refused");
if(w[131]<0u || w[131]>599u) return fail("State guard refused");
if(w[132]<0u || w[132]>599u) return fail("State guard refused");
if(w[133]<0u || w[133]>599u) return fail("State guard refused");
if(w[134]<0u || w[134]>599u) return fail("State guard refused");
if(w[135]<0u || w[135]>599u) return fail("State guard refused");
if(w[136]<0u || w[136]>599u) return fail("State guard refused");
if(w[137]<0u || w[137]>599u) return fail("State guard refused");
if(w[138]<0u || w[138]>599u) return fail("State guard refused");
if(w[139]<0u || w[139]>599u) return fail("State guard refused");
if(w[140]<0u || w[140]>599u) return fail("State guard refused");
if(w[141]<0u || w[141]>599u) return fail("State guard refused");
if(w[142]<0u || w[142]>599u) return fail("State guard refused");
if(w[143]<0u || w[143]>599u) return fail("State guard refused");
if(w[144]<0u || w[144]>599u) return fail("State guard refused");
if(w[145]<0u || w[145]>599u) return fail("State guard refused");
if(w[146]<0u || w[146]>599u) return fail("State guard refused");
if(w[147]<0u || w[147]>599u) return fail("State guard refused");
if(w[148]<0u || w[148]>599u) return fail("State guard refused");
if(w[149]<0u || w[149]>599u) return fail("State guard refused");
if(w[150]<0u || w[150]>599u) return fail("State guard refused");
if(w[151]<0u || w[151]>599u) return fail("State guard refused");
if(w[152]<0u || w[152]>599u) return fail("State guard refused");
if(w[153]<0u || w[153]>599u) return fail("State guard refused");
if(w[154]<0u || w[154]>599u) return fail("State guard refused");
if(w[155]<0u || w[155]>599u) return fail("State guard refused");
if(w[156]<0u || w[156]>599u) return fail("State guard refused");
if(w[157]<0u || w[157]>599u) return fail("State guard refused");
if(w[158]<0u || w[158]>599u) return fail("State guard refused");
if(w[159]<0u || w[159]>599u) return fail("State guard refused");
if(w[160]<0u || w[160]>599u) return fail("State guard refused");
if(w[161]<0u || w[161]>599u) return fail("State guard refused");
if(w[162]<0u || w[162]>599u) return fail("State guard refused");
if(w[163]<0u || w[163]>599u) return fail("State guard refused");
if(w[164]<0u || w[164]>599u) return fail("State guard refused");
if(w[165]<0u || w[165]>599u) return fail("State guard refused");
if(w[166]<0u || w[166]>599u) return fail("State guard refused");
if(w[167]<0u || w[167]>599u) return fail("State guard refused");
if(w[168]<0u || w[168]>599u) return fail("State guard refused");
if(w[169]<0u || w[169]>599u) return fail("State guard refused");
if(w[170]<0u || w[170]>599u) return fail("State guard refused");
if(w[171]<0u || w[171]>599u) return fail("State guard refused");
if(w[172]<0u || w[172]>599u) return fail("State guard refused");
if(w[173]<0u || w[173]>599u) return fail("State guard refused");
if(w[174]<0u || w[174]>599u) return fail("State guard refused");
if(w[175]<0u || w[175]>599u) return fail("State guard refused");
if(w[176]<0u || w[176]>599u) return fail("State guard refused");
if(w[177]<0u || w[177]>599u) return fail("State guard refused");
if(w[178]<0u || w[178]>599u) return fail("State guard refused");
if(w[179]<0u || w[179]>599u) return fail("State guard refused");
if(w[180]<0u || w[180]>599u) return fail("State guard refused");
if(w[181]<0u || w[181]>599u) return fail("State guard refused");
if(w[182]<0u || w[182]>599u) return fail("State guard refused");
if(w[183]<0u || w[183]>599u) return fail("State guard refused");
if(w[184]<0u || w[184]>599u) return fail("State guard refused");
if(w[185]<0u || w[185]>599u) return fail("State guard refused");
if(w[186]<0u || w[186]>599u) return fail("State guard refused");
if(w[187]<0u || w[187]>599u) return fail("State guard refused");
if(w[188]<0u || w[188]>599u) return fail("State guard refused");
if(w[189]<0u || w[189]>599u) return fail("State guard refused");
if(w[190]<0u || w[190]>599u) return fail("State guard refused");
if(w[191]<0u || w[191]>599u) return fail("State guard refused");
if(w[192]<0u || w[192]>599u) return fail("State guard refused");
if(w[193]<0u || w[193]>599u) return fail("State guard refused");
if(w[194]<0u || w[194]>599u) return fail("State guard refused");
if(w[195]<0u || w[195]>599u) return fail("State guard refused");
if(w[196]<0u || w[196]>599u) return fail("State guard refused");
if(w[197]<0u || w[197]>599u) return fail("State guard refused");
if(w[198]<0u || w[198]>599u) return fail("State guard refused");
if(w[199]<0u || w[199]>599u) return fail("State guard refused");
if(w[200]<0u || w[200]>599u) return fail("State guard refused");
if(w[201]<0u || w[201]>599u) return fail("State guard refused");
if(w[202]<0u || w[202]>599u) return fail("State guard refused");
if(w[203]<0u || w[203]>599u) return fail("State guard refused");
if(w[204]<0u || w[204]>599u) return fail("State guard refused");
if(w[205]<0u || w[205]>599u) return fail("State guard refused");
if(w[206]<0u || w[206]>599u) return fail("State guard refused");
if(w[207]<0u || w[207]>599u) return fail("State guard refused");
if(w[208]<0u || w[208]>599u) return fail("State guard refused");
if(w[209]<0u || w[209]>599u) return fail("State guard refused");
if(w[210]<0u || w[210]>599u) return fail("State guard refused");
if(w[211]<0u || w[211]>599u) return fail("State guard refused");
if(w[212]<0u || w[212]>599u) return fail("State guard refused");
if(w[213]<0u || w[213]>599u) return fail("State guard refused");
if(w[214]<0u || w[214]>599u) return fail("State guard refused");
if(w[215]<0u || w[215]>599u) return fail("State guard refused");
if(w[216]<0u || w[216]>599u) return fail("State guard refused");
if(w[217]<0u || w[217]>599u) return fail("State guard refused");
if(w[218]<0u || w[218]>599u) return fail("State guard refused");
if(w[219]<0u || w[219]>599u) return fail("State guard refused");
if(w[220]<0u || w[220]>599u) return fail("State guard refused");
if(w[221]<0u || w[221]>599u) return fail("State guard refused");
if(w[222]<0u || w[222]>599u) return fail("State guard refused");
if(w[223]<0u || w[223]>599u) return fail("State guard refused");
if(w[224]<0u || w[224]>599u) return fail("State guard refused");
if(w[225]<0u || w[225]>599u) return fail("State guard refused");
if(w[226]<0u || w[226]>599u) return fail("State guard refused");
if(w[227]<0u || w[227]>599u) return fail("State guard refused");
if(w[228]<0u || w[228]>599u) return fail("State guard refused");
if(w[229]<0u || w[229]>599u) return fail("State guard refused");
if(w[230]<0u || w[230]>599u) return fail("State guard refused");
if(w[231]<0u || w[231]>599u) return fail("State guard refused");
if(w[232]<0u || w[232]>599u) return fail("State guard refused");
if(w[233]<0u || w[233]>599u) return fail("State guard refused");
if(w[234]<0u || w[234]>599u) return fail("State guard refused");
if(w[235]<0u || w[235]>599u) return fail("State guard refused");
if(w[236]<0u || w[236]>599u) return fail("State guard refused");
if(w[237]<0u || w[237]>599u) return fail("State guard refused");
if(w[238]<0u || w[238]>599u) return fail("State guard refused");
if(w[239]<0u || w[239]>599u) return fail("State guard refused");
if(w[240]<0u || w[240]>599u) return fail("State guard refused");
if(w[241]<0u || w[241]>599u) return fail("State guard refused");
if(w[242]<0u || w[242]>599u) return fail("State guard refused");
if(w[243]<0u || w[243]>599u) return fail("State guard refused");
if(w[244]<0u || w[244]>599u) return fail("State guard refused");
if(w[245]<0u || w[245]>599u) return fail("State guard refused");
if(w[246]<0u || w[246]>599u) return fail("State guard refused");
if(w[247]<0u || w[247]>599u) return fail("State guard refused");
if(w[248]<0u || w[248]>599u) return fail("State guard refused");
if(w[249]<0u || w[249]>599u) return fail("State guard refused");
if(w[250]<0u || w[250]>599u) return fail("State guard refused");
if(w[251]<0u || w[251]>599u) return fail("State guard refused");
if(w[252]<0u || w[252]>599u) return fail("State guard refused");
if(w[253]<0u || w[253]>599u) return fail("State guard refused");
if(w[254]<0u || w[254]>599u) return fail("State guard refused");
if(w[255]<0u || w[255]>599u) return fail("State guard refused");
if(w[256]<0u || w[256]>599u) return fail("State guard refused");
if(w[257]<0u || w[257]>599u) return fail("State guard refused");
if(w[258]<0u || w[258]>599u) return fail("State guard refused");
if(w[259]<0u || w[259]>599u) return fail("State guard refused");
if(w[260]<0u || w[260]>599u) return fail("State guard refused");
if(w[261]<0u || w[261]>599u) return fail("State guard refused");
if(w[262]<0u || w[262]>599u) return fail("State guard refused");
if(w[263]<0u || w[263]>599u) return fail("State guard refused");
if(w[264]<0u || w[264]>599u) return fail("State guard refused");
if(w[265]<0u || w[265]>599u) return fail("State guard refused");
if(w[266]<0u || w[266]>599u) return fail("State guard refused");
if(w[267]<0u || w[267]>599u) return fail("State guard refused");
if(w[268]<0u || w[268]>599u) return fail("State guard refused");
if(w[269]<0u || w[269]>599u) return fail("State guard refused");
if(w[270]<0u || w[270]>599u) return fail("State guard refused");
if(w[271]<0u || w[271]>599u) return fail("State guard refused");
if(w[272]<0u || w[272]>599u) return fail("State guard refused");
if(w[273]<0u || w[273]>599u) return fail("State guard refused");
if(w[274]<0u || w[274]>599u) return fail("State guard refused");
if(w[275]<0u || w[275]>599u) return fail("State guard refused");
if(w[276]<0u || w[276]>599u) return fail("State guard refused");
if(w[277]<0u || w[277]>599u) return fail("State guard refused");
if(w[278]<0u || w[278]>599u) return fail("State guard refused");
if(w[279]<0u || w[279]>599u) return fail("State guard refused");
if(w[280]<0u || w[280]>599u) return fail("State guard refused");
if(w[281]<0u || w[281]>599u) return fail("State guard refused");
if(w[282]<0u || w[282]>599u) return fail("State guard refused");
if(w[283]<0u || w[283]>599u) return fail("State guard refused");
if(w[284]<0u || w[284]>599u) return fail("State guard refused");
if(w[285]<0u || w[285]>599u) return fail("State guard refused");
if(w[286]<0u || w[286]>599u) return fail("State guard refused");
if(w[287]<0u || w[287]>599u) return fail("State guard refused");
if(w[288]<0u || w[288]>599u) return fail("State guard refused");
if(w[289]<0u || w[289]>599u) return fail("State guard refused");
if(w[290]<0u || w[290]>599u) return fail("State guard refused");
if(w[291]<0u || w[291]>599u) return fail("State guard refused");
if(w[292]<0u || w[292]>599u) return fail("State guard refused");
if(w[293]<0u || w[293]>599u) return fail("State guard refused");
if(w[294]<0u || w[294]>599u) return fail("State guard refused");
if(w[295]<0u || w[295]>599u) return fail("State guard refused");
if(w[296]<0u || w[296]>599u) return fail("State guard refused");
if(w[297]<0u || w[297]>599u) return fail("State guard refused");
if(w[298]<0u || w[298]>599u) return fail("State guard refused");
if(w[299]<0u || w[299]>599u) return fail("State guard refused");
if(w[300]<0u || w[300]>599u) return fail("State guard refused");
if(w[301]<0u || w[301]>599u) return fail("State guard refused");
if(w[302]<0u || w[302]>599u) return fail("State guard refused");
if(w[303]<0u || w[303]>599u) return fail("State guard refused");
if(w[304]<0u || w[304]>599u) return fail("State guard refused");
if(w[305]<0u || w[305]>599u) return fail("State guard refused");
if(w[306]<0u || w[306]>599u) return fail("State guard refused");
if(w[307]<0u || w[307]>599u) return fail("State guard refused");
if(w[308]<0u || w[308]>599u) return fail("State guard refused");
if(w[309]<0u || w[309]>599u) return fail("State guard refused");
if(w[310]<0u || w[310]>599u) return fail("State guard refused");
if(w[311]<0u || w[311]>599u) return fail("State guard refused");
if(w[312]<0u || w[312]>599u) return fail("State guard refused");
if(w[313]<0u || w[313]>599u) return fail("State guard refused");
if(w[314]<0u || w[314]>599u) return fail("State guard refused");
if(w[315]<0u || w[315]>599u) return fail("State guard refused");
if(w[316]<0u || w[316]>599u) return fail("State guard refused");
if(w[317]<0u || w[317]>599u) return fail("State guard refused");
if(w[318]<0u || w[318]>599u) return fail("State guard refused");
if(w[319]<0u || w[319]>599u) return fail("State guard refused");
if(w[320]<0u || w[320]>599u) return fail("State guard refused");
if(w[321]<0u || w[321]>599u) return fail("State guard refused");
if(w[322]<0u || w[322]>599u) return fail("State guard refused");
if(w[323]<0u || w[323]>599u) return fail("State guard refused");
if(w[324]<0u || w[324]>599u) return fail("State guard refused");
if(w[325]<0u || w[325]>599u) return fail("State guard refused");
if(w[326]<0u || w[326]>599u) return fail("State guard refused");
if(w[327]<0u || w[327]>599u) return fail("State guard refused");
if(w[328]<0u || w[328]>599u) return fail("State guard refused");
if(w[329]<0u || w[329]>599u) return fail("State guard refused");
if(w[330]<0u || w[330]>599u) return fail("State guard refused");
if(w[331]<0u || w[331]>599u) return fail("State guard refused");
if(w[332]<0u || w[332]>599u) return fail("State guard refused");
if(w[333]<0u || w[333]>599u) return fail("State guard refused");
if(w[334]<0u || w[334]>599u) return fail("State guard refused");
if(w[335]<0u || w[335]>599u) return fail("State guard refused");
if(w[336]<0u || w[336]>599u) return fail("State guard refused");
if(w[337]<0u || w[337]>599u) return fail("State guard refused");
if(w[338]<0u || w[338]>599u) return fail("State guard refused");
if(w[339]<0u || w[339]>599u) return fail("State guard refused");
if(w[340]<0u || w[340]>599u) return fail("State guard refused");
if(w[341]<0u || w[341]>599u) return fail("State guard refused");
if(w[342]<0u || w[342]>599u) return fail("State guard refused");
if(w[343]<0u || w[343]>599u) return fail("State guard refused");
if(w[344]<0u || w[344]>599u) return fail("State guard refused");
if(w[345]<0u || w[345]>599u) return fail("State guard refused");
if(w[346]<0u || w[346]>599u) return fail("State guard refused");
if(w[347]<0u || w[347]>599u) return fail("State guard refused");
if(w[348]<0u || w[348]>599u) return fail("State guard refused");
if(w[349]<0u || w[349]>599u) return fail("State guard refused");
if(w[350]<0u || w[350]>599u) return fail("State guard refused");
if(w[351]<0u || w[351]>599u) return fail("State guard refused");
if(w[352]<0u || w[352]>599u) return fail("State guard refused");
if(w[353]<0u || w[353]>599u) return fail("State guard refused");
if(w[354]<0u || w[354]>599u) return fail("State guard refused");
if(w[355]<0u || w[355]>599u) return fail("State guard refused");
if(w[356]<0u || w[356]>599u) return fail("State guard refused");
if(w[357]<0u || w[357]>599u) return fail("State guard refused");
if(w[358]<0u || w[358]>599u) return fail("State guard refused");
if(w[359]<0u || w[359]>599u) return fail("State guard refused");
if(w[360]<0u || w[360]>599u) return fail("State guard refused");
if(w[361]<0u || w[361]>599u) return fail("State guard refused");
if(w[362]<0u || w[362]>599u) return fail("State guard refused");
if(w[363]<0u || w[363]>599u) return fail("State guard refused");
if(w[364]<0u || w[364]>599u) return fail("State guard refused");
if(w[365]<0u || w[365]>599u) return fail("State guard refused");
if(w[366]<0u || w[366]>599u) return fail("State guard refused");
if(w[367]<0u || w[367]>599u) return fail("State guard refused");
if(w[368]<0u || w[368]>599u) return fail("State guard refused");
if(w[369]<0u || w[369]>599u) return fail("State guard refused");
if(w[370]<0u || w[370]>599u) return fail("State guard refused");
if(w[371]<0u || w[371]>599u) return fail("State guard refused");
if(w[372]<0u || w[372]>599u) return fail("State guard refused");
if(w[373]<0u || w[373]>599u) return fail("State guard refused");
if(w[374]<0u || w[374]>599u) return fail("State guard refused");
if(w[375]<0u || w[375]>599u) return fail("State guard refused");
if(w[376]<0u || w[376]>599u) return fail("State guard refused");
if(w[377]<0u || w[377]>599u) return fail("State guard refused");
if(w[378]<0u || w[378]>599u) return fail("State guard refused");
if(w[379]<0u || w[379]>599u) return fail("State guard refused");
if(w[380]<0u || w[380]>599u) return fail("State guard refused");
if(w[381]<0u || w[381]>599u) return fail("State guard refused");
if(w[382]<0u || w[382]>599u) return fail("State guard refused");
if(w[383]<0u || w[383]>599u) return fail("State guard refused");
if(w[384]<0u || w[384]>599u) return fail("State guard refused");
if(w[385]<0u || w[385]>599u) return fail("State guard refused");
if(w[386]<0u || w[386]>599u) return fail("State guard refused");
if(w[387]<0u || w[387]>599u) return fail("State guard refused");
if(w[388]<0u || w[388]>599u) return fail("State guard refused");
if(w[389]<0u || w[389]>599u) return fail("State guard refused");
if(w[390]<0u || w[390]>599u) return fail("State guard refused");
if(w[391]<0u || w[391]>599u) return fail("State guard refused");
if(w[392]<0u || w[392]>599u) return fail("State guard refused");
if(w[393]<0u || w[393]>599u) return fail("State guard refused");
if(w[394]<0u || w[394]>599u) return fail("State guard refused");
if(w[395]<0u || w[395]>599u) return fail("State guard refused");
if(w[396]<0u || w[396]>599u) return fail("State guard refused");
if(w[397]<0u || w[397]>599u) return fail("State guard refused");
if(w[398]<0u || w[398]>599u) return fail("State guard refused");
if(w[399]<0u || w[399]>599u) return fail("State guard refused");
if(w[400]<0u || w[400]>599u) return fail("State guard refused");
if(w[401]<0u || w[401]>599u) return fail("State guard refused");
if(w[402]<0u || w[402]>599u) return fail("State guard refused");
if(w[403]<0u || w[403]>599u) return fail("State guard refused");
if(w[404]<0u || w[404]>599u) return fail("State guard refused");
if(w[405]<0u || w[405]>599u) return fail("State guard refused");
if(w[406]<0u || w[406]>599u) return fail("State guard refused");
if(w[407]<0u || w[407]>599u) return fail("State guard refused");
if(w[408]<0u || w[408]>599u) return fail("State guard refused");
if(w[409]<0u || w[409]>599u) return fail("State guard refused");
if(w[410]<0u || w[410]>599u) return fail("State guard refused");
if(w[411]<0u || w[411]>599u) return fail("State guard refused");
if(w[412]<0u || w[412]>599u) return fail("State guard refused");
if(w[413]<0u || w[413]>599u) return fail("State guard refused");
if(w[414]<0u || w[414]>599u) return fail("State guard refused");
if(w[415]<0u || w[415]>599u) return fail("State guard refused");
if(w[416]<0u || w[416]>599u) return fail("State guard refused");
if(w[417]<0u || w[417]>599u) return fail("State guard refused");
if(w[418]<0u || w[418]>599u) return fail("State guard refused");
if(w[419]<0u || w[419]>599u) return fail("State guard refused");
if(w[420]<0u || w[420]>599u) return fail("State guard refused");
if(w[421]<0u || w[421]>599u) return fail("State guard refused");
if(w[422]<0u || w[422]>599u) return fail("State guard refused");
if(w[423]<0u || w[423]>599u) return fail("State guard refused");
if(w[424]<0u || w[424]>599u) return fail("State guard refused");
if(w[425]<0u || w[425]>599u) return fail("State guard refused");
if(w[426]<0u || w[426]>599u) return fail("State guard refused");
if(w[427]<0u || w[427]>599u) return fail("State guard refused");
if(w[428]<0u || w[428]>599u) return fail("State guard refused");
if(w[429]<0u || w[429]>599u) return fail("State guard refused");
if(w[430]<0u || w[430]>599u) return fail("State guard refused");
if(w[431]<0u || w[431]>599u) return fail("State guard refused");
if(w[432]<0u || w[432]>599u) return fail("State guard refused");
if(w[433]<0u || w[433]>599u) return fail("State guard refused");
if(w[434]<0u || w[434]>599u) return fail("State guard refused");
if(w[435]<0u || w[435]>599u) return fail("State guard refused");
if(w[436]<0u || w[436]>599u) return fail("State guard refused");
if(w[437]<0u || w[437]>599u) return fail("State guard refused");
if(w[438]<0u || w[438]>599u) return fail("State guard refused");
if(w[439]<0u || w[439]>599u) return fail("State guard refused");
if(w[440]<0u || w[440]>599u) return fail("State guard refused");
if(w[441]<0u || w[441]>599u) return fail("State guard refused");
if(w[442]<0u || w[442]>599u) return fail("State guard refused");
if(w[443]<0u || w[443]>599u) return fail("State guard refused");
if(w[444]<0u || w[444]>599u) return fail("State guard refused");
if(w[445]<0u || w[445]>599u) return fail("State guard refused");
if(w[446]<0u || w[446]>599u) return fail("State guard refused");
if(w[447]<0u || w[447]>599u) return fail("State guard refused");
if(w[448]<0u || w[448]>599u) return fail("State guard refused");
if(w[449]<0u || w[449]>599u) return fail("State guard refused");
if(w[450]<0u || w[450]>599u) return fail("State guard refused");
if(w[451]<0u || w[451]>599u) return fail("State guard refused");
if(w[452]<0u || w[452]>599u) return fail("State guard refused");
if(w[453]<0u || w[453]>599u) return fail("State guard refused");
if(w[454]<0u || w[454]>599u) return fail("State guard refused");
if(w[455]<0u || w[455]>599u) return fail("State guard refused");
if(w[456]<0u || w[456]>599u) return fail("State guard refused");
if(w[457]<0u || w[457]>599u) return fail("State guard refused");
if(w[458]<0u || w[458]>599u) return fail("State guard refused");
if(w[459]<0u || w[459]>599u) return fail("State guard refused");
if(w[460]<0u || w[460]>599u) return fail("State guard refused");
if(w[461]<0u || w[461]>599u) return fail("State guard refused");
if(w[462]<0u || w[462]>599u) return fail("State guard refused");
if(w[463]<0u || w[463]>599u) return fail("State guard refused");
if(w[464]<0u || w[464]>599u) return fail("State guard refused");
if(w[465]<0u || w[465]>599u) return fail("State guard refused");
if(w[466]<0u || w[466]>599u) return fail("State guard refused");
if(w[467]<0u || w[467]>599u) return fail("State guard refused");
if(w[468]<0u || w[468]>599u) return fail("State guard refused");
if(w[469]<0u || w[469]>599u) return fail("State guard refused");
if(w[470]<0u || w[470]>599u) return fail("State guard refused");
if(w[471]<0u || w[471]>599u) return fail("State guard refused");
if(w[472]<0u || w[472]>599u) return fail("State guard refused");
if(w[473]<0u || w[473]>599u) return fail("State guard refused");
if(w[474]<0u || w[474]>599u) return fail("State guard refused");
if(w[475]<0u || w[475]>599u) return fail("State guard refused");
if(w[476]<0u || w[476]>599u) return fail("State guard refused");
if(w[477]<0u || w[477]>599u) return fail("State guard refused");
if(w[478]<0u || w[478]>599u) return fail("State guard refused");
if(w[479]<0u || w[479]>599u) return fail("State guard refused");
if(w[480]<0u || w[480]>599u) return fail("State guard refused");
if(w[481]<0u || w[481]>599u) return fail("State guard refused");
if(w[482]<0u || w[482]>599u) return fail("State guard refused");
if(w[483]<0u || w[483]>599u) return fail("State guard refused");
if(w[484]<0u || w[484]>599u) return fail("State guard refused");
if(w[485]<0u || w[485]>599u) return fail("State guard refused");
if(w[486]<0u || w[486]>599u) return fail("State guard refused");
if(w[487]<0u || w[487]>599u) return fail("State guard refused");
if(w[488]<0u || w[488]>599u) return fail("State guard refused");
if(w[489]<0u || w[489]>599u) return fail("State guard refused");
if(w[490]<0u || w[490]>599u) return fail("State guard refused");
if(w[491]<0u || w[491]>599u) return fail("State guard refused");
if(w[492]<0u || w[492]>599u) return fail("State guard refused");
if(w[493]<0u || w[493]>599u) return fail("State guard refused");
if(w[494]<0u || w[494]>599u) return fail("State guard refused");
if(w[495]<0u || w[495]>599u) return fail("State guard refused");
if(w[496]<0u || w[496]>599u) return fail("State guard refused");
if(w[497]<0u || w[497]>599u) return fail("State guard refused");
if(w[498]<0u || w[498]>599u) return fail("State guard refused");
if(w[499]<0u || w[499]>599u) return fail("State guard refused");
if(w[500]<0u || w[500]>599u) return fail("State guard refused");
if(w[501]<0u || w[501]>599u) return fail("State guard refused");
if(w[502]<0u || w[502]>599u) return fail("State guard refused");
if(w[503]<0u || w[503]>599u) return fail("State guard refused");
if(w[504]<0u || w[504]>599u) return fail("State guard refused");
if(w[505]<0u || w[505]>599u) return fail("State guard refused");
if(w[506]<0u || w[506]>599u) return fail("State guard refused");
if(w[507]<0u || w[507]>599u) return fail("State guard refused");
if(w[508]<0u || w[508]>599u) return fail("State guard refused");
if(w[509]<0u || w[509]>599u) return fail("State guard refused");
if(w[510]<0u || w[510]>599u) return fail("State guard refused");
if(w[511]<0u || w[511]>599u) return fail("State guard refused");
if(w[512]<0u || w[512]>599u) return fail("State guard refused");
if(w[513]<0u || w[513]>599u) return fail("State guard refused");
if(w[514]<0u || w[514]>599u) return fail("State guard refused");
if(w[515]<0u || w[515]>599u) return fail("State guard refused");
if(w[516]<0u || w[516]>599u) return fail("State guard refused");
if(w[517]<0u || w[517]>599u) return fail("State guard refused");
if(w[518]<0u || w[518]>599u) return fail("State guard refused");
if(w[519]<0u || w[519]>599u) return fail("State guard refused");
if(w[520]<0u || w[520]>599u) return fail("State guard refused");
if(w[521]<0u || w[521]>599u) return fail("State guard refused");
if(w[522]<0u || w[522]>599u) return fail("State guard refused");
if(w[523]<0u || w[523]>599u) return fail("State guard refused");
if(w[524]<0u || w[524]>599u) return fail("State guard refused");
if(w[525]<0u || w[525]>599u) return fail("State guard refused");
if(w[526]<0u || w[526]>599u) return fail("State guard refused");
if(w[527]<0u || w[527]>599u) return fail("State guard refused");
if(w[528]<0u || w[528]>599u) return fail("State guard refused");
if(w[529]<0u || w[529]>599u) return fail("State guard refused");
if(w[530]<0u || w[530]>599u) return fail("State guard refused");
if(w[531]<0u || w[531]>599u) return fail("State guard refused");
if(w[532]<0u || w[532]>599u) return fail("State guard refused");
if(w[533]<0u || w[533]>599u) return fail("State guard refused");
if(w[534]<0u || w[534]>599u) return fail("State guard refused");
if(w[535]<0u || w[535]>599u) return fail("State guard refused");
if(w[536]<0u || w[536]>599u) return fail("State guard refused");
if(w[537]<0u || w[537]>599u) return fail("State guard refused");
if(w[538]<0u || w[538]>599u) return fail("State guard refused");
if(w[539]<0u || w[539]>599u) return fail("State guard refused");
if(w[540]<0u || w[540]>599u) return fail("State guard refused");
if(w[541]<0u || w[541]>599u) return fail("State guard refused");
if(w[542]<0u || w[542]>599u) return fail("State guard refused");
if(w[543]<0u || w[543]>599u) return fail("State guard refused");
if(w[544]<0u || w[544]>599u) return fail("State guard refused");
if(w[545]<0u || w[545]>599u) return fail("State guard refused");
if(w[546]<0u || w[546]>599u) return fail("State guard refused");
if(w[547]<0u || w[547]>599u) return fail("State guard refused");
if(w[548]<0u || w[548]>599u) return fail("State guard refused");
if(w[549]<0u || w[549]>599u) return fail("State guard refused");
if(w[550]<0u || w[550]>599u) return fail("State guard refused");
if(w[551]<0u || w[551]>599u) return fail("State guard refused");
if(w[552]<0u || w[552]>599u) return fail("State guard refused");
if(w[553]<0u || w[553]>599u) return fail("State guard refused");
if(w[554]<0u || w[554]>599u) return fail("State guard refused");
if(w[555]<0u || w[555]>599u) return fail("State guard refused");
if(w[556]<0u || w[556]>599u) return fail("State guard refused");
if(w[557]<0u || w[557]>599u) return fail("State guard refused");
if(w[558]<0u || w[558]>599u) return fail("State guard refused");
if(w[559]<0u || w[559]>599u) return fail("State guard refused");
if(w[560]<0u || w[560]>599u) return fail("State guard refused");
if(w[561]<0u || w[561]>599u) return fail("State guard refused");
if(w[562]<0u || w[562]>599u) return fail("State guard refused");
if(w[563]<0u || w[563]>599u) return fail("State guard refused");
if(w[564]<0u || w[564]>599u) return fail("State guard refused");
if(w[565]<0u || w[565]>599u) return fail("State guard refused");
if(w[566]<0u || w[566]>599u) return fail("State guard refused");
if(w[567]<0u || w[567]>599u) return fail("State guard refused");
if(w[568]<0u || w[568]>599u) return fail("State guard refused");
if(w[569]<0u || w[569]>599u) return fail("State guard refused");
if(w[570]<0u || w[570]>599u) return fail("State guard refused");
if(w[571]<0u || w[571]>599u) return fail("State guard refused");
if(w[572]<0u || w[572]>599u) return fail("State guard refused");
if(w[573]<0u || w[573]>599u) return fail("State guard refused");
if(w[574]<0u || w[574]>599u) return fail("State guard refused");
if(w[575]<0u || w[575]>599u) return fail("State guard refused");
if(w[576]<0u || w[576]>599u) return fail("State guard refused");
if(w[577]<0u || w[577]>599u) return fail("State guard refused");
if(w[578]<0u || w[578]>599u) return fail("State guard refused");
if(w[579]<0u || w[579]>599u) return fail("State guard refused");
if(w[580]<0u || w[580]>599u) return fail("State guard refused");
if(w[581]<0u || w[581]>599u) return fail("State guard refused");
if(w[582]<0u || w[582]>599u) return fail("State guard refused");
if(w[583]<0u || w[583]>599u) return fail("State guard refused");
if(w[584]<0u || w[584]>599u) return fail("State guard refused");
if(w[585]<0u || w[585]>599u) return fail("State guard refused");
if(w[586]<0u || w[586]>599u) return fail("State guard refused");
if(w[587]<0u || w[587]>599u) return fail("State guard refused");
if(w[588]<0u || w[588]>599u) return fail("State guard refused");
if(w[589]<0u || w[589]>599u) return fail("State guard refused");
if(w[590]<0u || w[590]>599u) return fail("State guard refused");
if(w[591]<0u || w[591]>599u) return fail("State guard refused");
if(w[592]<0u || w[592]>599u) return fail("State guard refused");
if(w[593]<0u || w[593]>599u) return fail("State guard refused");
if(w[594]<0u || w[594]>599u) return fail("State guard refused");
if(w[595]<0u || w[595]>599u) return fail("State guard refused");
if(w[596]<0u || w[596]>599u) return fail("State guard refused");
if(w[597]<0u || w[597]>599u) return fail("State guard refused");
if(w[598]<0u || w[598]>599u) return fail("State guard refused");
if(w[599]<0u || w[599]>599u) return fail("State guard refused");
{ uint32_t n=w[600]; if(n>600u) return fail("Array length refused");
for(uint32_t i=0;i<n;i++) { uint32_t value=w[0u+i]; if(value<0u || value>599u) return fail("Array value refused");
if(i) { uint32_t previous=w[0u+i-1],distance=value>previous?value-previous:previous-value;
if(!(distance==30u || (distance==1u && value/30u==previous/30u))) return fail("Array adjacency refused"); } }
uint32_t *copy=(uint32_t*)malloc((n?n:1u)*sizeof(uint32_t)); if(!copy) return fail("Allocation refused"); memcpy(copy,w+0u,n*sizeof(uint32_t)); qsort(copy,n,sizeof(uint32_t),compare_words);
int duplicate=0; for(uint32_t i=1;i<n;i++) if(copy[i-1]==copy[i]) duplicate=1; free(copy); if(duplicate) return fail("Duplicate array value");
if(w[604]==0u) { uint32_t value=w[612]; if(value<0u || value>599u) return fail("Excluded value refused");
for(uint32_t i=0;i<n;i++) if(w[0u+i]==value) return fail("Excluded value overlaps array"); } }
{ static const uint32_t colors[]={0u,1u,2u,8u,10u,12u,15u};
for(uint32_t i=4096u;i<68096u;i++) { int found=0; for(size_t j=0;j<sizeof(colors)/sizeof(colors[0]);j++) if(w[i]==colors[j]) found=1; if(!found) return fail("Palette index refused"); } }
return 0; }
FdbBlockResult fdb_native_0(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  uint32_t fdb_v37 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v8 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (630u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t0 = (uint32_t)fdb_words[630u];
    uint32_t fdb_t1 = (uint32_t)(fdb_t0 == 1u);
    if (fdb_t1 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (608u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t2 = (uint32_t)fdb_words[608u];
      uint32_t fdb_t3 = (uint32_t)(fdb_t2 + 1u);
      uint32_t fdb_t4 = (uint32_t)(fdb_t3 & 65535u);
      if (608u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[608u] = fdb_t4;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (631u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t5 = (uint32_t)fdb_words[631u];
      fdb_v1 = fdb_t5;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t6 = (uint32_t)(fdb_v1 >= 65u);
      uint32_t fdb_t7 = (uint32_t)(fdb_v1 <= 90u);
      uint32_t fdb_t8 = (uint32_t)(fdb_t6 & fdb_t7);
      if (fdb_t8 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t9 = (uint32_t)(fdb_v1 + 32u);
        fdb_v1 = fdb_t9;
      } else {
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t10 = (uint32_t)(fdb_v1 == 27u);
      if (fdb_t10 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v8 = 8u;
      } else {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t11 = (uint32_t)(fdb_v1 == 32u);
        if (fdb_t11 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 5u;
        } else {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t12 = (uint32_t)(fdb_v1 == 112u);
          if (fdb_t12 != 0u) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            fdb_v8 = 5u;
          } else {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t13 = (uint32_t)(fdb_v1 == 110u);
            if (fdb_t13 != 0u) {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              fdb_v8 = 6u;
            } else {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t14 = (uint32_t)(fdb_v1 == 114u);
              if (fdb_t14 != 0u) {
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                fdb_v8 = 7u;
              } else {
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t15 = (uint32_t)(fdb_v1 == 119u);
                if (632u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                uint32_t fdb_t16 = (uint32_t)fdb_words[632u];
                uint32_t fdb_t17 = (uint32_t)(fdb_t16 == 72u);
                uint32_t fdb_t18 = (uint32_t)(fdb_t15 | fdb_t17);
                if (fdb_t18 != 0u) {
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  fdb_v8 = 1u;
                } else {
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  uint32_t fdb_t19 = (uint32_t)(fdb_v1 == 100u);
                  if (632u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                  uint32_t fdb_t20 = (uint32_t)fdb_words[632u];
                  uint32_t fdb_t21 = (uint32_t)(fdb_t20 == 77u);
                  uint32_t fdb_t22 = (uint32_t)(fdb_t19 | fdb_t21);
                  if (fdb_t22 != 0u) {
                    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                    --fdb_remaining;
                    fdb_v8 = 2u;
                  } else {
                    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                    --fdb_remaining;
                    uint32_t fdb_t23 = (uint32_t)(fdb_v1 == 115u);
                    if (632u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                    uint32_t fdb_t24 = (uint32_t)fdb_words[632u];
                    uint32_t fdb_t25 = (uint32_t)(fdb_t24 == 80u);
                    uint32_t fdb_t26 = (uint32_t)(fdb_t23 | fdb_t25);
                    if (fdb_t26 != 0u) {
                      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                      --fdb_remaining;
                      fdb_v8 = 3u;
                    } else {
                      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                      --fdb_remaining;
                      uint32_t fdb_t27 = (uint32_t)(fdb_v1 == 97u);
                      if (632u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                      uint32_t fdb_t28 = (uint32_t)fdb_words[632u];
                      uint32_t fdb_t29 = (uint32_t)(fdb_t28 == 75u);
                      uint32_t fdb_t30 = (uint32_t)(fdb_t27 | fdb_t29);
                      if (fdb_t30 != 0u) {
                        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                        --fdb_remaining;
                        fdb_v8 = 4u;
                      } else {
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (630u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t31 = (uint32_t)fdb_words[630u];
    uint32_t fdb_t32 = (uint32_t)(fdb_t31 == 2u);
    if (611u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t33 = (uint32_t)fdb_words[611u];
    uint32_t fdb_t34 = (uint32_t)(fdb_t33 != 0u);
    uint32_t fdb_t35 = (uint32_t)(fdb_t32 & fdb_t34);
    if (fdb_t35 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (617u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t36 = (uint32_t)fdb_words[617u];
      fdb_v22 = fdb_t36;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (635u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t37 = (uint32_t)fdb_words[635u];
      uint32_t fdb_t38 = (uint32_t)(fdb_t37 & 65535u);
      if (617u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[617u] = fdb_t38;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t39 = (uint32_t)fdb_words[633u];
      uint32_t fdb_t40 = (uint32_t)(fdb_t39 & 65535u);
      if (618u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[618u] = fdb_t40;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t41 = (uint32_t)fdb_words[634u];
      uint32_t fdb_t42 = (uint32_t)(fdb_t41 & 65535u);
      if (619u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[619u] = fdb_t42;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (635u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t43 = (uint32_t)fdb_words[635u];
      uint32_t fdb_t44 = (uint32_t)(fdb_t43 & 1u);
      uint32_t fdb_t45 = (uint32_t)(fdb_t44 != 0u);
      uint32_t fdb_t46 = (uint32_t)(fdb_v22 & 1u);
      uint32_t fdb_t47 = (uint32_t)(fdb_t46 == 0u);
      uint32_t fdb_t48 = (uint32_t)(fdb_t45 & fdb_t47);
      if (fdb_t48 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (609u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t49 = (uint32_t)fdb_words[609u];
        uint32_t fdb_t50 = (uint32_t)(fdb_t49 + 1u);
        uint32_t fdb_t51 = (uint32_t)(fdb_t50 & 65535u);
        if (609u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[609u] = fdb_t51;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t52 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t53 = (uint32_t)(fdb_t52 >= 280u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t54 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t55 = (uint32_t)(fdb_t54 < 304u);
        uint32_t fdb_t56 = (uint32_t)(fdb_t53 & fdb_t55);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t57 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t58 = (uint32_t)(fdb_t57 >= 40u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t59 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t60 = (uint32_t)(fdb_t59 < 60u);
        uint32_t fdb_t61 = (uint32_t)(fdb_t58 & fdb_t60);
        uint32_t fdb_t62 = (uint32_t)(fdb_t56 & fdb_t61);
        if (fdb_t62 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 1u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t63 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t64 = (uint32_t)(fdb_t63 >= 256u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t65 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t66 = (uint32_t)(fdb_t65 < 280u);
        uint32_t fdb_t67 = (uint32_t)(fdb_t64 & fdb_t66);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t68 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t69 = (uint32_t)(fdb_t68 >= 64u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t70 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t71 = (uint32_t)(fdb_t70 < 84u);
        uint32_t fdb_t72 = (uint32_t)(fdb_t69 & fdb_t71);
        uint32_t fdb_t73 = (uint32_t)(fdb_t67 & fdb_t72);
        if (fdb_t73 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 4u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t74 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t75 = (uint32_t)(fdb_t74 >= 288u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t76 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t77 = (uint32_t)(fdb_t76 < 312u);
        uint32_t fdb_t78 = (uint32_t)(fdb_t75 & fdb_t77);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t79 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t80 = (uint32_t)(fdb_t79 >= 64u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t81 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t82 = (uint32_t)(fdb_t81 < 84u);
        uint32_t fdb_t83 = (uint32_t)(fdb_t80 & fdb_t82);
        uint32_t fdb_t84 = (uint32_t)(fdb_t78 & fdb_t83);
        if (fdb_t84 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 2u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t85 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t86 = (uint32_t)(fdb_t85 >= 280u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t87 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t88 = (uint32_t)(fdb_t87 < 304u);
        uint32_t fdb_t89 = (uint32_t)(fdb_t86 & fdb_t88);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t90 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t91 = (uint32_t)(fdb_t90 >= 88u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t92 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t93 = (uint32_t)(fdb_t92 < 108u);
        uint32_t fdb_t94 = (uint32_t)(fdb_t91 & fdb_t93);
        uint32_t fdb_t95 = (uint32_t)(fdb_t89 & fdb_t94);
        if (fdb_t95 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 3u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t96 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t97 = (uint32_t)(fdb_t96 >= 256u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t98 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t99 = (uint32_t)(fdb_t98 < 312u);
        uint32_t fdb_t100 = (uint32_t)(fdb_t97 & fdb_t99);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t101 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t102 = (uint32_t)(fdb_t101 >= 120u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t103 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t104 = (uint32_t)(fdb_t103 < 140u);
        uint32_t fdb_t105 = (uint32_t)(fdb_t102 & fdb_t104);
        uint32_t fdb_t106 = (uint32_t)(fdb_t100 & fdb_t105);
        if (fdb_t106 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 5u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t107 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t108 = (uint32_t)(fdb_t107 >= 256u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t109 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t110 = (uint32_t)(fdb_t109 < 312u);
        uint32_t fdb_t111 = (uint32_t)(fdb_t108 & fdb_t110);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t112 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t113 = (uint32_t)(fdb_t112 >= 144u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t114 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t115 = (uint32_t)(fdb_t114 < 164u);
        uint32_t fdb_t116 = (uint32_t)(fdb_t113 & fdb_t115);
        uint32_t fdb_t117 = (uint32_t)(fdb_t111 & fdb_t116);
        if (fdb_t117 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 6u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t118 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t119 = (uint32_t)(fdb_t118 >= 256u);
        if (633u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t120 = (uint32_t)fdb_words[633u];
        uint32_t fdb_t121 = (uint32_t)(fdb_t120 < 312u);
        uint32_t fdb_t122 = (uint32_t)(fdb_t119 & fdb_t121);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t123 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t124 = (uint32_t)(fdb_t123 >= 168u);
        if (634u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t125 = (uint32_t)fdb_words[634u];
        uint32_t fdb_t126 = (uint32_t)(fdb_t125 < 188u);
        uint32_t fdb_t127 = (uint32_t)(fdb_t124 & fdb_t126);
        uint32_t fdb_t128 = (uint32_t)(fdb_t122 & fdb_t127);
        if (fdb_t128 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v8 = 7u;
        } else {
        }
      } else {
      }
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t129 = (uint32_t)(fdb_v8 >= 1u);
    uint32_t fdb_t130 = (uint32_t)(fdb_v8 <= 4u);
    uint32_t fdb_t131 = (uint32_t)(fdb_t129 & fdb_t130);
    if (fdb_t131 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t132 = (uint32_t)fdb_words[604u];
      uint32_t fdb_t133 = (uint32_t)(fdb_t132 == 0u);
      if (613u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t134 = (uint32_t)fdb_words[613u];
      uint32_t fdb_t135 = (uint32_t)(fdb_t134 == 0u);
      uint32_t fdb_t136 = (uint32_t)(fdb_t133 & fdb_t135);
      uint32_t fdb_t137 = (uint32_t)(fdb_v8 - 1u);
      if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t138 = (uint32_t)fdb_words[601u];
      uint32_t fdb_t139 = (uint32_t)(fdb_t137 != fdb_t138);
      uint32_t fdb_t140 = (uint32_t)(fdb_v8 - 1u);
      if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t141 = (uint32_t)fdb_words[601u];
      uint32_t fdb_t142 = (uint32_t)(fdb_t141 + 2u);
      uint32_t fdb_t143 = (uint32_t)(fdb_t142 & 3u);
      uint32_t fdb_t144 = (uint32_t)(fdb_t140 != fdb_t143);
      uint32_t fdb_t145 = (uint32_t)(fdb_t139 & fdb_t144);
      uint32_t fdb_t146 = (uint32_t)(fdb_t136 & fdb_t145);
      if (fdb_t146 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t147 = (uint32_t)(fdb_v8 - 1u);
        uint32_t fdb_t148 = (uint32_t)(fdb_t147 & 65535u);
        if (602u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[602u] = fdb_t148;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t149 = (uint32_t)(1u & 65535u);
        if (613u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[613u] = fdb_t149;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t150 = (uint32_t)(1u & 65535u);
        if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[614u] = fdb_t150;
      } else {
      }
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t151 = (uint32_t)(fdb_v8 == 5u);
    if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t152 = (uint32_t)fdb_words[604u];
    uint32_t fdb_t153 = (uint32_t)(fdb_t152 == 0u);
    uint32_t fdb_t154 = (uint32_t)(fdb_t151 & fdb_t153);
    if (fdb_t154 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t155 = (uint32_t)fdb_words[603u];
      uint32_t fdb_t156 = (uint32_t)(fdb_t155 ^ 1u);
      uint32_t fdb_t157 = (uint32_t)(fdb_t156 & 65535u);
      if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[603u] = fdb_t157;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t158 = (uint32_t)(1u & 65535u);
      if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[614u] = fdb_t158;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t159 = (uint32_t)fdb_words[636u];
      uint32_t fdb_t160 = (uint32_t)(fdb_t159 & 65535u);
      if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[620u] = fdb_t160;
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t161 = (uint32_t)(fdb_v8 == 6u);
    if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t162 = (uint32_t)fdb_words[604u];
    uint32_t fdb_t163 = (uint32_t)(fdb_t162 == 0u);
    uint32_t fdb_t164 = (uint32_t)(fdb_t161 & fdb_t163);
    if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t165 = (uint32_t)fdb_words[603u];
    uint32_t fdb_t166 = (uint32_t)(fdb_t165 == 1u);
    uint32_t fdb_t167 = (uint32_t)(fdb_t164 & fdb_t166);
    if (fdb_t167 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t168 = (uint32_t)(1u & 65535u);
      if (615u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[615u] = fdb_t168;
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t169 = (uint32_t)(fdb_v8 == 7u);
    if (fdb_t169 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v15 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop0=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t170 = (uint32_t)(fdb_v15 < 600u);
        if (fdb_t170 == 0u) break;
        if (fdb_loop0 == 600u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop0;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (fdb_v15 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_v15] = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t171 = (uint32_t)(fdb_v15 + 1u);
        fdb_v15 = fdb_t171;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[0u] = 308u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (1u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[1u] = 307u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (2u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[2u] = 306u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t172 = (uint32_t)(3u & 65535u);
      if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[600u] = fdb_t172;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t173 = (uint32_t)(1u & 65535u);
      if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[601u] = fdb_t173;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t174 = (uint32_t)(1u & 65535u);
      if (602u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[602u] = fdb_t174;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t175 = (uint32_t)(1u & 65535u);
      if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[603u] = fdb_t175;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t176 = (uint32_t)(0u & 65535u);
      if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[604u] = fdb_t176;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t177 = (uint32_t)(0u & 65535u);
      if (605u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[605u] = fdb_t177;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t178 = (uint32_t)(4660u & 65535u);
      if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[606u] = fdb_t178;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t179 = (uint32_t)(312u & 65535u);
      if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[612u] = fdb_t179;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t180 = (uint32_t)(0u & 65535u);
      if (607u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[607u] = fdb_t180;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t181 = (uint32_t)(0u & 65535u);
      if (608u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[608u] = fdb_t181;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t182 = (uint32_t)(0u & 65535u);
      if (609u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[609u] = fdb_t182;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t183 = (uint32_t)(0u & 65535u);
      if (610u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[610u] = fdb_t183;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t184 = (uint32_t)(0u & 65535u);
      if (613u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[613u] = fdb_t184;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t185 = (uint32_t)(0u & 65535u);
      if (615u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[615u] = fdb_t185;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t186 = (uint32_t)(1u & 65535u);
      if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[614u] = fdb_t186;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t187 = (uint32_t)fdb_words[636u];
      uint32_t fdb_t188 = (uint32_t)(fdb_t187 & 65535u);
      if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[620u] = fdb_t188;
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t189 = (uint32_t)(fdb_v8 == 8u);
    if (fdb_t189 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t190 = (uint32_t)(1u & 65535u);
      if (616u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[616u] = fdb_t190;
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (616u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t191 = (uint32_t)fdb_words[616u];
    uint32_t fdb_t192 = (uint32_t)(fdb_t191 == 0u);
    if (fdb_t192 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (615u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t193 = (uint32_t)fdb_words[615u];
      uint32_t fdb_t194 = (uint32_t)(fdb_t193 != 0u);
      if (fdb_t194 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t195 = (uint32_t)(0u & 65535u);
        if (615u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[615u] = fdb_t195;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t196 = (uint32_t)fdb_words[603u];
        uint32_t fdb_t197 = (uint32_t)(fdb_t196 == 1u);
        if (fdb_t197 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v0 = 1u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          goto fdb_done;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t198 = (uint32_t)(1u & 65535u);
          if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[614u] = fdb_t198;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t199 = (uint32_t)fdb_words[636u];
          uint32_t fdb_t200 = (uint32_t)(fdb_t199 & 65535u);
          if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[620u] = fdb_t200;
        } else {
        }
      } else {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t201 = (uint32_t)fdb_words[603u];
        uint32_t fdb_t202 = (uint32_t)(fdb_t201 == 0u);
        if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t203 = (uint32_t)fdb_words[604u];
        uint32_t fdb_t204 = (uint32_t)(fdb_t203 == 0u);
        uint32_t fdb_t205 = (uint32_t)(fdb_t202 & fdb_t204);
        if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t206 = (uint32_t)fdb_words[636u];
        if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t207 = (uint32_t)fdb_words[620u];
        uint32_t fdb_t208 = (uint32_t)(fdb_t206 - fdb_t207);
        uint32_t fdb_t209 = (uint32_t)(fdb_t208 & 65535u);
        uint32_t fdb_t210 = (uint32_t)(fdb_t209 >= 4u);
        uint32_t fdb_t211 = (uint32_t)(fdb_t205 & fdb_t210);
        if (fdb_t211 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v0 = 2u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          goto fdb_done;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t212 = (uint32_t)(1u & 65535u);
          if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[614u] = fdb_t212;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t213 = (uint32_t)fdb_words[636u];
          uint32_t fdb_t214 = (uint32_t)(fdb_t213 & 65535u);
          if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[620u] = fdb_t214;
        } else {
        }
      }
    } else {
    }
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, fdb_failed ? 0u : fdb_v0 };
  return fdb_result;
}

FdbBlockResult fdb_native_1(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  uint32_t fdb_v37 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t0 = (uint32_t)(1u & 65535u);
    if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[614u] = fdb_t0;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t1 = (uint32_t)fdb_words[636u];
    uint32_t fdb_t2 = (uint32_t)(fdb_t1 & 65535u);
    if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[620u] = fdb_t2;
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, fdb_failed ? 0u : fdb_v0 };
  return fdb_result;
}

FdbBlockResult fdb_native_2(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  uint32_t fdb_v37 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t0 = (uint32_t)(1u & 65535u);
    if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[614u] = fdb_t0;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (636u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t1 = (uint32_t)fdb_words[636u];
    uint32_t fdb_t2 = (uint32_t)(fdb_t1 & 65535u);
    if (620u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[620u] = fdb_t2;
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, fdb_failed ? 0u : fdb_v0 };
  return fdb_result;
}

FdbBlockResult fdb_native_3(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v22 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop0=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t0 = (uint32_t)(fdb_v22 < 64000u);
      if (fdb_t0 == 0u) break;
      if (fdb_loop0 == 64000u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop0;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t1 = (uint32_t)(4096u + fdb_v22);
      if (fdb_t1 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[fdb_t1] = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t2 = (uint32_t)(fdb_v22 + 1u);
      fdb_v22 = fdb_t2;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 6u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 22u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 244u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 164u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 8u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop1=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t3 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t3 == 0u) break;
      if (fdb_loop1 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop1;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop2=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t4 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t4 == 0u) break;
        if (fdb_loop2 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop2;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t5 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t6 = (uint32_t)(fdb_t5 * 320u);
        uint32_t fdb_t7 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t8 = (uint32_t)(fdb_t6 + fdb_t7);
        uint32_t fdb_t9 = (uint32_t)(4096u + fdb_t8);
        if (fdb_t9 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t9] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t10 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t10;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t11 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t11;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 8u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 24u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 240u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 160u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop3=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t12 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t12 == 0u) break;
      if (fdb_loop3 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop3;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop4=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t13 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t13 == 0u) break;
        if (fdb_loop4 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop4;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t14 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t15 = (uint32_t)(fdb_t14 * 320u);
        uint32_t fdb_t16 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t17 = (uint32_t)(fdb_t15 + fdb_t16);
        uint32_t fdb_t18 = (uint32_t)(4096u + fdb_t17);
        if (fdb_t18 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t18] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t19 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t19;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t20 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t20;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v28 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop5=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t21 = (uint32_t)fdb_words[600u];
      uint32_t fdb_t22 = (uint32_t)(fdb_v28 < fdb_t21);
      if (fdb_t22 == 0u) break;
      if (fdb_loop5 == 600u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop5;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (fdb_v28 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t23 = (uint32_t)fdb_words[fdb_v28];
      if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t24 = (uint32_t)(fdb_t23 % 30u);
      uint32_t fdb_t25 = (uint32_t)(fdb_t24 * 8u);
      uint32_t fdb_t26 = (uint32_t)(8u + fdb_t25);
      fdb_v26 = fdb_t26;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (fdb_v28 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t27 = (uint32_t)fdb_words[fdb_v28];
      if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t28 = (uint32_t)(fdb_t27 / 30u);
      uint32_t fdb_t29 = (uint32_t)(fdb_t28 * 8u);
      uint32_t fdb_t30 = (uint32_t)(24u + fdb_t29);
      fdb_v27 = fdb_t30;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v25 = 7u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v23 = 7u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v5 = 2u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v24 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop6=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t31 = (uint32_t)(fdb_v24 < fdb_v23);
        if (fdb_t31 == 0u) break;
        if (fdb_loop6 == 200u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop6;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v6 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop7=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t32 = (uint32_t)(fdb_v6 < fdb_v25);
          if (fdb_t32 == 0u) break;
          if (fdb_loop7 == 320u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop7;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t33 = (uint32_t)(fdb_v27 + fdb_v24);
          uint32_t fdb_t34 = (uint32_t)(fdb_t33 * 320u);
          uint32_t fdb_t35 = (uint32_t)(fdb_v26 + fdb_v6);
          uint32_t fdb_t36 = (uint32_t)(fdb_t34 + fdb_t35);
          uint32_t fdb_t37 = (uint32_t)(4096u + fdb_t36);
          if (fdb_t37 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t37] = fdb_v5;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t38 = (uint32_t)(fdb_v6 + 1u);
          fdb_v6 = fdb_t38;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t39 = (uint32_t)(fdb_v24 + 1u);
        fdb_v24 = fdb_t39;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t40 = (uint32_t)(fdb_v28 + 1u);
      fdb_v28 = fdb_t40;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t41 = (uint32_t)fdb_words[0u];
    if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t42 = (uint32_t)(fdb_t41 % 30u);
    uint32_t fdb_t43 = (uint32_t)(fdb_t42 * 8u);
    uint32_t fdb_t44 = (uint32_t)(8u + fdb_t43);
    fdb_v26 = fdb_t44;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t45 = (uint32_t)fdb_words[0u];
    if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t46 = (uint32_t)(fdb_t45 / 30u);
    uint32_t fdb_t47 = (uint32_t)(fdb_t46 * 8u);
    uint32_t fdb_t48 = (uint32_t)(24u + fdb_t47);
    fdb_v27 = fdb_t48;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 7u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 7u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 10u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop8=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t49 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t49 == 0u) break;
      if (fdb_loop8 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop8;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop9=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t50 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t50 == 0u) break;
        if (fdb_loop9 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop9;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t51 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t52 = (uint32_t)(fdb_t51 * 320u);
        uint32_t fdb_t53 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t54 = (uint32_t)(fdb_t52 + fdb_t53);
        uint32_t fdb_t55 = (uint32_t)(4096u + fdb_t54);
        if (fdb_t55 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t55] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t56 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t56;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t57 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t57;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t58 = (uint32_t)fdb_words[612u];
    uint32_t fdb_t59 = (uint32_t)(fdb_t58 < 600u);
    if (fdb_t59 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t60 = (uint32_t)fdb_words[612u];
      if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t61 = (uint32_t)(fdb_t60 % 30u);
      uint32_t fdb_t62 = (uint32_t)(fdb_t61 * 8u);
      uint32_t fdb_t63 = (uint32_t)(8u + fdb_t62);
      fdb_v26 = fdb_t63;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t64 = (uint32_t)fdb_words[612u];
      if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t65 = (uint32_t)(fdb_t64 / 30u);
      uint32_t fdb_t66 = (uint32_t)(fdb_t65 * 8u);
      uint32_t fdb_t67 = (uint32_t)(24u + fdb_t66);
      fdb_v27 = fdb_t67;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v25 = 7u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v23 = 7u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v5 = 12u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v24 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop10=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t68 = (uint32_t)(fdb_v24 < fdb_v23);
        if (fdb_t68 == 0u) break;
        if (fdb_loop10 == 200u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop10;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v6 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop11=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t69 = (uint32_t)(fdb_v6 < fdb_v25);
          if (fdb_t69 == 0u) break;
          if (fdb_loop11 == 320u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop11;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t70 = (uint32_t)(fdb_v27 + fdb_v24);
          uint32_t fdb_t71 = (uint32_t)(fdb_t70 * 320u);
          uint32_t fdb_t72 = (uint32_t)(fdb_v26 + fdb_v6);
          uint32_t fdb_t73 = (uint32_t)(fdb_t71 + fdb_t72);
          uint32_t fdb_t74 = (uint32_t)(4096u + fdb_t73);
          if (fdb_t74 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t74] = fdb_v5;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t75 = (uint32_t)(fdb_v6 + 1u);
          fdb_v6 = fdb_t75;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t76 = (uint32_t)(fdb_v24 + 1u);
        fdb_v24 = fdb_t76;
      }
    } else {
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 280u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 40u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 24u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop12=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t77 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t77 == 0u) break;
      if (fdb_loop12 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop12;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop13=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t78 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t78 == 0u) break;
        if (fdb_loop13 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop13;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t79 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t80 = (uint32_t)(fdb_t79 * 320u);
        uint32_t fdb_t81 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t82 = (uint32_t)(fdb_t80 + fdb_t81);
        uint32_t fdb_t83 = (uint32_t)(4096u + fdb_t82);
        if (fdb_t83 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t83] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t84 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t84;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t85 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t85;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 64u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 24u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop14=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t86 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t86 == 0u) break;
      if (fdb_loop14 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop14;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop15=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t87 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t87 == 0u) break;
        if (fdb_loop15 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop15;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t88 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t89 = (uint32_t)(fdb_t88 * 320u);
        uint32_t fdb_t90 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t91 = (uint32_t)(fdb_t89 + fdb_t90);
        uint32_t fdb_t92 = (uint32_t)(4096u + fdb_t91);
        if (fdb_t92 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t92] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t93 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t93;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t94 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t94;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 288u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 64u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 24u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop16=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t95 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t95 == 0u) break;
      if (fdb_loop16 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop16;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop17=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t96 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t96 == 0u) break;
        if (fdb_loop17 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop17;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t97 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t98 = (uint32_t)(fdb_t97 * 320u);
        uint32_t fdb_t99 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t100 = (uint32_t)(fdb_t98 + fdb_t99);
        uint32_t fdb_t101 = (uint32_t)(4096u + fdb_t100);
        if (fdb_t101 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t101] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t102 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t102;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t103 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t103;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 280u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 88u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 24u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop18=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t104 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t104 == 0u) break;
      if (fdb_loop18 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop18;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop19=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t105 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t105 == 0u) break;
        if (fdb_loop19 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop19;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t106 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t107 = (uint32_t)(fdb_t106 * 320u);
        uint32_t fdb_t108 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t109 = (uint32_t)(fdb_t107 + fdb_t108);
        uint32_t fdb_t110 = (uint32_t)(4096u + fdb_t109);
        if (fdb_t110 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t110] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t111 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t111;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t112 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t112;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 120u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 56u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop20=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t113 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t113 == 0u) break;
      if (fdb_loop20 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop20;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop21=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t114 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t114 == 0u) break;
        if (fdb_loop21 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop21;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t115 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t116 = (uint32_t)(fdb_t115 * 320u);
        uint32_t fdb_t117 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t118 = (uint32_t)(fdb_t116 + fdb_t117);
        uint32_t fdb_t119 = (uint32_t)(4096u + fdb_t118);
        if (fdb_t119 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t119] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t120 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t120;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t121 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t121;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 144u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 56u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop22=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t122 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t122 == 0u) break;
      if (fdb_loop22 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop22;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop23=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t123 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t123 == 0u) break;
        if (fdb_loop23 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop23;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t124 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t125 = (uint32_t)(fdb_t124 * 320u);
        uint32_t fdb_t126 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t127 = (uint32_t)(fdb_t125 + fdb_t126);
        uint32_t fdb_t128 = (uint32_t)(4096u + fdb_t127);
        if (fdb_t128 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t128] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t129 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t129;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t130 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t130;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v26 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v27 = 168u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v25 = 56u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v23 = 20u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v5 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v24 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop24=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t131 = (uint32_t)(fdb_v24 < fdb_v23);
      if (fdb_t131 == 0u) break;
      if (fdb_loop24 == 200u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop24;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v6 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop25=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t132 = (uint32_t)(fdb_v6 < fdb_v25);
        if (fdb_t132 == 0u) break;
        if (fdb_loop25 == 320u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop25;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t133 = (uint32_t)(fdb_v27 + fdb_v24);
        uint32_t fdb_t134 = (uint32_t)(fdb_t133 * 320u);
        uint32_t fdb_t135 = (uint32_t)(fdb_v26 + fdb_v6);
        uint32_t fdb_t136 = (uint32_t)(fdb_t134 + fdb_t135);
        uint32_t fdb_t137 = (uint32_t)(4096u + fdb_t136);
        if (fdb_t137 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[fdb_t137] = fdb_v5;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t138 = (uint32_t)(fdb_v6 + 1u);
        fdb_v6 = fdb_t138;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t139 = (uint32_t)(fdb_v24 + 1u);
      fdb_v24 = fdb_t139;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3072u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 16u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop26=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t140 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t140 == 0u) break;
      if (fdb_loop26 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop26;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t141 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t141 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t142 = (uint32_t)fdb_words[fdb_t141];
      fdb_v3 = fdb_t142;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop27=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t143 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t143 == 0u) break;
        if (fdb_loop27 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop27;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t144 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t145 = (uint32_t)(fdb_t144 + fdb_v13);
        uint32_t fdb_t146 = (uint32_t)(1024u + fdb_t145);
        if (fdb_t146 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t147 = (uint32_t)fdb_words[fdb_t146];
        fdb_v1 = fdb_t147;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop28=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t148 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t148 == 0u) break;
          if (fdb_loop28 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop28;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t149 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t150 = (uint32_t)(fdb_v1 >> (fdb_t149 & 31u));
          uint32_t fdb_t151 = (uint32_t)(fdb_t150 & 1u);
          fdb_v15 = fdb_t151;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t152 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t153 = (uint32_t)(fdb_t152 * 320u);
          uint32_t fdb_t154 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t155 = (uint32_t)(fdb_t154 + fdb_v12);
          uint32_t fdb_t156 = (uint32_t)(fdb_v31 + fdb_t155);
          uint32_t fdb_t157 = (uint32_t)(fdb_t153 + fdb_t156);
          uint32_t fdb_t158 = (uint32_t)(4096u + fdb_t157);
          uint32_t fdb_t159 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t158 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t158] = fdb_t159;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t160 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t160;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t161 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t161;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t162 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t162;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (605u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t163 = (uint32_t)fdb_words[605u];
    fdb_v19 = fdb_t163;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v9 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop29=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t164 = (uint32_t)(fdb_v19 != 0u);
      uint32_t fdb_t165 = (uint32_t)(fdb_v9 == 0u);
      uint32_t fdb_t166 = (uint32_t)(fdb_t164 | fdb_t165);
      if (fdb_t166 == 0u) break;
      if (fdb_loop29 == 5u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop29;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t167 = (uint32_t)(760u + fdb_v9);
      if (10u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t168 = (uint32_t)(fdb_v19 % 10u);
      uint32_t fdb_t169 = (uint32_t)(48u + fdb_t168);
      if (fdb_t167 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[fdb_t167] = fdb_t169;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t170 = (uint32_t)(fdb_v9 + 1u);
      fdb_v9 = fdb_t170;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (10u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t171 = (uint32_t)(fdb_v19 / 10u);
      fdb_v19 = fdb_t171;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v8 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop30=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t172 = (uint32_t)(fdb_v8 < fdb_v9);
      if (fdb_t172 == 0u) break;
      if (fdb_loop30 == 5u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop30;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t173 = (uint32_t)(768u + fdb_v8);
      uint32_t fdb_t174 = (uint32_t)(fdb_v9 - 1u);
      uint32_t fdb_t175 = (uint32_t)(fdb_t174 - fdb_v8);
      uint32_t fdb_t176 = (uint32_t)(760u + fdb_t175);
      if (fdb_t176 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t177 = (uint32_t)fdb_words[fdb_t176];
      if (fdb_t173 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[fdb_t173] = fdb_t177;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t178 = (uint32_t)(fdb_v8 + 1u);
      fdb_v8 = fdb_t178;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 768u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = fdb_v9;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 128u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop31=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t179 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t179 == 0u) break;
      if (fdb_loop31 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop31;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t180 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t180 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t181 = (uint32_t)fdb_words[fdb_t180];
      fdb_v3 = fdb_t181;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop32=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t182 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t182 == 0u) break;
        if (fdb_loop32 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop32;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t183 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t184 = (uint32_t)(fdb_t183 + fdb_v13);
        uint32_t fdb_t185 = (uint32_t)(1024u + fdb_t184);
        if (fdb_t185 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t186 = (uint32_t)fdb_words[fdb_t185];
        fdb_v1 = fdb_t186;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop33=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t187 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t187 == 0u) break;
          if (fdb_loop33 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop33;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t188 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t189 = (uint32_t)(fdb_v1 >> (fdb_t188 & 31u));
          uint32_t fdb_t190 = (uint32_t)(fdb_t189 & 1u);
          fdb_v15 = fdb_t190;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t191 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t192 = (uint32_t)(fdb_t191 * 320u);
          uint32_t fdb_t193 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t194 = (uint32_t)(fdb_t193 + fdb_v12);
          uint32_t fdb_t195 = (uint32_t)(fdb_v31 + fdb_t194);
          uint32_t fdb_t196 = (uint32_t)(fdb_t192 + fdb_t195);
          uint32_t fdb_t197 = (uint32_t)(4096u + fdb_t196);
          uint32_t fdb_t198 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t197 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t197] = fdb_t198;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t199 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t199;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t200 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t200;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t201 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t201;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t202 = (uint32_t)fdb_words[604u];
    uint32_t fdb_t203 = (uint32_t)(fdb_t202 == 1u);
    if (fdb_t203 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v30 = 3102u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v29 = 7u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v31 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v32 = 8u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v33 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop34=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t204 = (uint32_t)(fdb_v33 < fdb_v29);
        if (fdb_t204 == 0u) break;
        if (fdb_loop34 == 80u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop34;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t205 = (uint32_t)(fdb_v30 + fdb_v33);
        if (fdb_t205 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t206 = (uint32_t)fdb_words[fdb_t205];
        fdb_v3 = fdb_t206;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v13 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop35=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t207 = (uint32_t)(fdb_v13 < 8u);
          if (fdb_t207 == 0u) break;
          if (fdb_loop35 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop35;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t208 = (uint32_t)(fdb_v3 * 8u);
          uint32_t fdb_t209 = (uint32_t)(fdb_t208 + fdb_v13);
          uint32_t fdb_t210 = (uint32_t)(1024u + fdb_t209);
          if (fdb_t210 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t211 = (uint32_t)fdb_words[fdb_t210];
          fdb_v1 = fdb_t211;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v12 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop36=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t212 = (uint32_t)(fdb_v12 < 8u);
            if (fdb_t212 == 0u) break;
            if (fdb_loop36 == 8u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop36;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t213 = (uint32_t)(7u - fdb_v12);
            uint32_t fdb_t214 = (uint32_t)(fdb_v1 >> (fdb_t213 & 31u));
            uint32_t fdb_t215 = (uint32_t)(fdb_t214 & 1u);
            fdb_v15 = fdb_t215;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t216 = (uint32_t)(fdb_v32 + fdb_v13);
            uint32_t fdb_t217 = (uint32_t)(fdb_t216 * 320u);
            uint32_t fdb_t218 = (uint32_t)(fdb_v33 * 8u);
            uint32_t fdb_t219 = (uint32_t)(fdb_t218 + fdb_v12);
            uint32_t fdb_t220 = (uint32_t)(fdb_v31 + fdb_t219);
            uint32_t fdb_t221 = (uint32_t)(fdb_t217 + fdb_t220);
            uint32_t fdb_t222 = (uint32_t)(4096u + fdb_t221);
            uint32_t fdb_t223 = (uint32_t)(fdb_v15 * 15u);
            if (fdb_t222 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            fdb_words[fdb_t222] = fdb_t223;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t224 = (uint32_t)(fdb_v12 + 1u);
            fdb_v12 = fdb_t224;
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t225 = (uint32_t)(fdb_v13 + 1u);
          fdb_v13 = fdb_t225;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t226 = (uint32_t)(fdb_v33 + 1u);
        fdb_v33 = fdb_t226;
      }
    } else {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t227 = (uint32_t)fdb_words[604u];
      uint32_t fdb_t228 = (uint32_t)(fdb_t227 == 2u);
      if (fdb_t228 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v30 = 3109u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v29 = 7u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v31 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v32 = 8u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v33 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop37=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t229 = (uint32_t)(fdb_v33 < fdb_v29);
          if (fdb_t229 == 0u) break;
          if (fdb_loop37 == 80u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop37;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t230 = (uint32_t)(fdb_v30 + fdb_v33);
          if (fdb_t230 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t231 = (uint32_t)fdb_words[fdb_t230];
          fdb_v3 = fdb_t231;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v13 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop38=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t232 = (uint32_t)(fdb_v13 < 8u);
            if (fdb_t232 == 0u) break;
            if (fdb_loop38 == 8u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop38;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t233 = (uint32_t)(fdb_v3 * 8u);
            uint32_t fdb_t234 = (uint32_t)(fdb_t233 + fdb_v13);
            uint32_t fdb_t235 = (uint32_t)(1024u + fdb_t234);
            if (fdb_t235 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t236 = (uint32_t)fdb_words[fdb_t235];
            fdb_v1 = fdb_t236;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            fdb_v12 = 0u;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            for (uint32_t fdb_loop39=0u;;) {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t237 = (uint32_t)(fdb_v12 < 8u);
              if (fdb_t237 == 0u) break;
              if (fdb_loop39 == 8u) { fdb_failed = 1u; goto fdb_done; }
              ++fdb_loop39;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t238 = (uint32_t)(7u - fdb_v12);
              uint32_t fdb_t239 = (uint32_t)(fdb_v1 >> (fdb_t238 & 31u));
              uint32_t fdb_t240 = (uint32_t)(fdb_t239 & 1u);
              fdb_v15 = fdb_t240;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t241 = (uint32_t)(fdb_v32 + fdb_v13);
              uint32_t fdb_t242 = (uint32_t)(fdb_t241 * 320u);
              uint32_t fdb_t243 = (uint32_t)(fdb_v33 * 8u);
              uint32_t fdb_t244 = (uint32_t)(fdb_t243 + fdb_v12);
              uint32_t fdb_t245 = (uint32_t)(fdb_v31 + fdb_t244);
              uint32_t fdb_t246 = (uint32_t)(fdb_t242 + fdb_t245);
              uint32_t fdb_t247 = (uint32_t)(4096u + fdb_t246);
              uint32_t fdb_t248 = (uint32_t)(fdb_v15 * 15u);
              if (fdb_t247 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              fdb_words[fdb_t247] = fdb_t248;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t249 = (uint32_t)(fdb_v12 + 1u);
              fdb_v12 = fdb_t249;
            }
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t250 = (uint32_t)(fdb_v13 + 1u);
            fdb_v13 = fdb_t250;
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t251 = (uint32_t)(fdb_v33 + 1u);
          fdb_v33 = fdb_t251;
        }
      } else {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t252 = (uint32_t)fdb_words[603u];
        uint32_t fdb_t253 = (uint32_t)(fdb_t252 == 0u);
        if (fdb_t253 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v30 = 3095u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v29 = 7u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v31 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v32 = 8u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v33 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop40=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t254 = (uint32_t)(fdb_v33 < fdb_v29);
            if (fdb_t254 == 0u) break;
            if (fdb_loop40 == 80u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop40;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t255 = (uint32_t)(fdb_v30 + fdb_v33);
            if (fdb_t255 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t256 = (uint32_t)fdb_words[fdb_t255];
            fdb_v3 = fdb_t256;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            fdb_v13 = 0u;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            for (uint32_t fdb_loop41=0u;;) {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t257 = (uint32_t)(fdb_v13 < 8u);
              if (fdb_t257 == 0u) break;
              if (fdb_loop41 == 8u) { fdb_failed = 1u; goto fdb_done; }
              ++fdb_loop41;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t258 = (uint32_t)(fdb_v3 * 8u);
              uint32_t fdb_t259 = (uint32_t)(fdb_t258 + fdb_v13);
              uint32_t fdb_t260 = (uint32_t)(1024u + fdb_t259);
              if (fdb_t260 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              uint32_t fdb_t261 = (uint32_t)fdb_words[fdb_t260];
              fdb_v1 = fdb_t261;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              fdb_v12 = 0u;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              for (uint32_t fdb_loop42=0u;;) {
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t262 = (uint32_t)(fdb_v12 < 8u);
                if (fdb_t262 == 0u) break;
                if (fdb_loop42 == 8u) { fdb_failed = 1u; goto fdb_done; }
                ++fdb_loop42;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t263 = (uint32_t)(7u - fdb_v12);
                uint32_t fdb_t264 = (uint32_t)(fdb_v1 >> (fdb_t263 & 31u));
                uint32_t fdb_t265 = (uint32_t)(fdb_t264 & 1u);
                fdb_v15 = fdb_t265;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t266 = (uint32_t)(fdb_v32 + fdb_v13);
                uint32_t fdb_t267 = (uint32_t)(fdb_t266 * 320u);
                uint32_t fdb_t268 = (uint32_t)(fdb_v33 * 8u);
                uint32_t fdb_t269 = (uint32_t)(fdb_t268 + fdb_v12);
                uint32_t fdb_t270 = (uint32_t)(fdb_v31 + fdb_t269);
                uint32_t fdb_t271 = (uint32_t)(fdb_t267 + fdb_t270);
                uint32_t fdb_t272 = (uint32_t)(4096u + fdb_t271);
                uint32_t fdb_t273 = (uint32_t)(fdb_v15 * 15u);
                if (fdb_t272 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                fdb_words[fdb_t272] = fdb_t273;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t274 = (uint32_t)(fdb_v12 + 1u);
                fdb_v12 = fdb_t274;
              }
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t275 = (uint32_t)(fdb_v13 + 1u);
              fdb_v13 = fdb_t275;
            }
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t276 = (uint32_t)(fdb_v33 + 1u);
            fdb_v33 = fdb_t276;
          }
        } else {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v30 = 3088u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v29 = 7u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v31 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v32 = 8u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v33 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop43=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t277 = (uint32_t)(fdb_v33 < fdb_v29);
            if (fdb_t277 == 0u) break;
            if (fdb_loop43 == 80u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop43;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t278 = (uint32_t)(fdb_v30 + fdb_v33);
            if (fdb_t278 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t279 = (uint32_t)fdb_words[fdb_t278];
            fdb_v3 = fdb_t279;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            fdb_v13 = 0u;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            for (uint32_t fdb_loop44=0u;;) {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t280 = (uint32_t)(fdb_v13 < 8u);
              if (fdb_t280 == 0u) break;
              if (fdb_loop44 == 8u) { fdb_failed = 1u; goto fdb_done; }
              ++fdb_loop44;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t281 = (uint32_t)(fdb_v3 * 8u);
              uint32_t fdb_t282 = (uint32_t)(fdb_t281 + fdb_v13);
              uint32_t fdb_t283 = (uint32_t)(1024u + fdb_t282);
              if (fdb_t283 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              uint32_t fdb_t284 = (uint32_t)fdb_words[fdb_t283];
              fdb_v1 = fdb_t284;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              fdb_v12 = 0u;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              for (uint32_t fdb_loop45=0u;;) {
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t285 = (uint32_t)(fdb_v12 < 8u);
                if (fdb_t285 == 0u) break;
                if (fdb_loop45 == 8u) { fdb_failed = 1u; goto fdb_done; }
                ++fdb_loop45;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t286 = (uint32_t)(7u - fdb_v12);
                uint32_t fdb_t287 = (uint32_t)(fdb_v1 >> (fdb_t286 & 31u));
                uint32_t fdb_t288 = (uint32_t)(fdb_t287 & 1u);
                fdb_v15 = fdb_t288;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t289 = (uint32_t)(fdb_v32 + fdb_v13);
                uint32_t fdb_t290 = (uint32_t)(fdb_t289 * 320u);
                uint32_t fdb_t291 = (uint32_t)(fdb_v33 * 8u);
                uint32_t fdb_t292 = (uint32_t)(fdb_t291 + fdb_v12);
                uint32_t fdb_t293 = (uint32_t)(fdb_v31 + fdb_t292);
                uint32_t fdb_t294 = (uint32_t)(fdb_t290 + fdb_t293);
                uint32_t fdb_t295 = (uint32_t)(4096u + fdb_t294);
                uint32_t fdb_t296 = (uint32_t)(fdb_v15 * 15u);
                if (fdb_t295 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                fdb_words[fdb_t295] = fdb_t296;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t297 = (uint32_t)(fdb_v12 + 1u);
                fdb_v12 = fdb_t297;
              }
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t298 = (uint32_t)(fdb_v13 + 1u);
              fdb_v13 = fdb_t298;
            }
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t299 = (uint32_t)(fdb_v33 + 1u);
            fdb_v33 = fdb_t299;
          }
        }
      }
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (611u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t300 = (uint32_t)fdb_words[611u];
    uint32_t fdb_t301 = (uint32_t)(fdb_t300 == 0u);
    if (fdb_t301 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v30 = 3180u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v29 = 5u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v31 = 256u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v32 = 8u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v33 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop46=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t302 = (uint32_t)(fdb_v33 < fdb_v29);
        if (fdb_t302 == 0u) break;
        if (fdb_loop46 == 80u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop46;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t303 = (uint32_t)(fdb_v30 + fdb_v33);
        if (fdb_t303 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t304 = (uint32_t)fdb_words[fdb_t303];
        fdb_v3 = fdb_t304;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v13 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop47=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t305 = (uint32_t)(fdb_v13 < 8u);
          if (fdb_t305 == 0u) break;
          if (fdb_loop47 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop47;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t306 = (uint32_t)(fdb_v3 * 8u);
          uint32_t fdb_t307 = (uint32_t)(fdb_t306 + fdb_v13);
          uint32_t fdb_t308 = (uint32_t)(1024u + fdb_t307);
          if (fdb_t308 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t309 = (uint32_t)fdb_words[fdb_t308];
          fdb_v1 = fdb_t309;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v12 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop48=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t310 = (uint32_t)(fdb_v12 < 8u);
            if (fdb_t310 == 0u) break;
            if (fdb_loop48 == 8u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop48;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t311 = (uint32_t)(7u - fdb_v12);
            uint32_t fdb_t312 = (uint32_t)(fdb_v1 >> (fdb_t311 & 31u));
            uint32_t fdb_t313 = (uint32_t)(fdb_t312 & 1u);
            fdb_v15 = fdb_t313;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t314 = (uint32_t)(fdb_v32 + fdb_v13);
            uint32_t fdb_t315 = (uint32_t)(fdb_t314 * 320u);
            uint32_t fdb_t316 = (uint32_t)(fdb_v33 * 8u);
            uint32_t fdb_t317 = (uint32_t)(fdb_t316 + fdb_v12);
            uint32_t fdb_t318 = (uint32_t)(fdb_v31 + fdb_t317);
            uint32_t fdb_t319 = (uint32_t)(fdb_t315 + fdb_t318);
            uint32_t fdb_t320 = (uint32_t)(4096u + fdb_t319);
            uint32_t fdb_t321 = (uint32_t)(fdb_v15 * 15u);
            if (fdb_t320 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            fdb_words[fdb_t320] = fdb_t321;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t322 = (uint32_t)(fdb_v12 + 1u);
            fdb_v12 = fdb_t322;
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t323 = (uint32_t)(fdb_v13 + 1u);
          fdb_v13 = fdb_t323;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t324 = (uint32_t)(fdb_v33 + 1u);
        fdb_v33 = fdb_t324;
      }
    } else {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v30 = 3175u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v29 = 5u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v31 = 256u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v32 = 8u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v33 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop49=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t325 = (uint32_t)(fdb_v33 < fdb_v29);
        if (fdb_t325 == 0u) break;
        if (fdb_loop49 == 80u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop49;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t326 = (uint32_t)(fdb_v30 + fdb_v33);
        if (fdb_t326 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t327 = (uint32_t)fdb_words[fdb_t326];
        fdb_v3 = fdb_t327;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v13 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop50=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t328 = (uint32_t)(fdb_v13 < 8u);
          if (fdb_t328 == 0u) break;
          if (fdb_loop50 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop50;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t329 = (uint32_t)(fdb_v3 * 8u);
          uint32_t fdb_t330 = (uint32_t)(fdb_t329 + fdb_v13);
          uint32_t fdb_t331 = (uint32_t)(1024u + fdb_t330);
          if (fdb_t331 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t332 = (uint32_t)fdb_words[fdb_t331];
          fdb_v1 = fdb_t332;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v12 = 0u;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop51=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t333 = (uint32_t)(fdb_v12 < 8u);
            if (fdb_t333 == 0u) break;
            if (fdb_loop51 == 8u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop51;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t334 = (uint32_t)(7u - fdb_v12);
            uint32_t fdb_t335 = (uint32_t)(fdb_v1 >> (fdb_t334 & 31u));
            uint32_t fdb_t336 = (uint32_t)(fdb_t335 & 1u);
            fdb_v15 = fdb_t336;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t337 = (uint32_t)(fdb_v32 + fdb_v13);
            uint32_t fdb_t338 = (uint32_t)(fdb_t337 * 320u);
            uint32_t fdb_t339 = (uint32_t)(fdb_v33 * 8u);
            uint32_t fdb_t340 = (uint32_t)(fdb_t339 + fdb_v12);
            uint32_t fdb_t341 = (uint32_t)(fdb_v31 + fdb_t340);
            uint32_t fdb_t342 = (uint32_t)(fdb_t338 + fdb_t341);
            uint32_t fdb_t343 = (uint32_t)(4096u + fdb_t342);
            uint32_t fdb_t344 = (uint32_t)(fdb_v15 * 15u);
            if (fdb_t343 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            fdb_words[fdb_t343] = fdb_t344;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t345 = (uint32_t)(fdb_v12 + 1u);
            fdb_v12 = fdb_t345;
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t346 = (uint32_t)(fdb_v13 + 1u);
          fdb_v13 = fdb_t346;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t347 = (uint32_t)(fdb_v33 + 1u);
        fdb_v33 = fdb_t347;
      }
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3155u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 2u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 280u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 40u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop52=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t348 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t348 == 0u) break;
      if (fdb_loop52 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop52;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t349 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t349 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t350 = (uint32_t)fdb_words[fdb_t349];
      fdb_v3 = fdb_t350;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop53=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t351 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t351 == 0u) break;
        if (fdb_loop53 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop53;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t352 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t353 = (uint32_t)(fdb_t352 + fdb_v13);
        uint32_t fdb_t354 = (uint32_t)(1024u + fdb_t353);
        if (fdb_t354 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t355 = (uint32_t)fdb_words[fdb_t354];
        fdb_v1 = fdb_t355;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop54=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t356 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t356 == 0u) break;
          if (fdb_loop54 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop54;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t357 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t358 = (uint32_t)(fdb_v1 >> (fdb_t357 & 31u));
          uint32_t fdb_t359 = (uint32_t)(fdb_t358 & 1u);
          fdb_v15 = fdb_t359;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t360 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t361 = (uint32_t)(fdb_t360 * 320u);
          uint32_t fdb_t362 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t363 = (uint32_t)(fdb_t362 + fdb_v12);
          uint32_t fdb_t364 = (uint32_t)(fdb_v31 + fdb_t363);
          uint32_t fdb_t365 = (uint32_t)(fdb_t361 + fdb_t364);
          uint32_t fdb_t366 = (uint32_t)(4096u + fdb_t365);
          uint32_t fdb_t367 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t366 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t366] = fdb_t367;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t368 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t368;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t369 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t369;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t370 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t370;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3157u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 64u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop55=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t371 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t371 == 0u) break;
      if (fdb_loop55 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop55;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t372 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t372 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t373 = (uint32_t)fdb_words[fdb_t372];
      fdb_v3 = fdb_t373;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop56=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t374 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t374 == 0u) break;
        if (fdb_loop56 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop56;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t375 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t376 = (uint32_t)(fdb_t375 + fdb_v13);
        uint32_t fdb_t377 = (uint32_t)(1024u + fdb_t376);
        if (fdb_t377 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t378 = (uint32_t)fdb_words[fdb_t377];
        fdb_v1 = fdb_t378;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop57=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t379 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t379 == 0u) break;
          if (fdb_loop57 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop57;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t380 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t381 = (uint32_t)(fdb_v1 >> (fdb_t380 & 31u));
          uint32_t fdb_t382 = (uint32_t)(fdb_t381 & 1u);
          fdb_v15 = fdb_t382;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t383 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t384 = (uint32_t)(fdb_t383 * 320u);
          uint32_t fdb_t385 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t386 = (uint32_t)(fdb_t385 + fdb_v12);
          uint32_t fdb_t387 = (uint32_t)(fdb_v31 + fdb_t386);
          uint32_t fdb_t388 = (uint32_t)(fdb_t384 + fdb_t387);
          uint32_t fdb_t389 = (uint32_t)(4096u + fdb_t388);
          uint32_t fdb_t390 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t389 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t389] = fdb_t390;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t391 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t391;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t392 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t392;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t393 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t393;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3158u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 1u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 288u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 64u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop58=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t394 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t394 == 0u) break;
      if (fdb_loop58 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop58;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t395 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t395 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t396 = (uint32_t)fdb_words[fdb_t395];
      fdb_v3 = fdb_t396;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop59=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t397 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t397 == 0u) break;
        if (fdb_loop59 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop59;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t398 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t399 = (uint32_t)(fdb_t398 + fdb_v13);
        uint32_t fdb_t400 = (uint32_t)(1024u + fdb_t399);
        if (fdb_t400 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t401 = (uint32_t)fdb_words[fdb_t400];
        fdb_v1 = fdb_t401;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop60=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t402 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t402 == 0u) break;
          if (fdb_loop60 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop60;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t403 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t404 = (uint32_t)(fdb_v1 >> (fdb_t403 & 31u));
          uint32_t fdb_t405 = (uint32_t)(fdb_t404 & 1u);
          fdb_v15 = fdb_t405;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t406 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t407 = (uint32_t)(fdb_t406 * 320u);
          uint32_t fdb_t408 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t409 = (uint32_t)(fdb_t408 + fdb_v12);
          uint32_t fdb_t410 = (uint32_t)(fdb_v31 + fdb_t409);
          uint32_t fdb_t411 = (uint32_t)(fdb_t407 + fdb_t410);
          uint32_t fdb_t412 = (uint32_t)(4096u + fdb_t411);
          uint32_t fdb_t413 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t412 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t412] = fdb_t413;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t414 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t414;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t415 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t415;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t416 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t416;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3159u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 2u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 280u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 88u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop61=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t417 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t417 == 0u) break;
      if (fdb_loop61 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop61;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t418 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t418 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t419 = (uint32_t)fdb_words[fdb_t418];
      fdb_v3 = fdb_t419;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop62=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t420 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t420 == 0u) break;
        if (fdb_loop62 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop62;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t421 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t422 = (uint32_t)(fdb_t421 + fdb_v13);
        uint32_t fdb_t423 = (uint32_t)(1024u + fdb_t422);
        if (fdb_t423 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t424 = (uint32_t)fdb_words[fdb_t423];
        fdb_v1 = fdb_t424;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop63=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t425 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t425 == 0u) break;
          if (fdb_loop63 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop63;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t426 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t427 = (uint32_t)(fdb_v1 >> (fdb_t426 & 31u));
          uint32_t fdb_t428 = (uint32_t)(fdb_t427 & 1u);
          fdb_v15 = fdb_t428;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t429 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t430 = (uint32_t)(fdb_t429 * 320u);
          uint32_t fdb_t431 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t432 = (uint32_t)(fdb_t431 + fdb_v12);
          uint32_t fdb_t433 = (uint32_t)(fdb_v31 + fdb_t432);
          uint32_t fdb_t434 = (uint32_t)(fdb_t430 + fdb_t433);
          uint32_t fdb_t435 = (uint32_t)(4096u + fdb_t434);
          uint32_t fdb_t436 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t435 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t435] = fdb_t436;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t437 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t437;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t438 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t438;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t439 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t439;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3161u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 5u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 120u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop64=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t440 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t440 == 0u) break;
      if (fdb_loop64 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop64;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t441 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t441 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t442 = (uint32_t)fdb_words[fdb_t441];
      fdb_v3 = fdb_t442;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop65=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t443 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t443 == 0u) break;
        if (fdb_loop65 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop65;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t444 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t445 = (uint32_t)(fdb_t444 + fdb_v13);
        uint32_t fdb_t446 = (uint32_t)(1024u + fdb_t445);
        if (fdb_t446 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t447 = (uint32_t)fdb_words[fdb_t446];
        fdb_v1 = fdb_t447;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop66=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t448 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t448 == 0u) break;
          if (fdb_loop66 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop66;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t449 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t450 = (uint32_t)(fdb_v1 >> (fdb_t449 & 31u));
          uint32_t fdb_t451 = (uint32_t)(fdb_t450 & 1u);
          fdb_v15 = fdb_t451;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t452 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t453 = (uint32_t)(fdb_t452 * 320u);
          uint32_t fdb_t454 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t455 = (uint32_t)(fdb_t454 + fdb_v12);
          uint32_t fdb_t456 = (uint32_t)(fdb_v31 + fdb_t455);
          uint32_t fdb_t457 = (uint32_t)(fdb_t453 + fdb_t456);
          uint32_t fdb_t458 = (uint32_t)(4096u + fdb_t457);
          uint32_t fdb_t459 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t458 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t458] = fdb_t459;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t460 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t460;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t461 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t461;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t462 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t462;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3166u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 4u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 144u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop67=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t463 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t463 == 0u) break;
      if (fdb_loop67 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop67;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t464 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t464 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t465 = (uint32_t)fdb_words[fdb_t464];
      fdb_v3 = fdb_t465;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop68=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t466 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t466 == 0u) break;
        if (fdb_loop68 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop68;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t467 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t468 = (uint32_t)(fdb_t467 + fdb_v13);
        uint32_t fdb_t469 = (uint32_t)(1024u + fdb_t468);
        if (fdb_t469 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t470 = (uint32_t)fdb_words[fdb_t469];
        fdb_v1 = fdb_t470;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop69=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t471 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t471 == 0u) break;
          if (fdb_loop69 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop69;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t472 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t473 = (uint32_t)(fdb_v1 >> (fdb_t472 & 31u));
          uint32_t fdb_t474 = (uint32_t)(fdb_t473 & 1u);
          fdb_v15 = fdb_t474;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t475 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t476 = (uint32_t)(fdb_t475 * 320u);
          uint32_t fdb_t477 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t478 = (uint32_t)(fdb_t477 + fdb_v12);
          uint32_t fdb_t479 = (uint32_t)(fdb_v31 + fdb_t478);
          uint32_t fdb_t480 = (uint32_t)(fdb_t476 + fdb_t479);
          uint32_t fdb_t481 = (uint32_t)(4096u + fdb_t480);
          uint32_t fdb_t482 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t481 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t481] = fdb_t482;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t483 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t483;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t484 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t484;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t485 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t485;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3170u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 5u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 256u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 168u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop70=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t486 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t486 == 0u) break;
      if (fdb_loop70 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop70;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t487 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t487 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t488 = (uint32_t)fdb_words[fdb_t487];
      fdb_v3 = fdb_t488;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop71=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t489 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t489 == 0u) break;
        if (fdb_loop71 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop71;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t490 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t491 = (uint32_t)(fdb_t490 + fdb_v13);
        uint32_t fdb_t492 = (uint32_t)(1024u + fdb_t491);
        if (fdb_t492 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t493 = (uint32_t)fdb_words[fdb_t492];
        fdb_v1 = fdb_t493;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop72=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t494 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t494 == 0u) break;
          if (fdb_loop72 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop72;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t495 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t496 = (uint32_t)(fdb_v1 >> (fdb_t495 & 31u));
          uint32_t fdb_t497 = (uint32_t)(fdb_t496 & 1u);
          fdb_v15 = fdb_t497;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t498 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t499 = (uint32_t)(fdb_t498 * 320u);
          uint32_t fdb_t500 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t501 = (uint32_t)(fdb_t500 + fdb_v12);
          uint32_t fdb_t502 = (uint32_t)(fdb_v31 + fdb_t501);
          uint32_t fdb_t503 = (uint32_t)(fdb_t499 + fdb_t502);
          uint32_t fdb_t504 = (uint32_t)(4096u + fdb_t503);
          uint32_t fdb_t505 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t504 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t504] = fdb_t505;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t506 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t506;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t507 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t507;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t508 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t508;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v30 = 3116u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v29 = 39u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v31 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v32 = 192u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v33 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop73=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t509 = (uint32_t)(fdb_v33 < fdb_v29);
      if (fdb_t509 == 0u) break;
      if (fdb_loop73 == 80u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop73;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t510 = (uint32_t)(fdb_v30 + fdb_v33);
      if (fdb_t510 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t511 = (uint32_t)fdb_words[fdb_t510];
      fdb_v3 = fdb_t511;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v13 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop74=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t512 = (uint32_t)(fdb_v13 < 8u);
        if (fdb_t512 == 0u) break;
        if (fdb_loop74 == 8u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop74;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t513 = (uint32_t)(fdb_v3 * 8u);
        uint32_t fdb_t514 = (uint32_t)(fdb_t513 + fdb_v13);
        uint32_t fdb_t515 = (uint32_t)(1024u + fdb_t514);
        if (fdb_t515 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t516 = (uint32_t)fdb_words[fdb_t515];
        fdb_v1 = fdb_t516;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v12 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop75=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t517 = (uint32_t)(fdb_v12 < 8u);
          if (fdb_t517 == 0u) break;
          if (fdb_loop75 == 8u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop75;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t518 = (uint32_t)(7u - fdb_v12);
          uint32_t fdb_t519 = (uint32_t)(fdb_v1 >> (fdb_t518 & 31u));
          uint32_t fdb_t520 = (uint32_t)(fdb_t519 & 1u);
          fdb_v15 = fdb_t520;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t521 = (uint32_t)(fdb_v32 + fdb_v13);
          uint32_t fdb_t522 = (uint32_t)(fdb_t521 * 320u);
          uint32_t fdb_t523 = (uint32_t)(fdb_v33 * 8u);
          uint32_t fdb_t524 = (uint32_t)(fdb_t523 + fdb_v12);
          uint32_t fdb_t525 = (uint32_t)(fdb_v31 + fdb_t524);
          uint32_t fdb_t526 = (uint32_t)(fdb_t522 + fdb_t525);
          uint32_t fdb_t527 = (uint32_t)(4096u + fdb_t526);
          uint32_t fdb_t528 = (uint32_t)(fdb_v15 * 15u);
          if (fdb_t527 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[fdb_t527] = fdb_t528;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t529 = (uint32_t)(fdb_v12 + 1u);
          fdb_v12 = fdb_t529;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t530 = (uint32_t)(fdb_v13 + 1u);
        fdb_v13 = fdb_t530;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t531 = (uint32_t)(fdb_v33 + 1u);
      fdb_v33 = fdb_t531;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (610u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t532 = (uint32_t)fdb_words[610u];
    uint32_t fdb_t533 = (uint32_t)(fdb_t532 + 1u);
    uint32_t fdb_t534 = (uint32_t)(fdb_t533 & 65535u);
    if (610u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[610u] = fdb_t534;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t535 = (uint32_t)(0u & 65535u);
    if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[614u] = fdb_t535;
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, 0u };
  return fdb_result;
}

FdbBlockResult fdb_native_4(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v14 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop0=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t0 = (uint32_t)(fdb_v14 < 600u);
      if (fdb_t0 == 0u) break;
      if (fdb_loop0 == 600u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop0;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (fdb_v14 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[fdb_v14] = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t1 = (uint32_t)(fdb_v14 + 1u);
      fdb_v14 = fdb_t1;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[0u] = 308u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (1u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[1u] = 307u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (2u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[2u] = 306u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t2 = (uint32_t)(3u & 65535u);
    if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[600u] = fdb_t2;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t3 = (uint32_t)(1u & 65535u);
    if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[601u] = fdb_t3;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t4 = (uint32_t)(1u & 65535u);
    if (602u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[602u] = fdb_t4;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t5 = (uint32_t)(1u & 65535u);
    if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[603u] = fdb_t5;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t6 = (uint32_t)(0u & 65535u);
    if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[604u] = fdb_t6;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t7 = (uint32_t)(0u & 65535u);
    if (605u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[605u] = fdb_t7;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t8 = (uint32_t)(4660u & 65535u);
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[606u] = fdb_t8;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t9 = (uint32_t)(312u & 65535u);
    if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[612u] = fdb_t9;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t10 = (uint32_t)(0u & 65535u);
    if (607u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[607u] = fdb_t10;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t11 = (uint32_t)(0u & 65535u);
    if (608u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[608u] = fdb_t11;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t12 = (uint32_t)(0u & 65535u);
    if (609u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[609u] = fdb_t12;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t13 = (uint32_t)(0u & 65535u);
    if (610u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[610u] = fdb_t13;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t14 = (uint32_t)(0u & 65535u);
    if (613u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[613u] = fdb_t14;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t15 = (uint32_t)(0u & 65535u);
    if (615u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[615u] = fdb_t15;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t16 = (uint32_t)(1u & 65535u);
    if (614u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[614u] = fdb_t16;
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, 0u };
  return fdb_result;
}

FdbBlockResult fdb_native_5(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 1u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t0 = (uint32_t)fdb_words[606u];
    uint32_t fdb_t1 = (uint32_t)(fdb_t0 >> (1u & 31u));
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t2 = (uint32_t)fdb_words[606u];
    uint32_t fdb_t3 = (uint32_t)(fdb_t2 & 1u);
    uint32_t fdb_t4 = (uint32_t)(0u - fdb_t3);
    uint32_t fdb_t5 = (uint32_t)(fdb_t4 & 46080u);
    uint32_t fdb_t6 = (uint32_t)(fdb_t1 ^ fdb_t5);
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t7 = (uint32_t)fdb_words[606u];
    uint32_t fdb_t8 = (uint32_t)(fdb_t7 == 0u);
    uint32_t fdb_t9 = (uint32_t)(fdb_t8 * 44257u);
    uint32_t fdb_t10 = (uint32_t)(fdb_t6 | fdb_t9);
    uint32_t fdb_t11 = (uint32_t)(fdb_t10 & 65535u);
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[606u] = fdb_t11;
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 1u-fdb_remaining, 0u };
  return fdb_result;
}

FdbBlockResult fdb_native_6(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 1u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t0 = (uint32_t)fdb_words[606u];
    uint32_t fdb_t1 = (uint32_t)(fdb_t0 * 25173u);
    uint32_t fdb_t2 = (uint32_t)(fdb_t1 + 13849u);
    uint32_t fdb_t3 = (uint32_t)(fdb_t2 & 65535u);
    uint32_t fdb_t4 = (uint32_t)(fdb_t3 & 65535u);
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    fdb_words[606u] = fdb_t4;
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 1u-fdb_remaining, 0u };
  return fdb_result;
}

FdbBlockResult fdb_native_7(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  uint32_t fdb_v37 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t0 = (uint32_t)fdb_words[604u];
    uint32_t fdb_t1 = (uint32_t)(fdb_t0 == 0u);
    if (fdb_t1 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (607u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t2 = (uint32_t)fdb_words[607u];
      uint32_t fdb_t3 = (uint32_t)(fdb_t2 + 1u);
      uint32_t fdb_t4 = (uint32_t)(fdb_t3 & 65535u);
      if (607u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[607u] = fdb_t4;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (602u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t5 = (uint32_t)fdb_words[602u];
      if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t6 = (uint32_t)fdb_words[601u];
      uint32_t fdb_t7 = (uint32_t)(fdb_t6 + 2u);
      uint32_t fdb_t8 = (uint32_t)(fdb_t7 & 3u);
      uint32_t fdb_t9 = (uint32_t)(fdb_t5 != fdb_t8);
      if (fdb_t9 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (602u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t10 = (uint32_t)fdb_words[602u];
        uint32_t fdb_t11 = (uint32_t)(fdb_t10 & 65535u);
        if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[601u] = fdb_t11;
      } else {
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t12 = (uint32_t)fdb_words[601u];
      uint32_t fdb_t13 = (uint32_t)(fdb_t12 & 65535u);
      if (602u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[602u] = fdb_t13;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t14 = (uint32_t)(0u & 65535u);
      if (613u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[613u] = fdb_t14;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t15 = (uint32_t)fdb_words[0u];
      if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t16 = (uint32_t)(fdb_t15 % 30u);
      fdb_v36 = fdb_t16;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t17 = (uint32_t)fdb_words[0u];
      if (30u == 0u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t18 = (uint32_t)(fdb_t17 / 30u);
      fdb_v37 = fdb_t18;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      uint32_t fdb_t19 = (uint32_t)fdb_words[601u];
      uint32_t fdb_t20 = (uint32_t)(fdb_t19 == 0u);
      if (fdb_t20 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t21 = (uint32_t)(fdb_v37 - 1u);
        fdb_v37 = fdb_t21;
      } else {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t22 = (uint32_t)fdb_words[601u];
        uint32_t fdb_t23 = (uint32_t)(fdb_t22 == 1u);
        if (fdb_t23 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t24 = (uint32_t)(fdb_v36 + 1u);
          fdb_v36 = fdb_t24;
        } else {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (601u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t25 = (uint32_t)fdb_words[601u];
          uint32_t fdb_t26 = (uint32_t)(fdb_t25 == 2u);
          if (fdb_t26 != 0u) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t27 = (uint32_t)(fdb_v37 + 1u);
            fdb_v37 = fdb_t27;
          } else {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t28 = (uint32_t)(fdb_v36 - 1u);
            fdb_v36 = fdb_t28;
          }
        }
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t29 = (uint32_t)(fdb_v36 >= 30u);
      uint32_t fdb_t30 = (uint32_t)(fdb_v37 >= 20u);
      uint32_t fdb_t31 = (uint32_t)(fdb_t29 | fdb_t30);
      if (fdb_t31 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t32 = (uint32_t)(1u & 65535u);
        if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[604u] = fdb_t32;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t33 = (uint32_t)(1u & 65535u);
        if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[603u] = fdb_t33;
      } else {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t34 = (uint32_t)(fdb_v37 * 30u);
        uint32_t fdb_t35 = (uint32_t)(fdb_t34 + fdb_v36);
        fdb_v19 = fdb_t35;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t36 = (uint32_t)fdb_words[612u];
        uint32_t fdb_t37 = (uint32_t)(fdb_v19 == fdb_t36);
        fdb_v12 = fdb_t37;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t38 = (uint32_t)fdb_words[600u];
        uint32_t fdb_t39 = (uint32_t)(1u - fdb_v12);
        uint32_t fdb_t40 = (uint32_t)(fdb_t38 - fdb_t39);
        fdb_v18 = fdb_t40;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v15 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v5 = 0u;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        for (uint32_t fdb_loop0=0u;;) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t41 = (uint32_t)(fdb_v15 < fdb_v18);
          uint32_t fdb_t42 = (uint32_t)(fdb_v5 == 0u);
          uint32_t fdb_t43 = (uint32_t)(fdb_t41 & fdb_t42);
          if (fdb_t43 == 0u) break;
          if (fdb_loop0 == 600u) { fdb_failed = 1u; goto fdb_done; }
          ++fdb_loop0;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (fdb_v15 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t44 = (uint32_t)fdb_words[fdb_v15];
          uint32_t fdb_t45 = (uint32_t)(fdb_v19 == fdb_t44);
          if (fdb_t45 != 0u) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            fdb_v5 = 1u;
          } else {
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t46 = (uint32_t)(fdb_v15 + 1u);
          fdb_v15 = fdb_t46;
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (fdb_v5 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t47 = (uint32_t)(1u & 65535u);
          if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[604u] = fdb_t47;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          uint32_t fdb_t48 = (uint32_t)(1u & 65535u);
          if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[603u] = fdb_t48;
        } else {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (fdb_v12 != 0u) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t49 = (uint32_t)fdb_words[600u];
            uint32_t fdb_t50 = (uint32_t)(fdb_t49 + 1u);
            uint32_t fdb_t51 = (uint32_t)(fdb_t50 & 65535u);
            if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            fdb_words[600u] = fdb_t51;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            if (605u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t52 = (uint32_t)fdb_words[605u];
            uint32_t fdb_t53 = (uint32_t)(fdb_t52 + 1u);
            uint32_t fdb_t54 = (uint32_t)(fdb_t53 & 65535u);
            if (605u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            fdb_words[605u] = fdb_t54;
          } else {
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          uint32_t fdb_t55 = (uint32_t)fdb_words[600u];
          uint32_t fdb_t56 = (uint32_t)(fdb_t55 - 1u);
          fdb_v15 = fdb_t56;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          for (uint32_t fdb_loop1=0u;;) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t57 = (uint32_t)(fdb_v15 != 0u);
            if (fdb_t57 == 0u) break;
            if (fdb_loop1 == 599u) { fdb_failed = 1u; goto fdb_done; }
            ++fdb_loop1;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t58 = (uint32_t)(fdb_v15 - 1u);
            if (fdb_t58 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t59 = (uint32_t)fdb_words[fdb_t58];
            if (fdb_v15 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            fdb_words[fdb_v15] = fdb_t59;
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            uint32_t fdb_t60 = (uint32_t)(fdb_v15 - 1u);
            fdb_v15 = fdb_t60;
          }
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (0u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
          fdb_words[0u] = fdb_v19;
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          if (fdb_v12 != 0u) {
            if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
            --fdb_remaining;
            if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
            uint32_t fdb_t61 = (uint32_t)fdb_words[600u];
            uint32_t fdb_t62 = (uint32_t)(fdb_t61 == 600u);
            if (fdb_t62 != 0u) {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t63 = (uint32_t)(2u & 65535u);
              if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              fdb_words[604u] = fdb_t63;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t64 = (uint32_t)(1u & 65535u);
              if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              fdb_words[603u] = fdb_t64;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t65 = (uint32_t)(65535u & 65535u);
              if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              fdb_words[612u] = fdb_t65;
            } else {
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              fdb_v0 = 1u;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              goto fdb_done;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
              uint32_t fdb_t66 = (uint32_t)fdb_words[606u];
              if (600u == 0u) { fdb_failed = 1u; goto fdb_done; }
              uint32_t fdb_t67 = (uint32_t)(fdb_t66 % 600u);
              fdb_v3 = fdb_t67;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              fdb_v11 = 0u;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              fdb_v35 = 0u;
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              for (uint32_t fdb_loop2=0u;;) {
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t68 = (uint32_t)(fdb_v11 == 0u);
                uint32_t fdb_t69 = (uint32_t)(fdb_v35 < 600u);
                uint32_t fdb_t70 = (uint32_t)(fdb_t68 & fdb_t69);
                if (fdb_t70 == 0u) break;
                if (fdb_loop2 == 600u) { fdb_failed = 1u; goto fdb_done; }
                ++fdb_loop2;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                fdb_v21 = 0u;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                fdb_v17 = 0u;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                for (uint32_t fdb_loop3=0u;;) {
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                  uint32_t fdb_t71 = (uint32_t)fdb_words[600u];
                  uint32_t fdb_t72 = (uint32_t)(fdb_v17 < fdb_t71);
                  uint32_t fdb_t73 = (uint32_t)(fdb_v21 == 0u);
                  uint32_t fdb_t74 = (uint32_t)(fdb_t72 & fdb_t73);
                  if (fdb_t74 == 0u) break;
                  if (fdb_loop3 == 600u) { fdb_failed = 1u; goto fdb_done; }
                  ++fdb_loop3;
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  if (fdb_v17 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                  uint32_t fdb_t75 = (uint32_t)fdb_words[fdb_v17];
                  uint32_t fdb_t76 = (uint32_t)(fdb_v3 == fdb_t75);
                  if (fdb_t76 != 0u) {
                    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                    --fdb_remaining;
                    fdb_v21 = 1u;
                  } else {
                  }
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  uint32_t fdb_t77 = (uint32_t)(fdb_v17 + 1u);
                  fdb_v17 = fdb_t77;
                }
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t78 = (uint32_t)(fdb_v21 == 0u);
                if (fdb_t78 != 0u) {
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  uint32_t fdb_t79 = (uint32_t)(fdb_v3 & 65535u);
                  if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                  fdb_words[612u] = fdb_t79;
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  fdb_v11 = 1u;
                } else {
                  if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                  --fdb_remaining;
                  uint32_t fdb_t80 = (uint32_t)(fdb_v3 + 1u);
                  if (600u == 0u) { fdb_failed = 1u; goto fdb_done; }
                  uint32_t fdb_t81 = (uint32_t)(fdb_t80 % 600u);
                  fdb_v3 = fdb_t81;
                }
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t82 = (uint32_t)(fdb_v35 + 1u);
                fdb_v35 = fdb_t82;
              }
              if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
              --fdb_remaining;
              uint32_t fdb_t83 = (uint32_t)(fdb_v11 == 0u);
              if (fdb_t83 != 0u) {
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t84 = (uint32_t)(2u & 65535u);
                if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                fdb_words[604u] = fdb_t84;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t85 = (uint32_t)(1u & 65535u);
                if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                fdb_words[603u] = fdb_t85;
                if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
                --fdb_remaining;
                uint32_t fdb_t86 = (uint32_t)(65535u & 65535u);
                if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
                fdb_words[612u] = fdb_t86;
              } else {
              }
            }
          } else {
          }
        }
      }
    } else {
    }
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, fdb_failed ? 0u : fdb_v0 };
  return fdb_result;
}

FdbBlockResult fdb_native_8(uint32_t *fdb_words) {
  uint32_t fdb_remaining = 4000000u;
  uint32_t fdb_failed = 0u;
  if (!fdb_words) return (FdbBlockResult){1u,0u,0u};
  uint32_t *fdb_saved = (uint32_t *)malloc(70000u * sizeof(uint32_t));
  if (!fdb_saved) return (FdbBlockResult){1u,0u,0u};
  memcpy(fdb_saved,fdb_words,70000u * sizeof(uint32_t));
  uint32_t fdb_v0 = 0u;
  uint32_t fdb_v1 = 0u;
  uint32_t fdb_v2 = 0u;
  uint32_t fdb_v3 = 0u;
  uint32_t fdb_v4 = 0u;
  uint32_t fdb_v5 = 0u;
  uint32_t fdb_v6 = 0u;
  uint32_t fdb_v7 = 0u;
  uint32_t fdb_v8 = 0u;
  uint32_t fdb_v9 = 0u;
  uint32_t fdb_v10 = 0u;
  uint32_t fdb_v11 = 0u;
  uint32_t fdb_v12 = 0u;
  uint32_t fdb_v13 = 0u;
  uint32_t fdb_v14 = 0u;
  uint32_t fdb_v15 = 0u;
  uint32_t fdb_v16 = 0u;
  uint32_t fdb_v17 = 0u;
  uint32_t fdb_v18 = 0u;
  uint32_t fdb_v19 = 0u;
  uint32_t fdb_v20 = 0u;
  uint32_t fdb_v21 = 0u;
  uint32_t fdb_v22 = 0u;
  uint32_t fdb_v23 = 0u;
  uint32_t fdb_v24 = 0u;
  uint32_t fdb_v25 = 0u;
  uint32_t fdb_v26 = 0u;
  uint32_t fdb_v27 = 0u;
  uint32_t fdb_v28 = 0u;
  uint32_t fdb_v29 = 0u;
  uint32_t fdb_v30 = 0u;
  uint32_t fdb_v31 = 0u;
  uint32_t fdb_v32 = 0u;
  uint32_t fdb_v33 = 0u;
  uint32_t fdb_v34 = 0u;
  uint32_t fdb_v35 = 0u;
  uint32_t fdb_v36 = 0u;
  uint32_t fdb_v37 = 0u;
  {
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    if (606u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t0 = (uint32_t)fdb_words[606u];
    if (600u == 0u) { fdb_failed = 1u; goto fdb_done; }
    uint32_t fdb_t1 = (uint32_t)(fdb_t0 % 600u);
    fdb_v3 = fdb_t1;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v11 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    fdb_v35 = 0u;
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    for (uint32_t fdb_loop0=0u;;) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t2 = (uint32_t)(fdb_v11 == 0u);
      uint32_t fdb_t3 = (uint32_t)(fdb_v35 < 600u);
      uint32_t fdb_t4 = (uint32_t)(fdb_t2 & fdb_t3);
      if (fdb_t4 == 0u) break;
      if (fdb_loop0 == 600u) { fdb_failed = 1u; goto fdb_done; }
      ++fdb_loop0;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v21 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      fdb_v17 = 0u;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      for (uint32_t fdb_loop1=0u;;) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (600u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t5 = (uint32_t)fdb_words[600u];
        uint32_t fdb_t6 = (uint32_t)(fdb_v17 < fdb_t5);
        uint32_t fdb_t7 = (uint32_t)(fdb_v21 == 0u);
        uint32_t fdb_t8 = (uint32_t)(fdb_t6 & fdb_t7);
        if (fdb_t8 == 0u) break;
        if (fdb_loop1 == 600u) { fdb_failed = 1u; goto fdb_done; }
        ++fdb_loop1;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        if (fdb_v17 >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t9 = (uint32_t)fdb_words[fdb_v17];
        uint32_t fdb_t10 = (uint32_t)(fdb_v3 == fdb_t9);
        if (fdb_t10 != 0u) {
          if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
          --fdb_remaining;
          fdb_v21 = 1u;
        } else {
        }
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t11 = (uint32_t)(fdb_v17 + 1u);
        fdb_v17 = fdb_t11;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t12 = (uint32_t)(fdb_v21 == 0u);
      if (fdb_t12 != 0u) {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t13 = (uint32_t)(fdb_v3 & 65535u);
        if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
        fdb_words[612u] = fdb_t13;
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        fdb_v11 = 1u;
      } else {
        if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
        --fdb_remaining;
        uint32_t fdb_t14 = (uint32_t)(fdb_v3 + 1u);
        if (600u == 0u) { fdb_failed = 1u; goto fdb_done; }
        uint32_t fdb_t15 = (uint32_t)(fdb_t14 % 600u);
        fdb_v3 = fdb_t15;
      }
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t16 = (uint32_t)(fdb_v35 + 1u);
      fdb_v35 = fdb_t16;
    }
    if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
    --fdb_remaining;
    uint32_t fdb_t17 = (uint32_t)(fdb_v11 == 0u);
    if (fdb_t17 != 0u) {
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t18 = (uint32_t)(2u & 65535u);
      if (604u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[604u] = fdb_t18;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t19 = (uint32_t)(1u & 65535u);
      if (603u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[603u] = fdb_t19;
      if (fdb_remaining == 0u) { fdb_failed = 1u; goto fdb_done; }
      --fdb_remaining;
      uint32_t fdb_t20 = (uint32_t)(65535u & 65535u);
      if (612u >= 70000u) { fdb_failed = 1u; goto fdb_done; }
      fdb_words[612u] = fdb_t20;
    } else {
    }
  }
fdb_done:
  if (fdb_failed) memcpy(fdb_words,fdb_saved,70000u * sizeof(uint32_t));
  free(fdb_saved);
  FdbBlockResult fdb_result = { fdb_failed, 4000000u-fdb_remaining, fdb_failed ? 0u : fdb_v0 };
  return fdb_result;
}

static FdbBlockResult run_function(uint32_t fn,uint32_t *w,const uint32_t *choices,uint32_t depth);
static FdbBlockResult owner_0(uint32_t *w,const uint32_t *choices,uint32_t depth) {
uint32_t phase=0u; uint64_t total=0;
for(uint32_t hops=0;hops<=2u;hops++) { FdbBlockResult r={1u,0u,0u}; switch(phase) {
case 0u:r=fdb_native_0(w);break;
case 1u:r=fdb_native_1(w);break;
case 2u:r=fdb_native_2(w);break;
default:return (FdbBlockResult){1u,0u,0u}; }
if(r.status) { total+=r.steps;return (FdbBlockResult){1u,(uint32_t)(total>4000000u?4000000u:total),0u}; }
if(!r.cut) { total+=r.steps; if(total>4000000u) { fail("Canonical caller budget exhausted"); return (FdbBlockResult){1u,4000000u,0u}; } return (FdbBlockResult){0u,(uint32_t)total,0u}; }
if(r.steps<2u) return (FdbBlockResult){1u,0u,0u}; total+=r.steps-2u;
if(total>4000000u) { fail("Canonical caller budget exhausted"); return (FdbBlockResult){1u,4000000u,0u}; }
uint32_t child=0; switch(r.cut) {
case 1u:child=4u;phase=1u;break;
case 2u:child=4u;phase=2u;break;
default:return (FdbBlockResult){1u,0u,0u}; }
FdbBlockResult c=run_function(child,w,choices,depth+1u); total+=c.steps; if(c.status) return (FdbBlockResult){1u,(uint32_t)(total>4000000u?4000000u:total),0u};
if(total>4000000u) { fail("Canonical caller budget exhausted"); return (FdbBlockResult){1u,4000000u,0u}; }
} return (FdbBlockResult){1u,0u,0u}; }
static FdbBlockResult owner_4(uint32_t *w,const uint32_t *choices,uint32_t depth) {
uint32_t phase=0u; uint64_t total=0;
for(uint32_t hops=0;hops<=1u;hops++) { FdbBlockResult r={1u,0u,0u}; switch(phase) {
case 0u:r=fdb_native_7(w);break;
case 1u:r=fdb_native_8(w);break;
default:return (FdbBlockResult){1u,0u,0u}; }
if(r.status) { total+=r.steps;return (FdbBlockResult){1u,(uint32_t)(total>4000000u?4000000u:total),0u}; }
if(!r.cut) { total+=r.steps; if(total>4000000u) { fail("Canonical caller budget exhausted"); return (FdbBlockResult){1u,4000000u,0u}; } return (FdbBlockResult){0u,(uint32_t)total,0u}; }
if(r.steps<2u) return (FdbBlockResult){1u,0u,0u}; total+=r.steps-2u;
if(total>4000000u) { fail("Canonical caller budget exhausted"); return (FdbBlockResult){1u,4000000u,0u}; }
uint32_t child=0; switch(r.cut) {
case 1u:child=3u;phase=1u;break;
default:return (FdbBlockResult){1u,0u,0u}; }
FdbBlockResult c=run_function(child,w,choices,depth+1u); total+=c.steps; if(c.status) return (FdbBlockResult){1u,(uint32_t)(total>4000000u?4000000u:total),0u};
if(total>4000000u) { fail("Canonical caller budget exhausted"); return (FdbBlockResult){1u,4000000u,0u}; }
} return (FdbBlockResult){1u,0u,0u}; }
static FdbBlockResult run_function(uint32_t fn,uint32_t *w,const uint32_t *choices,uint32_t depth) {
if(depth>=16u || fn>=FDB_FUNCTIONS) return (FdbBlockResult){1u,0u,0u};
if(g_calls[fn]==UINT64_MAX) return (FdbBlockResult){1u,0u,0u}; ++g_calls[fn];
uint32_t *before=(uint32_t*)malloc(FDB_WORDS*sizeof(uint32_t)); if(!before) return (FdbBlockResult){1u,0u,0u}; memcpy(before,w,FDB_WORDS*sizeof(uint32_t));
FdbBlockResult r={1u,0u,0u}; switch(fn) {
case 0u:
r=owner_0(w,choices,depth);
if(!r.status) for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,outputs_0,1u) && w[i]!=before[i]) { r.status=1u; fail("Kernel wrote outside declared output"); break; }
break;
case 1u:
r=fdb_native_3(w);
if(!r.status) for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,outputs_1,4u) && w[i]!=before[i]) { r.status=1u; fail("Kernel wrote outside declared output"); break; }
break;
case 2u:
r=fdb_native_4(w);
if(!r.status) for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,outputs_2,1u) && w[i]!=before[i]) { r.status=1u; fail("Kernel wrote outside declared output"); break; }
break;
case 3u:
switch(choices[0]) {
case 0u: if(g_region_calls_0[0]==UINT64_MAX) break; ++g_region_calls_0[0]; r=fdb_native_5(w); break;
case 1u: if(g_region_calls_0[1]==UINT64_MAX) break; ++g_region_calls_0[1]; r=fdb_native_6(w); break;
default:break; }
if(!r.status && (r.steps!=1u || w[606]<0u || w[606]>65535u)) { r.status=1u; fail("Region output domain refused"); }
if(!r.status) for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,outputs_3,1u) && w[i]!=before[i]) { r.status=1u; fail("Kernel wrote outside declared output"); break; }
break;
case 4u:
r=owner_4(w,choices,depth);
if(!r.status) for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,outputs_4,1u) && w[i]!=before[i]) { r.status=1u; fail("Kernel wrote outside declared output"); break; }
break;
default:break; } free(before); return r; }
size_t fdb_word_count(void) { return FDB_WORDS; }
const uint32_t *fdb_words(void) { return fdb_owner_thread()&&!g_closed?g_words:NULL; }
const char *fdb_last_error(void) { return g_error; }
const char *fdb_config_sha256(void) { return "de88dfc2e117068d60060f9105220b30794ef68957aa081abf2ebe6458f433ff"; }
int fdb_closed(void) { return !fdb_owner_thread() || g_closed; }
uint64_t fdb_revision(void) { return fdb_owner_thread()?g_revision:0; }
uint32_t fdb_last_steps(void) { return fdb_owner_thread()?g_last_steps:0; }
uint64_t fdb_invocation_count(size_t fn) { return fdb_owner_thread()&&fn<FDB_FUNCTIONS?g_calls[fn]:0; }
int fdb_function_index(const char *name) { if(!name) return -1; for(int i=0;i<FDB_FUNCTIONS;i++) if(!strcmp(name,g_names[i])) return i; return -1; }
int fdb_copy_words(uint32_t *out,size_t n) { if(admit()) return 1; if(!out || n!=FDB_WORDS) return fail("Snapshot length differs"); memmove(out,g_words,sizeof(g_words)); return 0; }
int fdb_selected_region(size_t slot) { if(!fdb_owner_thread() || g_closed) return -1; switch(slot) {
case 0:return (int)g_choice_0;
default:return -1; } }
uint64_t fdb_region_invocation_count(size_t slot,size_t variant) { if(!fdb_owner_thread()) return 0; switch(slot) {
case 0:return variant<2u?g_region_calls_0[variant]:0;
default:return 0; } }
int fdb_select_region(size_t slot,size_t variant) { if(admit()) return 1; if(g_epoch==UINT64_MAX) return fail("Epoch exhausted"); switch(slot) {
case 0:if(variant>=2u) return fail("Unknown region variant"); g_choice_0=(uint32_t)variant;break;
default:return fail("Unknown region"); } ++g_epoch;g_error="";return 0; }
int fdb_replace_words(const uint32_t *w,size_t n) { if(admit()) return 1; if(!w || n!=FDB_WORDS) return fail("Replacement length differs"); if(g_revision==UINT64_MAX || g_epoch==UINT64_MAX) return fail("Revision exhausted"); if(validate(w)) return 1;
for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,replace_ranges,2u) && w[i]!=g_words[i]) return fail("Replacement touched immutable input");
memmove(g_words,w,sizeof(g_words));++g_revision;++g_epoch;g_error="";return 0; }
int fdb_call(size_t fn,const uint32_t *indices,const uint32_t *values,size_t count,int render) {
if(admit()) return 1;g_error="";if(fn>=FDB_FUNCTIONS || count>FDB_WORDS || (count&&(!indices||!values)) || (render!=0&&render!=1)) return fail("Invalid native call");
if(g_revision==UINT64_MAX) return fail("Revision exhausted");
for(size_t i=0;i<count;i++) { int allowed=0; for(size_t j=0;j<sizeof(input_indices)/sizeof(input_indices[0]);j++) if(indices[i]==input_indices[j]) allowed=1; if(!allowed) return fail("Invalid input patch"); for(size_t j=0;j<i;j++) if(indices[j]==indices[i]) return fail("Duplicate input patch"); }
uint32_t *w=(uint32_t*)malloc(sizeof(g_words));if(!w) return fail("Allocation refused");memcpy(w,g_words,sizeof(g_words));for(size_t i=0;i<count;i++) w[indices[i]]=values[i];
uint32_t choices[1]={g_choice_0};uint64_t epoch=g_epoch;g_busy=1;
FdbBlockResult r=run_function((uint32_t)fn,w,choices,0u);g_last_steps=r.steps;
int failed=(int)r.status;if(!failed) failed=validate(w);
if(!failed && render && fn!=1u && w[614]!=0u) { r=run_function(1u,w,choices,0u);failed=(int)r.status; if(!failed) failed=validate(w); }
if(epoch!=g_epoch || g_closed) failed=fail("Stale operation");
if(!failed) { for(size_t i=0;i<2u;i++) memcpy(g_words+commit_ranges[i].start,w+commit_ranges[i].start,commit_ranges[i].count*sizeof(uint32_t)); ++g_revision; }
free(w);g_busy=0;if(failed && !*g_error) fail("Native block refused");return failed?1:0; }
int fdb_dispatch(const uint32_t *i,const uint32_t *v,size_t n,int render) { return fdb_call(0u,i,v,n,render); }
int fdb_initialize(uint32_t clock) { uint32_t index=636u;return fdb_call(2u,&index,&clock,1u,1); }
void fdb_close(void) { if(!fdb_owner_thread() || g_busy || g_closed) return;g_closed=1;memset(g_words,0,sizeof(g_words)); }
