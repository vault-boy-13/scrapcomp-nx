/* Replay one captured Scrapland PVIDEO frame through deko3d image transfers. */
#include <deko3d.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <switch.h>

#define CAPTURE_DIR "sdmc:/switch/scrapland-workspace/"
enum { WIDTH = 720, HEIGHT = 540, FRAME_BYTES = WIDTH * HEIGHT * 4 };

static uint32_t align_up(uint32_t size, uint32_t alignment)
{
    return (size + alignment - 1) & ~(alignment - 1);
}

static int replay_frame(FILE *log, FILE *source)
{
    DkDeviceMaker device_maker;
    dkDeviceMakerDefaults(&device_maker);
    DkDevice device = dkDeviceCreate(&device_maker);
    if (!device) return 2;

    DkQueue queue = NULL;
    DkCmdBuf commands = NULL;
    DkMemBlock staging = NULL, images = NULL, command_memory = NULL;
    int result = 3;
    const uint32_t frame_stride = align_up(FRAME_BYTES, DK_MEMBLOCK_ALIGNMENT);
    DkMemBlockMaker memory;
    dkMemBlockMakerDefaults(&memory, device, 2 * frame_stride);
    memory.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuUncached;
    staging = dkMemBlockCreate(&memory);
    if (!staging) goto cleanup;
    uint8_t *input = dkMemBlockGetCpuAddr(staging);
    uint8_t *output = input + frame_stride;
    if (fread(input, 1, FRAME_BYTES, source) != FRAME_BYTES ||
        fgetc(source) != EOF || ferror(source)) {
        fprintf(log, "Expected a 720x540 BGRA capture of %u bytes\n", FRAME_BYTES);
        goto cleanup;
    }
    memset(output, 0xA5, FRAME_BYTES);

    DkImageLayoutMaker layout_maker;
    dkImageLayoutMakerDefaults(&layout_maker, device);
    layout_maker.flags = DkImageFlags_Usage2DEngine;
    layout_maker.format = DkImageFormat_BGRA8_Unorm;
    layout_maker.dimensions[0] = WIDTH;
    layout_maker.dimensions[1] = HEIGHT;
    DkImageLayout layout;
    dkImageLayoutInitialize(&layout, &layout_maker);
    uint32_t image_stride = align_up(dkImageLayoutGetSize(&layout),
                                     dkImageLayoutGetAlignment(&layout));
    dkMemBlockMakerDefaults(&memory, device, align_up(2 * image_stride, DK_MEMBLOCK_ALIGNMENT));
    memory.flags = DkMemBlockFlags_GpuCached | DkMemBlockFlags_Image;
    images = dkMemBlockCreate(&memory);
    if (!images) goto cleanup;

    DkImage source_image, target_image;
    dkImageInitialize(&source_image, &layout, images, 0);
    dkImageInitialize(&target_image, &layout, images, image_stride);
    DkImageView source_view, target_view;
    dkImageViewDefaults(&source_view, &source_image);
    dkImageViewDefaults(&target_view, &target_image);
    DkGpuAddr staging_address = dkMemBlockGetGpuAddr(staging);
    const DkCopyBuf upload = {.addr = staging_address};
    const DkCopyBuf download = {.addr = staging_address + frame_stride};
    const DkImageRect rect = {0, 0, 0, WIDTH, HEIGHT, 1};

    dkMemBlockMakerDefaults(&memory, device, 16384);
    memory.flags = DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached;
    command_memory = dkMemBlockCreate(&memory);
    DkCmdBufMaker command_maker;
    dkCmdBufMakerDefaults(&command_maker, device);
    commands = dkCmdBufCreate(&command_maker);
    DkQueueMaker queue_maker;
    dkQueueMakerDefaults(&queue_maker, device);
    queue_maker.flags = DkQueueFlags_Graphics;
    queue = dkQueueCreate(&queue_maker);
    if (!command_memory || !commands || !queue) goto cleanup;

    fprintf(log, "Submitting captured frame to deko3d\n");
    dkCmdBufAddMemory(commands, command_memory, 0, 16384);
    dkCmdBufCopyBufferToImage(commands, &upload, &source_view, &rect, 0);
    dkCmdBufBarrier(commands, DkBarrier_Full, 0);
    dkCmdBufCopyImage(commands, &source_view, &rect, &target_view, &rect, 0);
    dkCmdBufBarrier(commands, DkBarrier_Full, 0);
    dkCmdBufCopyImageToBuffer(commands, &target_view, &rect, &download, 0);
    dkQueueSubmitCommands(queue, dkCmdBufFinishList(commands));
    dkQueueWaitIdle(queue);

    unsigned mismatches = 0;
    for (size_t i = 0; i < FRAME_BYTES; i += 4) {
        if (memcmp(input + i, output + i, 4)) ++mismatches;
    }
    fprintf(log, "%u/%u BGRA pixels match the captured frame\n",
            WIDTH * HEIGHT - mismatches, WIDTH * HEIGHT);
    FILE *readback = fopen(CAPTURE_DIR "deko-game-frame.argb", "wb");
    if (readback) {
        size_t written = fwrite(output, 1, FRAME_BYTES, readback);
        int close_error = fclose(readback);
        if (written == FRAME_BYTES && !close_error) result = mismatches ? 4 : 0;
    }

cleanup:
    if (queue) dkQueueDestroy(queue);
    if (commands) dkCmdBufDestroy(commands);
    if (command_memory) dkMemBlockDestroy(command_memory);
    if (images) dkMemBlockDestroy(images);
    if (staging) dkMemBlockDestroy(staging);
    dkDeviceDestroy(device);
    return result;
}

int main(void)
{
    FILE *log = fopen(CAPTURE_DIR "deko-game-frame.log", "w");
    if (!log) return 1;
    setvbuf(log, NULL, _IONBF, 0);
    FILE *capture = fopen(CAPTURE_DIR "pvideo-119.argb", "rb");
    int result = 1;
    if (capture) {
        result = replay_frame(log, capture);
        fclose(capture);
    }
    fprintf(log, "Replay exit=%d\n", result);
    fclose(log);
    return result;
}
