"""Native checks of the actual APU MMIO read function and its sample-clock units."""
from pathlib import Path
import subprocess
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]

def extract(source):
    start=source.index('uint64_t mcpx_apu_read(')
    opening=source.index('{',start)
    depth=1;end=opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]

def main():
    out=ROOT/'build/tests/apu-sample-clock';out.mkdir(parents=True,exist_ok=True)
    sdk=ROOT/'runtime/xboxrecomp/src/apu/apu_core.c'
    prelude='''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint64_t hwaddr;
typedef struct {int ep_frame_div;uint32_t regs[0x20000];} MCPXAPUState;
#define qatomic_read(p) (*(p))
#define NUM_SAMPLES_PER_FRAME 32
#define NV_PAPU_XGSCNT 0x200C
#define QEMU_CLOCK_VIRTUAL 0
static uint64_t now;
static uint64_t qemu_clock_get_ns(int ignored){(void)ignored;return now;}
'''
    maincode='''
int main(void) {
 static MCPXAPUState state;
 const uint32_t frames[]={0,1,1500,134217727,134217728,2147483647};
 const uint64_t times[]={0,100,1000000000,999999999999ULL};
 unsigned cases=0;
 for(unsigned f=0;f<6;f++) for(unsigned t=0;t<4;t++) {
   state.ep_frame_div=(int)frames[f];now=times[t];
   uint32_t expected=(uint32_t)((uint64_t)frames[f]*32);
   uint64_t value=mcpx_apu_read(&state,NV_PAPU_XGSCNT,4);
   if(value!=expected){fprintf(stderr,"FAIL frame%u time%llu got%llu expected%u\\n",frames[f],now,value,expected);return 6;}
   cases++;
 }
 state.regs[0x1234]=0xA1B2C3D;
 if(mcpx_apu_read(&state,0x1234,4)!=0xA1B2C3D || mcpx_apu_read(&state,0x20000,4)!=0)return 7;
 printf("PASS: %u actual MMIO sample-clock checks, wall-clock independence, wrap and ordinary reads\\n",cases);
 return 0;
}
'''
    paths=ws.paths();env=ws.vs_environment(paths)
    report={}
    for name,source in [('fixed',sdk),('baseline',ROOT/'references/nfsu2-sw/xboxrecomp/src/apu/apu_core.c')]:
        fixture=out/(name+'.c');fixture.write_text(prelude+extract(source.read_text(encoding='utf-8'))+maincode,encoding='utf-8')
        exe=out/(name+'.exe')
        ws.run([paths['host_compiler'],'/nologo','/O2',fixture,'/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='apu-clock-'+name+'-build',env=env)
        result=subprocess.run([str(exe)],env=env,capture_output=True,text=True,timeout=10)
        (out/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        expected=0 if name=='fixed' else 6
        if result.returncode!=expected:raise RuntimeError(name+': '+result.stdout+result.stderr)
        report[name]={'exit_code':result.returncode,'exe_sha256':ws.digest(exe),'source_sha256':ws.digest(source)}
    ws.write_json(out/'manifest.json',{'scope':'Actual MMIO read function with deterministic clocks/frame counts; no audio device',
        'passed':True,'results':report})

if __name__=='__main__':main()
