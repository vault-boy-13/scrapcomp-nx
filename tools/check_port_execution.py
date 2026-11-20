"""Execute synthetic x86 IN/WBINVD against the bounded host GPIO model."""
from pathlib import Path
import subprocess
import sys
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator


def main():
    # cmp esi,edi; wbinvd; in al,dx; jne bad; ret; bad: mov eax,DEADBEEF; ret
    raw = bytes.fromhex('39fe0f09ec7501c3b8efbeaddec3')
    base = 0x10000
    config._SECTIONS = [config.Section('.text', base, len(raw), 0, len(raw), True)]
    info = {'_addr': base, 'start': hex(base), 'end': base + len(raw),
            'size': len(raw), 'section': '.text'}
    translator = FunctionTranslator(raw, {base: info})
    body = translator.translate_function(base, info)
    directory = ROOT / 'build/tests/port-execution'
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'port_test.c'
    preamble = '''#define RECOMP_GENERATED_CODE
#include "recomp_types.h"
#include <stdio.h>
#include <stdlib.h>
RECOMP_TLS uint32_t g_eax,g_ecx,g_edx,g_esp,g_ebx,g_esi,g_edi,g_ebp,g_seh_ebp;
volatile int g_gil_contended;
void recomp_preempt(void) { abort(); }
void recomp_unimpl(const char *instruction, uint32_t va) {
    fprintf(stderr, "Expected strict stop: %s guest=%08X\\n", instruction, va);
    exit(77);
}
'''
    driver = '''
int main(int argc, char **argv) {
    if(argc>1) {
        if(argv[1][0]=='p') recomp_port_in(0x1234,1,0x1000);
        else recomp_port_in(0x80C0,2,0x1000);
        return 1;
    }
    recomp_port_out(0x80C0,255,1,0x1000);
    for(unsigned i=0;i<1000;i++) {
        g_eax=0x123456FF; g_edx=0xABCD80C0; g_esp=0x10000;
        g_esi=7; g_edi=7;
        sub_00010000();
        unsigned expected=0x12345600|((i&1)?0:0x20);
        if(g_eax!=expected || g_edx!=0xABCD80C0 || g_esp!=0x10004) return 2;
    }
    g_esi=7; g_edi=8; g_esp=0x10000;
    sub_00010000();
    if(g_eax!=0xDEADBEEF || g_esp!=0x10004) return 3;
    puts("PASS: 1001 translated IN/WBINVD calls, high EAX/DX, flags, stack, field parity");
    return 0;
}
'''
    source.write_text(preamble + body + driver, encoding='utf-8', newline='\n')
    tools = ws.paths()
    env = ws.vs_environment(tools)
    objects = []
    for input_path in [source, ROOT / 'src/runtime/io_ports.c', ROOT / 'src/runtime/cache.c']:
        obj = directory / (input_path.stem + '.obj')
        ws.run([tools['host_compiler'], '/nologo', '/c', '/Od', '/we4013',
                '/I' + str(ROOT / 'runtime/xboxrecomp/templates/runtime'),
                input_path, '/Fo' + str(obj)], name='port-execution-' + input_path.stem, env=env)
        objects.append(obj)
    executable = directory / 'port_test.exe'
    ws.run([tools['host_compiler'], '/nologo', *objects, '/Fe' + str(executable)],
           name='port-execution-link', env=env)
    ws.run([executable], name='port-execution', env=env)
    for argument in ['port', 'width']:
        result = subprocess.run([str(executable), argument], capture_output=True, timeout=10, env=env)
        (directory / (argument + '.log')).write_bytes(result.stdout + result.stderr)
        if result.returncode != 77:
            raise RuntimeError('Unsupported ' + argument + ' did not terminate strictly')
    ws.write_json(directory / 'manifest.json', {
        'scope': 'Synthetic CPU/GPIO fixture; no game code or data', 'x86_hex': raw.hex(),
        'source_sha256': ws.digest(source), 'executable_sha256': ws.digest(executable),
        'runtime_sources': {p: ws.digest(ROOT / p) for p in ['src/runtime/io_ports.c', 'src/runtime/cache.c']},
        'unsupported_port_and_width': 'strict exit 77', 'passed': True,
    })


if __name__ == '__main__':
    main()
