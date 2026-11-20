"""Verify exact bounded pre/post output capture without an audio device."""
from pathlib import Path
import subprocess
import wave
import array
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT/'build/tests/audio-capture'
    directory.mkdir(parents=True, exist_ok=True)
    source = directory/'audio_capture_test.c'
    capture = ROOT/'src/platform/host/audio_capture.c'
    source.write_text(r'''
#include <windows.h>
#include <assert.h>
static ULONGLONG tick=1000;
static ULONGLONG fixture_clock(void) { return tick; }
#define GetTickCount64 fixture_clock
#include "CAPTURE_SOURCE"
#undef GetTickCount64
static Xa2Observer installed;
void xa2_set_observer(Xa2Observer cb) { installed=cb; }
int main(void) {
    _putenv_s("RECOMP_AUDIO_CAPTURE","1,1");_putenv_s("RECOMP_HOST_PROFILE","1");
    scrap_host_audio_observe_install();assert(installed&&observation.capture);
    Xa2Stats stats={0};
    for(unsigned base=0;base<96000;base+=256) {
        int16_t input[512],output[512],copy[512];
        for(unsigned i=0;i<256;i++) {
            input[i*2]=(int16_t)((int)((base+i)%5000)-2500);
            input[i*2+1]=(int16_t)(-input[i*2]);
            output[i*2]=(int16_t)(input[i*2]/2);output[i*2+1]=(int16_t)(input[i*2+1]/2);
        }
        memcpy(copy,input,sizeof input);
        stats.samples+=256;stats.submitted++;tick+=6;
        installed(input,NULL,0,12,&stats);
        installed(input,output,256,7,&stats);
        assert(!memcmp(copy,input,sizeof input));
    }
    assert(!observation.capture&&observation.frames==48000&&observation.skip==0);
    assert(!observation.input&&!observation.output);
    installed=NULL;_putenv_s("RECOMP_AUDIO_CAPTURE","1,31");_putenv_s("RECOMP_HOST_PROFILE","0");
    scrap_host_audio_observe_install();assert(!installed&&!observation.capture);
    puts("PASS: bounded stereo WAV capture, partial-block skip, dropped block exclusion, exact duration and read-only input");
    return 0;
}
'''.replace('CAPTURE_SOURCE', capture.as_posix()), encoding='utf-8', newline='\n')
    paths=ws.paths();env=ws.vs_environment(paths);exe=directory/'audio_capture_test.exe'
    ws.run([paths['host_compiler'],'/nologo','/Od','/we4013',
            '/I'+str(ROOT/'runtime/xboxrecomp/src/apu'),source,
            '/Fe'+str(exe),'/Fo'+str(directory)+'\\'],name='audio-capture-build',env=env)
    result=subprocess.run([str(exe)],cwd=directory,capture_output=True,timeout=10,env=env)
    (directory/'test.log').write_bytes(result.stdout+result.stderr)
    if result.returncode: raise RuntimeError('Audio capture fixture failed')
    for name,divisor in [('audio-input.wav',1),('audio-output.wav',2)]:
        with wave.open(str(directory/name),'rb') as wav:
            assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())==(2,2,48000,48000)
            actual=array.array('h',wav.readframes(48000))
        expected=array.array('h')
        for frame in range(48000,96000):
            value=frame%5000-2500
            value=int(value/divisor)
            expected.extend([value,-value])
        assert actual==expected,name
    ws.write_json(directory/'manifest.json',{'scope':'Synthetic PCM, no audio device or game input',
        'source_sha256':ws.digest(capture),'fixture_sha256':ws.digest(source),
        'input_wav_sha256':ws.digest(directory/'audio-input.wav'),
        'output_wav_sha256':ws.digest(directory/'audio-output.wav'),'passed':True})
    print('PASS: 192000 exact PCM values, WAV metadata, skip/cap/bounds and dropped blocks')


if __name__=='__main__':
    main()
