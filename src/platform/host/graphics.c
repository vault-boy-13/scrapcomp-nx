/* Native host observation for the shared raw NV2A renderer. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <stdio.h>
#include <stdint.h>
#include "nv2a_gl.h"
#include "nv2a_overlay.h"
#include "nv2a_backend.h"
#include "xbox_memory_layout.h"
#include "../../runtime/pvideo.h"
#include <windows.h>
#include <stdlib.h>
#include <string.h>
#include "renderdoc_capture.h"

extern ptrdiff_t g_xbox_mem_offset;
static volatile LONG video_presented;
static int in_video_poll;
static void (*previous_batch_hook)(Nv2aRawBatch *, float *);
static ULONGLONG state_dump_at;

/* Bounded, read-only method-shadow snapshots for reached fixed-function draws. */
static void graphics_observe_batch(Nv2aRawBatch *batch, float *attrs)
{
    static uint32_t seen[16][5];
    static unsigned count;
    if (previous_batch_hook) previous_batch_hook(batch, attrs);
    if (count == 16 || GetTickCount64() < state_dump_at || batch->xform != 1) return;
    const uint32_t *r = batch->regs;
    uint32_t key[5] = {batch->attr_present, r[0x314/4], r[0x3BC/4], r[0x1E70/4], r[0x1E60/4]};
    for (unsigned i=0; i<count; ++i) if (!memcmp(key,seen[i],sizeof key)) return;
    memcpy(seen[count],key,sizeof key);
    char name[64];
    snprintf(name,sizeof name,"ffp-state-%02u.bin",count++);
    FILE *file=fopen(name,"wb");
    if (!file || fwrite(r,1,0x2000,file)!=0x2000) {
        if(file) fclose(file);
        fprintf(stderr,"[FAULT] could not save bounded GPU state\n");ExitProcess(84);
    }
    fclose(file);
    fprintf(stderr,"[GPU-STATE] %s attrs=%04X lighting=%u lights=%08X colmat=%08X shader=%08X control=%08X\n",
            name,batch->attr_present,r[0x314/4],r[0x3BC/4],r[0x298/4],r[0x1E70/4],r[0x1E60/4]);
}

static void graphics_device_poll(void)
{
    uint64_t ticks = SDL_GetPerformanceCounter(), frequency = SDL_GetPerformanceFrequency();
    uint64_t us = (ticks/frequency)*1000000 + (ticks%frequency)*1000000/frequency;
    in_video_poll=1;
    int status = scrap_pvideo_tick((uintptr_t)g_xbox_mem_offset, us, nv2a_gl_present_overlay);
    in_video_poll=0;
    if (status < 0) {
        fprintf(stderr, "[FAULT] PVIDEO scanout failed; unsupported mode is not discarded\n");
        ExitProcess(83);
    }
    if (status > 0) InterlockedIncrement(&video_presented);
}

void scrap_host_graphics_install(void)
{
    if(!scrap_host_renderdoc_install()) ExitProcess(84);
    SDL_SetMainReady();
    nv2a_gl_install();
    const char *state_at=getenv("RECOMP_GPU_STATE_AT");
    if(state_at) {
        char *tail;unsigned long seconds=strtoul(state_at,&tail,10);
        if(!*state_at || *tail || seconds>300) ExitProcess(84);
        state_dump_at=GetTickCount64()+(ULONGLONG)seconds*1000;
        previous_batch_hook=nv2a_raw_batch_hook;
        nv2a_raw_batch_hook=graphics_observe_batch;
    }
    if (!xbox_Nv2aInstallPollHook(graphics_device_poll)) ExitProcess(83);
    fprintf(stderr, "[BOOT] raw NV2A OpenGL backend installed; context creation is lazy\n");
}

