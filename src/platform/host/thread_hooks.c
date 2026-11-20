/* Desktop counterparts of optional hooks supplied by POSIX/Switch platform. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

void xbox_nx_raise_host_thread(void)
{
    /* The donor APU already calls native SetThreadPriority(HIGHEST).
     * Its additional Horizon-only priority hook is a no-op on desktop. */
}

void xbox_nx_retag_thread(void *entry)
{
    typedef HRESULT (WINAPI *set_description_t)(HANDLE, PCWSTR);
    set_description_t describe = (set_description_t)GetProcAddress(
        GetModuleHandleW(L"kernel32.dll"), "SetThreadDescription");
    if (describe) {
        wchar_t name[64];
        swprintf_s(name, 64, L"scrapcomp guest %p", entry);
        describe(GetCurrentThread(), name);
    }
}

void xbox_guest_pin(int interrupt)
{
    const char *policy = getenv("RECOMP_GUEST_ONE_CORE");
    DWORD_PTR process_mask, system_mask;
    /* Guest serialization is provided by the runtime GIL. Pinning is the
     * separate, opt-in diagnostic policy used by the donor platform. */
    if (!policy || (policy[0] != '1' && policy[0] != '2') ||
        (interrupt && policy[0] == '2')) return;
    if (!GetProcessAffinityMask(GetCurrentProcess(), &process_mask, &system_mask) || !process_mask) {
        fprintf(stderr, "[HOST] cannot query guest affinity policy\n"); return;
    }
    DWORD_PTR core = process_mask & (~process_mask + 1);
    if (!SetThreadAffinityMask(GetCurrentThread(), core))
        fprintf(stderr, "[HOST] cannot pin guest thread: Win32 error %lu\n", GetLastError());
}
