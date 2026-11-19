/* Exercise a real donor format conversion; no guest title or window needed. */
#include <stdio.h>
#include <stdint.h>
#include "d3d8_swizzle.h"

int main(void)
{
    puts("Scrapland workspace: native host compiler/linker probe");
    puts("Original Xbox tooling; no game code has been executed.");
    /* Morton address calculation is supplied by the pinned runtime header. */
    for (uint32_t value = 0; value < 65536; ++value)
        if (swizzle_compact(swizzle_spread(value)) != value) return 2;
    printf("runtime Morton spread/compact: PASS (65536 values); pointer width = %zu\n", sizeof(void*));
    return sizeof(void*) == 8 ? 0 : 1;
}
