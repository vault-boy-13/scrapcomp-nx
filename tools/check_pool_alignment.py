"""Execute actual pool bridges against the whole-page allocation contract."""
from pathlib import Path
import subprocess
import workspace as ws
from check_dma_alias import function

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'build/tests/pool-alignment'
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'runtime/xboxrecomp/src/kernel/kernel_bridge.c'
    baseline = ROOT / 'references/nfsu2-sw/xboxrecomp/src/kernel/kernel_bridge.c'
    prelude = '''#include <stdint.h>
#include <stdio.h>
#define KERNEL_LOG_ON() 0
static uint32_t args[2], g_eax, next, last_size;
#define STACK_ARG(i) args[i]
static uint32_t xbox_HeapAlloc(uint32_t size, uint32_t alignment) {
    last_size=size;
    uint32_t result=(next+alignment-1)&~(alignment-1);
    next=result+size;return result;
}
'''
    fixture = '''
int main(void) {
    unsigned count=0;
    for(unsigned tagged=0;tagged<2;tagged++) {
        for(unsigned size=1;size<=8193;size++) {
            next=0x01391670;args[0]=size;args[1]=0x626F5344;
            if(tagged)bridge_ExAllocatePoolWithTag();else bridge_ExAllocatePool();
            if(last_size!=size || !g_eax || (g_eax&15))return 5;
            if(size>=4096 && (g_eax&4095)) {
                printf("Misaligned whole-page pool: size=%u va=%08X\\n",size,g_eax);return 6;
            }
            ++count;
        }
    }
    printf("PASS: %u actual pool bridge allocations, including 4095/4096/4097 boundaries\\n",count);
    return 0;
}
'''
    paths = ws.paths()
    env = ws.vs_environment(paths)
    for name, input_path, expected in [('fixed', source, 0), ('baseline', baseline, 6)]:
        text = input_path.read_text(encoding='utf-8')
        routines = ''.join(function(text, signature) for signature in
                           ['static void bridge_ExAllocatePool(void)', 'static void bridge_ExAllocatePoolWithTag(void)'])
        cfile = out / (name + '.c')
        cfile.write_text(prelude + routines + fixture, encoding='utf-8', newline='\n')
        exe = out / (name + '.exe')
        ws.run([paths['host_compiler'], '/nologo', '/O2', cfile,
                '/Fe'+str(exe), '/Fo'+str(out)+'\\'], name='pool-'+name+'-build', env=env)
        result = subprocess.run([exe], env=env, capture_output=True, text=True)
        print(name, result.returncode, result.stdout.strip())
        if result.returncode != expected:
            raise RuntimeError(f'{name} expected {expected}, got {result.returncode}: {result.stderr}')
    ws.write_json(out/'manifest.json', {'scope': 'Actual pool bridges; adversarial allocator cursor and whole-page API contract',
        'source_sha256': ws.digest(source), 'baseline_sha256': ws.digest(baseline),
        'fixture_sha256': ws.digest(out/'fixed.c'), 'passed': True, 'baseline_expected_failure': 6})


if __name__ == '__main__':
    main()
