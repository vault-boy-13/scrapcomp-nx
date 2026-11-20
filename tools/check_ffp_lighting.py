"""Verify production fixed-function lighting against known synthetic GPU outputs."""
from pathlib import Path
import os
import subprocess
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]

def main():
    paths=ws.paths();env=ws.vs_environment(paths)
    env['PATH']=str(ROOT/'build/host-workspace')+os.pathsep+env['PATH']
    out=ROOT/'build/tests/ffp-lighting';out.mkdir(parents=True,exist_ok=True)
    sdk=ROOT/'runtime/xboxrecomp/src/nv2a_gl';sdl=ROOT/'.deps/SDL2-2.32.10'
    command=[paths['host_compiler'],'/nologo','/O2','/I'+str(sdk),'/I'+str(sdl/'include'),
             ROOT/'probes/host_ffp_lighting.c',sdk/'gl_vsh.c',sdk/'gl_api.c',
             sdl/'lib/x64/SDL2.lib','/Fo'+str(out)+'\\']
    executable=out/'test.exe'
    ws.run([*command,'/Fe'+str(executable)],name='ffp-lighting-build',env=env)
    ws.run([executable],name='ffp-lighting-execution',env=env)
    control=out/'baseline.exe'
    ws.run([*command,'/DBASELINE_NO_LIGHTING','/Fe'+str(control)],name='ffp-lighting-control-build',env=env)
    result=subprocess.run([str(control)],env=env,capture_output=True,text=True,timeout=30)
    (out/'baseline.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode!=6:raise RuntimeError('Expected known ambient-color failure: '+result.stderr)
    ws.write_json(out/'manifest.json',{'scope':'Synthetic float GPU pixels; no game assets',
        'passed':True,'source_sha256':ws.digest(ROOT/'probes/host_ffp_lighting.c'),
        'generator_sha256':ws.digest(sdk/'gl_vsh.c'),'uniform_packer_sha256':ws.digest(sdk/'gl_lighting.h'),
        'executable_sha256':ws.digest(executable),'baseline_expected_failure':result.returncode})

if __name__=='__main__':main()
