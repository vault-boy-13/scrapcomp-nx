"""Compile/execute synthetic translated REP MOVS/STOS with real MMIO rewriting."""
from pathlib import Path
import sys
import workspace as ws
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator
from tools.recomp.mmio_rewrite import rewrite

def main():
    destination=ROOT/'build/tests/mmio-strings'
    destination.mkdir(parents=True,exist_ok=True)
    bodies=[]
    for index,opcode in enumerate(('f3a4','f366a5','f3a5','f3aa','f366ab','f3ab')):
        # CMP EAX,EBX; REP; JNE bad; RET; bad: MOV EAX,DEADBEEF; RET.
        raw=bytes.fromhex('39d8'+opcode+'7501c3b8efbeaddec3')
        base=0x10000+index*0x100
        config._SECTIONS=[config.Section('.text',base,len(raw),0,len(raw),True)]
        info={'_addr':base,'start':hex(base),'end':base+len(raw),'size':len(raw),'section':'.text'}
        translator=FunctionTranslator(raw,{base:info})
        body=rewrite(translator.translate_function(base,info))
        bodies.append(body)
    source=destination/'functions.c'
    source.write_text('#define RECOMP_GENERATED_CODE\n#include "recomp_types.h"\n'+'\n'.join(bodies),
                      encoding='utf-8',newline='\n')
    p=ws.paths()
    env=ws.vs_environment(p)
    exe=destination/'mmio_strings.exe'
    ws.run([p['host_compiler'],'/nologo','/Od','/we4013',
        '/I'+str(ROOT/'runtime/xboxrecomp/templates/runtime'),
        ROOT/'probes/host_mmio_strings.c',source,'/Fe'+str(exe),
        '/Fo'+str(destination)+'\\'],name='mmio-string-build',env=env)
    ws.run([exe],name='mmio-string-execution',env=env)
    ws.write_json(destination/'manifest.json',{
        'scope':'Synthetic x86 REP; no game data. MMIO host backing is PAGE_NOACCESS.',
        'rewrite_sha256':ws.digest(ROOT/'runtime/xboxrecomp/tools/recomp/mmio_rewrite.py'),
        'source_sha256':ws.digest(source),'fixture_sha256':ws.digest(ROOT/'probes/host_mmio_strings.c'),
        'executable_sha256':ws.digest(exe),'passed':True})

if __name__=='__main__':
    main()
