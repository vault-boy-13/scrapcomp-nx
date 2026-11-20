/* Guest cache lines are not separate from host RAM. GPU uploads/readbacks
 * provide device visibility in the backend. WBINVD therefore publishes CPU
 * stores with a full compiler/CPU fence; never execute privileged host WBINVD. */
#if defined(_MSC_VER)
#include <intrin.h>
#if defined(_M_X64) || defined(_M_IX86)
#include <emmintrin.h>
#endif
#endif

void recomp_cache_writeback_invalidate(void)
{
#if defined(_MSC_VER) && (defined(_M_X64) || defined(_M_IX86))
    _ReadWriteBarrier();
    _mm_mfence();
    _ReadWriteBarrier();
#elif defined(_MSC_VER) && defined(_M_ARM64)
    __dmb(_ARM64_BARRIER_SY);
#elif defined(__GNUC__) || defined(__clang__)
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
#else
#error Implement the guest coherent-memory publication fence for this compiler
#endif
}
