/* Independent synthetic guest code, actual runtime scheduler/IRQL locks. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "kernel.h"
#include "recomp_types.h"

extern void xbox_gil_enter(void), xbox_gil_leave(void);
extern int xbox_gil_suspend(void);
extern void xbox_gil_isr_begin(void), xbox_gil_isr_end(void);
extern int xbox_IrqlBlocksInterrupts(void);
extern KIRQL xbox_CurrentIrql(void);
extern void sub_00010000(void), sub_00010010(void), sub_00010020(void);

recomp_func_t recomp_lookup(uint32_t va) { (void)va; abort(); }
recomp_func_t recomp_lookup_manual(uint32_t va) { (void)va; abort(); }

static HANDLE ready, delivered;
static volatile LONG *poll_gate;
static DWORD WINAPI interrupt_worker(void *mode)
{
    KIRQL previous;
    if (!mode) SetEvent(ready);
    previous = xbox_KfRaiseIrql(DISPATCH_LEVEL);
    if (mode) SetEvent(ready);
    xbox_gil_isr_begin();
    SetEvent(delivered);
    xbox_gil_isr_end();
    xbox_KfLowerIrql(previous);
    return 0;
}

static DWORD WINAPI poll_interrupt_worker(void *unused)
{
    (void)unused;
    /* Do not contend until AFTER translated entry-point preemption. Only a
     * yield from the poll backedge can release the emulated CPU here. */
    while (!poll_gate[1]) SwitchToThread();
    KIRQL previous = xbox_KfRaiseIrql(DISPATCH_LEVEL);
    xbox_gil_isr_begin();
    InterlockedExchange(&poll_gate[0], 1);
    xbox_gil_isr_end();
    xbox_KfLowerIrql(previous);
    return 0;
}

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); ExitProcess(1); } } while (0)

int main(void)
{
    HANDLE worker;
    KIRQL previous;
    _putenv_s("RECOMP_GIL", "1");
    ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    delivered = CreateEventW(NULL, TRUE, FALSE, NULL);
    CHECK(ready && delivered);
    xbox_gil_enter();
    CHECK(recomp_interrupts_enabled());
    g_esp = 0x100000;
    sub_00010000();                 /* translated CLI; CLI; RET */
    CHECK(!recomp_interrupts_enabled());
    CHECK(xbox_CurrentIrql() == PASSIVE_LEVEL);
    CHECK(xbox_IrqlBlocksInterrupts());
    worker = CreateThread(NULL, 0, interrupt_worker, NULL, 0, NULL);
    CHECK(worker);
    CHECK(WaitForSingleObject(ready, 3000) == WAIT_OBJECT_0);
    CHECK(WaitForSingleObject(delivered, 40) == WAIT_TIMEOUT);
    CHECK(xbox_gil_suspend() == 0); /* kernel boundaries cannot yield with IF=0 */
    CHECK(WaitForSingleObject(delivered, 40) == WAIT_TIMEOUT);
    sub_00010010();                 /* translated STI; RET */
    CHECK(recomp_interrupts_enabled());
    CHECK(WaitForSingleObject(delivered, 40) == WAIT_TIMEOUT); /* still owns guest CPU */
    xbox_gil_leave();
    CHECK(WaitForSingleObject(worker, 3000) == WAIT_OBJECT_0);
    CHECK(WaitForSingleObject(delivered, 0) == WAIT_OBJECT_0);
    CloseHandle(worker);

    /* Resolve dispatch/GIL contention before clearing IF. */
    ResetEvent(ready); ResetEvent(delivered);
    xbox_gil_enter();
    worker = CreateThread(NULL, 0, interrupt_worker, (void *)1, 0, NULL);
    CHECK(worker);
    CHECK(WaitForSingleObject(ready, 3000) == WAIT_OBJECT_0);
    /* Enter the runtime helper directly so an entry-point preemption cannot
     * resolve this lock inversion before CLI itself handles it. */
    recomp_cli();
    sub_00010000();
    CHECK(!recomp_interrupts_enabled());
    CHECK(WaitForSingleObject(delivered, 0) == WAIT_OBJECT_0);
    sub_00010010();
    xbox_gil_leave();
    CHECK(WaitForSingleObject(worker, 3000) == WAIT_OBJECT_0);
    CloseHandle(worker);

    previous = xbox_KfRaiseIrql(DISPATCH_LEVEL);
    sub_00010000(); sub_00010010();
    CHECK(xbox_CurrentIrql() == DISPATCH_LEVEL);
    CHECK(xbox_IrqlBlocksInterrupts());
    xbox_KfLowerIrql(previous);
    CHECK(!xbox_IrqlBlocksInterrupts());

    poll_gate = VirtualAlloc((void *)0x200000, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    CHECK(poll_gate == (void *)0x200000 && g_xbox_mem_offset == 0);
    xbox_gil_enter();
    g_esp = 0x100000;
    worker = CreateThread(NULL, 0, poll_interrupt_worker, NULL, 0, NULL);
    CHECK(worker);
    sub_00010020();
    CHECK(poll_gate[0] == 1 && poll_gate[1] == 1 && g_esp == 0x100004 && g_eax == 1);
    xbox_gil_leave();
    CHECK(WaitForSingleObject(worker, 3000) == WAIT_OBJECT_0);
    CloseHandle(worker);
    VirtualFree((void *)poll_gate, 0, MEM_RELEASE);
    CloseHandle(ready); CloseHandle(delivered);
    puts("Interrupt execution: PASS (translated CLI/STI, delivery gate, contention, IRQL, poll backedge ISR)");
    return 0;
}
