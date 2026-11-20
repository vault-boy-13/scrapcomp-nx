/* Inspect recorded PCM only; never opens an audio device or changes game data. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "safety.h"

static uint32_t u32(const unsigned char *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static FILE *open_pcm(const char *path,uint32_t *frames)
{
    unsigned char h[44];FILE *f=fopen(path,"rb");
    if(!f || fread(h,1,44,f)!=44 || memcmp(h,"RIFF",4) || memcmp(h+8,"WAVEfmt ",8) ||
       memcmp(h+36,"data",4) || h[20]!=1 || h[22]!=2 || h[34]!=16 || u32(h+24)!=48000 ||
       u32(h+40)%4) {fprintf(stderr,"Invalid canonical stereo PCM WAV: %s\n",path);exit(2);}
    *frames=u32(h+40)/4;return f;
}
int main(int argc,char **argv)
{
    if(argc!=3)return 2;
    uint32_t input_frames,output_frames;
    FILE *in=open_pcm(argv[1],&input_frames),*out=open_pcm(argv[2],&output_frames);
    if(input_frames!=output_frames)return 3;
    uint64_t differences=0,clipped=0;uint32_t processed=0,second=0;
    int16_t a[96000],b[96000],expected[96000];
    printf("{\"frames\":%u,\"duration_s\":%.6f,\"seconds\":[",input_frames,input_frames/48000.0);
    while(processed<input_frames) {
        uint32_t n=input_frames-processed;if(n>48000)n=48000;
        if(fread(a,4,n,in)!=n || fread(b,4,n,out)!=n)return 4;
        apu_output_safety(a,expected,(int)n*2);
        double squares_a=0,squares_b=0,delta_squares=0,edges=0;unsigned edge_count=0;
        int peak_a=0,peak_b=0,previous=0;
        for(unsigned i=0;i<n*2;i++) {
            if(b[i]!=expected[i])differences++;
            int av=abs((int)a[i]),bv=abs((int)b[i]);
            if(av>peak_a)peak_a=av;if(bv>peak_b)peak_b=bv;
            if(av>=32767)clipped++;
            squares_a+=(double)a[i]*a[i];squares_b+=(double)b[i]*b[i];
            if(i%2==0) {
                int delta=(int)a[i]-previous;
                if(i) {delta_squares+=(double)delta*delta;
                    if(((processed+i/2)%256)==0) {edges+=(double)delta*delta;edge_count++;}}
                previous=a[i];
            }
        }
        if(second)printf(",");
        printf("{\"second\":%u,\"frames\":%u,\"input_peak\":%d,\"output_peak\":%d,"
               "\"input_rms\":%.6f,\"output_rms\":%.6f,\"delta_rms\":%.6f,\"block_edge_delta_rms\":%.6f}",
               second++,n,peak_a,peak_b,sqrt(squares_a/(n*2)),sqrt(squares_b/(n*2)),
               n>1?sqrt(delta_squares/(n-1)):0,edge_count?sqrt(edges/edge_count):0);
        processed+=n;
    }
    fclose(in);fclose(out);
    printf("],\"postprocess_mismatched_samples\":%llu,\"input_clipped_samples\":%llu}\n",
        (unsigned long long)differences,(unsigned long long)clipped);
    return differences?5:0;
}
