"""Check bounded host-run liveness, audio continuity and observed presentation pacing."""
import argparse,csv,json,math,re,statistics
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--scene-from',type=float,default=150)
    args=parser.parse_args();run=args.run
    manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    text=(run/'host.log').read_text(encoding='utf-8',errors='replace')
    health=[{key:int(value) for key,value in re.findall(r'(\w+)=(-?\d+)',line)}
            for line in text.splitlines() if line.startswith('[AUDIO] wall_ms=')]
    failures=[]
    def check(condition,message):
        if not condition:failures.append(message)
    check(manifest['exit_code']==3 and not manifest['timed_out'],
          'Expected the recorded bounded watchdog stop, without a premature guest/crash exit')
    check(manifest['original_inputs_unchanged'],'Original input inventory changed')
    check('[STOP]' not in text and '[EXIT] firmware=' not in text,'Guest stop/firmware error recorded')
    deadline=int(manifest['diagnostic_environment']['RECOMP_WATCHDOG_SECS'])*1000
    check(len(health)>=2,'Missing periodic audio observations')
    audio_rate=None
    if len(health)>=2:
        check(health[-1]['wall_ms']>=deadline-5000,'Audio progress stopped before the diagnostic deadline')
        check(all(not row['underruns'] and not row['dropped'] and not row['clipped'] for row in health),
              'Audio underruns, dropped blocks or clipping were observed')
        span=health[-1]['wall_ms']-health[0]['wall_ms']
        audio_rate=(health[-1]['samples']-health[0]['samples'])*1000/span if span else 0
        check(47040<=audio_rate<=48960,'Audio sample delivery does not track the 48 kHz device clock')
    with (run/'present-times.csv').open(encoding='utf-8') as stream:
        presents=[float(row['ms']) for row in csv.DictReader(stream)
                  if row['source']=='3d_present' and int(row['width']) and int(row['height'])]
    check(bool(presents),'No nonempty 3D presentations recorded')
    if presents:check(presents[-1]>=deadline-5000,'3D presentations stopped before the diagnostic deadline')
    scene=[at for at in presents if at>=args.scene_from*1000]
    intervals=sorted(b-a for a,b in zip(scene,scene[1:]))
    check(len(intervals)>=500,'Too few first-scene presentation observations')
    cadence={}
    if intervals:
        percentile=lambda p:intervals[min(len(intervals)-1,math.ceil(len(intervals)*p)-1)]
        cadence={'intervals':len(intervals),'median_ms':statistics.median(intervals),
                 'p95_ms':percentile(.95),'p99_ms':percentile(.99),'max_ms':intervals[-1]}
        check(cadence['p95_ms']<=50,'Observed scene p95 exceeds 50 ms')
        check(cadence['p99_ms']<=100,'Observed scene p99 exceeds 100 ms')
        check(cadence['max_ms']<2000,'Observed scene contains a presentation gap of at least two seconds')
    result={'scope':'Bounded native-host observation: liveness, audio counters/device-clock continuity and presentation intervals. '
                   'Watchdog exit3 is a diagnostic stop, not a normal game exit. Does not certify every scene/material/effect or simulation FPS.',
            'executable_sha256':manifest['executable_sha256'],'pdb_sha256':manifest['pdb_sha256'],
            'deadline_ms':deadline,'last_audio_ms':health[-1]['wall_ms'] if health else None,
            'last_3d_present_ms':presents[-1] if presents else None,'audio_samples_per_second':audio_rate,
            'audio_last':health[-1] if health else None,'scene_from_s':args.scene_from,
            'presentation_cadence':cadence,'failures':failures,'passed':not failures}
    (run/'stability-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
