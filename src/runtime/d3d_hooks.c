/* Scrapland XDK 5849 integration with the pinned NV2A executor APIs.
 * All three original guest bodies remain generated and execute below.
 * Field evidence: D3D_BlockOnTime 0x002AAFA0, device global 0x002B5AD8;
 * DPC 0x002B0DE0 calls VBlank 0x002B0630 and PGRAPH 0x002B0BA0.
 * Integration design: pinned xboxrecomp docs/technical/d3d8ltcg-device-context.md
 * and the successful NFSU donor handler/semaphore wrappers.
 */
#include "kernel.h"
#include "recomp_types.h"
#include <stdio.h>

extern void sub_002AAFA0_gen(void);
extern void sub_002B0630_gen(void);
extern void sub_002B0BA0_gen(void);
extern void sub_0030EDC7_gen(void);
extern void nv2a_pb_set_semaphore_target(uint32_t guest_va);
extern void nv2a_pb_flip_retired(unsigned count);
extern void nv2a_pb_trap_lock(void), nv2a_pb_trap_unlock(void), nv2a_pb_trap_taken(void);
extern void xbox_Nv2aVblankTaken(void);
extern KIRQL xbox_CurrentIrql(void);
extern int xbox_gil_suspend(void);
extern void xbox_gil_resume(int depth);

/* The sole caller 0x192EBB observes only AL, then overwrites flags with TEST.
 * 0x19F1C0 is the standard EFLAGS.ID-toggle CPUID availability probe.
 * The emulated Pentium III has CPUID on every host, including ARM64.
 * Keep other PUSHFD/POPFD sites strict until full flag packing is supported. */
void sub_0019F1C0(void)
{
    static unsigned shown;
    if(!shown++) fprintf(stderr,"[CPU] CPUID availability probe: original Xbox Pentium III\n");
    g_eax=1;
    g_esp+=4;
}

typedef struct {
    uint32_t hardware_block;
    uint32_t retire_index;
    KIRQL previous_irql;
} HandlerState;

static HandlerState handler_begin(uint32_t hardware_block)
{
    HandlerState state;
    state.previous_irql = xbox_CurrentIrql();
    if (state.previous_irql < DISPATCH_LEVEL) {
        int depth = xbox_gil_suspend();
        xbox_KfRaiseIrql(DISPATCH_LEVEL);
        xbox_gil_resume(depth);
    }
    state.hardware_block = hardware_block;
    state.retire_index = MEM32(hardware_block + 0x1BC);
    return state;
}

static void handler_end(HandlerState state)
{
    nv2a_pb_flip_retired(MEM32(state.hardware_block + 0x1BC) - state.retire_index);
    if (state.previous_irql < DISPATCH_LEVEL)
        xbox_KfLowerIrql(state.previous_irql);
}

void sub_002AAFA0(void)
{
    static uint32_t registered;
    uint32_t device = MEM32(0x002B5AD8);
    uint32_t semaphore = device ? MEM32(device + 0x30) : 0;
    if (semaphore && semaphore != registered) {
        nv2a_pb_set_semaphore_target(semaphore);
        registered = semaphore;
        fprintf(stderr, "[D3D] executor semaphore=%08X device=%08X\n", semaphore, device);
    }
    /* Original entry/window test, kickoff, callbacks and wait all execute. */
    sub_002AAFA0_gen();
}

void sub_002B0630(void)
{
    HandlerState state = handler_begin(g_ecx);
    /* Caller already observed the pending VBlank. Model W1C before its spin. */
    xbox_Nv2aVblankTaken();
    sub_002B0630_gen();
    handler_end(state);
}

void sub_002B0BA0(void)
{
    HandlerState state = handler_begin(g_ecx);
    nv2a_pb_trap_lock();
    uint32_t source = MEM32(0xFD400108);
    sub_002B0BA0_gen();
    if (source)
        nv2a_pb_trap_taken();
    nv2a_pb_trap_unlock();
    handler_end(state);
}

/* Read-only, bounded XMV progress observation. The original decoder executes. */
void sub_0030EDC7(void)
{
    static unsigned calls;
    uint32_t decoder = MEM32(g_esp + 4);
    uint32_t status = MEM32(g_esp + 12), timestamp = MEM32(g_esp + 16);
    sub_0030EDC7_gen();
    if (++calls <= 4 || calls % 500 == 0) {
        fprintf(stderr, "[XMV] call=%u obj=%08X result=%08X status=%u time=%u vb=%u\n",
            calls, decoder, g_eax, MEM32(status), MEM32(timestamp), MEM32(0x2B78C8));
        const uint32_t offsets[] = {0x18,0x3C,0x48,0x50,0x60,0x64,0x68,0x6C,
            0x74,0x78,0xAC,0xB0,0xB4,0xB8,0xBC,0xC0,0xC4,0xC8,0xE4,0xE8,0xF8,
            0x138,0x148,0x14C};
        for (unsigned i=0; i<sizeof(offsets)/sizeof(offsets[0]); ++i)
            fprintf(stderr, " %03X=%08X", offsets[i], MEM32(decoder+offsets[i]));
        fputc('\n', stderr);
        if (MEM32(decoder+0x48) && MEM32(decoder+0x48) < 16) {
            for (unsigned i=0;i<MEM32(decoder+0x48);i++)
                fprintf(stderr, "[XMV] audio[%u] enabled=%08X pending=%08X next=%08X\n", i,
                    MEM32(MEM32(decoder+0x138)+i*4),
                    MEM32(decoder+0x148) ? MEM32(MEM32(decoder+0x148)+i*4) : 0,
                    MEM32(decoder+0x14C) ? MEM32(MEM32(decoder+0x14C)+i*4) : 0);
        }
    }
}
