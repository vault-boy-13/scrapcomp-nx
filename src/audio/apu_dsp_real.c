/*
 * QEMU MCPX Audio Processing Unit implementation
 *
 * Copyright (c) 2012 espes
 * Copyright (c) 2018-2019 Jannik Vogel
 * Copyright (c) 2019-2025 Matt Borgerson
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, see <http://www.gnu.org/licenses/>.
 */

#include "apu_state.h"
#include "fpconv.h"
#include "debug.h"
/* Standalone adaptation of xemu 711b416840c2a528cb989621b6456a72bd02d768.
 * Physical DMA uses the pinned runtime contiguous-memory resolver. */

static const int16_t ep_silence[256][2] = { 0 };
static uint64_t observed_gp_runs, observed_ep_runs;

/* Optional bounded stage observation. Each record is 16 little-endian u32
 * header words, bin-major 32x32 float input, channel-major 2x32 GP u24 words,
 * then the 256x2 s16 monitor buffer. A monitor buffer is new only when header
 * word 7 (EP FIFO writes) changes; GP observations are new every frame.
 * No guest/DSP data is modified. Disabled unless explicitly requested. */
static struct {
    bool checked;
    FILE *file, *fifo, *dma;
    uint64_t frames, skip, remaining, dma_period;
    uint32_t ep_writes;
} stage_capture;

static void capture_dsp_stages(MCPXAPUState *d,
                              float mixbins[NUM_MIXBINS][NUM_SAMPLES_PER_FRAME])
{
    if (!stage_capture.checked) {
        stage_capture.checked = true;
        const char *spec = getenv("RECOMP_DSP_CAPTURE");
        const char *period = getenv("RECOMP_DSP_DMA_PERIOD");
        unsigned skip, duration;
        char tail;
        if (period) {
            unsigned seconds;
            if (sscanf(period, "%u%c", &seconds, &tail) != 1 || seconds < 5 || seconds > 300) {
                fprintf(stderr, "[DSP-CAPTURE] invalid DMA period\n"); abort();
            }
            stage_capture.dma_period = (uint64_t)seconds * 1500;
        }
        if (spec && sscanf(spec, "%u,%u%c", &skip, &duration, &tail) == 2 &&
            skip <= 600 && duration >= 1 && duration <= 10) {
            stage_capture.skip = (uint64_t)skip * 1500;
            stage_capture.remaining = (uint64_t)duration * 1500;
            stage_capture.file = fopen("dsp-stages.bin", "wb");
            if (!stage_capture.file) { perror("dsp-stages.bin"); abort(); }
            fprintf(stderr, "[DSP-CAPTURE] skip=%u duration=%u seconds; record_bytes=5440\n",
                    skip, duration);
        }
    }
    uint64_t frame = stage_capture.frames++;
    if (stage_capture.dma && stage_capture.dma_period && frame % stage_capture.dma_period == 31 &&
        fflush(stage_capture.dma)) { perror("DSP DMA checkpoint"); abort(); }
    if (!stage_capture.file || frame < stage_capture.skip) return;
    uint32_t header[16] = {0x31505344, 5440, (uint32_t)frame,
        (uint32_t)(frame >> 32), d->ep_frame_div, d->gp.regs[NV_PAPU_GPRST],
        d->ep.regs[NV_PAPU_EPRST], stage_capture.ep_writes,
        dsp_get_cycle_count(d->gp.dsp), dsp_get_cycle_count(d->ep.dsp)};
    uint32_t gp[2][NUM_SAMPLES_PER_FRAME];
    for (unsigned ch = 0; ch < 2; ++ch)
        for (unsigned i = 0; i < NUM_SAMPLES_PER_FRAME; ++i)
            gp[ch][i] = dsp_read_memory(d->gp.dsp, 'X', 0x1400 + ch * 0x20 + i);
    if (fwrite(header, sizeof(header), 1, stage_capture.file) != 1 ||
        fwrite(mixbins, sizeof(float)*NUM_MIXBINS*NUM_SAMPLES_PER_FRAME, 1, stage_capture.file) != 1 ||
        fwrite(gp, sizeof(gp), 1, stage_capture.file) != 1 ||
        fwrite(d->monitor.frame_buf, sizeof(d->monitor.frame_buf), 1, stage_capture.file) != 1) {
        perror("DSP capture write"); abort();
    }
    if (!--stage_capture.remaining) {
        if (fclose(stage_capture.file)) { perror("DSP capture close"); abort(); }
        stage_capture.file = NULL;
        if (stage_capture.fifo && fclose(stage_capture.fifo)) { perror("DSP FIFO close"); abort(); }
        stage_capture.fifo = NULL;
        if (stage_capture.dma && fclose(stage_capture.dma)) { perror("DSP DMA close"); abort(); }
        stage_capture.dma = NULL;
        fprintf(stderr, "[DSP-CAPTURE] completed at frame=%llu\n", (unsigned long long)frame);
    }
}

