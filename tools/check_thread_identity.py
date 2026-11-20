"""Run the actual lifted XAPI thread-ID reader on independent native threads."""
from pathlib import Path
import argparse,json,subprocess
import workspace as ws
from check_dma_alias import function

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path)
    args=parser.parse_args()
    sdk=args.candidate or ROOT/'runtime/xboxrecomp'
    layout=sdk/'src/kernel/xbox_memory_layout.c'
    baseline=ROOT/'references/nfsu2-sw/xboxrecomp/src/kernel/xbox_memory_layout.c'
    image=json.loads((ROOT/'config/scrapland/image.json').read_text())
    generated=ROOT/'generated'/image['sha256'][:16]/'c/recomp_0034.c'
    guest=function(generated.read_text(encoding='utf-8'),'void sub_00186363(void)')
    out=ROOT/'build/tests/thread-identity';out.mkdir(parents=True,exist_ok=True)
    paths=ws.paths();env=ws.vs_environment(paths);reports={}
    prelude='''#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define XBOX_TIB_MAIN 0x4000u
#define XBOX_FS_BASE g_fs_base
static uintptr_t g_memory_offset;
static uint32_t g_tls_total=16,g_tls_thread_size=64,g_tls_template_va=0x5000;
static __declspec(thread) uint32_t g_fs_base,r_eax,r_esp;
static volatile LONG cursor=0x800000;
static uint32_t xbox_HeapAlloc(uint32_t size,uint32_t alignment) {
    if(alignment!=16)abort();
    return (uint32_t)InterlockedExchangeAdd(&cursor,(size+15)&~15u);
}
#define MEM32(va) (*(uint32_t *)(g_memory_offset+(uint32_t)(va)))
#define RECOMP_PREEMPT() ((void)0)
#define recomp_leaf_ld_eax() r_eax
#define recomp_leaf_ld_esp() r_esp
#define recomp_leaf_st_eax(v) (r_eax=(v))
#define recomp_leaf_st_esp(v) (r_esp=(v))
#define eax g_eax
#define esp g_esp
'''
    fixture='''
enum {N=8};
static HANDLE gate;
static volatile LONG ready;
static uint32_t objects[N],tibs[N];
static DWORD WINAPI worker(void *argument) {
    unsigned i=(unsigned)(uintptr_t)argument;
    g_fs_base=xbox_AllocThreadTib();tibs[i]=g_fs_base;
    if(!g_fs_base)return 3;
    objects[i]=MEM32(g_fs_base+0x28);
#if FIXED
    xbox_SetThreadIdentity(g_fs_base,GetCurrentThreadId());
#endif
    InterlockedIncrement(&ready);
    WaitForSingleObject(gate,10000);
    sub_00186363();
    if(r_eax!=GetCurrentThreadId() || !r_eax)return 6;
    if(MEM32(g_fs_base)!=0xFFFFFFFFu || MEM32(objects[i]+0x28)!=0x700000)return 7;
    uint32_t tls=MEM32(g_fs_base+4)-g_tls_total;
    if(MEM32(tls+4)!=0xAABBCCDD || MEM32(tls)<tls+g_tls_total)return 8;
    return 0;
}
int main(void) {
    g_memory_offset=(uintptr_t)calloc(1,0x1000000);if(!g_memory_offset)return 2;
    g_fs_base=XBOX_TIB_MAIN;
    MEM32(XBOX_TIB_MAIN+0x28)=0x760000;
    MEM32(0x760000+0x28)=0x700000;
    MEM32(g_tls_template_va+4)=0xAABBCCDD;
#if FIXED
    xbox_SetThreadIdentity(g_fs_base,GetCurrentThreadId());
#endif
    gate=CreateEvent(NULL,TRUE,FALSE,NULL);
    HANDLE threads[N];
    for(unsigned i=0;i<N;i++)threads[i]=CreateThread(NULL,0,worker,(void *)(uintptr_t)i,0,NULL);
    for(unsigned tries=0;ready!=N && tries<10000;tries++)Sleep(1);
    if(ready!=N)return 4;
    SetEvent(gate);
    if(WaitForMultipleObjects(N,threads,TRUE,10000)!=WAIT_OBJECT_0)return 5;
    for(unsigned i=0;i<N;i++) {
        DWORD code=99;GetExitCodeThread(threads[i],&code);if(code)return code;
        for(unsigned j=0;j<i;j++)if(objects[j]==objects[i] || tibs[j]==tibs[i])return 9;
    }
    sub_00186363();if(r_eax!=GetCurrentThreadId())return 10;
    puts("PASS: actual guest GetCurrentThreadId on eight workers + main; distinct records and preserved TLS/template fields");
    for(unsigned i=0;i<N;i++)CloseHandle(threads[i]);CloseHandle(gate);
    free((void *)g_memory_offset);return 0;
}
'''
    for name,source,fixed,expected in [('fixed',layout,1,0),('baseline',baseline,0,6)]:
        text=source.read_text(encoding='utf-8')
        routines=(function(text,'void xbox_SetThreadIdentity(') if fixed else '')
        routines+=function(text,'uint32_t xbox_AllocThreadTib(void)')
        cfile=out/(name+'.c');cfile.write_text(prelude+f'\n#define FIXED {fixed}\n'+routines+guest+fixture,encoding='utf-8',newline='\n')
        exe=out/(name+'.exe')
        ws.run([paths['host_compiler'],'/nologo','/O2',cfile,'/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='thread-id-'+name+'-build',env=env)
        result=subprocess.run([exe],env=env,capture_output=True,text=True,timeout=20)
        print(name,result.returncode,result.stdout.strip())
        if result.returncode!=expected:raise RuntimeError(f'{name} expected{expected}, got{result.returncode}: {result.stderr}')
        reports[name]={'layout_sha256':ws.digest(source),'fixture_sha256':ws.digest(cfile),'executable_sha256':ws.digest(exe),'exit_code':result.returncode}
    ws.write_json(out/'manifest.json',{'scope':'Actual guest XAPI reader and actual TIB/identity routines with real native threads',
        'generated_source_sha256':ws.digest(generated),'cases':reports,'passed':True})


if __name__=='__main__':main()
