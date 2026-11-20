"""Compare the reached lifted copy routine against native memmove.

Game-derived C and section bytes remain in the ignored build directory.
The published driver and test data pattern contain no game code or assets.
"""
from pathlib import Path
import sys
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator


def main():
    image = ws.checked_image()
    config.configure_from_xbe(str(image))
    raw = image.read_bytes()
    start, end = 0x17BA30, 0x17BD6D
    translator = FunctionTranslator(raw, {
        start: {'_addr': start, 'start': hex(start), 'end': end,
                'size': end - start, 'section': '.text'},
    })
    translator.coalesce_function(start, end, [])
    body = translator.translate_function(start, translator.func_db[start])
    directory = ROOT / 'build/tests/memmove-execution'
    directory.mkdir(parents=True, exist_ok=True)
    section = next(s for s in config._SECTIONS if s.name == '.text')
    section_file = directory / 'private-text.bin'
    section_file.write_bytes(raw[section.raw_addr:section.raw_addr + section.raw_size])
    preamble = r'''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
RECOMP_TLS int g_df;
ptrdiff_t g_xbox_mem_offset;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
#undef RECOMP_ITAIL
#define RECOMP_ITAIL(va) do { fprintf(stderr,"Unexpected tail target %08X\n",(uint32_t)(va)); abort(); } while (0)
'''
    driver = r'''
static unsigned char expected[4096];
static unsigned long cases;
static int check(unsigned src, unsigned dst, unsigned n) {
    unsigned char *actual=(unsigned char *)(g_xbox_mem_offset+0x500000);
    for(unsigned i=0;i<4096;i++) actual[i]=expected[i]=(unsigned char)(i*37+n*13);
    memmove(expected+dst,expected+src,n);
    g_esp=0x700000; g_ebp=0x12345678; g_ebx=0x24681357;
    g_esi=0x13572468; g_edi=0x87654321; g_df=0;
    MEM32(g_esp)=0; MEM32(g_esp+4)=0x500000+dst;
    MEM32(g_esp+8)=0x500000+src; MEM32(g_esp+12)=n;
    sub_0017BA30();
    if(memcmp(actual,expected,4096) || g_eax!=0x500000+dst ||
       g_esp!=0x700004 || MEM32(0x6FFFFC)!=0x12345678 || g_ebx!=0x24681357 ||
       g_esi!=0x13572468 || g_edi!=0x87654321 || g_df) {
        fprintf(stderr,"FAIL src=%u dst=%u n=%u eax=%08X esp=%08X df=%d\n",
                src,dst,n,g_eax,g_esp,g_df);
        fprintf(stderr,"ebp=%08X ebx=%08X esi=%08X edi=%08X\n",g_ebp,g_ebx,g_esi,g_edi);
        for(unsigned i=0;i<4096;i++) if(actual[i]!=expected[i]) {
            fprintf(stderr,"first byte mismatch %u actual=%02X expected=%02X\n",i,actual[i],expected[i]); break;
        }
        return 0;
    }
    cases++; return 1;
}
int main(int argc,char **argv) {
    if(argc!=4) return 2;
    unsigned char *memory=calloc(1,8*1024*1024);
    if(!memory) return 2;
    g_xbox_mem_offset=(ptrdiff_t)memory;
    FILE *file=fopen(argv[1],"rb");
    unsigned va=strtoul(argv[2],NULL,0), size=strtoul(argv[3],NULL,0);
    if(!file || va+size>8*1024*1024 || fread(memory+va,1,size,file)!=size) return 2;
    fclose(file);
    const int distance[]={-63,-31,-7,-1,0,1,3,7,15,31,64,128,512};
    for(unsigned n=0;n<=512;n++) for(unsigned a=0;a<4;a++) {
        for(unsigned d=0;d<sizeof(distance)/sizeof(distance[0]);d++)
            if(!check(128+a,128+a+distance[d],n)) return 1;
        for(unsigned b=0;b<4;b++) if(!check(128+a,2048+b,n)) return 1;
    }
    printf("Copy execution: PASS (%lu cases, lengths 0..512, alignment/overlap, return/stack/EBX/ESI/EDI/DF)\n",cases);
    free(memory); return 0;
}
'''
    source = directory / 'private-copy-test.c'
    source.write_text(preamble + body + driver, encoding='utf-8', newline='\n')
    tools = ws.paths()
    env = ws.vs_environment(tools)
    executable = directory / 'copy-test.exe'
    ws.run([tools['host_compiler'], '/nologo', '/TC', '/Od', '/we4013',
            '/I' + str(ROOT / 'runtime/xboxrecomp/templates/runtime'), str(source),
            '/Fo' + str(directory / 'copy-test.obj'), '/Fe' + str(executable)],
           name='memmove-execution-build', env=env)
    ws.run([executable, section_file, hex(section.va), str(section.raw_size)],
           name='memmove-execution', env=env)
    ws.write_json(directory / 'manifest.json', {
        'scope': 'Reached lifted copy routine compared against host memmove; not game boot',
        'image_sha256': ws.digest(image), 'source_sha256': ws.digest(source),
        'executable_sha256': ws.digest(executable), 'passed': True,
    })


if __name__ == '__main__':
    main()
