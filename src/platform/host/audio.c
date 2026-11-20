/* Connect the pinned APU to lifted DSOUND MMIO, as in the NFSU2 host. */
#include "apu.h"
#include "xbox_memory_layout.h"
#include <stdio.h>
#include <stdint.h>
#include "audio_capture.h"

extern MCPXAPUState *g_apu_state;
static uint32_t audio_read(void *state, uint32_t offset, unsigned size)
{
    return (uint32_t)mcpx_apu_mmio_read(state, offset, size);
}
static void audio_write(void *state, uint32_t offset, uint32_t value, unsigned size)
{
    static unsigned writes;
    if (writes++ < 24)
        fprintf(stderr,"[APU-MMIO] write %05X=%08X size=%u\n",offset,value,size);
    mcpx_apu_mmio_write(state, offset, value, size);
}
int scrap_host_audio_install(void)
{
    scrap_host_audio_observe_install();
    g_apu_state = mcpx_apu_init_standalone((uint8_t *)xbox_GetMemoryBase());
    if (!g_apu_state) return 0;
    if (xbox_MmioRegister(0xFE800000u,0xFE880000u,audio_read,audio_write,g_apu_state)) {
        mcpx_apu_shutdown(g_apu_state);
        g_apu_state = NULL;
        return 0;
    }
    fprintf(stderr,"[BOOT] MCPX APU connected through lifted DSOUND MMIO with real GP/EP execution\n");
    return 1;
}
void scrap_host_audio_shutdown(void)
{
    mcpx_apu_shutdown(g_apu_state);
    g_apu_state = NULL;
    scrap_host_audio_observe_finish();
}
