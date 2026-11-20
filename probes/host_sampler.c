/* Read-only native stacks for one explicitly selected diagnostic process. */
#include <windows.h>
#include <tlhelp32.h>
#include <dbghelp.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    HANDLE process;
    CONTEXT *context;
    uint64_t guest_offset;
    uint32_t eax,edi;
    unsigned valid;
} LocalObservation;

static BOOL CALLBACK observe_local(SYMBOL_INFO *symbol,ULONG size,void *opaque)
{
    (void)size;LocalObservation *o=opaque;
    const char *names[]={"g_eax","g_ebx","g_ecx","g_edx","g_esi","g_edi","g_esp","ebp"};
    unsigned index;
    for(index=0;index<8 && strcmp(names[index],symbol->Name);++index) {}
    if(index==8) return TRUE;
    uint64_t base=0;uint32_t value=0;SIZE_T got;
    if(symbol->Flags&SYMFLAG_REGREL) {
        /* CodeView AMD64 RBP/RSP register identifiers. */
        if(symbol->Register==334)base=o->context->Rbp;
        if(symbol->Register==335)base=o->context->Rsp;
        if(!base || !ReadProcessMemory(o->process,(void *)(uintptr_t)(base+(int64_t)symbol->Address),&value,4,&got) || got!=4) return TRUE;
        fprintf(stdout,"[LOCAL] %s=%08X reg=%u offset=%lld\n",symbol->Name,value,symbol->Register,(long long)symbol->Address);
        if(index==0){o->eax=value;o->valid|=1;}
        if(index==5){o->edi=value;o->valid|=2;}
    }
    return TRUE;
}

static void observe_locals(HANDLE process,CONTEXT *context,uint64_t guest_offset)
{
    IMAGEHLP_STACK_FRAME scope={0};
    scope.InstructionOffset=context->Rip;scope.StackOffset=context->Rsp;scope.FrameOffset=context->Rbp;
    SymSetContext(process,&scope,NULL);
    LocalObservation observation={process,context,guest_offset,0,0,0};
    SymEnumSymbols(process,0,NULL,observe_local,&observation);
    const uint32_t roots[]={observation.eax,observation.edi};
    for(unsigned root=0;root<2;root++) {
        if(!(observation.valid&(1u<<root)))continue;
        uint32_t va=roots[root];
        if(root==1 && va>=0x10000 && va<0x04000000) {
            uint32_t words[12];SIZE_T got;
            if(ReadProcessMemory(process,(void *)(uintptr_t)(guest_offset+va),words,sizeof words,&got) && got==sizeof words) {
                fprintf(stdout,"[GUEST-OWNER] %08X:",va);
                for(unsigned i=0;i<12;i++)fprintf(stdout," %08X",words[i]);
                fputc('\n',stdout);
            }
            va+=0x10;
        }
        for(unsigned node=0;node<8 && va;node++) {
            if(!((va>=0x10000 && va<0x04000000) || (va>=0x80000000 && va<0x84000000)))break;
            uint32_t words[4];SIZE_T got;
            if(!ReadProcessMemory(process,(void *)(uintptr_t)(guest_offset+va),words,sizeof words,&got) || got!=sizeof words)break;
            fprintf(stdout,"[GUEST-LIST] root%u %08X: %08X %08X %08X %08X\n",root,va,words[0],words[1],words[2],words[3]);
            if(words[0]==va)break;va=words[0];
        }
    }
}

