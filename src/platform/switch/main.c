#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <switch.h>
#include <sys/stat.h>

#include "apu.h"
#include "apu_xaudio2.h"
#include "firmware_observer.h"
#include "kernel.h"
#include "nv2a_gl.h"
#include "nv2a_overlay.h"
#include "ohci.h"
#include "recomp_types.h"
#include "scrap_image.h"
#include "xbox_memory_layout.h"
#include "../../runtime/pvideo.h"

#define APP_DIR "sdmc:/switch/scrapcomp-nx"
#define GAME_DIR APP_DIR "/game"
#define SAVE_DIR APP_DIR "/saves"
#define XBE_PATH GAME_DIR "/Default.xbe"
#define DIAGNOSTICS_FILE APP_DIR "/diagnostics.env"

extern MCPXAPUState *g_apu_state;
extern void xbe_entry_point(void);
extern int recomp_dispatch_init(void);
extern void xbox_path_init(const char *game_dir, const char *save_dir);
extern void xbox_nx_spread_thread(void);
extern void xbox_gil_mark_main(void);
extern void xbox_gil_enter(void);
extern void xbox_gil_leave(void);
extern int mcpx_apu_pacing_stats(char *buffer, int capacity);

static void *load_xbe(void)
{
    FILE *file = fopen(XBE_PATH, "rb");
    if (!file) {
        fprintf(stderr, "[BOOT] cannot open %s: %s\n", XBE_PATH, strerror(errno));
        return NULL;
    }
    void *image = malloc(SCRAP_IMAGE_SIZE);
    int valid_size = image && fread(image, 1, SCRAP_IMAGE_SIZE, file) == SCRAP_IMAGE_SIZE
        && fgetc(file) == EOF && !ferror(file);
    fclose(file);
    if (valid_size) {
        unsigned char digest[32];
        char hex[65];
        sha256CalculateHash(digest, image, SCRAP_IMAGE_SIZE);
        for (unsigned i = 0; i < sizeof digest; ++i)
            snprintf(hex + 2 * i, 3, "%02x", (unsigned)digest[i]);
        if (strcmp(hex, SCRAP_IMAGE_SHA256) == 0)
            return image;
        fprintf(stderr, "[BOOT] XBE SHA256 mismatch: %s\n", hex);
    } else {
        fprintf(stderr, "[BOOT] cannot read %ld bytes from %s\n", SCRAP_IMAGE_SIZE, XBE_PATH);
    }
    free(image);
    return NULL;
}

static uint32_t apu_read(void *state, uint32_t offset, unsigned size)
{
    return (uint32_t)mcpx_apu_mmio_read(state, offset, size);
}

static void apu_write(void *state, uint32_t offset, uint32_t value, unsigned size)
{
    mcpx_apu_mmio_write(state, offset, value, size);
}

static void observe_audio(const int16_t *input, const int16_t *output, int frames,
                          int queued_before, const Xa2Stats *stats)
{
    static uint64_t start, last_report;
    static unsigned peak;
    (void)input;
    uint64_t now = armTicksToNs(armGetSystemTick()) / 1000000;
    if (!start) start = last_report = now;
    for (int i = 0; i < frames * 2; ++i) {
        unsigned amplitude = (unsigned)abs(output[i]);
        if (amplitude > peak) peak = amplitude;
    }
    if (now - last_report < 2000) return;
    char pacing[256];
    mcpx_apu_pacing_stats(pacing, sizeof pacing);
    fprintf(stderr, "[SWITCH-AUDIO] ms=%llu frames=%llu submitted=%llu dropped=%llu "
        "underruns=%llu clipped=%llu peak=%u queue_before=%d apu_fps=%d busy=%.1f%%; %s\n",
        (unsigned long long)(now - start), (unsigned long long)stats->samples,
        (unsigned long long)stats->submitted, (unsigned long long)stats->dropped,
        (unsigned long long)stats->underruns, (unsigned long long)stats->clipped,
        peak, queued_before, mcpx_apu_frames_per_second(),
        100.0 * mcpx_apu_utilization(), pacing);
    last_report = now;
    peak = 0;
}

