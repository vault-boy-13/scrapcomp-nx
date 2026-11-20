"""Run synthetic x87 compare/LAHF/parity branches through the real lifter."""
from pathlib import Path
import subprocess
import sys
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator

def main():
    baseline='--prior-semantics' in sys.argv[1:]
    if baseline:
        from tools.recomp import lifter
        # The prior x87 path could not construct SF for LAHF and emitted a
        # comment. Reproduce that single omission as a negative control.
        lifter._lahf_value=lambda setter, operands: None
    bodies=[]
    # Each body consumes two preloaded x87 values, materialises AH, and returns
    # the parity branch in AL. No game instructions or assets are used.
    for i,opcode in enumerate(('dbf1','dff1','dbe9','dfe9')):
        pop='ddd8' if i%2 else 'ddd8ddd8'
        raw=bytes.fromhex(opcode+pop+'9ff6c4447a03b000c3b001c3')
        base=0x10000+i*0x100
        config._SECTIONS=[config.Section('.text',base,len(raw),0,len(raw),True)]
        info={'_addr':base,'start':hex(base),'end':base+len(raw),'size':len(raw),'section':'.text'}
        bodies.append(FunctionTranslator(raw,{base:info}).translate_function(base,info))
    preamble='''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
RECOMP_TLS double g_fp_stack[8];
RECOMP_TLS int g_fp_top,g_fp_cmp;
RECOMP_TLS uint16_t g_fp_control_word,g_fp_cc;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
void recomp_unimpl(const char *name,uint32_t va) { (void)name; (void)va; abort(); }
'''
    driver='''
int main(void) {
    const double values[]={0.0,-0.0,1.0,-1.0,1e-300,INFINITY,-INFINITY,NAN};
    void (*functions[])(void)={sub_00010000,sub_00010100,sub_00010200,sub_00010300};
    unsigned cases=0;
    for(unsigned f=0;f<4;++f) for(unsigned a=0;a<8;++a) for(unsigned b=0;b<8;++b)
    for(unsigned seed=0;seed<256;++seed) {
        double left=values[a],right=values[b];
        int unordered=isnan(left)||isnan(right);
        unsigned ah=2 | ((left==right||unordered)?0x40:0) |
            (unordered?4:0) | ((left<right||unordered)?1:0);
        unsigned low=(ah&0x44)==0 || (ah&0x44)==0x44;
        g_eax=0xA5C30000|(seed<<8)|0x77;
        g_ecx=0x12345678;g_edx=0x87654321;g_ebx=0x11223344;
        g_esi=0x55667788;g_edi=0x99AABBCC;g_esp=0x100000;
        g_fp_top=0;g_fp_stack[0]=left;g_fp_stack[1]=right;
        functions[f]();
        if(g_eax!=(0xA5C30000|(ah<<8)|low) || g_esp!=0x100004 || g_fp_top!=2 ||
           g_ecx!=0x12345678 || g_edx!=0x87654321 || g_ebx!=0x11223344 ||
           g_esi!=0x55667788 || g_edi!=0x99AABBCC) {
            fprintf(stderr,"FAIL f=%u a=%u b=%u seed=%u eax=%08X ah=%02X low=%u top=%d\\n",
                f,a,b,seed,g_eax,ah,low,g_fp_top); return 1;
        }
        ++cases;
    }
    printf("PASS: %u translated x87 compare/LAHF/parity cases\\n",cases);
    return 0;
}
'''
    directory=ROOT/('build/tests/x87-lahf-prior' if baseline else 'build/tests/x87-lahf-execution')
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'x87_lahf_test.c'
    source.write_text(preamble+'\n'.join(bodies)+driver,encoding='utf-8',newline='\n')
    p=ws.paths(); env=ws.vs_environment(p); exe=directory/'x87_lahf_test.exe'
    ws.run([p['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/templates/runtime'),source,
        '/Fe'+str(exe),'/Fo'+str(directory)+'\\'],name='x87-lahf-build',env=env)
    if baseline:
        result=subprocess.run([str(exe)],capture_output=True,timeout=10,env=env)
        (directory/'negative-control.log').write_bytes(result.stdout+result.stderr)
        if result.returncode!=1: raise RuntimeError('Prior omission unexpectedly passed')
        print('PASS: negative control rejects the prior missing-LAHF semantics')
    else:
        ws.run([exe],name='x87-lahf-execution',env=env)
    ws.write_json(directory/'manifest.json',{'scope':'Synthetic translated CPU fixture; no game input',
        'source_sha256':ws.digest(source),'executable_sha256':ws.digest(exe),
        'lifter_sha256':ws.digest(ROOT/'runtime/xboxrecomp/tools/recomp/lifter.py'),
        'cases':65536 if not baseline else 1,'negative_control':baseline,'passed':True})

if __name__=='__main__': main()
