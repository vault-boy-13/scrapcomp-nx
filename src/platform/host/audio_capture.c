/* Bounded, read-only native audio evidence. No DSP/mixer/output changes. */
#include "audio_capture.h"
#include "apu_xaudio2.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static struct {
    int profile, capture;
    uint64_t skip, frames, capacity;
    int16_t *input, *output;
    ULONGLONG start, last;
} observation;

static struct {
    FILE *input, *output;
    uint32_t frames, capacity, checkpoint;
} streaming;

static int wav_header(FILE *file, uint32_t frames)
{
    uint32_t bytes=frames*4, riff=bytes+36;
    unsigned char h[44]={ 'R','I','F','F',0,0,0,0,'W','A','V','E',
        'f','m','t',' ',16,0,0,0,1,0,2,0,0x80,0xBB,0,0,
        0,0xEE,2,0,4,0,16,0,'d','a','t','a',0,0,0,0 };
    for(unsigned b=0;b<4;b++) { h[4+b]=(unsigned char)(riff>>(b*8));h[40+b]=(unsigned char)(bytes>>(b*8)); }
    return !fseek(file,0,SEEK_SET) && fwrite(h,1,sizeof h,file)==sizeof h &&
           !fflush(file) && !fseek(file,0,SEEK_END);
}

void scrap_host_audio_observe_finish(void)
{
    FILE *files[2]={streaming.input,streaming.output};
    for(unsigned i=0;i<2;i++) if(files[i]) {
        if(!wav_header(files[i],streaming.frames) || fclose(files[i])) {
            fprintf(stderr,"[AUDIO] streaming capture finalization failed\n"); ExitProcess(84);
        }
    }
    streaming.input=streaming.output=NULL;
}

static void stream_samples(const int16_t *input,const int16_t *output,unsigned frames)
{
    if(!streaming.input) return;
    unsigned remaining=streaming.capacity-streaming.frames;
    if(frames>remaining) frames=remaining;
    if(fwrite(input,4,frames,streaming.input)!=frames ||
       fwrite(output,4,frames,streaming.output)!=frames) {
        fprintf(stderr,"[AUDIO] streaming capture write failed\n"); ExitProcess(84);
    }
    streaming.frames+=frames;
    if(streaming.frames-streaming.checkpoint>=48000) {
        if(!wav_header(streaming.input,streaming.frames) || !wav_header(streaming.output,streaming.frames)) {
            fprintf(stderr,"[AUDIO] streaming capture checkpoint failed\n"); ExitProcess(84);
        }
        streaming.checkpoint=streaming.frames;
    }
    if(streaming.frames==streaming.capacity) {
        scrap_host_audio_observe_finish();
        fprintf(stderr,"[AUDIO] streaming capture complete frames=%u\n",streaming.frames);
    }
}

static int write_wav(const char *path, const int16_t *pcm, uint32_t frames)
{
    uint32_t bytes=frames*4;
    unsigned char h[44]={ 'R','I','F','F',0,0,0,0,'W','A','V','E',
        'f','m','t',' ',16,0,0,0,1,0,2,0,0x80,0xBB,0,0,
        0,0xEE,2,0,4,0,16,0,'d','a','t','a',0,0,0,0 };
    uint32_t riff=bytes+36;
    for(unsigned b=0;b<4;b++) { h[4+b]=(unsigned char)(riff>>(b*8));h[40+b]=(unsigned char)(bytes>>(b*8)); }
    FILE *f=fopen(path,"wb");
    if(!f) return 0;
    int ok=fwrite(h,1,sizeof h,f)==sizeof h && fwrite(pcm,4,frames,f)==frames;
    if(fclose(f)) ok=0;
    return ok;
}

