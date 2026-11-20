"""Verify bounded exact streaming PCM, durable headers and partial finalization."""
from pathlib import Path
import array,subprocess,wave
import workspace as ws

ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'build/tests/audio-stream';out.mkdir(parents=True,exist_ok=True)
    capture=ROOT/'src/platform/host/audio_capture.c'
    cfile=out/'fixture.c'
    cfile.write_text(r'''
#include <windows.h>
#include <assert.h>
#include "CAPTURE"
static Xa2Observer installed;
void xa2_set_observer(Xa2Observer cb) {installed=cb;}
static void feed(unsigned total) {
    Xa2Stats stats={0};
    for(unsigned base=0;base<total;base+=256) {
        unsigned n=total-base<256?total-base:256;
        int16_t input[512],output[512],saved[512];
        for(unsigned i=0;i<n;i++) {
            int16_t v=(int16_t)((int)((base+i)%5000)-2500);
            input[i*2]=v;input[i*2+1]=-v;
            output[i*2]=v/2;output[i*2+1]=-v/2;
        }
        memcpy(saved,input,n*4);
        installed(input,NULL,0,12,&stats); /* Dropped blocks have no PCM. */
        installed(input,output,n,7,&stats);
        assert(!memcmp(saved,input,n*4));
    }
}
int main(void) {
    _putenv_s("RECOMP_AUDIO_CAPTURE","");_putenv_s("RECOMP_HOST_PROFILE","0");
    _putenv_s("RECOMP_AUDIO_STREAM","2");scrap_host_audio_observe_install();
    assert(installed&&streaming.input);feed(60000);
    assert(streaming.frames==60000&&streaming.checkpoint>=48000);
    /* Durable RIFF size is visible before close, despite buffered writes. */
    FILE *f=fopen("audio-stream-input.wav","rb");assert(f);
    uint32_t bytes;assert(!fseek(f,40,SEEK_SET));assert(fread(&bytes,4,1,f)==1);
    fclose(f);assert(bytes==streaming.checkpoint*4);
    scrap_host_audio_observe_finish();assert(!streaming.input&&!streaming.output);
    assert(!rename("audio-stream-input.wav","partial-input.wav"));
    assert(!rename("audio-stream-output.wav","partial-output.wav"));
    _putenv_s("RECOMP_AUDIO_STREAM","1");scrap_host_audio_observe_install();
    assert(streaming.frames==0);feed(48256);
    assert(streaming.frames==48000&&!streaming.input&&!streaming.output);
    puts("PASS: exact bounded PCM, per-second durable headers, partial close, dropped-block exclusion and reset");
    return 0;
}
'''.replace('CAPTURE',capture.as_posix()),encoding='utf-8',newline='\n')
    paths=ws.paths();env=ws.vs_environment(paths);exe=out/'fixture.exe'
    # Avoid carrying a previous fixture's partial output into rename checks.
    for name in ['partial-input.wav','partial-output.wav']:
        p=out/name
        if p.exists():p.unlink()
    ws.run([paths['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/src/apu'),cfile,'/Fe'+str(exe),'/Fo'+str(out)+'\\'],
        name='audio-stream-build',env=env)
    result=subprocess.run([exe],cwd=out,env=env,capture_output=True,timeout=10)
    (out/'test.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(f'Stream fixture failed: {result.returncode}')
    for name,frames,divisor in [('partial-input.wav',60000,1),('partial-output.wav',60000,2),
        ('audio-stream-input.wav',48000,1),('audio-stream-output.wav',48000,2)]:
        with wave.open(str(out/name),'rb') as f:
            assert (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getnframes())==(2,2,48000,frames)
            actual=array.array('h',f.readframes(frames))
        expected=array.array('h',(c for i in range(frames) for c in
            (int((i%5000-2500)/divisor),-int((i%5000-2500)/divisor))))
        assert actual==expected,name
    ws.write_json(out/'manifest.json',dict(scope=__doc__,source_sha256=ws.digest(capture),
        fixture_sha256=ws.digest(cfile),executable_sha256=ws.digest(exe),passed=True))
    print(result.stdout.decode().strip())

if __name__=='__main__':main()