int scrap_host_pvideo_smoke(void)
{
    volatile uint32_t *regs = (volatile uint32_t *)((uintptr_t)g_xbox_mem_offset + 0xFD000000u);
    uint8_t *bytes = (uint8_t *)((uintptr_t)g_xbox_mem_offset + 0x80100000u);
    const uint8_t yuy2[16] = {16,128,235,128,0,0,0,0,81,90,81,240,0,0,0,0};
    memcpy(bytes, yuy2, sizeof yuy2);
    regs[0x8900/4]=0; regs[0x8908/4]=0x4000000;
    regs[0x8910/4]=regs[0x8918/4]=0x1000;
    regs[0x8920/4]=0x100000; regs[0x8928/4]=0x20002;
    regs[0x8930/4]=regs[0x8948/4]=0;
    regs[0x8938/4]=regs[0x8940/4]=0x100000;
    regs[0x8950/4]=0x20002; regs[0x8958/4]=0x10008;
    InterlockedExchange((volatile LONG *)&regs[0x8700/4],1);
    ULONGLONG deadline = GetTickCount64()+3000;
    while (InterlockedCompareExchange(&video_presented,0,0)<2 && GetTickCount64()<deadline) Sleep(1);
    if (video_presented<2) return 83;
    InterlockedExchange((volatile LONG *)&regs[0x8704/4],1);
    while (regs[0x8700/4] && GetTickCount64()<deadline) Sleep(1);
    if (regs[0x8700/4] || regs[0x8704/4]) return 83;
    fprintf(stderr,"[BOOT] synthetic PVIDEO frames submitted; verify BMP readback pixels\n");
    return 0;
}

void nv2a_host_frame_presented(uint32_t width, uint32_t height)
{
    scrap_host_renderdoc_presented(!in_video_poll);
    static unsigned frames;
    static int profile=-1;
    static FILE *timings;
    static LARGE_INTEGER frequency, start;
    ++frames;
    if(profile<0) {
        const char *value=getenv("RECOMP_HOST_PROFILE");
        profile=value && !strcmp(value,"1");
        if(profile) {
            timings=fopen("present-times.csv","wb");
            QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&start);
            if(timings) fprintf(timings,"present,ms,source,width,height\n");
        }
    }
    if(timings) {
        LARGE_INTEGER now;QueryPerformanceCounter(&now);
        fprintf(timings,"%u,%.6f,%s,%u,%u\n",frames,
            (now.QuadPart-start.QuadPart)*1000.0/frequency.QuadPart,
            in_video_poll?"video_refresh":"3d_present",width,height);
        if(frames%60==0) fflush(timings);
    }
    if (frames <= 3 || frames % 60 == 0)
        fprintf(stderr, "[FRAME] present=%u drawn_surface=%ux%u\n", frames, width, height);
}

/* Known NV097 state and clear commands; no guest instructions are executed. */
static int texture_decode_smoke(void)
{
    uint16_t *input=(uint16_t *)((uintptr_t)g_xbox_mem_offset+0x80100000u);
    uint32_t *output=(uint32_t *)malloc(65536*sizeof(uint32_t));
    Nv2aTexture texture={0};
    if (!output) return 0;
    texture.offset=0x80100000; texture.width=256; texture.height=256;
    texture.pitch=512; texture.color=0x17;
    for (unsigned i=0;i<65536;++i) input[i]=(uint16_t)i;
    if (!nv2a_backend_decode_texture(&texture,output)) { free(output); return 0; }
    for (unsigned i=0;i<65536;++i) {
        unsigned lo=i&255,hi=i>>8;
        if (output[i]!=((hi<<24)|(lo<<16)|(hi<<8)|lo)) { free(output); return 0; }
    }
    {
        /* Hand-listed Morton order for a non-square 4x2 image. */
        const unsigned morton[]={0,1,4,5,2,3,6,7};
        texture.width=4; texture.height=2; texture.pitch=0; texture.color=0x28;
        for (unsigned i=0;i<8;++i) input[i]=(uint16_t)((i*17<<8)|(255-i*29));
        if (!nv2a_backend_decode_texture(&texture,output)) { free(output); return 0; }
        for (unsigned i=0;i<8;++i) {
            unsigned lo=255-morton[i]*29,hi=morton[i]*17;
            if (output[i]!=((hi<<24)|(lo<<16)|(hi<<8)|lo)) { free(output); return 0; }
        }
        texture.color=0x17; texture.pitch=12;
        for (unsigned i=0;i<12;++i) input[i]=(uint16_t)((i*11<<8)|(i*19));
        if (!nv2a_backend_decode_texture(&texture,output)) { free(output); return 0; }
        for (unsigned i=0;i<8;++i) {
            unsigned source=i+(i>=4?2:0),lo=source*19,hi=source*11;
            if (output[i]!=((hi<<24)|(lo<<16)|(hi<<8)|lo)) { free(output); return 0; }
        }
        texture.color=0xFF;
        if (nv2a_backend_decode_texture(&texture,output)) { free(output); return 0; }
    }
    free(output);
    fprintf(stderr,"[TEXTURE] G8B8 PASS: 65552 exact texels, Morton rectangle, row padding, unknown-format rejection\n");
    return 1;
}

