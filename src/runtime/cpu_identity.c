/* Original Xbox CPU identity, independent of the host CPU.
 * Model evidence: xemu 711b416840c2a528cb989621b6456a72bd02d768,
 * hw/xbox/xbox.c and target/i386/cpu.c: Pentium III, family 6/model 8/step 10.
 * This bounded model implements the reached CPUID leaf 1 only. */
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>

void recomp_cpuid(uint32_t leaf,uint32_t *a,uint32_t *b,uint32_t *c,uint32_t *d,uint32_t va)
{
    if(leaf!=1) {
        fprintf(stderr,"[CPU] unsupported CPUID leaf=%08X guest=%08X\n",leaf,va);
        recomp_unimpl("cpuid leaf",va);
        abort();
    }
    *a=0x0000068A; *b=0; *c=0; *d=0x0383FBFF;
}
