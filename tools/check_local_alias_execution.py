"""Execute an independently constructed loop after explicit local-alias proof."""
from pathlib import Path
import sys
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_local_aliases import subject,BASE,ALIAS,END
from tools.recomp import config

def main():
    config._SECTIONS=[config.Section('.text',BASE,0x400,0,0x400,True)]
    s=subject()
    s.coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS])
    body=s.translate_function(BASE,s.func_db[BASE])
    directory=ROOT/'build/tests/local-alias-execution'
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'alias_test.c'
    source.write_text('''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
'''+body+'''
int main(void) {
    for(unsigned count=1;count<=100;count++) {
        g_eax=123; g_esi=count; g_ebx=11; g_edi=12; g_edx=13; g_esp=0x100000;
        sub_00010000();
        if(g_eax!=123+count || g_ecx || g_esi!=count || g_ebx!=11 ||
           g_edi!=12 || g_edx!=13 || g_esp!=0x100004) return 1;
    }
    puts("PASS: 100 native executions of a translated recovered loop, counters/registers/stack");
    return 0;
}
''',encoding='utf-8',newline='\n')
    p=ws.paths()
    env=ws.vs_environment(p)
    exe=directory/'alias_test.exe'
    ws.run([p['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/templates/runtime'),source,
        '/Fe'+str(exe),'/Fo'+str(directory)+'\\'],name='local-alias-build',env=env)
    ws.run([exe],name='local-alias-execution',env=env)
    ws.write_json(directory/'manifest.json',{
        'scope':'Synthetic loop/local alias, no game input',
        'proof_sha256':ws.digest(ROOT/'runtime/xboxrecomp/tools/recomp/local_alias.py'),
        'source_sha256':ws.digest(source),'executable_sha256':ws.digest(exe),'passed':True})

if __name__=='__main__': main()
