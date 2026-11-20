/* Integration types for the separately obtained GPL DSP interpreter. */
#ifndef SCRAP_DSP_STATE_H
#define SCRAP_DSP_STATE_H
#include "interp/dsp_cpu.h"
#include "dsp_dma.h"
typedef struct DSPState {
    dsp_core_t core;
    DSPDMAState dma;
    int save_cycles;
    uint32_t interrupts;
    bool is_gp;
} DSPState;
DSPState *dsp_init(void *, dsp_scratch_rw_func, dsp_fifo_rw_func, bool);
void dsp_destroy(DSPState *);
void dsp_reset(DSPState *);
void dsp_run(DSPState *, int);
void dsp_bootstrap(DSPState *);
void dsp_start_frame(DSPState *);
uint32_t dsp_read_memory(DSPState *, char, uint32_t);
void dsp_write_memory(DSPState *, char, uint32_t, uint32_t);
bool dsp_get_halt_requested(DSPState *);
void dsp_set_halt_requested(DSPState *, bool);
uint32_t dsp_get_cycle_count(DSPState *);
void dsp_set_cycle_count(DSPState *, uint32_t);
struct MCPXAPUState;
uint64_t scrap_gp_read(struct MCPXAPUState *, uint32_t, unsigned);
uint64_t scrap_ep_read(struct MCPXAPUState *, uint32_t, unsigned);
void scrap_gp_write(struct MCPXAPUState *, uint32_t, uint32_t, unsigned);
void scrap_ep_write(struct MCPXAPUState *, uint32_t, uint32_t, unsigned);
#endif