int scrap_host_graphics_smoke(void)
{
    extern void nv2a_pb_exec_method(uint32_t subchannel, uint32_t method, uint32_t value);
    uint32_t pixels[64 * 64], width = 0, height = 0;
    if (!texture_decode_smoke()) {
        fprintf(stderr,"[FAULT] G8B8 texture decoding failed\n"); return 82;
    }
    nv2a_pb_exec_method(0, 0x0200, 64u << 16);
    nv2a_pb_exec_method(0, 0x0204, 64u << 16);
    nv2a_pb_exec_method(0, 0x0208, 8);
    nv2a_pb_exec_method(0, 0x020C, 256);
    nv2a_pb_exec_method(0, 0x0210, 0x00100000);
    for (unsigned i = 0; i < 4; ++i) {
        uint32_t expected = (i & 1) ? 0xFFCC6633 : 0xFF3366CC;
        nv2a_pb_exec_method(0, 0x1D90, expected);
        nv2a_pb_exec_method(0, 0x1D94, 0xF0);
        if (nv2a_gl_readback(0x80100000, pixels, 1, &width, &height) ||
            nv2a_gl_readback(0x81234560, pixels, 64 * 64, &width, &height) ||
            !nv2a_gl_readback(0x80100000, pixels, 64 * 64, &width, &height) ||
            width != 64 || height != 64) {
            fprintf(stderr, "[FAULT] graphics smoke readback failed\n"); return 82;
        }
        for (unsigned p = 0; p < 64 * 64; ++p) {
            if (pixels[p] != expected) {
                fprintf(stderr, "[FAULT] GPU pixel %u actual=%08X expected=%08X\n",
                        p, pixels[p], expected); return 82;
            }
        }
        /* A clip change must preserve allocation and previous pixels.
         * CLEAR_SURFACE with no bits binds the target without clearing it. */
        nv2a_pb_exec_method(0, 0x0200, (16u << 16) | 32u);
        nv2a_pb_exec_method(0, 0x0204, (24u << 16) | 8u);
        nv2a_pb_exec_method(0, 0x1D94, 0);
        if (!nv2a_gl_readback(0x80100000, pixels, 64*64, &width, &height) || width!=64 || height!=64) {
            fprintf(stderr,"[FAULT] clipping changed surface allocation\n"); return 82;
        }
        for (unsigned p=0;p<64*64;++p) {
            if (pixels[p]!=expected) {
                fprintf(stderr,"[FAULT] clipping destroyed prior GPU pixel %u\n",p); return 82;
            }
        }
        nv2a_pb_exec_method(0, 0x0200, 64u << 16);
        nv2a_pb_exec_method(0, 0x0204, 64u << 16);
        char path[64];
        snprintf(path, sizeof path, "readback%03u.argb", i);
        FILE *output = fopen(path, "wb");
        if (!output) return 82;
        size_t written = fwrite(pixels, sizeof pixels, 1, output);
        int closed = fclose(output);
        if (written != 1 || closed) return 82;
        fprintf(stderr, "[FRAME] verified readback=%u surface=80100000 pixels=4096 ARGB=%08X\n",
                i, expected);
        nv2a_pb_exec_method(0, 0x0130, 0);
    }
    fprintf(stderr, "[BOOT] synthetic graphics commands finished; readback must be verified\n");
    return 0;
}
