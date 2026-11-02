/* Authored arithmetic specification for batch validation of generated code.
 * This is NOT a 6502 CPU emulator or a console/device oracle.
 * Overflow is specified using signed mathematical bounds, separately from the
 * lifter's sign-bit construction. Only declared outputs are compared.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef int (*run_fn)(const uint32_t *,size_t,uint32_t *,size_t);

uint32_t check_arithmetic(run_fn run, uint32_t operation, const uint32_t *indices,
                          uint32_t count, uint32_t *failure) {
    if (!run || !indices || !failure || count>256u || operation>2u) return 0;
    uint32_t input[256],output[256];
    uint32_t done=0;
    for (uint32_t a=0;a<256u;a++) for(uint32_t b=0;b<256u;b++)
    for(uint32_t mode=0;mode<2u;mode++) {
        memset(input,0,sizeof(input));
        input[indices[0]]=a; input[indices[1]]=b;
        input[indices[2]]=mode; input[indices[5]]=mode;
        input[indices[6]]=0xA5; input[indices[7]]=0x5A;
        int mathematical = operation==0u ? (int)a+(int)b+(int)mode :
                           operation==1u ? (int)a-(int)b-(int)(1u-mode) :
                                           (int)a-(int)b;
        uint32_t result=(uint32_t)mathematical & 255u;
        int sa=a<128u?(int)a:(int)a-256;
        int sb=b<128u?(int)b:(int)b-256;
        int signed_math=operation==0u?sa+sb+(int)mode:sa-sb-(int)(1u-mode);
        uint32_t carry=operation==0u?(mathematical>255):(mathematical>=0);
        uint32_t overflow=operation==2u?mode:(signed_math < -128 || signed_math > 127);
        uint32_t expected[]={operation==2u?a:result,b,carry,result==0u,
                             result>=128u,overflow,0xA5,0x5A};
        int status=run(input,count,output,count);
        if(status){failure[0]=a;failure[1]=b;failure[2]=mode;failure[3]=99;failure[4]=(uint32_t)status;return done;}
        for(uint32_t field=0;field<8u;field++) {
            if(output[indices[field]]!=expected[field]) {
                failure[0]=a;failure[1]=b;failure[2]=mode;failure[3]=field;
                failure[4]=output[indices[field]];failure[5]=expected[field];return done;
            }
        }
        done++;
    }
    return done;
}
