"""Check integer MMX helpers against SSE2 with both host decoder compile modes."""
from pathlib import Path
import json
import workspace as ws

ROOT=Path(__file__).resolve().parents[1]


def main():
    directory=ROOT/'build/tests/xmv-mmx';directory.mkdir(parents=True,exist_ok=True)
    source=ROOT/'probes/host_xmv_mmx.c'
    header=ROOT/'runtime/xboxrecomp/templates/runtime/recomp_types.h'
    paths=ws.paths();env=ws.vs_environment(paths);results=[]
    for mode in ['Od','O2']:
        exe=directory/f'mmx-{mode}.exe'
        ws.run([paths['host_compiler'],'/nologo',f'/{mode}','/fp:strict',
                '/I'+str(header.parent),source,'/Fe'+str(exe),'/Fo'+str(directory/f'mmx-{mode}.obj')],
               name=f'xmv-mmx-{mode}-build',env=env)
        ws.run([exe],name=f'xmv-mmx-{mode}-run',env=env)
        results.append(dict(optimization=mode,executable_sha256=ws.digest(exe),passed=True))
    ws.write_json(directory/'manifest.json',dict(
        scope='Integer helper semantics on native x86 SSE2 hardware; not complete XMV decoder equivalence or ARM64 validation',
        source_sha256=ws.digest(source),runtime_header_sha256=ws.digest(header),results=results))


if __name__=='__main__':main()
