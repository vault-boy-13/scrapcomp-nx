/* Independent bounded PVIDEO model. Register behavior reference:
 * xemu 711b416840c2a528cb989621b6456a72bd02d768 hw/xbox/nv2a/pvideo.c
 * and pgraph/gl/display.c. No QEMU/xemu source is copied into this file.
 * Current mode: packed YUY2, unity luminance/chrominance, origin-to-origin,
 * full-frame scaled video. Other modes remain visible errors. */
#include "pvideo.h"
#include <stdio.h>
#include <stdlib.h>

static uint32_t *pixels;
static size_t pixel_capacity;
static uint64_t next_scanout;
static unsigned shown, stopped;
static unsigned char byte_clamp(int value)
{
    return value < 0 ? 0 : value > 255 ? 255 : (unsigned char)value;
}

int scrap_pvideo_tick(uintptr_t guest_offset, uint64_t now_us, ScrapVideoPresent present)
{
    volatile uint32_t *registers = (volatile uint32_t *)(guest_offset + 0xFD000000u);
#define VIDEO(r) registers[(r) / 4]
    if (VIDEO(0x8704) & 1) {
        VIDEO(0x8700) = 0; /* stop disables scanout; BUFFER is not a completion counter */
        VIDEO(0x8704) = 0; /* STOP reads zero */
        if (stopped++ < 8) fprintf(stderr, "[PVIDEO] scanout stopped\n");
        next_scanout = 0;
        return 0;
    }
    uint32_t use = VIDEO(0x8700);
    if (!(use & 0x11)) { next_scanout = 0; return 0; }
    uint32_t bank = (use & 1) ? 0 : 4;
    uint32_t size_in = VIDEO(0x8928 + bank);
    if (!size_in || size_in == 0xFFFFFFFFu) return 0;
    if (now_us < next_scanout) return 0;
    uint32_t width = size_in & 0x7FF, height = (size_in >> 16) & 0x7FF;
    uint32_t format = VIDEO(0x8958 + bank), pitch = format & 0x1FFF;
    uint32_t size_out = VIDEO(0x8950 + bank);
    uint32_t out_width = size_out & 0xFFF, out_height = (size_out >> 16) & 0xFFF;
    uint32_t base = VIDEO(0x8900 + bank), offset = VIDEO(0x8920 + bank);
    uint32_t limit = VIDEO(0x8908 + bank);
    if (!width || !height || (width & 1) || pitch < width*2 || !out_width || !out_height ||
        (format & 0x130000) != 0x10000 || VIDEO(0x8930 + bank) || VIDEO(0x8948 + bank) ||
        VIDEO(0x8910 + bank) != 0x1000 || VIDEO(0x8918 + bank) != 0x1000) {
        fprintf(stderr, "[PVIDEO] unsupported layout in=%08X out=%08X fmt=%08X\n", size_in, size_out, format);
        return -1;
    }
    /* Reached scaling maps the complete source image to the output rectangle.
     * Verify the programmed fixed-point steps rather than silently ignoring them. */
    uint32_t src_x = (uint32_t)(((uint64_t)VIDEO(0x8938 + bank)*(out_width-1) + 0x80000) >> 20) + 1;
    uint32_t src_y = (uint32_t)(((uint64_t)VIDEO(0x8940 + bank)*(out_height-1) + 0x80000) >> 20) + 1;
    if (src_x != width || src_y != height) {
        fprintf(stderr, "[PVIDEO] unsupported crop/scale %ux%u -> %ux%u\n", src_x, src_y, width, height);
        return -1;
    }
    uint64_t end = (uint64_t)base + offset + (uint64_t)(height-1)*pitch + width*2;
    if (end > 0x04000000u || (uint64_t)offset + (height-1)*(uint64_t)pitch + width*2 > limit) {
        fprintf(stderr, "[PVIDEO] invalid source range %08X + %08X pitch=%u\n", base, offset, pitch);
        return -1;
    }
    size_t count = (size_t)width*height;
    if (count > pixel_capacity) {
        uint32_t *replacement = realloc(pixels, count*sizeof(*pixels));
        if (!replacement) return -1;
        pixels = replacement; pixel_capacity = count;
    }
    const uint8_t *source = (const uint8_t *)(guest_offset + 0x80000000u + base + offset);
    for (uint32_t y=0;y<height;y++) {
        const uint8_t *row = source + (size_t)y*pitch;
        for (uint32_t x=0;x<width;x++) {
            const uint8_t *pair = row + (x & ~1u)*2;
            int luminance = (int)pair[(x & 1)*2] - 16;
            int u = (int)pair[1]-128, v = (int)pair[3]-128;
            unsigned r = byte_clamp((298*luminance+409*v+128)>>8);
            unsigned g = byte_clamp((298*luminance-100*u-208*v+128)>>8);
            unsigned b = byte_clamp((298*luminance+516*u+128)>>8);
            pixels[(size_t)y*width+x] = 0xFF000000u | (r<<16) | (g<<8) | b;
        }
    }
    if (VIDEO(0x8920 + bank) != offset || VIDEO(0x8928 + bank) != size_in ||
        VIDEO(0x8704) & 1) return 0; /* producer changed frame while sampling */
    if (!present(pixels, width, height, out_width, out_height)) return -1;
    next_scanout = now_us + 16683;
    if (shown++ < 3 || shown % 60 == 0)
        fprintf(stderr, "[PVIDEO] frame=%u source=%08X %ux%u pitch=%u -> %ux%u\n",
                shown, 0x80000000u+base+offset, width, height, pitch, out_width, out_height);
    return 1;
#undef VIDEO
}
