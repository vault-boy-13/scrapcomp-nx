"""Audit all recorded PCM values and compare a bounded capture with the stream.

Checks duration/format and exact current host volume/limiter transformation.
It reports signal statistics; it does not infer perceptual correctness from
low peaks, smoothness or the absence of clipping.
"""
from pathlib import Path
import argparse,json,re,subprocess,wave
import workspace as ws
from check_dma_alias import function

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);args=parser.parse_args();run=args.run.resolve()
    out=ROOT/'build/tests/audio-stream-analysis';out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'runtime/xboxrecomp/src/apu/apu_xaudio2.c'
    text=source.read_text(encoding='utf-8')
    initial=re.search(r'static float g_xa2_volume\s*=\s*([^;]+);',text).group(1)
    header=out/'safety.h'
    header.write_text('static float g_xa2_volume='+initial+';\n'+
        function(text,'void apu_output_safety('),encoding='utf-8',newline='\n')
    paths=ws.paths();env=ws.vs_environment(paths);exe=out/'host_audio_stream_check.exe'
    ws.run([paths['host_compiler'],'/nologo','/O2','/I'+str(out),ROOT/'probes/host_audio_stream_check.c',
        '/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='audio-stream-analysis-build',env=env)
    result=subprocess.run([exe,run/'audio-stream-input.wav',run/'audio-stream-output.wav'],
        env=env,capture_output=True,text=True,timeout=90)
    if result.returncode:raise RuntimeError(f'PCM audit failed: {result.returncode}: {result.stderr}')
    report=json.loads(result.stdout);report['scope']=__doc__
    manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    profile=[]
    for line in (run/'host.log').read_text(encoding='utf-8',errors='replace').splitlines():
        if line.startswith('[AUDIO] wall_ms='):
            profile.append({k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)})
    if profile:
        report['last_profile_audio_samples']=profile[-1]['samples']
        report['checkpoint_difference_frames']=profile[-1]['samples']-report['frames']
        if report['frames']+48000<profile[-1]['samples']:
            raise RuntimeError('Streaming capture ends more than one second before the last audio observation')
    interval=manifest['diagnostic_environment'].get('RECOMP_AUDIO_CAPTURE')
    if interval:
        start,duration=map(int,interval.split(','));checks={}
        for suffix in ['input','output']:
            with wave.open(str(run/f'audio-stream-{suffix}.wav'),'rb') as full:
                full.setpos(start*48000);actual=full.readframes(duration*48000)
            with wave.open(str(run/f'audio-{suffix}.wav'),'rb') as clip:
                expected=clip.readframes(clip.getnframes())
            checks[suffix]=len(expected)==duration*48000*4 and actual==expected
        report['bounded_capture_matches_stream']=checks
        if not all(checks.values()):raise RuntimeError('Independent bounded and streamed captures differ')
    report['source_sha256']=ws.digest(source)
    report['probe_sha256']=ws.digest(ROOT/'probes/host_audio_stream_check.c')
    report['executable_sha256']=ws.digest(exe)
    (run/'audio-stream-analysis.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('seconds','scope')},indent=2))

if __name__=='__main__':main()
