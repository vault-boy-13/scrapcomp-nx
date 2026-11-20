"""Build/use the read-only audio source probe for a runner-owned Windows host."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/tests/audio-source-snapshot'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','capture'])
    parser.add_argument('--run',type=Path)
    parser.add_argument('--voice',default='74')
    args=parser.parse_args()
    executable=OUT/'snapshot.exe'
    if args.command=='build':
        paths=ws.paths();env=ws.vs_environment(paths);OUT.mkdir(parents=True,exist_ok=True)
        sdk=ROOT/'runtime/xboxrecomp/src'
        ws.run([paths['host_compiler'],'/nologo','/O2','/I'+str(sdk),'/I'+str(sdk/'apu'),'/I'+str(sdk/'nv2a'),
                ROOT/'probes/host_audio_snapshot.c','Dbghelp.lib','/Fe'+str(executable),'/Fo'+str(OUT)+'\\'],
               name='audio-source-snapshot-build',env=env)
        ws.write_json(OUT/'build.json',{'source_sha256':ws.digest(ROOT/'probes/host_audio_snapshot.c'),
            'state_header_sha256':ws.digest(sdk/'apu/apu_state.h'),'executable_sha256':ws.digest(executable),
            'dependency_lock_sha256':ws.digest(ROOT/'config/dependencies.lock.json')})
        return
    if not args.run:parser.error('--run is required for capture')
    run=args.run.resolve(strict=True)
    if not run.is_relative_to(ROOT/'runs/host'):parser.error('--run must belong to this workspace runner')
    voice=int(args.voice,16)
    if not 0<=voice<256:parser.error('voice must be 00..FF')
    built=json.loads((OUT/'build.json').read_text(encoding='utf-8'))
    if (built['source_sha256']!=ws.digest(ROOT/'probes/host_audio_snapshot.c') or
        built['state_header_sha256']!=ws.digest(ROOT/'runtime/xboxrecomp/src/apu/apu_state.h') or
        built['dependency_lock_sha256']!=ws.digest(ROOT/'config/dependencies.lock.json') or
        built['executable_sha256']!=ws.digest(executable)):raise RuntimeError('Rebuild stale snapshot probe')
    query="Get-CimInstance Win32_Process -Filter \"Name='scrapcomp_host.exe'\" | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json"
    raw=subprocess.check_output(['rtk','proxy','powershell','-NoProfile','-Command',query],text=True,encoding='utf-8-sig')
    processes=json.loads(raw) if raw.strip() else []
    if isinstance(processes,dict):processes=[processes]
    expected=ROOT/'build/host-workspace/scrapcomp_host.exe'
    owned=[p for p in processes if str(run/'saves').lower() in p['CommandLine'].lower()
           and Path(p['ExecutablePath']).resolve()==expected.resolve()]
    if len(owned)!=1:raise RuntimeError('Expected exactly one running host owned by this run')
    manifest=json.loads((expected.parent/'game-build-manifest.json').read_text(encoding='utf-8'))
    if ws.digest(expected)!=manifest['executable_sha256'] or ws.digest(expected.with_suffix('.pdb'))!=manifest['pdb_sha256']:
        raise RuntimeError('Host artifact/symbol hashes differ from build manifest')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    prefix=run/f'audio-source-{voice:02x}-{stamp}'
    subprocess.run([str(executable),str(owned[0]['ProcessId']),str(expected),str(expected.parent),
                    f'{voice:02x}',str(prefix)],check=True,timeout=20)
    report=json.loads(prefix.with_suffix('.json').read_text(encoding='utf-8'))
    report.update(source_sha256=ws.digest(prefix.with_suffix('.pcm')),
                  low_alias_sha256=ws.digest(Path(str(prefix)+'-low.pcm')),
                  host_executable_sha256=manifest['executable_sha256'],pdb_sha256=manifest['pdb_sha256'])
    ws.write_json(prefix.with_suffix('.json'),report)
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