static void capture_dsp_dma(bool gp, bool dir, uint32_t addr, const uint8_t *ptr, size_t len)
{
    bool window = stage_capture.file && stage_capture.frames >= stage_capture.skip &&
                  stage_capture.frames < stage_capture.skip + 32;
    bool periodic = stage_capture.dma_period && stage_capture.frames < 900*1500 &&
                    stage_capture.frames % stage_capture.dma_period < 32;
    if (!window && !periodic) return;
    if (len > 65536) { fprintf(stderr, "[DSP-CAPTURE] DMA record too large\n"); abort(); }
    if (!stage_capture.dma) {
        stage_capture.dma = fopen("dsp-dma.bin", "ab");
        if (!stage_capture.dma) { perror("dsp-dma.bin"); abort(); }
    }
    uint32_t header[6] = {0x31414D44, (uint32_t)stage_capture.frames, gp, dir, addr, (uint32_t)len};
    if (fwrite(header, sizeof(header), 1, stage_capture.dma) != 1 ||
        fwrite(ptr, len, 1, stage_capture.dma) != 1) { perror("DSP DMA write"); abort(); }
}

void mcpx_apu_update_dsp_preference(MCPXAPUState *d)
{
    d->monitor.point = MCPX_APU_DEBUG_MON_GP_OR_EP;
    d->gp.realtime = d->ep.realtime = true;
}

static void scatter_gather_rw(MCPXAPUState *d, hwaddr sge_base,
                              unsigned int max_sge, uint8_t *ptr, uint32_t addr,
                              size_t len, bool dir)
{
    unsigned int page_entry = addr / TARGET_PAGE_SIZE;
    unsigned int offset_in_page = addr % TARGET_PAGE_SIZE;
    unsigned int bytes_to_copy = TARGET_PAGE_SIZE - offset_in_page;

    while (len > 0) {
        assert(page_entry <= max_sge);

        uint32_t prd_address = ldl_le_phys(address_space_memory,
                                           sge_base + page_entry * 8 + 0);
        // uint32_t prd_control = ldl_le_phys(address_space_memory,
        //                                     sge_base + page_entry * 8 + 4);

        hwaddr paddr = prd_address + offset_in_page;

        if (bytes_to_copy > len) {
            bytes_to_copy = len;
        }

        assert(paddr + bytes_to_copy <= 0x04000000u);

        /* Optional bring-up watch: report the DMA provenance of a watched
         * guest dword before a device overwrites it. No data is changed. */
        static bool watch_checked;
        static uint32_t watch_va;
        static unsigned watch_reports;
        if (!watch_checked) {
            const char *spec = getenv("RECOMP_WATCH");
            if (spec && *spec != '[') watch_va = (uint32_t)strtoul(spec, NULL, 0);
            watch_checked = true;
        }
        if (dir && watch_va && watch_reports < 4) {
          uint64_t target_va = (uint64_t)(apu_phys(paddr) - g_apu_ram_ptr);
          if (target_va <= watch_va && target_va + bytes_to_copy > watch_va) {
            ++watch_reports;
            fprintf(stderr, "[DSP-DMA-WATCH] sge=%08X max=%u entry=%u scratch=%08X "
                    "prd=%08X phys=%08X va=%08llX bytes=%zu\n",
                    (uint32_t)sge_base, max_sge, page_entry, addr,
                    prd_address, (uint32_t)paddr, (unsigned long long)target_va, bytes_to_copy);
            for (unsigned j = page_entry > 2 ? page_entry - 2 : 0;
                    j <= max_sge && j <= page_entry + 2; ++j) {
                uint32_t prd = ldl_le_phys(address_space_memory, sge_base + j * 8);
                fprintf(stderr, "[DSP-DMA-SGE] %u prd=%08X resolved=%08llX\n", j,
                        prd, (unsigned long long)(apu_phys(prd) - g_apu_ram_ptr));
            }
          }
        }

        if (dir) {
            memcpy(apu_phys(paddr), ptr, bytes_to_copy);
        } else {
            memcpy(ptr, apu_phys(paddr), bytes_to_copy);
        }

        ptr += bytes_to_copy;
        len -= bytes_to_copy;

        /* After the first iteration, we are page aligned */
        page_entry += 1;
        bytes_to_copy = TARGET_PAGE_SIZE;
        offset_in_page = 0;
    }
}

