#ifndef SCRAP_PVIDEO_H
#define SCRAP_PVIDEO_H
#include <stdint.h>
#include <stddef.h>
typedef int (*ScrapVideoPresent)(const uint32_t *argb, uint32_t width, uint32_t height,
                                 uint32_t logical_width, uint32_t logical_height);
/* 0 inactive/not due, 1 displayed, -1 unsupported or invalid. */
int scrap_pvideo_tick(uintptr_t guest_offset, uint64_t now_us, ScrapVideoPresent present);
#endif
