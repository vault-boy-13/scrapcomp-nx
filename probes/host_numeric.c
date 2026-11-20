/* Check the actual runtime helper used by lifted SSE conversions on MSVC. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include "recomp_types.h"

int main(void)
{
    const struct { double value; int rounded; int truncated; } cases[] = {
        {0.5, 0, 0}, {1.5, 2, 1}, {2.5, 2, 2}, {-0.5, 0, 0},
        {-1.5, -2, -1}, {-2.5, -2, -2}, {2147483647.0, INT32_MAX, INT32_MAX},
        {2147483648.0, INT32_MIN, INT32_MIN}, {-2147483648.0, INT32_MIN, INT32_MIN},
        {-2147483649.0, INT32_MIN, INT32_MIN}, {INFINITY, INT32_MIN, INT32_MIN},
        {-INFINITY, INT32_MIN, INT32_MIN}, {NAN, INT32_MIN, INT32_MIN},
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        int32_t rounded = recomp_cvt_si(cases[i].value, 1);
        int32_t truncated = recomp_cvt_si(cases[i].value, 0);
        if (rounded != cases[i].rounded || truncated != cases[i].truncated) {
            fprintf(stderr, "SSE conversion case %u failed: %d/%d\n", i, rounded, truncated);
            return 1;
        }
    }
    puts("SSE conversions: PASS (ties-to-even, truncation, int32 bounds, NaN/Inf)");
    return 0;
}