static void gp_scratch_rw(void *opaque, uint8_t *ptr, uint32_t addr, size_t len,
                          bool dir)
{
    MCPXAPUState *d = opaque;
    // fprintf(stderr, "GP %s scratch 0x%x bytes (0x%x words) at %x (0x%x words)\n", dir ? "writing to" : "reading from", len, len/4, addr, addr/4);
    scatter_gather_rw(d, d->regs[NV_PAPU_GPSADDR], d->regs[NV_PAPU_GPSMAXSGE],
                      ptr, addr, len, dir);
    capture_dsp_dma(true, dir, addr, ptr, len);
    if (dir && len == 128 && addr >= 0x8000 && addr < 0x8800 &&
        observed_gp_runs < 20 && getenv("RECOMP_DSP_CAPTURE"))
        fprintf(stderr, "[DSP-PHASE] GP write runs=%llu ep_runs=%llu ep_div=%d addr=%08X\n",
                (unsigned long long)observed_gp_runs, (unsigned long long)observed_ep_runs,
                d->ep_frame_div, addr);
}

static void ep_scratch_rw(void *opaque, uint8_t *ptr, uint32_t addr, size_t len,
                          bool dir)
{
    MCPXAPUState *d = opaque;
    // fprintf(stderr, "EP %s scratch 0x%x bytes (0x%x words) at %x (0x%x words)\n", dir ? "writing to" : "reading from", len, len/4, addr, addr/4);
    scatter_gather_rw(d, d->regs[NV_PAPU_EPSADDR], d->regs[NV_PAPU_EPSMAXSGE],
                      ptr, addr, len, dir);
    capture_dsp_dma(false, dir, addr, ptr, len);
    if (!dir && len == 1024 && addr >= 0x10000 && addr < 0x10800 &&
        observed_ep_runs < 5 && getenv("RECOMP_DSP_CAPTURE"))
        fprintf(stderr, "[DSP-PHASE] EP read gp_runs=%llu ep_runs=%llu ep_div=%d addr=%08X\n",
                (unsigned long long)observed_gp_runs, (unsigned long long)observed_ep_runs,
                d->ep_frame_div, addr);
}

static uint32_t circular_scatter_gather_rw(MCPXAPUState *d, hwaddr sge_base,
                                           unsigned int max_sge, uint8_t *ptr,
                                           uint32_t base, uint32_t end,
                                           uint32_t cur, size_t len, bool dir)
{
    while (len > 0) {
        unsigned int bytes_to_copy = end - cur;

        if (bytes_to_copy > len) {
            bytes_to_copy = len;
        }

        DPRINTF("circular scatter gather %s in range 0x%x - 0x%x at 0x%x of "
                "length 0x%x / 0x%zx bytes\n",
                dir ? "write" : "read", base, end, cur, bytes_to_copy, len);

        assert((cur >= base) && ((cur + bytes_to_copy) <= end));
        scatter_gather_rw(d, sge_base, max_sge, ptr, cur, bytes_to_copy, dir);

        ptr += bytes_to_copy;
        len -= bytes_to_copy;

        /* After the first iteration we might have to wrap */
        cur += bytes_to_copy;
        if (cur >= end) {
            assert(cur == end);
            cur = base;
        }
    }

    return cur;
}

