#include <stdalign.h>
#include <stdio.h>
#include <stdlib.h>
#include <switch.h>

#include "recomp_types.h"

#ifdef SCRAP_SWITCH_TRACE_XPP
extern void sub_0033A47A(void);
extern void sub_0033A8D3(void);

void __cyg_profile_func_enter(void *function, void *caller)
{
    (void)caller;
    if (function == (void *)sub_0033A8D3) {
        static unsigned calls;
        if (++calls <= 30) {
            uint32_t context = MEM32(g_esp + 8);
            if (context >= 0x80000000u && context <= 0x83FFFB00u) {
                uint32_t hcca = MEM32(context + 8);
                if (hcca >= 0x80000000u && hcca <= 0x83FFFF00u) {
                    uint32_t done = MEM32(hcca + 0x84);
                    fprintf(stderr, "[XPP-DPC] #%u bits=%08X done=%08X",
                        calls, MEM32(context + 0x438), done);
                    for (unsigned i = 0; i < 12; ++i) {
                        uint32_t td = done & ~15u;
                        if (td == 0 || td > 0x03FFFFE0u) break;
                        uint32_t va = 0x80000000u + td;
                        done = MEM32(va + 8);
                        fprintf(stderr, " %08X/%u/%08X", td, MEM32(va) >> 28, done);
                    }
                    fputc('\n', stderr);
                }
            }
        }
        return;
    }
    if (function != (void *)sub_0033A47A) return;
    uint32_t td = g_edx;
    if (td < 0x80000000u || td > 0x83FFFFE0u) return;
    uint32_t ed = MEM32(td + 20);
    fprintf(stderr, "[XPP-ERROR] td=%08X cc=%u next=%08X ed=%08X ctx=%08X\n",
        td, MEM32(td) >> 28, MEM32(td + 8), ed, g_ecx);
    if (ed < 0x80000000u || ed > 0x83FFFFF0u) return;
    uint32_t head = (MEM32(ed + 8) & ~15u) + 0x80000000u;
    fprintf(stderr, "[XPP-ERROR] ed head=%08X tail=%08X flags=%08X\n",
        MEM32(ed + 8), MEM32(ed + 4), MEM32(ed));
    for (unsigned i = 0; i < 10 && head >= 0x80000000u && head <= 0x83FFFFE0u; ++i) {
        uint32_t next = MEM32(head + 8);
        fprintf(stderr, "[XPP-ERROR] head chain[%u]=%08X cc=%u next=%08X type=%02X flags=%02X\n",
            i, head, MEM32(head) >> 28, next, MEM8(head + 0x1E), MEM8(head + 0x1C));
        if (!next) break;
        head = (next & ~15u) + 0x80000000u;
    }
}

void __cyg_profile_func_exit(void *function, void *caller)
{
    (void)function;
    (void)caller;
}
#endif

static void print_guest_registers(void)
{
    fprintf(stderr, "[GUEST] eax=%08X ecx=%08X edx=%08X ebx=%08X esi=%08X edi=%08X esp=%08X ebp=%08X\n",
        g_eax, g_ecx, g_edx, g_ebx, g_esi, g_edi, g_esp, g_ebp);
    fprintf(stderr, "[GUEST] recent indirect targets:");
    for (unsigned i = 0; i < 16; ++i)
        fprintf(stderr, " %08X", g_icall_trace[(g_icall_trace_idx + i) & 15]);
    fputc('\n', stderr);
}

static _Noreturn void stop_at(const char *reason, uint32_t va, int status)
{
    fprintf(stderr, "[STOP] %s guest_va=0x%08X\n", reason, va);
    print_guest_registers();
    exit(status);
}

recomp_func_t recomp_lookup_manual(uint32_t va)
{
    (void)va;
    return NULL;
}

void scrap_stop_unresolved(uint32_t va) { stop_at("unresolved direct call", va, 74); }
void recomp_icall_fail_log(uint32_t va) { stop_at("unresolved indirect call", va, 75); }
void recomp_icall_not_code_log(uint32_t va) { stop_at("indirect target outside code", va, 76); }
void recomp_unimpl(const char *instruction, uint32_t va)
{
    fprintf(stderr, "[UNIMPL] %s\n", instruction);
    stop_at("unsupported instruction reached", va, 77);
}

alignas(16) u8 __nx_exception_stack[0x4000];
u64 __nx_exception_stack_size = sizeof(__nx_exception_stack);

void __libnx_exception_handler(ThreadExceptionDump *ctx)
{
    const uintptr_t offset = (uintptr_t)g_xbox_mem_offset;
    const uintptr_t far = ctx->far.x;
    fprintf(stderr, "[FAULT] exception=%u pc=0x%llX lr=0x%llX sp=0x%llX far=0x%llX handler=%p\n",
        ctx->error_desc, (unsigned long long)ctx->pc.x, (unsigned long long)ctx->lr.x,
        (unsigned long long)ctx->sp.x, (unsigned long long)far, (void *)__libnx_exception_handler);
    if (offset && far >= offset && far - offset <= UINT32_MAX)
        fprintf(stderr, "[FAULT] guest_va=0x%08X\n", (uint32_t)(far - offset));
    print_guest_registers();
    fflush(stderr);
    svcExitProcess();
}
