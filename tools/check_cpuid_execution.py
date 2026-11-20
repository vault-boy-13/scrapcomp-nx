"""Execute a synthetic translated CPUID with the bounded Xbox CPU model."""
from pathlib import Path
import subprocess
import sys
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator

def main():
    raw=bytes.fromhex('39fe0fa27501c3b8efbeaddec3')
    base=0x10000
    config._SECTIONS=[config.Section('.text',base,len(raw),0,len(raw),True)]
    info={'_addr':base,'start':hex(base),'end':base+len(raw),'size':len(raw),'section':'.text'}
    body=FunctionTranslator(raw,{base:info}).translate_function(base,info)
    directory=ROOT/'build/tests/cpuid-execution'
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'cpuid_test.c'
    preamble='''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
void recomp_unimpl(const char *name,uint32_t va) { (void)name; (void)va; exit(77); }
'''
    driver='''
int main(int argc,char **argv) {
    if(argc>1) {
        uint32_t a,b,c,d;
        recomp_cpuid(0,&a,&b,&c,&d,0x10000);
        return 1;
    }
    for(unsigned i=0;i<1000;i++) {
        g_eax=1; g_ebx=0xDEADBEEF; g_ecx=i; g_edx=0xDEADBEEF;
        g_esi=i; g_edi=i; g_esp=0x100000;
        sub_00010000();
        if(g_eax!=0x68A || g_ebx || g_ecx || g_edx!=0x0383FBFF ||
           g_esp!=0x100004 || g_esi!=i || g_edi!=i) return 2;
    }
    g_eax=1; g_esi=1; g_edi=2; g_esp=0x100000;
    sub_00010000();
    if(g_eax!=0xDEADBEEF || g_esp!=0x100004) return 3;
    puts("PASS: 1001 translated CPUID calls, Xbox identity, preserved comparison flags and stack");
    return 0;
}
'''
    source.write_text(preamble+body+driver,encoding='utf-8',newline='\n')
    p=ws.paths()
    env=ws.vs_environment(p)
    exe=directory/'cpuid_test.exe'
    ws.run([p['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/templates/runtime'),source,
        ROOT/'src/runtime/cpu_identity.c','/Fe'+str(exe),'/Fo'+str(directory)+'\\'],
        name='cpuid-execution-build',env=env)
    ws.run([exe],name='cpuid-execution',env=env)
    result=subprocess.run([str(exe),'unknown'],capture_output=True,timeout=10,env=env)
    (directory/'unknown-leaf.log').write_bytes(result.stdout+result.stderr)
    if result.returncode!=77: raise RuntimeError('Unsupported CPUID leaf did not stop strictly')
    ws.write_json(directory/'manifest.json',{
        'scope':'Synthetic CPU fixture, no game input','source_sha256':ws.digest(source),
        'cpu_model_sha256':ws.digest(ROOT/'src/runtime/cpu_identity.c'),
        'executable_sha256':ws.digest(exe),'unsupported_leaf_exit':77,'passed':True})

if __name__=='__main__':
    main()
