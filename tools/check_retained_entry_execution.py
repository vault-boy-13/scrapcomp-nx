"""Run both native entry wrappers of a synthetic shared guest CFG."""
from pathlib import Path
import subprocess,sys
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_retained_entries import subject,BASE,ALIAS,END
from tools.recomp import config

def main():
    fallthrough='--fallthrough' in sys.argv[1:]
    config._SECTIONS=[config.Section('.text',BASE,0x400,0,0x400,True)]
    code=bytes.fromhex('5389cb909090909083fb0001d85bc3') if fallthrough else None
    s=subject(code) if code else subject()
    immediate_reference='--immediate-reference' in sys.argv[1:]
    if immediate_reference:
        s.func_db[ALIAS]['detection_method']='imm_ref_target'
    s.coalesce_function(BASE,BASE+len(code) if code else END,[ALIAS],retained_entries=[ALIAS])
    owner=s.translate_function(BASE,s.func_db[BASE])
    alias=s.translate_function(ALIAS,s.func_db[ALIAS])
    out=ROOT/('build/tests/retained-entry-fallthrough' if fallthrough else 'build/tests/retained-entry-execution');out.mkdir(parents=True,exist_ok=True)
    if immediate_reference:
        out=out.parent/(out.name+'-immediate-reference');out.mkdir(parents=True,exist_ok=True)
    source=out/'retained_test.c'
    source.write_text('''#define RECOMP_GENERATED_CODE
#include <windows.h>
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
ptrdiff_t g_xbox_mem_offset;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
void recomp_unimpl(const char *instruction,uint32_t va) { (void)instruction;(void)va;exit(77); }
'''+owner+alias+'''
int main(int argc,char **argv) {
    g_xbox_mem_offset=(ptrdiff_t)VirtualAlloc(NULL,0x200000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    if(!g_xbox_mem_offset) return 2;
    if(argc>1) { g_ecx=0xFFFFFFFF;g_esp=0x100000;sub_00010000();return 3; }
    for(unsigned count=0;count<1000;++count) {
        g_eax=1;g_ecx=count;g_ebx=0x12345678;g_edx=9;g_esi=10;g_edi=11;g_esp=0x100000;
        MEM32(g_esp)=0xDEAD0000;
        sub_00010000();
        if(g_eax!=1+count*(count+1)/2 || g_ebx!=0x12345678 || g_ecx!=count ||
           g_edx!=9 || g_esi!=10 || g_edi!=11 || g_esp!=0x100004) return 4;
        g_eax=1;g_ecx=0xFF;g_ebx=count;g_edx=9;g_esi=10;g_edi=11;g_esp=0x100000;
        MEM32(g_esp)=0x12345678;MEM32(g_esp+4)=0xDEAD0000;
        sub_00010008();
        if(g_eax!=1+count*(count+1)/2 || g_ebx!=0x12345678 || g_ecx!=0xFF ||
           g_edx!=9 || g_esi!=10 || g_edi!=11 || g_esp!=0x100008) return 5;
    }
    puts("PASS: 2000 shared-CFG executions through original and retained entries; registers/stack/trap");
    return 0;
}
''',encoding='utf-8',newline='\n')
    if fallthrough:
        source.write_text(source.read_text(encoding='utf-8').replace('1+count*(count+1)/2','1+count'),encoding='utf-8',newline='\n')
    p=ws.paths();env=ws.vs_environment(p);exe=out/'retained_test.exe'
    ws.run([p['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/templates/runtime'),source,
        '/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='retained-entry-build',env=env)
    ws.run([exe],name='retained-entry-execution',env=env)
    if not fallthrough:
        result=subprocess.run([str(exe),'trap'],capture_output=True,timeout=10,env=env)
        if result.returncode!=77: raise RuntimeError('Assertion no longer stops strictly')
    ws.write_json(out/'manifest.json',{'scope':'Synthetic shared CFG, no game input','executions':2000,
        'source_sha256':ws.digest(source),'executable_sha256':ws.digest(exe),
        'trap_child_exit':None if fallthrough else 77,'fallthrough_entry':fallthrough,
        'entry_detection_method':s.func_db[ALIAS]['detection_method'],'passed':True})

if __name__=='__main__': main()
