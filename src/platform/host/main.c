/* Windows bring-up harness for the pinned xboxrecomp ABI. No game code here. */
#include <windows.h>
#include <bcrypt.h>
#include <dbghelp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "kernel.h"
#include "xbox_memory_layout.h"
#include "ohci.h"
#include "recomp_types.h"
#include "scrap_image.h"
#include "firmware_observer.h"

/* Request the discrete adapter on Optimus notebooks before any GL ICD loads.
 * This is an executable-local preference; it changes no system GPU profile.
 * NVIDIA Optimus Rendering Policies, TB-05942-003v02. */
__declspec(dllexport) DWORD NvOptimusEnablement = 1;

extern void xbe_entry_point(void);
extern int recomp_dispatch_init(void);
extern void xbox_path_init(const char *game_dir, const char *save_dir);
extern void xbox_gil_mark_main(void);
extern void xbox_gil_enter(void);
extern void xbox_gil_leave(void);
extern void scrap_host_graphics_install(void);
extern int scrap_host_graphics_smoke(void);
extern int scrap_host_audio_install(void);
extern void scrap_host_audio_shutdown(void);

static int image_hash_matches(const void *image, ULONG size)
{
    BCRYPT_ALG_HANDLE algorithm = NULL;
    unsigned char digest[32];
    char hex[65];
    NTSTATUS status = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0);
    if (status < 0) return 0;
    status = BCryptHash(algorithm, NULL, 0, (PUCHAR)image, size, digest, sizeof(digest));
    BCryptCloseAlgorithmProvider(algorithm, 0);
    if (status < 0) return 0;
    for (unsigned i = 0; i < sizeof(digest); ++i) sprintf(hex + 2 * i, "%02x", digest[i]);
    return strcmp(hex, SCRAP_IMAGE_SHA256) == 0;
}

static LONG CALLBACK crash_report(EXCEPTION_POINTERS *ep)
{
    /* SDL/GL/audio drivers can be loaded after the startup symbol census. */
    SymRefreshModuleList(GetCurrentProcess());
    char storage[sizeof(SYMBOL_INFO) + 256] = {0};
    SYMBOL_INFO *symbol = (SYMBOL_INFO *)storage;
    DWORD64 displacement = 0;
    symbol->SizeOfStruct = sizeof(SYMBOL_INFO);
    symbol->MaxNameLen = 255;
    fprintf(stderr, "[FAULT] exception=0x%08lX host_pc=0x%llX\n",
        ep->ExceptionRecord->ExceptionCode, (unsigned long long)ep->ContextRecord->Rip);
    {
        HMODULE module;
        char module_path[MAX_PATH];
        if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                (LPCSTR)(uintptr_t)ep->ContextRecord->Rip,&module) &&
            GetModuleFileNameA(module,module_path,sizeof module_path))
            fprintf(stderr,"[FAULT] module=%s offset=0x%llX\n",module_path,
                (unsigned long long)(ep->ContextRecord->Rip-(uintptr_t)module));
    }
    if (SymFromAddr(GetCurrentProcess(), ep->ContextRecord->Rip, &displacement, symbol))
        fprintf(stderr, "[FAULT] symbol=%s+0x%llX\n", symbol->Name,
            (unsigned long long)displacement);
    {
        IMAGEHLP_LINE64 line = {0};
        DWORD line_offset = 0;
        line.SizeOfStruct = sizeof(line);
        if (SymGetLineFromAddr64(GetCurrentProcess(), ep->ContextRecord->Rip, &line_offset, &line))
            fprintf(stderr, "[FAULT] source=%s:%lu+%lu\n", line.FileName, line.LineNumber, line_offset);
    }
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION &&
        ep->ExceptionRecord->NumberParameters >= 2) {
        uintptr_t address = ep->ExceptionRecord->ExceptionInformation[1];
        fprintf(stderr, "[FAULT] access=%llu host_address=0x%llX guest_va=0x%08X\n",
            (unsigned long long)ep->ExceptionRecord->ExceptionInformation[0],
            (unsigned long long)address, (uint32_t)(address - g_xbox_mem_offset));
    }
    fprintf(stderr, "[FAULT] eax=%08X ecx=%08X edx=%08X ebx=%08X esi=%08X edi=%08X esp=%08X ebp=%08X\n",
        g_eax, g_ecx, g_edx, g_ebx, g_esi, g_edi, g_esp, g_ebp);
    {
        CONTEXT context = *ep->ContextRecord;
        STACKFRAME64 frame = {0};
        frame.AddrPC.Offset = context.Rip;
        frame.AddrFrame.Offset = context.Rbp;
        frame.AddrStack.Offset = context.Rsp;
        frame.AddrPC.Mode = frame.AddrFrame.Mode = frame.AddrStack.Mode = AddrModeFlat;
        for (unsigned i = 0; i < 40 && StackWalk64(IMAGE_FILE_MACHINE_AMD64,
             GetCurrentProcess(), GetCurrentThread(), &frame, &context, NULL,
             SymFunctionTableAccess64, SymGetModuleBase64, NULL); ++i) {
            if (!frame.AddrPC.Offset) break;
            if (SymFromAddr(GetCurrentProcess(), frame.AddrPC.Offset, &displacement, symbol))
                fprintf(stderr, "[FAULT] stack[%u] %s+0x%llX\n", i, symbol->Name,
                    (unsigned long long)displacement);
        }
    }
    fflush(stderr);
    /* This harness does not skip a faulting instruction or fake MMIO reads. */
    return EXCEPTION_CONTINUE_SEARCH;
}

