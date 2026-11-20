"""Build and run a hidden native GL test of generated bump fragment shaders."""
from pathlib import Path
import os,subprocess
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=ws.paths();env=ws.vs_environment(p)
    env['PATH']=str(ROOT/'build/host-workspace')+os.pathsep+env['PATH']
    out=ROOT/'build/tests/bump-shader';out.mkdir(parents=True,exist_ok=True)
    sdk=ROOT/'runtime/xboxrecomp/src/nv2a_gl';sdl=ROOT/'.deps/SDL2-2.32.10'
    exe=out/'test.exe'
    ws.run([p['host_compiler'],'/nologo','/O2','/I'+str(sdk),'/I'+str(sdl/'include'),
        ROOT/'probes/host_bump_shader.c',sdk/'gl_psh.c',sdk/'gl_api.c',
        str(sdl/'lib/x64/SDL2.lib'),'/Fe'+str(exe),'/Fo'+str(out)+'\\'],name='bump-shader-build',env=env)
    ws.run([exe],name='bump-shader-execution',env=env)
    baseline=out/'baseline.exe'
    ws.run([p['host_compiler'],'/nologo','/O2','/I'+str(sdk),'/I'+str(sdl/'include'),
        ROOT/'probes/host_bump_shader.c',ROOT/'references/nfsu2-sw/xboxrecomp/src/nv2a_gl/gl_psh.c',sdk/'gl_api.c',
        str(sdl/'lib/x64/SDL2.lib'),'/Fe'+str(baseline),'/Fo'+str(out)+'\\'],name='bump-shader-control-build',env=env)
    control=subprocess.run([str(baseline)],env=env,capture_output=True,text=True,timeout=30)
    if control.returncode!=6: raise RuntimeError(f'Expected old shader pixel failure, got {control.returncode}: {control.stderr}')
    (out/'baseline.log').write_text(control.stdout+control.stderr,encoding='utf-8')
    ws.write_json(out/'manifest.json',{'scope':'Synthetic generated fragment shader pixel checks; no game assets',
        'cases':3072,'source_sha256':ws.digest(ROOT/'probes/host_bump_shader.c'),
        'generator_sha256':ws.digest(sdk/'gl_psh.c'),'executable_sha256':ws.digest(exe),
        'baseline_expected_pixel_failure':control.returncode,'passed':True})

if __name__=='__main__':main()
