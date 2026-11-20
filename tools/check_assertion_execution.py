"""Execute the valid path and strict breakpoint stop of a synthetic owner."""
from pathlib import Path
import subprocess
import sys
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_assertion_continuations import subject,BASE,CONT,END
from tools.recomp import config
def main():
    config._SECTIONS=[config.Section('.text',BASE,0x400,0,0x400,True)]
    s=subject()
    s.coalesce_function(BASE,END,[CONT])
    body=s.translate_function(BASE,s.func_db[BASE])
    directory=ROOT/'build/tests/assertion-execution'
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'assert_test.c'
    source.write_text('''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdlib.h>
#include <stdio.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
void recomp_unimpl(const char *name,uint32_t va) {
    if(strcmp(name,"int3") || va!=0x10006) exit(2);
    exit(77);
}
'''+body+'''
int main(int argc,char **argv) {
    g_ecx=argc>1?0:1; g_edx=123; g_eax=0; g_esp=0x100000;
    sub_00010000();
    if(argc>1 || g_eax!=123 || g_edx!=123 || g_esp!=0x100004) return 1;
    puts("PASS: valid path executes; conditional INT3 is a strict child-process stop");
    return 0;
}
''',encoding='utf-8',newline='\n')
    p=ws.paths()
    env=ws.vs_environment(p)
    exe=directory/'assert_test.exe'
    ws.run([p['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/templates/runtime'),source,
        '/Fe'+str(exe),'/Fo'+str(directory)+'\\'],name='assertion-build',env=env)
    ws.run([exe],name='assertion-execution',env=env)
    r=subprocess.run([str(exe),'trap'],capture_output=True,env=env,timeout=10)
    (directory/'trap.log').write_bytes(r.stdout+r.stderr)
    if r.returncode!=77: raise RuntimeError('Reached breakpoint was not a strict stop')
    ws.write_json(directory/'manifest.json',{
        'scope':'Synthetic assertion/continuation, no game input','source_sha256':ws.digest(source),
        'executable_sha256':ws.digest(exe),'trap_exit':77,'passed':True})
if __name__=='__main__': main()