static void observe(const int16_t *input,const int16_t *output,int frames,
                    int queued,const Xa2Stats *stats)
{
    ULONGLONG now=GetTickCount64();
    if(observation.profile && now-observation.last>=1000) {
        observation.last=now;
        fprintf(stderr,"[AUDIO] wall_ms=%llu samples=%llu submitted=%llu underruns=%llu dropped=%llu clipped=%llu peak=%d queued_before=%d\n",
            (unsigned long long)(now-observation.start),(unsigned long long)stats->samples,
            (unsigned long long)stats->submitted,(unsigned long long)stats->underruns,
            (unsigned long long)stats->dropped,(unsigned long long)stats->clipped,stats->peak,queued);
    }
    if(frames>0 && output) stream_samples(input,output,(unsigned)frames);
    if(!observation.capture || frames<=0 || !output) return;
    uint64_t skip=observation.skip<(uint64_t)frames?observation.skip:(uint64_t)frames;
    observation.skip-=skip;
    input+=skip*2;output+=skip*2;frames-=(int)skip;
    uint64_t take=(uint64_t)frames;
    if(take>observation.capacity-observation.frames) take=observation.capacity-observation.frames;
    memcpy(observation.input+observation.frames*2,input,(size_t)take*4);
    memcpy(observation.output+observation.frames*2,output,(size_t)take*4);
    observation.frames+=take;
    if(observation.frames==observation.capacity) {
        observation.capture=0;
        int ok=write_wav("audio-input.wav",observation.input,(uint32_t)observation.frames);
        ok &= write_wav("audio-output.wav",observation.output,(uint32_t)observation.frames);
        fprintf(stderr,"[AUDIO] capture frames=%llu wall_ms=%llu written=%d (input before/output after volume and limiter)\n",
            (unsigned long long)observation.frames,(unsigned long long)(now-observation.start),ok);
        free(observation.input);free(observation.output);
        observation.input=observation.output=NULL;
    }
}

void scrap_host_audio_observe_install(void)
{
    const char *spec=getenv("RECOMP_AUDIO_CAPTURE");
    const char *profile=getenv("RECOMP_HOST_PROFILE");
    const char *stream=getenv("RECOMP_AUDIO_STREAM");
    scrap_host_audio_observe_finish();
    memset(&streaming,0,sizeof(streaming));
    observation.profile=profile && !strcmp(profile,"1");
    observation.start=observation.last=GetTickCount64();
    if(stream && *stream) {
        unsigned seconds;char tail;
        if(sscanf(stream,"%u%c",&seconds,&tail)!=1 || seconds<1 || seconds>900) {
            fprintf(stderr,"[AUDIO] invalid streaming capture duration\n"); ExitProcess(84);
        }
        streaming.capacity=seconds*48000;
        streaming.input=fopen("audio-stream-input.wav","wb");
        streaming.output=fopen("audio-stream-output.wav","wb");
        if(!streaming.input || !streaming.output || !wav_header(streaming.input,0) ||
           !wav_header(streaming.output,0)) {
            fprintf(stderr,"[AUDIO] streaming capture open failed\n"); ExitProcess(84);
        }
        fprintf(stderr,"[AUDIO] streaming capture duration<=%u seconds; checkpoint every second\n",seconds);
    }
    if(spec && *spec) {
        unsigned start,seconds;char tail;
        if(sscanf(spec,"%u,%u%c",&start,&seconds,&tail)!=2 || start>300 || !seconds || seconds>30) {
            fprintf(stderr,"[AUDIO] invalid capture interval; expected start<=300, duration1..30 seconds\n");
        } else {
            observation.skip=(uint64_t)start*48000;
            observation.capacity=(uint64_t)seconds*48000;
            observation.input=malloc((size_t)observation.capacity*4);
            observation.output=malloc((size_t)observation.capacity*4);
            if(observation.input && observation.output) observation.capture=1;
            else { free(observation.input);free(observation.output);observation.input=observation.output=NULL; }
            fprintf(stderr,"[AUDIO] bounded capture start_sample_s=%u duration_s=%u active=%d\n",start,seconds,observation.capture);
        }
    }
    if(observation.profile || observation.capture || streaming.input) xa2_set_observer(observe);
}