static void gp_fifo_rw(void *opaque, uint8_t *ptr, unsigned int index,
                       size_t len, bool dir)
{
    if (dir && stage_capture.file && stage_capture.frames >= stage_capture.skip) {
        if (!stage_capture.fifo) {
            stage_capture.fifo = fopen("dsp-gp-fifo.bin", "wb");
            if (!stage_capture.fifo) { perror("dsp-gp-fifo.bin"); abort(); }
        }
        uint32_t header[4] = {0x31465047, (uint32_t)stage_capture.frames, index, (uint32_t)len};
        if (fwrite(header, sizeof(header), 1, stage_capture.fifo) != 1 ||
            fwrite(ptr, len, 1, stage_capture.fifo) != 1) {
            perror("DSP FIFO write"); abort();
        }
    }
    MCPXAPUState *d = opaque;
    uint32_t base;
    uint32_t end;
    hwaddr cur_reg;
    if (dir) {
        assert(index < GP_OUTPUT_FIFO_COUNT);
        base = GET_MASK(d->regs[NV_PAPU_GPOFBASE0 + 0x10 * index],
                        NV_PAPU_GPOFBASE0_VALUE);
        end = GET_MASK(d->regs[NV_PAPU_GPOFEND0 + 0x10 * index],
                       NV_PAPU_GPOFEND0_VALUE);
        cur_reg = NV_PAPU_GPOFCUR0 + 0x10 * index;
    } else {
        assert(index < GP_INPUT_FIFO_COUNT);
        base = GET_MASK(d->regs[NV_PAPU_GPIFBASE0 + 0x10 * index],
                        NV_PAPU_GPOFBASE0_VALUE);
        end = GET_MASK(d->regs[NV_PAPU_GPIFEND0 + 0x10 * index],
                       NV_PAPU_GPOFEND0_VALUE);
        cur_reg = NV_PAPU_GPIFCUR0 + 0x10 * index;
    }

    uint32_t cur = GET_MASK(d->regs[cur_reg], NV_PAPU_GPOFCUR0_VALUE);

    // fprintf(stderr, "GP %s fifo #%d, base = %x, end = %x, cur = %x, len = %x\n",
    //     dir ? "writing to" : "reading from", index,
    //     base, end, cur, len);

    /* DSP hangs if current >= end; but forces current >= base */
    assert(cur < end);
    if (cur < base) {
        cur = base;
    }

    cur = circular_scatter_gather_rw(d,
        d->regs[NV_PAPU_GPFADDR], d->regs[NV_PAPU_GPFMAXSGE],
        ptr, base, end, cur, len, dir);

    SET_MASK(d->regs[cur_reg], NV_PAPU_GPOFCUR0_VALUE, cur);
}

static bool ep_sink_samples(MCPXAPUState *d, uint8_t *ptr, size_t len)
{
    ++stage_capture.ep_writes;
    if (d->monitor.point == MCPX_APU_DEBUG_MON_AC97) {
        return false;
    } else if ((d->monitor.point == MCPX_APU_DEBUG_MON_EP) ||
        (d->monitor.point == MCPX_APU_DEBUG_MON_GP_OR_EP)) {
        assert(len == sizeof(d->monitor.frame_buf));
        memcpy(d->monitor.frame_buf, ptr, len);
    }

    return true;
}

static void ep_fifo_rw(void *opaque, uint8_t *ptr, unsigned int index,
                       size_t len, bool dir)
{
    MCPXAPUState *d = opaque;
    uint32_t base;
    uint32_t end;
    hwaddr cur_reg;
    if (dir) {
        assert(index < EP_OUTPUT_FIFO_COUNT);
        base = GET_MASK(d->regs[NV_PAPU_EPOFBASE0 + 0x10 * index],
                        NV_PAPU_GPOFBASE0_VALUE);
        end = GET_MASK(d->regs[NV_PAPU_EPOFEND0 + 0x10 * index],
                       NV_PAPU_GPOFEND0_VALUE);
        cur_reg = NV_PAPU_EPOFCUR0 + 0x10 * index;
    } else {
        assert(index < EP_INPUT_FIFO_COUNT);
        base = GET_MASK(d->regs[NV_PAPU_EPIFBASE0 + 0x10 * index],
                        NV_PAPU_GPOFBASE0_VALUE);
        end = GET_MASK(d->regs[NV_PAPU_EPIFEND0 + 0x10 * index],
                       NV_PAPU_GPOFEND0_VALUE);
        cur_reg = NV_PAPU_EPIFCUR0 + 0x10 * index;
    }

    uint32_t cur = GET_MASK(d->regs[cur_reg], NV_PAPU_GPOFCUR0_VALUE);

    // fprintf(stderr, "EP %s fifo #%d, base = %x, end = %x, cur = %x, len = %x\n",
    //     dir ? "writing to" : "reading from", index,
    //     base, end, cur, len);

    if (dir && index == 0) {
        bool did_sink = ep_sink_samples(d, ptr, len);
        if (did_sink) {
            /* Since we are sinking, push silence out */
            assert(len <= sizeof(ep_silence));
            ptr = (uint8_t*)ep_silence;
        }
    }

    /* DSP hangs if current >= end; but forces current >= base */
    if (cur >= end) {
        cur = cur % (end - base);
    }
    if (cur < base) {
        cur = base;
    }

    cur = circular_scatter_gather_rw(d,
        d->regs[NV_PAPU_EPFADDR], d->regs[NV_PAPU_EPFMAXSGE],
        ptr, base, end, cur, len, dir);

    SET_MASK(d->regs[cur_reg], NV_PAPU_GPOFCUR0_VALUE, cur);
}

