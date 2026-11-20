/* Independent fixtures: real wrapper/scheduler/executor, no game bytes. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "kernel.h"
#include "recomp_types.h"

extern void sub_002AAFA0(void), sub_002B0630(void), sub_002B0BA0(void);
extern void sub_0019F1C0(void);
extern void nv2a_pb_exec_method(uint32_t subchannel, uint32_t method, uint32_t value);
extern KIRQL xbox_CurrentIrql(void);
extern void xbox_gil_enter(void), xbox_gil_leave(void);
recomp_func_t recomp_lookup(uint32_t va) { (void)va; abort(); }
recomp_func_t recomp_lookup_manual(uint32_t va) { (void)va; abort(); }

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); ExitProcess(1); } } while (0)
static unsigned block_calls, vb_calls, trap_calls;
static uint32_t expected_sem;
/* XMV observation wrapper is linked here but outside this D3D fixture scope. */
void sub_0030EDC7_gen(void) { abort(); }

void sub_002AAFA0_gen(void)
{
    ++block_calls;
    CHECK(g_esp == 0x100000 && g_ecx == 0x12345678);
    CHECK(MEM32(expected_sem) == 0);
    nv2a_pb_exec_method(0, 0x1D70, 43);
    CHECK(MEM32(expected_sem) == 43);
    g_eax = 43;
    g_esp += 12;
}

void sub_002B0630_gen(void)
{
    ++vb_calls;
    CHECK(xbox_CurrentIrql() == DISPATCH_LEVEL);
    CHECK(!(MEM32(0xFD000100) & 0x01000000) && !(MEM32(0xFD600100) & 1));
    MEM32(g_ecx + 0x1BC) += 2;
    g_ecx = 0xDEADBEEF;
    g_eax = 17;
    g_esp += 4;
}

void sub_002B0BA0_gen(void)
{
    ++trap_calls;
    CHECK(xbox_CurrentIrql() == DISPATCH_LEVEL);
    CHECK(MEM32(0xFD400108) == 1);
    MEM32(g_ecx + 0x1BC) += 1;
    g_eax = 19;
    g_esp += 4;
}

int main(void)
{
    _putenv_s("RECOMP_GIL", "1");
    CHECK(VirtualAlloc((void *)0x200000, 4096, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE) == (void *)0x200000);
    CHECK(VirtualAlloc((void *)0x2B0000, 65536, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE) == (void *)0x2B0000);
    CHECK(VirtualAlloc((void *)0xFD000000, 0x1000000, MEM_RESERVE|MEM_COMMIT, PAGE_READWRITE) == (void *)0xFD000000);
    CHECK(g_xbox_mem_offset == 0);
    xbox_gil_enter();
    g_eax=0; g_ebx=11; g_ecx=12; g_edx=13; g_esi=14; g_edi=15; g_ebp=16; g_esp=0x100000;
    sub_0019F1C0();
    CHECK(g_eax==1 && g_esp==0x100004 && g_ebx==11 && g_ecx==12 &&
          g_edx==13 && g_esi==14 && g_edi==15 && g_ebp==16);
    MEM32(0x2B5AD8) = 0x2B5AE0;
    for (unsigned i=0;i<2;i++) {
        expected_sem = 0x200000 + i*4;
        MEM32(0x2B5AE0 + 0x30) = expected_sem;
        g_esp = 0x100000; g_ecx = 0x12345678;
        sub_002AAFA0();
        CHECK(g_esp == 0x10000C && g_eax == 43 && block_calls == i+1);
    }
    const uint32_t block = 0x2B7708;
    MEM32(0xFD000100) = 0x01000000;
    MEM32(0xFD600100) = 1;
    g_esp = 0x100000; g_ecx = block;
    sub_002B0630();
    CHECK(vb_calls == 1 && MEM32(block+0x1BC) == 2);
    CHECK(g_esp == 0x100004 && g_eax == 17 && g_ecx == 0xDEADBEEF);
    CHECK(xbox_CurrentIrql() == PASSIVE_LEVEL);
    MEM32(0xFD000100) = 0x1000;
    MEM32(0xFD400100) = 1;
    MEM32(0xFD400108) = 1;
    g_esp = 0x100000; g_ecx = block;
    sub_002B0BA0();
    CHECK(trap_calls == 1 && MEM32(block+0x1BC) == 3);
    CHECK(g_esp == 0x100004 && g_eax == 19);
    CHECK(MEM32(0xFD400108) == 0 && !(MEM32(0xFD400100)&1) && !(MEM32(0xFD000100)&0x1000));
    CHECK(xbox_CurrentIrql() == PASSIVE_LEVEL);
    xbox_gil_leave();
    puts("PASS: executor semaphore/rebind, original calls/ABI, VBlank/PGRAPH acknowledgment and IRQL");
    return 0;
}