static int present_video(const uint32_t *pixels, uint32_t width, uint32_t height,
                         uint32_t output_width, uint32_t output_height)
{
    static unsigned frames;
    if (++frames == 119) {
        const char *dump = getenv("RECOMP_PVIDEO_DUMP");
        if (dump) {
            FILE *out = fopen(dump, "wb");
            size_t count = (size_t)width * height;
            size_t written = out ? fwrite(pixels, sizeof *pixels, count, out) : 0;
            int error = out ? fclose(out) : EOF;
            fprintf(stderr, "[PVIDEO] CPU scanout snapshot: %ux%u %zu/%zu pixels to %s\n",
                width, height, written, count, dump);
            if (written != count || error) exit(83);
        }
    }
    return nv2a_gl_present_overlay(pixels, width, height, output_width, output_height);
}

static void poll_video(void)
{
    uint64_t us = armTicksToNs(armGetSystemTick()) / 1000;
    if (scrap_pvideo_tick((uintptr_t)g_xbox_mem_offset, us, present_video) < 0) {
        fprintf(stderr, "[FAULT] PVIDEO scanout failed\n");
        exit(83);
    }
}

void nv2a_host_frame_presented(uint32_t width, uint32_t height)
{
    static unsigned count;
    ++count;
    if (count <= 3 || count % 60 == 0)
        fprintf(stderr, "[FRAME] present=%u drawn_surface=%ux%u\n", count, width, height);
}

static void firmware_report(uint32_t routine)
{
    const uintptr_t mem = (uintptr_t)g_xbox_mem_offset;
    fprintf(stderr, "[EXIT] firmware=%u engine_error=%u journal_index=%u: %.1023s\n",
        routine, *(const uint32_t *)(mem + 0x3AF554), *(const uint32_t *)(mem + 0x3AF54C),
        (const char *)(mem + 0x3AE570));
}

static int configure_diagnostics(void)
{
    static const char *const allowed[] = {
        "RECOMP_PAD_SCRIPT", "RECOMP_USB_TRACE", "RECOMP_GL_DUMP", "RECOMP_GL_TRACE",
        "RECOMP_PVIDEO_DUMP",
        "RECOMP_AUDIO_DUMP", "RECOMP_AUDIO_METRICS", "RECOMP_WATCHDOG_SECS", "RECOMP_WATCHDOG_KEEP",
        "RECOMP_NX_SHM",
    };
    FILE *file = fopen(DIAGNOSTICS_FILE, "r");
    if (!file) {
        if (errno == ENOENT) return 1;
        perror(DIAGNOSTICS_FILE);
        return 0;
    }

    char line[4096];
    unsigned line_number = 0;
    int valid = 1;
    while (valid && fgets(line, sizeof line, file)) {
        ++line_number;
        size_t end = strcspn(line, "\r\n");
        if (!line[end] && !feof(file)) {
            valid = 0;
            break;
        }
        line[end] = '\0';
        if (!line[0] || line[0] == '#') continue;
        char *value = strchr(line, '=');
        if (!value || !value[1]) {
            valid = 0;
            break;
        }
        *value++ = '\0';
        valid = 0;
        for (unsigned i = 0; i < sizeof allowed / sizeof *allowed; ++i) {
            if (strcmp(line, allowed[i]) == 0) {
                valid = setenv(line, value, 1) == 0;
                break;
            }
        }
    }
    valid = valid && !ferror(file);
    fclose(file);
    if (!valid)
        fprintf(stderr, "[BOOT] invalid diagnostics configuration near line %u of %s\n",
            line_number, DIAGNOSTICS_FILE);
    return valid;
}

