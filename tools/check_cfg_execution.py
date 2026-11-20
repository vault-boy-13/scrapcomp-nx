"""Compile/execute independently constructed x86 CFG recovery on the host."""
from pathlib import Path
import sys
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator


def main():
    base = 0x10000
    # xor eax,eax; loop: test ecx,ecx; jne valid; int3;
    # valid: add eax,ecx; dec ecx; jne loop; ret
    raw = bytes.fromhex('31c085c97501cc01c84975f6c3')
    split, end = base + 7, base + len(raw)
    config._SECTIONS = [config.Section('.text', base, 0x100, 0, 0x100, True)]
    database = {start: {'_addr': start, 'start': hex(start), 'end': upper,
                        'size': upper - start, 'section': '.text'}
                for start, upper in [(base, split), (split, end)]}
    translator = FunctionTranslator(raw.ljust(0x100, b'\xcc'), database)
    translator.coalesce_function(base, end, [split])
    body = translator.translate_function(base, translator.func_db[base])
    directory = ROOT / 'build/tests/cfg-execution'
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'cfg_loop.c'
    preamble = '''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
'''
    driver = '''
int main(void) {
    const unsigned cases[] = {1,2,13,127};
    for(unsigned i=0;i<4;i++) {
        unsigned n=cases[i];
        g_ecx=n; g_esp=0x10000; g_ebx=0x12345678;
        g_esi=0x24681357; g_edi=0x87654321;
        sub_00010000();
        if(g_eax!=n*(n+1)/2 || g_ecx!=0 || g_esp!=0x10004 ||
           g_ebx!=0x12345678 || g_esi!=0x24681357 || g_edi!=0x87654321) {
            fprintf(stderr,"CFG execution failed for n=%u\\n",n); return 1;
        }
    }
    puts("CFG execution: PASS (loop backedge, flags, stack, preserved registers)");
    return 0;
}
'''
    source.write_text(preamble + body + driver, encoding='utf-8', newline='\n')
    tools = ws.paths()
    env = ws.vs_environment(tools)
    executable = directory / 'cfg_loop.exe'
    ws.run([tools['host_compiler'], '/nologo', '/TC', '/Od', '/we4013',
            '/I' + str(ROOT / 'runtime/xboxrecomp/templates/runtime'), str(source),
            '/Fo' + str(directory / 'cfg_loop.obj'), '/Fe' + str(executable)],
           name='cfg-execution-build', env=env)
    ws.run([executable], name='cfg-execution', env=env)
    ws.write_json(directory / 'manifest.json', {
        'scope': 'Synthetic CPU/CFG fixture; no game code or data',
        'x86_hex': raw.hex(), 'source_sha256': ws.digest(source),
        'executable_sha256': ws.digest(executable), 'passed': True,
    })


if __name__ == '__main__':
    main()
