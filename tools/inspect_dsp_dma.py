"""Check actual GP-to-EP sample chronology in a bounded DSP DMA capture.

Splits 1024-byte EP reads into eight 128-byte u24 slices, matching their bytes
to earlier GP writes. Unknown/ambiguous/zero slices remain unverified. This is
an observation of this reached transfer shape, not an arbitrary DSP validator.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct


def inspect(path):
    raw=path.read_bytes();offset=0;writes={};results=[]
    while offset<len(raw):
        if offset+24>len(raw):raise ValueError('Incomplete DMA record header')
        magic,frame,gp,direction,address,length=struct.unpack_from('<6I',raw,offset)
        offset+=24
        if magic!=0x31414D44 or offset+length>len(raw):raise ValueError('Invalid/incomplete DMA record')
        payload=raw[offset:offset+length];offset+=length
        if gp and direction and length==128 and any(payload):
            writes.setdefault(hashlib.sha256(payload).digest(),set()).add(frame)
        if not gp and not direction and length==1024 and any(payload):
            producers=[]
            for start in range(0,1024,128):
                chunk=payload[start:start+128]
                matches=writes.get(hashlib.sha256(chunk).digest(),set()) if any(chunk) else set()
                producers.append(next(iter(matches)) if len(matches)==1 else None)
            complete=all(v is not None for v in producers)
            results.append(dict(ep_frame=frame,scratch_address=hex(address),producer_frames=producers,
                fully_observed=complete,
                consecutive=(all(b==a+1 for a,b in zip(producers,producers[1:])) if complete else None)))
    known=[row for row in results if row['fully_observed']]
    return dict(scope=__doc__,fully_observed_blocks=len(known),
        nonconsecutive_blocks=sum(not row['consecutive'] for row in known),results=results)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('--summary',action='store_true',help='Print coverage/counters without individual blocks')
    args=parser.parse_args()
    report=inspect(args.run/'dsp-dma.bin')
    identity=next((args.run/name for name in ['manifest.json','launch-manifest.json'] if (args.run/name).exists()),None)
    if identity:
        env=json.loads(identity.read_text(encoding='utf-8')).get('diagnostic_environment',{})
        period=int(env.get('RECOMP_DSP_DMA_PERIOD','0'))
        if period:
            windows={}
            for row in report['results']:
                if not row['fully_observed']:continue
                window=row['ep_frame']//(period*1500)
                item=windows.setdefault(str(window),dict(active_start_s=window*period,verified_blocks=0,errors=0))
                item['verified_blocks']+=1
                item['errors']+=not row['consecutive']
            report['periodic_windows']=windows
            report['verified_window_count']=len(windows)
    (args.run/'dsp-dma-slice-order.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','periodic_windows')}
                     if args.summary else report,indent=2))
    if report['nonconsecutive_blocks']:return 1
    if not report['fully_observed_blocks']:return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
