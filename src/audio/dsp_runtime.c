/*
 * MCPX DSP emulator
 *
 * Copyright (c) 2015 espes
 * Copyright (c) 2020-2025 Matt Borgerson
 *
 * Adapted from Hatari DSP M56001 emulation
 * (C) 2001-2008 ARAnyM developer team
 * Adaption to Hatari (C) 2008 by Thomas Huth
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

#include "qemu/osdep.h"
#include "scrap_dsp_state.h"

static uint32_t dma_read(void *core, int space, uint32_t address)
{ return dsp56k_read_memory(core,space,address); }
static void dma_write(void *core, int space, uint32_t address, uint32_t value)
{ dsp56k_write_memory(core,space,address,value); }
static uint32_t read_peripheral(dsp_core_t *core, uint32_t address)
{
    DSPState *dsp=core->opaque;
    switch(address) {
    case 0xFFFFB3: return 0;
    case 0xFFFFC5: return dsp->interrupts | (dsp->dma.eol ? 0x80 : 0);
    case 0xFFFFD4: return dsp_dma_read(&dsp->dma,DMA_NEXT_BLOCK);
    case 0xFFFFD5: return dsp_dma_read(&dsp->dma,DMA_START_BLOCK);
    case 0xFFFFD6: return dsp_dma_read(&dsp->dma,DMA_CONTROL);
    case 0xFFFFD7: return dsp_dma_read(&dsp->dma,DMA_CONFIGURATION);
    default: fprintf(stderr,"[DSP] unsupported peripheral read %06X\n",address); abort();
    }
}
static void write_peripheral(dsp_core_t *core, uint32_t address, uint32_t value)
{
    DSPState *dsp=core->opaque;
    switch(address) {
    case 0xFFFFB0:
    case 0xFFFFB1:
    case 0xFFFFB2:
        /* The pinned xemu backend does not advance this timing peripheral.
         * Retain the programmed value and expose the timing limitation. */
        core->periph[address&0x7F]=value&0xFFFFFF;
        {
            static unsigned shown;
            if(shown++<6) fprintf(stderr,"[DSP] timing register %06X=%06X latched; cycle-accurate timer unsupported\n",address,value);
        }
        break;
    case 0xFFFFC4: if(value&1) core->is_idle=true; break;
    case 0xFFFFC5: dsp->interrupts &= ~value; if(value&0x80) dsp->dma.eol=false; break;
    case 0xFFFFD4: dsp_dma_write(&dsp->dma,DMA_NEXT_BLOCK,value); break;
    case 0xFFFFD5: dsp_dma_write(&dsp->dma,DMA_START_BLOCK,value); break;
    case 0xFFFFD6: dsp_dma_write(&dsp->dma,DMA_CONTROL,value); break;
    case 0xFFFFD7: dsp_dma_write(&dsp->dma,DMA_CONFIGURATION,value); break;
    default:
        /* xemu's pinned C backend ignores these writes. Keep a latch and
         * report each unsupported register; a read still fails visibly. */
        {
            static unsigned char reported[128];
            core->periph[address&0x7F]=value&0xFFFFFF;
            if(!reported[address&0x7F]++) fprintf(stderr,
                "[DSP-LIMIT] peripheral %06X write=%06X latched; side effects unsupported (pinned xemu ignores write)\n",
                address,value);
        }
        break;
    }
}
DSPState *dsp_init(void *opaque, dsp_scratch_rw_func scratch, dsp_fifo_rw_func fifo, bool gp)
{
    DSPState *dsp=calloc(1,sizeof(*dsp));
    if(!dsp) abort();
    dsp->is_gp=dsp->core.is_gp=gp; dsp->core.opaque=dsp;
    dsp->core.read_peripheral=read_peripheral; dsp->core.write_peripheral=write_peripheral;
    dsp->dma.rw_opaque=opaque; dsp->dma.scratch_rw=scratch; dsp->dma.fifo_rw=fifo;
    dsp->dma.mem_opaque=&dsp->core; dsp->dma.mem_read=dma_read; dsp->dma.mem_write=dma_write;
    dsp_reset(dsp);
    return dsp;
}
void dsp_destroy(DSPState *dsp) { free(dsp); }
void dsp_reset(DSPState *dsp)
{
    dsp56k_reset_cpu(&dsp->core);
    memset((void *)dsp->core.pram_opcache,0,sizeof(dsp->core.pram_opcache));
    dsp->save_cycles=0;
}
void dsp_run(DSPState *dsp, int cycles)
{
    dsp->save_cycles+=cycles;
    while(dsp->save_cycles>0) {
        dsp56k_execute_instruction(&dsp->core);
        dsp->save_cycles-=dsp->core.instr_cycle;
        dsp->core.cycle_count+=dsp->core.instr_cycle;
        if(dsp->core.is_idle) break;
    }
}
void dsp_bootstrap(DSPState *dsp)
{
    dsp->dma.scratch_rw(dsp->dma.rw_opaque,(uint8_t *)dsp->core.pram,0,0x800*4,false);
    for(unsigned i=0;i<0x800;i++) dsp->core.pram[i]&=0xFFFFFF;
    memset((void *)dsp->core.pram_opcache,0,sizeof(dsp->core.pram_opcache));
    fprintf(stderr,"[DSP] %s bootstrap loaded from guest scratch (PC=%04X)\n",
        dsp->is_gp?"GP":"EP",dsp->core.pc);
}
void dsp_start_frame(DSPState *dsp) { dsp->interrupts |= 2; }
static int memory_space(char space)
{
    switch(space) { case 'X': return DSP_SPACE_X; case 'Y': return DSP_SPACE_Y; case 'P': return DSP_SPACE_P; }
    abort();
}
uint32_t dsp_read_memory(DSPState *dsp,char space,uint32_t address)
{ return dsp56k_read_memory(&dsp->core,memory_space(space),address); }
void dsp_write_memory(DSPState *dsp,char space,uint32_t address,uint32_t value)
{ dsp56k_write_memory(&dsp->core,memory_space(space),address,value); }
bool dsp_get_halt_requested(DSPState *dsp) { return dsp->core.is_idle; }
void dsp_set_halt_requested(DSPState *dsp,bool halt) { dsp->core.is_idle=halt; }
uint32_t dsp_get_cycle_count(DSPState *dsp) { return dsp->core.cycle_count; }
void dsp_set_cycle_count(DSPState *dsp,uint32_t count) { dsp->core.cycle_count=count; }
