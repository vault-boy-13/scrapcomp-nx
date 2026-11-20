"""Summarize captured PCM and presentation cadence; these are not gameplay FPS."""
from pathlib import Path
import argparse,array,csv,json,math,re,statistics,wave


def signal(path):
    with wave.open(str(path),'rb') as stream:
        assert stream.getsampwidth()==2 and stream.getnchannels()==2
        rate=stream.getframerate();samples=array.array('h',stream.readframes(stream.getnframes()))
    windows=[]
    for at in range(0,len(samples),rate*2):
        block=samples[at:at+rate*2];n=len(block)
        rms=math.sqrt(sum(x*x for x in block)/n)
        windows.append({'sample_second':at/(rate*2),'rms_dbfs':20*math.log10(rms/32768) if rms else None,
            'dc':sum(block)/n,'peak':max(abs(x) for x in block),
            'clipped':sum(abs(x)>=32767 for x in block)})
    return {'rate':rate,'frames':len(samples)//2,'seconds':len(samples)/(rate*2),'windows':windows}


def cadence(path):
    previous=None;groups={}
    for row in csv.DictReader(path.open(encoding='utf-8')):
        if not row.get('height') or not int(row['width']) or not int(row['height']):
            previous=None
            continue
        source=row['source'];now=float(row['ms'])
        shape=(row['width'],row['height'])
        if previous and previous[0]==source and previous[2]==shape:
            delta=now-previous[1]
            groups.setdefault((source,int(now//10000)),[]).append(delta)
        previous=(source,now,shape)
    result=[]
    for (source,bucket),values in sorted(groups.items()):
        values.sort()
        def percentile(p): return values[min(len(values)-1,math.ceil(len(values)*p)-1)]
        result.append({'source':source,'present_time_bucket_s':bucket*10,'intervals':len(values),
            'median_ms':statistics.median(values),'p95_ms':percentile(.95),'p99_ms':percentile(.99),
            'max_ms':values[-1]})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run
    result={'scope':'Presentation intervals include diagnostics and are not simulation FPS; PCM is actual captured stereo',
        'run':run.name}
    for name in ['audio-input.wav','audio-output.wav']:
        if (run/name).exists(): result[name]=signal(run/name)
    if (run/'present-times.csv').exists(): result['presentation_cadence']=cadence(run/'present-times.csv')
    text=(run/'host.log').read_text(encoding='utf-8',errors='replace')
    lines=[line for line in text.splitlines() if line.startswith('[AUDIO] wall_ms=')]
    result['audio_queue_health']=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)} for line in lines]
    (run/'av-analysis.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    for name in ['audio-input.wav','audio-output.wav']:
        if name in result:
            windows=result[name]['windows']
            print(name,'seconds',result[name]['seconds'],'peak',max(w['peak'] for w in windows),
                  'clipped',sum(w['clipped'] for w in windows),
                  'rms_dbfs_range',[min((w['rms_dbfs'] for w in windows if w['rms_dbfs'] is not None),default=None),
                                    max((w['rms_dbfs'] for w in windows if w['rms_dbfs'] is not None),default=None)])
    for source in ['3d_present','video_refresh']:
        print(source,'latest intervals:',[row for row in result.get('presentation_cadence',[]) if row['source']==source][-3:])
    print('Latest audio queue:',result['audio_queue_health'][-1:] )


if __name__=='__main__': main()
