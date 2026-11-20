"""Force hold/ack overlap against the real donor routines and a pinned control."""
from pathlib import Path
import re
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]

def function(source, signature):
    at=source.index(signature);begin=source.index('{',at);depth=1;end=begin+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[at:end]

def main():
    paths=ws.paths();env=ws.vs_environment(paths)
    reports=[]
    for baseline in [True,False]:
        path=ROOT/('references/nfsu2-sw/xboxrecomp' if baseline else 'runtime/xboxrecomp')/'src/kernel/xbox_memory_layout.c'
        src=path.read_text(encoding='utf-8')
        body=''
        for name in ['NV2A_ACK','NV2A_IDLE']:
            body+=re.search(r'static const struct \{[^\n]+\} '+name+r'\[\] = \{.*?\n\};',src,re.S).group()+'\n'
        if not baseline:
            body+='static volatile LONG s_nv2a_ack_lock;\n'
            body+=function(src,'static void nv2a_ack_lock(void)')+'\n'
            body+=function(src,'static void nv2a_ack_unlock(void)')+'\n'
        body+=function(src,'void xbox_Nv2aHoldInterrupts(int on)')+'\n'
        body+=function(src,'static void nv2a_ack_flags(volatile uint32_t *regs)')+'\n'
        out=ROOT/'build/tests/nv2a-ack-race'/('baseline' if baseline else 'fixed');out.mkdir(parents=True,exist_ok=True)
        c=out/'test.c'
        c.write_text('''#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static volatile LONG g_nv2a_intr_hold;
static HANDLE read_hold,continue_ack,publish_attempt,published;
static DWORD ack_tid;
static uint32_t regs[0x610000/4];
static LONG test_compare_exchange(volatile LONG *p,LONG x,LONG c) {
    LONG value=InterlockedCompareExchange(p,x,c);
    if(p==&g_nv2a_intr_hold && x==0 && c==0 && GetCurrentThreadId()==ack_tid) {
        SetEvent(read_hold);
        if(WaitForSingleObject(continue_ack,5000)!=WAIT_OBJECT_0) ExitProcess(10);
    }
    return value;
}
#define InterlockedCompareExchange test_compare_exchange
static int vblank_held(void) {return 0;}
'''+body+'''
static DWORD WINAPI ack(void *unused) {
    (void)unused;ack_tid=GetCurrentThreadId();nv2a_ack_flags(regs);return 0;
}
static DWORD WINAPI publisher(void *unused) {
    (void)unused;SetEvent(publish_attempt);xbox_Nv2aHoldInterrupts(1);
    regs[0x400108/4]=1;regs[0x400100/4]|=1;regs[0x100/4]|=0x1000;
    SetEvent(published);return 0;
}
int main(void) {
    read_hold=CreateEventA(NULL,TRUE,FALSE,NULL);continue_ack=CreateEventA(NULL,TRUE,FALSE,NULL);
    publish_attempt=CreateEventA(NULL,TRUE,FALSE,NULL);published=CreateEventA(NULL,TRUE,FALSE,NULL);
    for(unsigned i=0;i<32;++i) {
        memset(regs,0,sizeof regs);ResetEvent(read_hold);ResetEvent(continue_ack);
        ResetEvent(publish_attempt);ResetEvent(published);
        regs[0x100410/4]=0x10000;regs[0x600100/4]=1;
        HANDLE a=CreateThread(NULL,0,ack,NULL,0,NULL);
        if(WaitForSingleObject(read_hold,5000)!=WAIT_OBJECT_0) return 11;
        HANDLE p=CreateThread(NULL,0,publisher,NULL,0,NULL);
        if(WaitForSingleObject(publish_attempt,5000)!=WAIT_OBJECT_0) return 12;
        DWORD observed=WaitForSingleObject(published,BASELINE?5000:10);
        if(observed!=(BASELINE?WAIT_OBJECT_0:WAIT_TIMEOUT)) return 13;
        SetEvent(continue_ack);
        if(WaitForSingleObject(a,5000)!=WAIT_OBJECT_0 || WaitForSingleObject(p,5000)!=WAIT_OBJECT_0) return 14;
        if(regs[0x400100/4]!=(BASELINE?0u:1u) || regs[0x100/4]!=(BASELINE?0u:0x1000u)) return 15;
        if(regs[0x400108/4]!=1 || regs[0x100410/4]!=0 || regs[0x600100/4]!=0) return 16;
        xbox_Nv2aHoldInterrupts(0);CloseHandle(a);CloseHandle(p);
    }
    CloseHandle(read_hold);CloseHandle(continue_ack);CloseHandle(publish_attempt);CloseHandle(published);
    puts(BASELINE?"PASS control: 32 forced overlaps lose the pending interrupt":"PASS fixed: 32 forced overlaps preserve the pending interrupt and unrelated acknowledgements");
    return 0;
}
'''.replace('BASELINE','1' if baseline else '0'),encoding='utf-8',newline='\n')
        exe=out/'test.exe'
        ws.run([paths['host_compiler'],'/nologo','/O2',c,'/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='nv2a-ack-race-build',env=env)
        ws.run([exe],name='nv2a-ack-race-execution',env=env)
        reports.append({'baseline':baseline,'cases':32,'source_sha256':ws.digest(c),'executable_sha256':ws.digest(exe),'passed':True})
    ws.write_json(ROOT/'build/tests/nv2a-ack-race/manifest.json',{'scope':'Forced concurrent execution of extracted actual hold/ack routines; not game stability proof','runs':reports})

if __name__=='__main__':main()
