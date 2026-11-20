"""Execute actual APU worker and GP/EP orchestration across inactive/reset epochs.

DSP callbacks model the observed bootstrap and tagged 32-to-256 sample double
buffer; this tests scheduling and software-output preservation, not DSP opcodes.
"""
from pathlib import Path
import subprocess
import workspace as ws
from check_dma_alias import function

ROOT=Path(__file__).resolve().parents[1]

PRELUDE=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fpconv.h"
#define NUM_MIXBINS 32
#define NUM_SAMPLES_PER_FRAME 32
#define GP_DSP_MIXBUF_BASE 0x1400
#define NV_PAPU_GPRST 0
#define NV_PAPU_EPRST 0
#define NV_PAPU_GPRST_GPRST 1
#define NV_PAPU_GPRST_GPDSPRST 2
#define MCPX_APU_DEBUG_MON_GP 2
#define MCPX_APU_DEBUG_MON_GP_OR_EP 4
#define NV_PAPU_SECTL 0
#define NV_PAPU_FECTL 1
#define NV_PAPU_SECTL_XCNTMODE 1
#define NV_PAPU_SECTL_XCNTMODE_OFF 0
#define NV_PAPU_FECTL_FEMETHMODE_TRAPPED 1
#define NV_PAPU_FECTL_FEMETHMODE_HALTED 2
#define GET_MASK(v,m) ((v)&(m))
#define QEMU_CLOCK_REALTIME 0
#define THREAD_PRIORITY_HIGHEST 0
#define MCPX_APU_DEVICE(d) ((MCPXAPUState *)(d))
typedef struct DSPState { bool gp, idle; struct { unsigned pc; } core; } DSPState;
typedef struct { DSPState *dsp; unsigned regs[1]; bool realtime; } Processor;
typedef struct { Processor gp,ep; int ep_frame_div; unsigned regs[2];
    bool exiting,pause_requested,is_idle,in_trap; int lock,cond,idle_cond,lock_waiters;
    struct { unsigned point; int16_t frame_buf[256][2]; } monitor;
} MCPXAPUState;
static struct { struct { unsigned cycles; } gp,ep; } g_dbg;
static struct { bool active; } g_test_tone;
static int g_mixer_active_count;
static int64_t s_thr_traps,s_thr_trap_us;
static uint64_t observed_gp_runs,observed_ep_runs;
static int ring[16][32],cursor,generation,gp_init,ep_init,previous,have_previous,blocks,bad;
static int consumer_half,inactive,step,software_blocks,active_frames,clock_bad;
static MCPXAPUState *current;
static void reset_model(void) {
    cursor=generation=gp_init=ep_init=consumer_half=have_previous=0;
    memset(ring,0,sizeof(ring)); current->ep_frame_div=0;
}
static void iteration(const void *p) {
    if(p!=&current->exiting)return;
    const int span=inactive+256;
    if(step==span*3) {current->exiting=true;return;}
    int pos=step%span;
    if(pos==0)reset_model();
    current->regs[NV_PAPU_SECTL]=pos>=inactive;
    if(current->ep_frame_div!=(pos<inactive?0:pos-inactive))clock_bad=1;
    for(int i=0;i<256;i++)for(int c=0;c<2;c++)
        if(current->monitor.frame_buf[i][c]!=23456)bad=1;
    step++;
}
#define qatomic_read(p) (iteration(p),*(p))
#define qemu_mutex_lock(p) ((void)(p))
#define qemu_mutex_unlock(p) ((void)(p))
#define qemu_cond_signal(p) ((void)(p))
#define qemu_cond_wait(c,l) ((void)(c),(void)(l))
#define qemu_cond_timedwait(c,l,t) ((void)(c),(void)(l),(void)(t))
#define GetCurrentThread() 0
#define SetThreadPriority(t,p) ((void)(t),(void)(p))
void xbox_nx_raise_host_thread(void) {}
static int64_t qemu_clock_get_us(int clock) {(void)clock;return 0;}
#define throttle(d,...) ((void)(d))
static void monitor_output_block(MCPXAPUState *d) {
    software_blocks++;
    memset(d->monitor.frame_buf,0,sizeof(d->monitor.frame_buf));
}
static void mcpx_apu_monitor_frame(MCPXAPUState *d) {
    if((d->ep_frame_div+1)%8==0)software_blocks++;
}
static void dsp_write_memory(DSPState *d,char s,unsigned a,unsigned v) {(void)d;(void)s;(void)a;(void)v;}
static unsigned dsp_read_memory(DSPState *d,char s,unsigned a) {(void)d;(void)s;(void)a;return 0;}
static void dsp_start_frame(DSPState *d) {(void)d;}
static void dsp_set_halt_requested(DSPState *d,bool v) {d->idle=v;}
static bool dsp_get_halt_requested(DSPState *d) {return d->idle;}
static void dsp_set_cycle_count(DSPState *d,unsigned v) {(void)d;(void)v;}
static unsigned dsp_get_cycle_count(DSPState *d) {(void)d;return 1;}
static void dsp_run(DSPState *d,int cycles) {
    (void)cycles;
    if(d->gp) {
        if(gp_init++) {
            for(int i=0;i<32;i++)ring[cursor][i]=generation*32+i;
            cursor=(cursor+1)%16;generation++;
        }
    } else if(ep_init++>=2) {
        for(int j=0;j<8;j++)for(int i=0;i<32;i++) {
            int sample=ring[consumer_half*8+j][i];
            if(have_previous && sample!=previous+1)bad=1;
            previous=sample;have_previous=1;
        }
        consumer_half^=1;blocks++;
    }
    d->idle=true;
}
static void capture_dsp_stages(MCPXAPUState *d,float mix[32][32]) {(void)d;(void)mix;}
'''

MIDDLE=r'''
static void se_frame(MCPXAPUState *d) {
    float mix[32][32]={{0}};
    mcpx_apu_dsp_frame(d,mix);d->ep_frame_div++;active_frames++;
}
'''

FIXTURE=r'''
int main(void) {
    unsigned total=0;
    for(inactive=0;inactive<32;inactive++) {
        DSPState gp={true},ep={false};MCPXAPUState d={0};current=&d;
        d.gp.dsp=&gp;d.ep.dsp=&ep;d.gp.regs[0]=d.ep.regs[0]=3;
        d.gp.realtime=d.ep.realtime=true;d.monitor.point=MCPX_APU_DEBUG_MON_GP_OR_EP;
        for(int i=0;i<256;i++)for(int c=0;c<2;c++)d.monitor.frame_buf[i][c]=23456;
        step=software_blocks=active_frames=clock_bad=bad=blocks=0;
        mcpx_apu_frame_thread(&d);
        if(clock_bad || bad || active_frames!=768 || software_blocks!=(inactive*3)/8 || blocks!=90) {
            fprintf(stderr,"inactive=%d clock_bad=%d samples_bad=%d active=%d software_blocks=%d EP_blocks=%d\n",
                inactive,clock_bad,bad,active_frames,software_blocks,blocks);return 6;
        }
        total+=active_frames;
    }
    printf("PASS: %u actual worker/pipeline active frames; 32 inactive durations x3 resets, contiguous EP samples and preserved pending block\n",total);
    return 0;
}
'''

def main():
    out=ROOT/'build/tests/apu-clock';out.mkdir(parents=True,exist_ok=True)
    paths=ws.paths();env=ws.vs_environment(paths);results={}
    dsp=ROOT/'src/audio/apu_dsp_real.c'
    pipeline=function(dsp.read_text(encoding='utf-8'),'void mcpx_apu_dsp_frame(')
    for name,source,expected in [
        ('fixed',ROOT/'runtime/xboxrecomp/src/apu/apu_core.c',0),
        ('baseline',ROOT/'references/nfsu2-sw/xboxrecomp/src/apu/apu_core.c',6)]:
        text=source.read_text(encoding='utf-8')
        software=(function(text,'static void monitor_software_frame(') if name=='fixed' else '')
        worker=function(text,'static void *mcpx_apu_frame_thread(')
        cfile=out/(name+'.c');cfile.write_text(PRELUDE+pipeline+MIDDLE+software+worker+FIXTURE,encoding='utf-8',newline='\n')
        exe=out/(name+'.exe')
        ws.run([paths['host_compiler'],'/nologo','/O2','/I'+str(ROOT/'runtime/xboxrecomp/src/apu'),
                cfile,'/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='apu-clock-'+name+'-build',env=env)
        r=subprocess.run([exe],env=env,capture_output=True,text=True,timeout=10)
        (out/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        print(name,r.returncode,r.stdout.strip(),r.stderr.strip())
        if r.returncode!=expected:raise RuntimeError(f'{name}: expected {expected}, got {r.returncode}')
        results[name]=dict(source_sha256=ws.digest(source),fixture_sha256=ws.digest(cfile),
            executable_sha256=ws.digest(exe),exit_code=r.returncode)
    ws.write_json(out/'manifest.json',dict(scope=__doc__,dsp_adapter_sha256=ws.digest(dsp),inputs=results,passed=True))

if __name__=='__main__':main()