static LONG CALLBACK device_mmio(EXCEPTION_POINTERS *ep)
{
    EXCEPTION_RECORD *record = ep->ExceptionRecord;
    if (record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION &&
        record->NumberParameters >= 2 && record->ExceptionInformation[0] <= 1) {
        uintptr_t address = record->ExceptionInformation[1];
        uintptr_t offset = (uintptr_t)g_xbox_mem_offset;
        if (address >= offset && address - offset <= UINT32_MAX) {
            uint32_t va = (uint32_t)(address - offset);
            if (xbox_OhciOwnsAddress(va) && xbox_OhciHandleMmio(ep->ContextRecord, va))
                return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static uint32_t diagnostic_word(uint32_t va)
{
    uint32_t value=0;
    SIZE_T done=0;
    ReadProcessMemory(GetCurrentProcess(),(const void *)((uintptr_t)g_xbox_mem_offset+va),
        &value,sizeof value,&done);
    return done==sizeof value ? value : 0;
}

static void diagnostic_text(uint32_t va)
{
    char text[512]={0};
    SIZE_T done=0;
    if (va) ReadProcessMemory(GetCurrentProcess(),
        (const void *)((uintptr_t)g_xbox_mem_offset+va),text,sizeof text-1,&done);
    for (SIZE_T i=0;i<done && text[i];++i)
        fputc((unsigned char)text[i]>=32 ? (unsigned char)text[i] : '.',stderr);
}

static void diagnostic_object(uint32_t va, unsigned depth)
{
    uint32_t type=diagnostic_word(va+4),name=diagnostic_word(type+12);
    fprintf(stderr,"[EXIT] object %08X type=",va); diagnostic_text(name);
    for (unsigned i=0;i<8;++i) fprintf(stderr," %08X",diagnostic_word(va+4*i));
    fprintf(stderr," text20="); diagnostic_text(va+20); fputc('\n',stderr);
    /* Only recurse into a tuple whose type name is exactly known. */
    if (depth<3 && diagnostic_word(name)==0x6C707574 &&
        (diagnostic_word(name+4)&0xFFFF)==0x0065) {
        uint32_t size=diagnostic_word(va+8);
        for (unsigned i=0;i<size && i<8;++i)
            diagnostic_object(diagnostic_word(va+12+4*i),depth+1);
    }
    if (depth<8 && diagnostic_word(name)==0x63617274) {
        uint32_t frame=diagnostic_word(va+12),code=diagnostic_word(frame+12);
        fprintf(stderr,"[EXIT] traceback line=%u lasti=%u file=",
            diagnostic_word(va+20),diagnostic_word(va+16));
        diagnostic_text(diagnostic_word(code+40)+20);
        fprintf(stderr," function="); diagnostic_text(diagnostic_word(code+44)+20);
        fputc('\n',stderr);
        /* Preserve the actual bytecode and local operands for private analysis. */
        if (code) {
            diagnostic_object(diagnostic_word(code+28),depth+1);
            diagnostic_object(diagnostic_word(code+32),depth+1);
        }
        if (diagnostic_word(va+8)) diagnostic_object(diagnostic_word(va+8),depth+1);
    }
}

static void firmware_report(uint32_t routine)
{
    /* Read-only, title-specific error journal. These are ordinary RAM slots in
     * the hash-checked image, retained when its fatal handler launches Xbox UI. */
    uintptr_t mem = (uintptr_t)g_xbox_mem_offset;
    void *frames[48];
    unsigned count = CaptureStackBackTrace(0, 48, frames, NULL);
    fprintf(stderr,"[EXIT] firmware=%u engine_error=%u journal_index=%u\n",
        routine,*(const uint32_t *)(mem+0x3AF554),
        *(const uint32_t *)(mem+0x3AF54C));
    for (unsigned row=0; row<23; ++row) {
        const unsigned char *line=(const unsigned char *)(mem+0x3AE970+row*0x84);
        fprintf(stderr,"[EXIT] journal[%u] ",row);
        for (unsigned i=0;i<128 && line[i];++i)
            fputc(line[i]>=32 && line[i]!=127 ? line[i] : '.',stderr);
        fputc('\n',stderr);
    }
    fprintf(stderr,"[EXIT] formatted: %.1023s\n",(const char *)(mem+0x3AE570));
    {
        uint32_t state=diagnostic_word(0x43DAB0);
        fprintf(stderr,"[EXIT] Python thread=%08X\n",state);
        if (state) {
            for (unsigned i=0x20;i<=0x34;i+=4)
                diagnostic_object(diagnostic_word(state+i),0);
        }
    }
    for (unsigned i=0;i<count;++i) {
        char storage[sizeof(SYMBOL_INFO)+256]={0};
        SYMBOL_INFO *symbol=(SYMBOL_INFO *)storage;
        DWORD64 displacement=0;
        symbol->SizeOfStruct=sizeof(SYMBOL_INFO); symbol->MaxNameLen=255;
        if (SymFromAddr(GetCurrentProcess(),(DWORD64)(uintptr_t)frames[i],&displacement,symbol))
            fprintf(stderr,"[EXIT] stack[%u] %s+0x%llX\n",i,symbol->Name,
                (unsigned long long)displacement);
    }
    fflush(stderr);
}

int main(int argc, char **argv)
{
    FILE *file;
    void *image;
    long size;
    void *device_handler;
    const char *xbe = argc > 1 ? argv[1] : "original/Default.xbe";
    const char *game = argc > 2 ? argv[2] : "original";
    const char *save = argc > 3 ? argv[3] : "runs/host-saves";
    int synthetic = argc > 4 && (strcmp(argv[4],"--graphics-smoke")==0 ||
                                strcmp(argv[4],"--pvideo-smoke")==0);
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME);
    SymInitialize(GetCurrentProcess(), NULL, TRUE);
    SetUnhandledExceptionFilter(crash_report);
    fprintf(stderr, "[BOOT] scrapcomp-nx Windows diagnostic host; expected XBE %s\n", SCRAP_IMAGE_SHA256);
    /* The reached XPP code enumerates the hardware controllers itself. */
    if (_putenv_s("RECOMP_USB", "1")) return 3;
    if (_putenv_s("RECOMP_PB_EXEC", "1") || _putenv_s("RECOMP_VBLANK", "1")) return 3;
    /* Native Windows AC97 write trapping completes channel reset before the
     * guest's first read; this XDK routine keeps that read in CL while polling. */
    if (!synthetic && _putenv_s("RECOMP_AC97_READY", "1")) return 3;
    file = fopen(xbe, "rb");
    if (!file) { fprintf(stderr, "[BOOT] cannot open input XBE\n"); return 2; }
    if (fseek(file, 0, SEEK_END) || (size = ftell(file)) != SCRAP_IMAGE_SIZE ||
        fseek(file, 0, SEEK_SET)) { fclose(file); return 2; }
    image = malloc((size_t)size);
    if (!image || fread(image, 1, (size_t)size, file) != (size_t)size) {
        fclose(file); free(image); return 2;
    }
    fclose(file);
    if (!image_hash_matches(image, (ULONG)size)) {
        fprintf(stderr, "[BOOT] input SHA256 mismatch; refusing guest execution\n");
        free(image); return 2;
    }
    if (!xbox_MemoryLayoutInit(image, (size_t)size)) {
        fprintf(stderr, "[BOOT] guest memory mapping failed\n"); free(image); return 3;
    }
    g_xbox_mem_offset = xbox_GetMemoryOffset();
    fprintf(stderr, "[BOOT] guest memory mapped; offset=0x%llX\n", (unsigned long long)g_xbox_mem_offset);
    device_handler = AddVectoredExceptionHandler(1, device_mmio);
    if (!device_handler) { free(image); return 3; }
    xbox_OhciInit();
    scrap_host_graphics_install();
    if (!synthetic && !scrap_host_audio_install()) {
        fprintf(stderr,"[BOOT] MCPX APU initialization failed\n"); return 84;
    }
    xbox_kernel_init();
    xbox_path_init(game, save);
    xbox_kernel_bridge_init();
    if (argc > 4 && strcmp(argv[4], "--pvideo-smoke") == 0) {
        extern int scrap_host_pvideo_smoke(void);
        return scrap_host_pvideo_smoke();
    }
    if (argc > 4 && strcmp(argv[4], "--graphics-smoke") == 0)
        return scrap_host_graphics_smoke();
    g_esp = XBOX_STACK_TOP - 4;
    *(uint32_t *)((uintptr_t)g_xbox_mem_offset + g_esp) = 0;
    if (!recomp_dispatch_init()) fprintf(stderr, "[BOOT] using binary-search dispatch\n");
    xbox_WatchdogStart();
    fprintf(stderr, "[BOOT] enter guest=0x%08X esp=0x%08X\n", SCRAP_ENTRY_POINT, g_esp);
    xbox_gil_mark_main();
    xbox_SetFirmwareObserver(firmware_report);
    xbox_gil_enter();
    xbe_entry_point();
    xbox_gil_leave();
    fprintf(stderr, "[BOOT] XBE entry returned; this is not a menu/gameplay pass\n");
    xbox_kernel_shutdown();
    if (!synthetic) scrap_host_audio_shutdown();
    xbox_MemoryLayoutShutdown();
    RemoveVectoredExceptionHandler(device_handler);
    free(image);
    SymCleanup(GetCurrentProcess());
    return 0;
}