static void describe(HANDLE process, DWORD64 pc)
{
    char storage[sizeof(SYMBOL_INFO) + MAX_SYM_NAME] = {0};
    SYMBOL_INFO *symbol = (SYMBOL_INFO *)storage;
    DWORD64 displacement = 0;
    symbol->SizeOfStruct = sizeof(*symbol);
    symbol->MaxNameLen = MAX_SYM_NAME;
    fprintf(stdout, "  pc=%016llX ", (unsigned long long)pc);
    if (SymFromAddr(process, pc, &displacement, symbol))
        fprintf(stdout, "%s+%llX", symbol->Name, (unsigned long long)displacement);
    IMAGEHLP_LINE64 line = {0};
    DWORD offset = 0;
    line.SizeOfStruct = sizeof(line);
    if (SymGetLineFromAddr64(process, pc, &offset, &line))
        fprintf(stdout, " %s:%lu", line.FileName, line.LineNumber);
    fputc('\n', stdout);
}

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    DWORD pid = (DWORD)strtoul(argv[1], NULL, 10);
    if (!pid || pid == GetCurrentProcessId()) return 2;
    HANDLE process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid);
    if (!process) return 3;
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME | SYMOPT_LOAD_LINES);
    if (!SymInitialize(process, argv[2], TRUE)) { CloseHandle(process); return 4; }
    const char *state_names[] = {"g_vblank_dpc", "g_vblank_hold", "g_nv2a_intr_hold",
        "g_cli_masked_count", "g_irql_raised_count", "g_gil_contended", "s_gil_next", "s_gil_serving",
        "g_xbox_mem_offset"};
    uint64_t guest_offset = 0;
    for (unsigned i = 0; i < sizeof(state_names) / sizeof(state_names[0]); ++i) {
        char storage[sizeof(SYMBOL_INFO) + MAX_SYM_NAME] = {0};
        SYMBOL_INFO *symbol = (SYMBOL_INFO *)storage;
        symbol->SizeOfStruct = sizeof(*symbol);
        symbol->MaxNameLen = MAX_SYM_NAME;
        uint64_t value = 0;
        SIZE_T got = 0;
        if (SymFromName(process, state_names[i], symbol) && symbol->Size &&
            ReadProcessMemory(process, (void *)(uintptr_t)symbol->Address, &value,
                symbol->Size > 8 ? 8 : symbol->Size, &got))
        {
            if (!strcmp(state_names[i], "g_xbox_mem_offset")) guest_offset = value;
            fprintf(stdout, "[STATE] %s=%016llX bytes=%llu\n", state_names[i],
                (unsigned long long)value, (unsigned long long)got);
        }
    }
    const uint32_t video_offsets[] = {0x8700,0x8704,0x8900,0x8908,0x8910,0x8918,0x8920,
        0x8928,0x8930,0x8938,0x8940,0x8948,0x8950,0x8958,0x8B00,
        0x100,0x140,0x600100,0x600140,0x800040,0x800044,
        0x400100,0x400108,0x400704,0x400708,0x400B10};
    for (unsigned i=0;i<sizeof(video_offsets)/sizeof(video_offsets[0]);++i) {
        uint32_t value;
        SIZE_T got;
        if (ReadProcessMemory(process, (void *)(uintptr_t)(guest_offset+0xFD000000u+video_offsets[i]),
                              &value, sizeof value, &got))
            fprintf(stdout,"[PVIDEO] %04X=%08X\n",video_offsets[i],value);
    }
    const uint32_t driver_addresses[] = {0x2B5AE0+0x1DE8,0x2B5AE0+0x2410,
        0x2B7708+0xA0,0x2B7708+0xA4,0x2B7708+0xB4,0x2B7708+0x1B4,
        0x2B7708+0x1BC,0x2B7708+0x1C0,
        0x2B5AE0,0x2B5AE0+0x24,0x2B5AE0+0x28,0x2B5AE0+0x2C,
        0x2B5AE0+0x30,0x2B5AE0+0x1DCC,0x2B5AE0+0x1DD0};
    for(unsigned i=0;i<sizeof(driver_addresses)/sizeof(driver_addresses[0]);i++) {
        uint32_t value; SIZE_T got;
        if(ReadProcessMemory(process,(void *)(uintptr_t)(guest_offset+driver_addresses[i]),
                             &value,sizeof value,&got))
            fprintf(stdout,"[D3D-STATE] %08X=%08X\n",driver_addresses[i],value);
    }
    /* Read only: exact XDK fence records and their in-place wait commands. */
    for (unsigned i=0;i<64;i++) {
        uint32_t pair[2]; SIZE_T got;
        uint32_t address=0x2B5AE0u+0x64u+i*8u;
        if(ReadProcessMemory(process,(void *)(uintptr_t)(guest_offset+address),pair,sizeof pair,&got)) {
            fprintf(stdout,"[D3D-FENCE] %08X seq=%08X pb=%08X",address,pair[0],pair[1]);
            uint32_t words[8];
            if(pair[1] && ReadProcessMemory(process,(void *)(uintptr_t)(guest_offset+pair[1]),words,sizeof words,&got))
                for(unsigned j=0;j<8;j++) fprintf(stdout," %08X",words[j]);
            fputc('\n',stdout);
        }
    }
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) { SymCleanup(process); CloseHandle(process); return 5; }
    THREADENTRY32 entry = {0};
    entry.dwSize = sizeof(entry);
    unsigned sampled = 0;
    for (BOOL more = Thread32First(snapshot, &entry); more; more = Thread32Next(snapshot, &entry)) {
        if (entry.th32OwnerProcessID != pid) continue;
        HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME | THREAD_QUERY_INFORMATION,
                                   FALSE, entry.th32ThreadID);
        if (!thread) continue;
        if (SuspendThread(thread) == (DWORD)-1) { CloseHandle(thread); continue; }
        CONTEXT context = {0};
        context.ContextFlags = CONTEXT_FULL;
        if (GetThreadContext(thread, &context)) {
            fprintf(stdout, "[THREAD] pid=%lu tid=%lu\n", pid, entry.th32ThreadID);
            describe(process, context.Rip);
            observe_locals(process,&context,guest_offset);
            STACKFRAME64 frame = {0};
            frame.AddrPC.Offset = context.Rip;
            frame.AddrFrame.Offset = context.Rbp;
            frame.AddrStack.Offset = context.Rsp;
            frame.AddrPC.Mode = frame.AddrFrame.Mode = frame.AddrStack.Mode = AddrModeFlat;
            for (unsigned i = 0; i < 36 && StackWalk64(IMAGE_FILE_MACHINE_AMD64, process, thread,
                    &frame, &context, NULL, SymFunctionTableAccess64, SymGetModuleBase64, NULL); ++i) {
                if (!frame.AddrPC.Offset) break;
                describe(process, frame.AddrPC.Offset);
            }
            ++sampled;
        }
        ResumeThread(thread);
        CloseHandle(thread);
        fflush(stdout);
    }
    CloseHandle(snapshot);
    SymCleanup(process);
    CloseHandle(process);
    return sampled ? 0 : 6;
}