static void proc_rst_write(DSPState *dsp, uint32_t oldval, uint32_t val)
{
    if (!(val & NV_PAPU_GPRST_GPRST) || !(val & NV_PAPU_GPRST_GPDSPRST)) {
        dsp_reset(dsp);
    } else if (
        (!(oldval & NV_PAPU_GPRST_GPRST) || !(oldval & NV_PAPU_GPRST_GPDSPRST))
        && ((val & NV_PAPU_GPRST_GPRST) && (val & NV_PAPU_GPRST_GPDSPRST))) {
        dsp_bootstrap(dsp);
    }
}

/* Host-portable GP/EP memory windows and reset/bootstrap control. */
static int dsp_window(bool gp, uint32_t address, char *space, uint32_t *word)
{
    if (address < (gp ? 0x1000u : 0xC00u)*4) {
        *space='X'; *word=address/4; return 1;
    }
    if(gp && address >= NV_PAPU_GPMIXBUF && address < NV_PAPU_GPMIXBUF+0x400*4) {
        *space='X'; *word=GP_DSP_MIXBUF_BASE+(address-NV_PAPU_GPMIXBUF)/4; return 1;
    }
    if(address >= NV_PAPU_GPYMEM && address < NV_PAPU_GPYMEM+(gp ? 0x800u : 0x100u)*4) {
        *space='Y'; *word=(address-NV_PAPU_GPYMEM)/4; return 1;
    }
    if(address >= NV_PAPU_GPPMEM && address < NV_PAPU_GPPMEM+0x1000*4) {
        *space='P'; *word=(address-NV_PAPU_GPPMEM)/4; return 1;
    }
    return 0;
}
static uint64_t processor_read(MCPXAPUState *d, bool gp, uint32_t address, unsigned size)
{
    assert(size==4 && !(address&3) && address<0x10000);
    DSPState *dsp=gp ? d->gp.dsp : d->ep.dsp;
    uint32_t *regs=gp ? d->gp.regs : d->ep.regs;
    char space; uint32_t word, value;
    mcpx_apu_lock_guest(d);
    value=dsp_window(gp,address,&space,&word) ? dsp_read_memory(dsp,space,word) : regs[address];
    qemu_mutex_unlock(&d->lock);
    return value;
}
static void processor_write(MCPXAPUState *d, bool gp, uint32_t address, uint32_t value, unsigned size)
{
    assert(size==4 && !(address&3) && address<0x10000);
    DSPState *dsp=gp ? d->gp.dsp : d->ep.dsp;
    uint32_t *regs=gp ? d->gp.regs : d->ep.regs;
    char space; uint32_t word;
    mcpx_apu_lock_guest(d);
    if(dsp_window(gp,address,&space,&word)) dsp_write_memory(dsp,space,word,value);
    else {
        if(address==NV_PAPU_GPRST) {
            if (getenv("RECOMP_DSP_CAPTURE"))
                fprintf(stderr,"[DSP-PHASE] %s reset %X->%X gp_runs=%llu ep_runs=%llu ep_div=%d\n",
                        gp?"GP":"EP",regs[address],value,(unsigned long long)observed_gp_runs,
                        (unsigned long long)observed_ep_runs,d->ep_frame_div);
            proc_rst_write(dsp,regs[address],value);
            if ((value & 3) == 3 && (regs[address] & 3) != 3) {
                if (gp) observed_gp_runs=0; else observed_ep_runs=0;
            }
            if(!gp) d->ep_frame_div=0;
        }
        regs[address]=value;
    }
    qemu_mutex_unlock(&d->lock);
}
uint64_t scrap_gp_read(MCPXAPUState *d,uint32_t a,unsigned s) { return processor_read(d,true,a,s); }
uint64_t scrap_ep_read(MCPXAPUState *d,uint32_t a,unsigned s) { return processor_read(d,false,a,s); }
void scrap_gp_write(MCPXAPUState *d,uint32_t a,uint32_t v,unsigned s) { processor_write(d,true,a,v,s); }
void scrap_ep_write(MCPXAPUState *d,uint32_t a,uint32_t v,unsigned s) { processor_write(d,false,a,v,s); }

