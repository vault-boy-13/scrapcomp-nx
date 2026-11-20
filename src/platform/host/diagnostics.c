/* Strict callbacks for initial guest execution; no success-shaped stubs. */
#include <windows.h>
#include <dbghelp.h>
#include <stdio.h>
#include "recomp_types.h"

static void stop_at(const char *reason, uint32_t va, unsigned status)
{
    fprintf(stderr, "[STOP] %s guest_va=0x%08X eax=%08X ecx=%08X edx=%08X esp=%08X\n",
        reason, va, g_eax, g_ecx, g_edx, g_esp);
    fprintf(stderr, "[STOP] recent indirect targets:");
    for (unsigned i = 0; i < 16; ++i)
        fprintf(stderr, " %08X", g_icall_trace[(g_icall_trace_idx + i) & 15]);
    fprintf(stderr, "\n");
    fprintf(stderr, "[STOP] ebx=%08X esi=%08X edi=%08X ebp=%08X thread=%lu\n",
        g_ebx, g_esi, g_edi, g_ebp, GetCurrentThreadId());
    fprintf(stderr, "[STOP] executable_base=0x%llX\n",
        (unsigned long long)(uintptr_t)GetModuleHandleW(NULL));
    SymRefreshModuleList(GetCurrentProcess());
    {
        void *frames[32];
        unsigned count = CaptureStackBackTrace(0, 32, frames, NULL);
        for (unsigned i = 0; i < count; ++i) {
            char storage[sizeof(SYMBOL_INFO) + 256] = {0};
            SYMBOL_INFO *symbol = (SYMBOL_INFO *)storage;
            DWORD64 displacement = 0;
            symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
            symbol->MaxNameLen = 255;
            if (SymFromAddr(GetCurrentProcess(), (DWORD64)(uintptr_t)frames[i],
                            &displacement, symbol))
                fprintf(stderr, "[STOP] stack[%u] %s+0x%llX\n", i, symbol->Name,
                    (unsigned long long)displacement);
            else
                fprintf(stderr, "[STOP] stack[%u] host=0x%llX symbol_error=%lu\n", i,
                    (unsigned long long)(uintptr_t)frames[i], GetLastError());
        }
    }
    fflush(stderr);
    ExitProcess(status);
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
