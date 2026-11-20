/* Synthetic DSP program: bootstrap, peripheral commands, bidirectional DMA,
 * guest-written data, and a program-issued end-of-frame halt. No game bytes. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/audio/scrap_dsp_state.h"
#define CHECK(c) do { if(!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); return 1; } } while(0)
static unsigned char scratch[8192];
static unsigned reads,writes;
static void scratch_rw(void *opaque,uint8_t *data,uint32_t offset,size_t bytes,bool write)
{
    (void)opaque;
    if(offset>sizeof scratch || bytes>sizeof scratch-offset) abort();
    if(write) { memcpy(scratch+offset,data,bytes); ++writes; }
    else { memcpy(data,scratch+offset,bytes); ++reads; }
}
static void fifo_rw(void *opaque,uint8_t *data,unsigned index,size_t bytes,bool write)
{ (void)opaque;(void)data;(void)index;(void)bytes;(void)write; abort(); }
int main(void)
{
    const uint32_t program[]={0x08F494,0x100,0x08F496,1,0x08F484,1};
    const uint32_t payload[]={0x00ABCDEF,0x00123456};
    memcpy(scratch,program,sizeof program);
    memcpy(scratch+0x1000,payload,sizeof payload);
    DSPState *dsp=dsp_init(NULL,scratch_rw,fifo_rw,true);
    dsp_bootstrap(dsp);
    CHECK(reads==1 && dsp_read_memory(dsp,'P',0)==program[0]);
    const uint32_t nodes[]={0x108,0x19E0,2,0x200,0x1000,0,0x1FFF,0,
                           0x4000,0x19E2,2,0x200,0x1100,0,0x1FFF};
    for(unsigned i=0;i<sizeof nodes/sizeof nodes[0];i++) dsp_write_memory(dsp,'X',0x100+i,nodes[i]);
    dsp_set_halt_requested(dsp,false);
    dsp_run(dsp,1000);
    CHECK(dsp_get_halt_requested(dsp) && dsp_get_cycle_count(dsp)>0);
    CHECK(dsp->core.pc==6 && dsp->dma.eol && writes==1 && reads==2);
    CHECK(dsp_read_memory(dsp,'X',0x200)==payload[0] && dsp_read_memory(dsp,'X',0x201)==payload[1]);
    CHECK(!memcmp(scratch+0x1100,payload,sizeof payload));
    CHECK(!(dsp->interrupts&2));
    dsp_start_frame(dsp);
    CHECK(dsp->interrupts&2);
    dsp_destroy(dsp);
    puts("PASS: synthetic DSP executes bootstrap program, peripheral writes, input/output DMA and halt");
    return 0;
}