void mcpx_apu_dsp_frame(MCPXAPUState *d, float mixbins[NUM_MIXBINS][NUM_SAMPLES_PER_FRAME])
{
    /* Write VP results to the GP DSP MIXBUF */
    for (int mixbin = 0; mixbin < NUM_MIXBINS; mixbin++) {
        uint32_t base = GP_DSP_MIXBUF_BASE + mixbin * NUM_SAMPLES_PER_FRAME;
        for (int sample = 0; sample < NUM_SAMPLES_PER_FRAME; sample++) {
            dsp_write_memory(d->gp.dsp, 'X', base + sample,
                             float_to_24b(mixbins[mixbin][sample]));
        }
    }

    bool ep_enabled = (d->ep.regs[NV_PAPU_EPRST] & NV_PAPU_GPRST_GPRST) &&
                      (d->ep.regs[NV_PAPU_EPRST] & NV_PAPU_GPRST_GPDSPRST);

    /* Run GP */
    if ((d->gp.regs[NV_PAPU_GPRST] & NV_PAPU_GPRST_GPRST) &&
        (d->gp.regs[NV_PAPU_GPRST] & NV_PAPU_GPRST_GPDSPRST)) {
        dsp_start_frame(d->gp.dsp);
        dsp_set_halt_requested(d->gp.dsp, false);
        dsp_set_cycle_count(d->gp.dsp, 0);
        do {
            dsp_run(d->gp.dsp, 1000);
            if(dsp_get_cycle_count(d->gp.dsp)>1000000) {
                fprintf(stderr,"[DSP] GP frame cycle limit PC=%04X\n",d->gp.dsp->core.pc); abort();
            }
        } while (!dsp_get_halt_requested(d->gp.dsp) && d->gp.realtime);
        g_dbg.gp.cycles = dsp_get_cycle_count(d->gp.dsp);
        ++observed_gp_runs;

        if ((d->monitor.point == MCPX_APU_DEBUG_MON_GP) ||
            (d->monitor.point == MCPX_APU_DEBUG_MON_GP_OR_EP && !ep_enabled)) {
            int off = (d->ep_frame_div % 8) * NUM_SAMPLES_PER_FRAME;
            for (int i = 0; i < NUM_SAMPLES_PER_FRAME; i++) {
                uint32_t l = dsp_read_memory(d->gp.dsp, 'X', 0x1400 + i);
                d->monitor.frame_buf[off + i][0] = l >> 8;
                uint32_t r =
                    dsp_read_memory(d->gp.dsp, 'X', 0x1400 + 1 * 0x20 + i);
                d->monitor.frame_buf[off + i][1] = r >> 8;
            }
        }
    }

    /* Run EP */
    if ((d->ep.regs[NV_PAPU_EPRST] & NV_PAPU_GPRST_GPRST) &&
        (d->ep.regs[NV_PAPU_EPRST] & NV_PAPU_GPRST_GPDSPRST)) {
        if (d->ep_frame_div % 8 == 0) {
            dsp_start_frame(d->ep.dsp);
            dsp_set_halt_requested(d->ep.dsp, false);
            dsp_set_cycle_count(d->ep.dsp, 0);
            do {
                dsp_run(d->ep.dsp, 1000);
                if(dsp_get_cycle_count(d->ep.dsp)>1000000) {
                    fprintf(stderr,"[DSP] EP frame cycle limit PC=%04X\n",d->ep.dsp->core.pc); abort();
                }
            } while (!dsp_get_halt_requested(d->ep.dsp) && d->ep.realtime);
            g_dbg.ep.cycles = dsp_get_cycle_count(d->ep.dsp);
            ++observed_ep_runs;
        }
    }
    capture_dsp_stages(d, mixbins);
}

void mcpx_apu_dsp_init(MCPXAPUState *d)
{
    d->gp.dsp = dsp_init(d, gp_scratch_rw, gp_fifo_rw, true);
    dsp_set_halt_requested(d->gp.dsp, false);
    dsp_set_cycle_count(d->gp.dsp, 0);

    d->ep.dsp = dsp_init(d, ep_scratch_rw, ep_fifo_rw, false);
    dsp_set_halt_requested(d->ep.dsp, false);
    dsp_set_cycle_count(d->ep.dsp, 0);

    fprintf(stderr,"[APU] real GP/EP DSP interpreter and DMA connected (no command auto-ack)\n");

    /* Until DSP is more performant, a switch to decide whether or not we should
     * use the full audio pipeline or not.
     */
    mcpx_apu_update_dsp_preference(d);
}
