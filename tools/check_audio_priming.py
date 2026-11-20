"""Exercise actual XAudio2 startup, intentional starvation and reinitialization."""
from pathlib import Path
import subprocess
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/'build/tests/audio-priming'
    out.mkdir(parents=True, exist_ok=True)
    paths = ws.paths()
    env = ws.vs_environment(paths)
    inputs = {}
    for name, relative, expected in [
        ('fixed', 'runtime/xboxrecomp/src/apu/apu_xaudio2.c', 0),
        ('baseline', 'references/nfsu2-sw/xboxrecomp/src/apu/apu_xaudio2.c', 6)]:
        backend = ROOT/relative
        cfile = out/(name+'.c')
        cfile.write_text('''#include <stdlib.h>
#include "BACKEND"
int main(void) {
    const int16_t silence[256][2]={{0}};
    Xa2Stats stats;
    if(!xa2_init())return 2;
    for(unsigned i=0;i<3;i++) {
        if(!xa2_submit_samples(&silence[0][0],256))return 3;
        Sleep(30); /* Slower than one block: no playback before prefill. */
        if(xa2_queued()!=(int)i+1) {xa2_shutdown();return 6;}
    }
    for(unsigned i=3;i<(unsigned)xa2_queue_target();i++)
        if(!xa2_submit_samples(&silence[0][0],256))return 4;
    xa2_get_stats(&stats);
    if(stats.underruns || stats.dropped || stats.clipped)return 7;
    Sleep(180); /* Deliberately exhaust a started device. */
    if(xa2_queued()!=0)return 8;
    if(!xa2_submit_samples(&silence[0][0],256))return 9;
    xa2_get_stats(&stats);
    if(stats.underruns!=1)return 10; /* Real starvation must stay visible. */
    xa2_shutdown();
    if(!xa2_init())return 11;
    if(!xa2_submit_samples(&silence[0][0],256))return 12;
    Sleep(30);
    xa2_get_stats(&stats);
    if(xa2_queued()!=1 || stats.submitted!=1 || stats.underruns)return 13;
    xa2_shutdown();
    puts("PASS: real XAudio2 prefill, playback, intentional starvation detection, clean reinitialization");
    return 0;
}
'''.replace('BACKEND', backend.as_posix()), encoding='utf-8', newline='\n')
        exe = out/(name+'.exe')
        ws.run([paths['host_compiler'], '/nologo', '/O2',
                '/I'+str(ROOT/'runtime/xboxrecomp/src/apu'), cfile,
                '/Fe'+str(exe), '/Fo'+str(out)+'\\'], name='audio-prime-'+name+'-build', env=env)
        result = subprocess.run([exe], env=env, capture_output=True, text=True, timeout=20)
        (out/(name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
        print(name, result.returncode, result.stdout.strip())
        if result.returncode != expected:
            raise RuntimeError(f'{name}: expected {expected}, got {result.returncode}: {result.stderr}')
        inputs[name] = {'backend_sha256': ws.digest(backend), 'fixture_sha256': ws.digest(cfile),
                        'executable_sha256': ws.digest(exe), 'exit_code': result.returncode}
    ws.write_json(out/'manifest.json', {'scope': 'Real Windows XAudio2 device, silent PCM, deliberate producer delay',
                                      'inputs': inputs, 'passed': True})


if __name__ == '__main__':
    main()