static int game_main(void)
{
    fprintf(stderr, "[BOOT] scrapcomp-nx Switch; expected XBE %s\n", SCRAP_IMAGE_SHA256);
    if (!configure_diagnostics()) return 3;
    if (setenv("RECOMP_USB", "1", 1) || setenv("RECOMP_PB_EXEC", "1", 1) ||
        setenv("RECOMP_VBLANK", "1", 1) || setenv("RECOMP_AC97_READY", "plain", 1)) {
        perror("[BOOT] setenv");
        return 3;
    }
    void *image = load_xbe();
    if (!image) return 2;
    if (!xbox_MemoryLayoutInit(image, SCRAP_IMAGE_SIZE)) {
        fprintf(stderr, "[BOOT] guest memory mapping failed\n");
        free(image);
        return 3;
    }
    g_xbox_mem_offset = xbox_GetMemoryOffset();
    fprintf(stderr, "[BOOT] guest memory mapped; offset=0x%llX\n", (unsigned long long)g_xbox_mem_offset);

    if (!xbox_Nv2aInstallPollHook(poll_video)) {
        fprintf(stderr, "[BOOT] failed to install the PVIDEO poll hook\n");
        exit(83);
    }
    SDL_SetMainReady();
    nv2a_gl_install();
    xbox_OhciInit();
    if (getenv("RECOMP_AUDIO_METRICS"))
        xa2_set_observer(observe_audio);
    g_apu_state = mcpx_apu_init_standalone((uint8_t *)xbox_GetMemoryBase());
    if (!g_apu_state || xbox_MmioRegister(0xFE800000u, 0xFE880000u,
                                         apu_read, apu_write, g_apu_state)) {
        fprintf(stderr, "[BOOT] MCPX APU initialization or MMIO registration failed\n");
        exit(84);
    }
    fprintf(stderr, "[BOOT] MCPX APU connected to lifted DSOUND MMIO with real GP/EP execution\n");
    if (!xa2_is_active()) {
        fprintf(stderr, "[BOOT] audio output is inactive\n");
        exit(84);
    }
    xbox_kernel_init();
    xbox_path_init(GAME_DIR, SAVE_DIR);
    xbox_kernel_bridge_init();
    g_esp = XBOX_STACK_TOP - 4;
    *(uint32_t *)((uintptr_t)g_xbox_mem_offset + g_esp) = 0;
    if (!recomp_dispatch_init()) fprintf(stderr, "[BOOT] using binary-search dispatch\n");
    xbox_WatchdogStart();
    xbox_SetFirmwareObserver(firmware_report);
    fprintf(stderr, "[BOOT] enter guest=0x%08X esp=0x%08X\n", SCRAP_ENTRY_POINT, g_esp);
    xbox_gil_mark_main();
    xbox_gil_enter();
    xbe_entry_point();
    xbox_gil_leave();
    fprintf(stderr, "[BOOT] XBE entry returned\n");
    xbox_kernel_shutdown();
    mcpx_apu_shutdown(g_apu_state);
    g_apu_state = NULL;
    xbox_MemoryLayoutShutdown();
    free(image);
    return 0;
}

static void *game_thread(void *arg)
{
    xbox_nx_spread_thread();
    *(int *)arg = game_main();
    return NULL;
}

int main(void)
{
    if ((mkdir(APP_DIR, 0777) && errno != EEXIST) ||
        (mkdir(SAVE_DIR, 0777) && errno != EEXIST))
        return 2;
    if (!freopen(APP_DIR "/stderr.log", "w", stderr) ||
        !freopen(APP_DIR "/stdout.log", "w", stdout))
        return 2;
    setvbuf(stderr, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);

    /* The original entry runs inline and needs more native stack than the
     * libnx main thread. Runtime-created guest threads retain their own ABI. */
    pthread_attr_t attr;
    pthread_t thread;
    int result = 3;
    int status = pthread_attr_init(&attr);
    if (!status) {
        status = pthread_attr_setstacksize(&attr, 16 * 1024 * 1024);
        if (!status) status = pthread_create(&thread, &attr, game_thread, &result);
        pthread_attr_destroy(&attr);
        if (!status) status = pthread_join(thread, NULL);
    }
    if (status) {
        fprintf(stderr, "[BOOT] game thread: %s\n", strerror(status));
        return 3;
    }
    return result;
}
