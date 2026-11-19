/* Independent Horizon service probe, not a Scrapland boot stub. */
#include <switch.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static void *thread_probe(void *argument)
{
    *(uint32_t *)argument = 0x5849;
    return NULL;
}

int main(void)
{
    consoleInit(NULL);
    puts("Scrapland workspace / Horizon runtime probe");
    puts("This is an environment test, not the game.");
    printf("Applet type: %d; ARM64 pointer size: %zu\n", appletGetAppletType(), sizeof(void*));
    mkdir("sdmc:/switch", 0777);
    mkdir("sdmc:/switch/scrapland-workspace", 0777);
    uint32_t threaded = 0;
    pthread_t worker;
    int created = pthread_create(&worker, NULL, thread_probe, &threaded);
    if (!created) pthread_join(worker, NULL);
    printf("pthread: %s\n", !created && threaded == 0x5849 ? "PASS" : "FAIL");
    const char *path = "sdmc:/switch/scrapland-workspace/runtime-probe.txt";
    FILE *out = fopen(path, "wb");
    int file_ok = 0;
    if (out) {
        const char token[] = "scrapland-xdk5849\n";
        file_ok = fwrite(token, 1, sizeof(token), out) == sizeof(token);
        fclose(out);
        char check[sizeof(token)] = {0};
        out = fopen(path, "rb");
        if (out) {
            file_ok = file_ok && fread(check, 1, sizeof(check), out) == sizeof(check)
                      && memcmp(token, check, sizeof(check)) == 0;
            fclose(out);
        } else file_ok = 0;
    }
    printf("SD file write/read: %s\n", file_ok ? "PASS" : "FAIL");
    /* Reserve/release the virtual span without committing 4 GB physical RAM. */
    virtmemLock();
    void *span = virtmemFindAslr(1ULL << 32, 0x10000);
    VirtmemReservation *reservation = span ? virtmemAddReservation(span, 1ULL << 32) : NULL;
    if (reservation) virtmemRemoveReservation(reservation);
    virtmemUnlock();
    printf("4 GB virtual reservation: %s\n", reservation ? "PASS" : "FAIL");
    FILE *results = fopen("sdmc:/switch/scrapland-workspace/runtime-probe-results.json", "w");
    if (results) {
        fprintf(results, "{\"pthread\":%s,\"sd_io\":%s,\"reserve_4g\":%s}\n",
            !created && threaded == 0x5849 ? "true" : "false", file_ok ? "true" : "false",
            reservation ? "true" : "false");
        fclose(results);
    }
    puts("Code-memory aliasing, guest IRQs and game runtime are later probes.");
    puts("Press + to exit.");
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        consoleUpdate(NULL);
    }
    consoleExit(NULL);
    return 0;
}
