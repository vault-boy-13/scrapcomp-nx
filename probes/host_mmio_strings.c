/* Independent byte/word/dword REP fixtures with inaccessible MMIO backing. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
RECOMP_TLS int g_df;
ptrdiff_t g_xbox_mem_offset;
volatile int g_gil_contended;
static unsigned char io[1024],expected_io[1024],expected_ram[1024];
static unsigned reads,writes,checks;
void recomp_preempt(void) { abort(); }
uint32_t xbox_mmio_read(uint32_t address,unsigned size)
{
    uint32_t value=0;
    if(address<0xFD100000 || address+size>0xFD100400) abort();
    memcpy(&value,io+address-0xFD100000,size); ++reads; return value;
}
void xbox_mmio_write(uint32_t address,uint32_t value,unsigned size)
{
    if(address<0xFD100000 || address+size>0xFD100400) abort();
    memcpy(io+address-0xFD100000,&value,size); ++writes;
}
extern void sub_00010000(void),sub_00010100(void),sub_00010200(void);
extern void sub_00010300(void),sub_00010400(void),sub_00010500(void);
static unsigned char *expected(uint32_t address)
{
    if(address>=0xFD100000 && address<0xFD100400) return expected_io+address-0xFD100000;
    if(address>=0x200000 && address<0x200400) return expected_ram+address-0x200000;
    abort();
}
static void check_case(unsigned operation,unsigned width,unsigned count,int backwards,
                       uint32_t source,uint32_t destination,int equal)
{
    unsigned char *ram=(unsigned char *)0x200000;
    for(unsigned i=0;i<1024;i++) { ram[i]=(unsigned char)(i*37+5); io[i]=(unsigned char)(i*19+9); }
    memcpy(expected_ram,ram,1024); memcpy(expected_io,io,1024);
    int32_t step=backwards?-(int32_t)width:(int32_t)width;
    if(backwards && count) { source+=(count-1)*width; destination+=(count-1)*width; }
    uint32_t s=source,d=destination,value=0xA1B2C3D4;
    for(unsigned i=0;i<count;i++) {
        unsigned char temporary[4];
        if(operation<3) memcpy(temporary,expected(s),width);
        else memcpy(temporary,&value,width);
        memcpy(expected(d),temporary,width);
        if(operation<3) s+=step;
        d+=step;
    }
    void (*functions[])(void)={sub_00010000,sub_00010100,sub_00010200,
                               sub_00010300,sub_00010400,sub_00010500};
    g_eax=value; g_ebx=equal?value:value+1; g_esi=source; g_edi=destination;
    g_ecx=count; g_df=backwards; g_esp=0x100000;
    functions[operation]();
    if(memcmp(ram,expected_ram,1024) || memcmp(io,expected_io,1024) ||
       g_esi!=s || g_edi!=d || g_ecx || g_esp!=0x100004 ||
       g_eax!=(equal?value:0xDEADBEEF) || g_ebx!=(equal?value:value+1)) {
        fprintf(stderr,"FAIL op=%u width=%u count=%u df=%d src=%08X dst=%08X eq=%d\n",
            operation,width,count,backwards,source,destination,equal); exit(1);
    }
    ++checks;
}
int main(void)
{
    if(!VirtualAlloc((void *)0x200000,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE) ||
       !VirtualAlloc((void *)0xFD100000,4096,MEM_RESERVE|MEM_COMMIT,PAGE_NOACCESS)) return 2;
    const unsigned widths[]={1,2,4},counts[]={0,1,3,16};
    for(unsigned op=0;op<6;op++) for(unsigned n=0;n<4;n++)
        for(int backwards=0;backwards<2;backwards++) for(int equal=0;equal<2;equal++)
            for(unsigned route=0;route<4;route++) {
                uint32_t src=(route&1)?0xFD100100:0x200100;
                uint32_t dst=(route&2)?0xFD100200:0x200200;
                check_case(op,widths[op%3],counts[n],backwards,src,dst,equal);
            }
    for(unsigned op=0;op<3;op++) for(int delta=-1;delta<=1;delta++)
        for(int backwards=0;backwards<2;backwards++)
            check_case(op,widths[op],16,backwards,0x200100,0x200100+delta*widths[op],1);
    if(!reads || !writes) return 3;
    printf("PASS: %u translated REP cases, MMIO reads=%u writes=%u; flags/GPRs/DF/zero count/overlap\n",
        checks,reads,writes);
    return 0;
}
