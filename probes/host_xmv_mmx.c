/* Compare the runtime helpers reached by XMV with independent SSE2 hardware
 * operations. No original game code or media is included in this fixture. */
#include <emmintrin.h>
#include <stdio.h>
#define RECOMP_GENERATED_CODE
#include "recomp_types.h"

static uint64_t random_bits(void)
{
    static uint64_t state = UINT64_C(0x5c8d8f0512a793ab);
    state ^= state << 13; state ^= state >> 7; state ^= state << 17;
    return state;
}

static unsigned checks;
static int equal(const char *name, RecompMmx got, __m128i expected)
{
    uint64_t bits = (uint64_t)_mm_cvtsi128_si64(expected);
    ++checks;
    if (got.q == bits) return 1;
    fprintf(stderr, "%s: got %016llX expected %016llX\n", name,
            (unsigned long long)got.q, (unsigned long long)bits);
    return 0;
}

#define CHECK(name, expression) do { if (!equal(#name, name(a,b), (expression))) return 1; } while (0)
#define SHIFT(name, expression) do { if (!equal(#name, name(a,count), (expression))) return 1; } while (0)

int main(void)
{
    static const uint64_t edge[] = {0, UINT64_MAX, UINT64_C(0x8000800080008000),
        UINT64_C(0x7fff7fff7fff7fff), UINT64_C(0x0080008000800080),
        UINT64_C(0x8000000080000000), UINT64_C(0x7fffffff7fffffff)};
    static const uint64_t counts[] = {0,1,7,8,15,16,17,31,32,33,63,64,65,UINT64_MAX};
    for (unsigned i=0;i<20000;++i) {
        RecompMmx a,b;
        a.q = i<49 ? edge[i/7] : random_bits();
        b.q = i<49 ? edge[i%7] : random_bits();
        __m128i x=_mm_cvtsi64_si128((int64_t)a.q), y=_mm_cvtsi64_si128((int64_t)b.q);
        CHECK(MMX_PADDB,_mm_add_epi8(x,y)); CHECK(MMX_PADDW,_mm_add_epi16(x,y));
        CHECK(MMX_PADDD,_mm_add_epi32(x,y)); CHECK(MMX_PSUBB,_mm_sub_epi8(x,y));
        CHECK(MMX_PSUBW,_mm_sub_epi16(x,y)); CHECK(MMX_PSUBD,_mm_sub_epi32(x,y));
        CHECK(MMX_PMULLW,_mm_mullo_epi16(x,y)); CHECK(MMX_PMADDWD,_mm_madd_epi16(x,y));
        CHECK(MMX_PAND,_mm_and_si128(x,y)); CHECK(MMX_PANDN,_mm_andnot_si128(x,y));
        CHECK(MMX_POR,_mm_or_si128(x,y)); CHECK(MMX_PXOR,_mm_xor_si128(x,y));
        CHECK(MMX_PAVGB,_mm_avg_epu8(x,y));
        CHECK(MMX_PCMPEQB,_mm_cmpeq_epi8(x,y)); CHECK(MMX_PCMPEQW,_mm_cmpeq_epi16(x,y));
        CHECK(MMX_PCMPGTB,_mm_cmpgt_epi8(x,y)); CHECK(MMX_PCMPGTW,_mm_cmpgt_epi16(x,y));
        CHECK(MMX_PCMPGTD,_mm_cmpgt_epi32(x,y));
        CHECK(MMX_PUNPCKLBW,_mm_unpacklo_epi8(x,y));
        CHECK(MMX_PUNPCKLWD,_mm_unpacklo_epi16(x,y));
        CHECK(MMX_PUNPCKLDQ,_mm_unpacklo_epi32(x,y));
        CHECK(MMX_PUNPCKHBW,_mm_unpacklo_epi8(_mm_srli_si128(x,4),_mm_srli_si128(y,4)));
        CHECK(MMX_PUNPCKHWD,_mm_unpacklo_epi16(_mm_srli_si128(x,4),_mm_srli_si128(y,4)));
        CHECK(MMX_PUNPCKHDQ,_mm_unpacklo_epi32(_mm_srli_si128(x,4),_mm_srli_si128(y,4)));
        __m128i both=_mm_unpacklo_epi64(x,y);
        CHECK(MMX_PACKSSDW,_mm_packs_epi32(both,both));
        CHECK(MMX_PACKUSWB,_mm_packus_epi16(both,both));
        uint64_t count = counts[i % (sizeof counts/sizeof counts[0])];
        __m128i c=_mm_cvtsi64_si128((int64_t)count);
        SHIFT(MMX_PSLLW,_mm_sll_epi16(x,c)); SHIFT(MMX_PSLLD,_mm_sll_epi32(x,c));
        SHIFT(MMX_PSLLQ,_mm_sll_epi64(x,c)); SHIFT(MMX_PSRLW,_mm_srl_epi16(x,c));
        SHIFT(MMX_PSRLD,_mm_srl_epi32(x,c)); SHIFT(MMX_PSRLQ,_mm_srl_epi64(x,c));
        SHIFT(MMX_PSRAW,_mm_sra_epi16(x,c)); SHIFT(MMX_PSRAD,_mm_sra_epi32(x,c));
    }
    printf("XMV integer MMX helpers: PASS (%u hardware comparisons, edge/overflow/shift and seeded random inputs)\n",checks);
    return 0;
}
