/* Independent PVIDEO state/range fixture; no guest executable or assets. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/runtime/pvideo.h"
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); return 1; } } while (0)
static unsigned presents;
static int present(const uint32_t *pixels, unsigned w, unsigned h, unsigned ow, unsigned oh)
{
    if(w!=2 || h!=2 || ow!=2 || oh!=2 || pixels[0]!=0xFF000000u ||
       pixels[1]!=0xFFFFFFFFu || pixels[2]!=0xFFFF0000u || pixels[3]!=0xFFFF0000u) abort();
    ++presents;
    return 1;
}
int main(void)
{
    CHECK(VirtualAlloc((void *)0xFD000000,0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    CHECK(VirtualAlloc((void *)0x80001000,0x1000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    volatile uint32_t *r=(volatile uint32_t *)0xFD000000;
#define R(x) r[(x)/4]
    const unsigned char data[16]={16,128,235,128,0,0,0,0,81,90,81,240,0,0,0,0};
    memcpy((void *)0x80001000,data,sizeof data);
    R(0x8700)=1; R(0x8908)=0x7FFFFFF; R(0x8910)=R(0x8918)=0x1000;
    R(0x8920)=0x1000; R(0x8928)=R(0x8950)=0x00020002;
    R(0x8938)=R(0x8940)=0x100000; R(0x8958)=0x10008;
    CHECK(scrap_pvideo_tick(0,0,present)==1 && presents==1 && R(0x8700)==1);
    CHECK(scrap_pvideo_tick(0,1,present)==0 && presents==1);
    CHECK(scrap_pvideo_tick(0,16683,present)==1 && presents==2);
    R(0x8704)=1;
    CHECK(scrap_pvideo_tick(0,16684,present)==0 && R(0x8700)==0 && R(0x8704)==0);
    CHECK(scrap_pvideo_tick(0,20000,present)==0 && presents==2);
    R(0x8700)=1; R(0x8958)=0x10002;
    CHECK(scrap_pvideo_tick(0,20001,present)==-1 && presents==2);
    R(0x8958)=0x10008; R(0x8920)=0x03FFFFFC;
    CHECK(scrap_pvideo_tick(0,20002,present)==-1 && presents==2);
    R(0x8920)=0x1000; R(0x8938)=0x200000;
    CHECK(scrap_pvideo_tick(0,20003,present)==-1 && presents==2);
    R(0x8938)=0x100000; R(0x8958)=0x110008;
    CHECK(scrap_pvideo_tick(0,20004,present)==-1 && presents==2);
    R(0x8958)=0x10008;
    for(unsigned offset=0x8900;offset<=0x8958;offset+=8) R(offset+4)=R(offset);
    R(0x8700)=0x10;
    CHECK(scrap_pvideo_tick(0,20005,present)==1 && presents==3);
    puts("PASS: YUY2 pixels, refresh gating, persistent BUFFER, STOP, bank 1 and strict invalid layouts/ranges");
    return 0;
}
