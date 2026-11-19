/* Minimal deko3d/UAM/swapchain probe using the official public C API.
 * API usage follows devkitPro switch-examples/deko_basic and deko3d Primer.
 * This is a triangle; no NV2A shader translator or game renderer is claimed.
 */
#include <switch.h>
#include <deko3d.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static int load_shader(DkShader *shader, DkMemBlock memory, uint32_t *cursor, const char *path)
{
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    rewind(file);
    if (size <= 0 || *cursor + (uint32_t)size > 65536) { fclose(file); return 0; }
    int ok = fread((char *)dkMemBlockGetCpuAddr(memory) + *cursor, 1, size, file) == (size_t)size;
    fclose(file);
    if (!ok) return 0;
    DkShaderMaker maker;
    dkShaderMakerDefaults(&maker, memory, *cursor);
    dkShaderInitialize(shader, &maker);
    *cursor += ((uint32_t)size + DK_SHADER_CODE_ALIGNMENT - 1) & ~(DK_SHADER_CODE_ALIGNMENT - 1);
    return 1;
}

int main(void)
{
    if (R_FAILED(romfsInit())) return 1;
    DkDeviceMaker device_maker;
    dkDeviceMakerDefaults(&device_maker);
    DkDevice device = dkDeviceCreate(&device_maker);
    if (!device) return 2;
    DkImageLayoutMaker layout_maker;
    dkImageLayoutMakerDefaults(&layout_maker, device);
    layout_maker.flags = DkImageFlags_UsageRender | DkImageFlags_UsagePresent;
    layout_maker.format = DkImageFormat_RGBA8_Unorm;
    layout_maker.dimensions[0] = 1280;
    layout_maker.dimensions[1] = 720;
    DkImageLayout layout;
    dkImageLayoutInitialize(&layout, &layout_maker);
    uint32_t align = dkImageLayoutGetAlignment(&layout);
    uint32_t stride = (dkImageLayoutGetSize(&layout) + align - 1) & ~(align - 1);
    DkMemBlockMaker memory_maker;
    dkMemBlockMakerDefaults(&memory_maker, device, stride * 2);
    memory_maker.flags = DkMemBlockFlags_GpuCached | DkMemBlockFlags_Image;
    DkMemBlock images_memory = dkMemBlockCreate(&memory_maker);
    DkImage images[2];
    const DkImage *image_pointers[2] = {&images[0], &images[1]};
    for (int i = 0; i < 2; ++i) dkImageInitialize(&images[i], &layout, images_memory, stride * i);
    DkSwapchainMaker swapchain_maker;
    dkSwapchainMakerDefaults(&swapchain_maker, device, nwindowGetDefault(), image_pointers, 2);
    DkSwapchain swapchain = dkSwapchainCreate(&swapchain_maker);
    dkMemBlockMakerDefaults(&memory_maker, device, 65536);
    memory_maker.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached | DkMemBlockFlags_Code;
    DkMemBlock code_memory = dkMemBlockCreate(&memory_maker);
    DkShader vertex, fragment;
    uint32_t cursor = 0;
    if (!load_shader(&vertex, code_memory, &cursor, "romfs:/shaders/triangle.vert.dksh") ||
        !load_shader(&fragment, code_memory, &cursor, "romfs:/shaders/triangle.frag.dksh")) return 3;
    dkMemBlockMakerDefaults(&memory_maker, device, 16384);
    memory_maker.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached;
    DkMemBlock command_memory = dkMemBlockCreate(&memory_maker);
    DkCmdBufMaker command_maker;
    dkCmdBufMakerDefaults(&command_maker, device);
    DkCmdBuf commands = dkCmdBufCreate(&command_maker);
    dkCmdBufAddMemory(commands, command_memory, 0, 16384);
    DkCmdList bind_target[2];
    for (int i = 0; i < 2; ++i) {
        DkImageView view;
        dkImageViewDefaults(&view, &images[i]);
        dkCmdBufBindRenderTarget(commands, &view, NULL);
        bind_target[i] = dkCmdBufFinishList(commands);
    }
    DkViewport viewport = {0, 0, 1280, 720, 0, 1};
    DkScissor scissor = {0, 0, 1280, 720};
    const DkShader *shaders[] = {&vertex, &fragment};
    DkRasterizerState raster;
    DkColorState color;
    DkColorWriteState color_write;
    dkRasterizerStateDefaults(&raster);
    dkColorStateDefaults(&color);
    dkColorWriteStateDefaults(&color_write);
    dkCmdBufSetViewports(commands, 0, &viewport, 1);
    dkCmdBufSetScissors(commands, 0, &scissor, 1);
    dkCmdBufClearColorFloat(commands, 0, DkColorMask_RGBA, 0.03f, 0.08f, 0.13f, 1);
    dkCmdBufBindShaders(commands, DkStageFlag_GraphicsMask, shaders, 2);
    dkCmdBufBindRasterizerState(commands, &raster);
    dkCmdBufBindColorState(commands, &color);
    dkCmdBufBindColorWriteState(commands, &color_write);
    dkCmdBufDraw(commands, DkPrimitive_Triangles, 3, 1, 0, 0);
    DkCmdList triangle = dkCmdBufFinishList(commands);
    DkQueueMaker queue_maker;
    dkQueueMakerDefaults(&queue_maker, device);
    queue_maker.flags = DkQueueFlags_Graphics;
    DkQueue queue = dkQueueCreate(&queue_maker);
    mkdir("sdmc:/switch", 0777);
    mkdir("sdmc:/switch/scrapland-workspace", 0777);
    FILE *log = fopen("sdmc:/switch/scrapland-workspace/deko-probe.log", "w");
    if (log) { fputs("deko3d device, DKSH shaders and swapchain created\n", log); fflush(log); }
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    if (log) { fputs("pad initialized; entering applet loop\n", log); fflush(log); }
    unsigned frames = 0;
    while (appletMainLoop()) {
        if (!frames && log) { fputs("frame 0: loop entered\n", log); fflush(log); }
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        if (!frames && log) { fputs("frame 0: acquiring image\n", log); fflush(log); }
        int slot = dkQueueAcquireImage(queue, swapchain);
        if (!frames && log) { fputs("frame 0: submitting commands\n", log); fflush(log); }
        dkQueueSubmitCommands(queue, bind_target[slot]);
        dkQueueSubmitCommands(queue, triangle);
        dkQueuePresentImage(queue, swapchain, slot);
        if (!frames && log) { fputs("frame 0: present returned\n", log); fflush(log); }
        if (++frames == 60 && log) { fputs("presented 60 frames\n", log); fflush(log); }
    }
    if (log) { fprintf(log,"applet loop ended after %u frames\n",frames); fflush(log); }
    dkQueueWaitIdle(queue);
    if (log) fclose(log);
    dkQueueDestroy(queue);
    dkCmdBufDestroy(commands);
    dkSwapchainDestroy(swapchain);
    dkMemBlockDestroy(command_memory);
    dkMemBlockDestroy(code_memory);
    dkMemBlockDestroy(images_memory);
    dkDeviceDestroy(device);
    romfsExit();
    return 0;
}
