/* DSP sources access native little-endian words directly on supported hosts. */
#pragma once
#include <stdint.h>
#include <string.h>
static inline uint32_t ldl_le_p(const void *pointer)
{
    uint32_t value;
    memcpy(&value,pointer,sizeof(value));
    return value;
}
static inline void stl_le_p(void *pointer,uint32_t value)
{
    memcpy(pointer,&value,sizeof(value));
}
