"""Translate synthetic CLI/STI functions and test the real runtime scheduler."""
from pathlib import Path
import subprocess
import sys
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator
from tools.recomp.spin_hint import rewrite as mark_spin_loops


def main():
    base = 0x10000
    poll = bytes.fromhex('c7050400200001000000a10000200085c074f7c3')
    raw = bytes.fromhex('fafac3').ljust(16, b'\xcc') + bytes.fromhex('fbc3').ljust(16, b'\xcc') + poll
    config._SECTIONS = [config.Section('.text', base, len(raw), 0, len(raw), True)]
    database = {start: {'_addr': start, 'start': hex(start), 'end': end,
                        'size': end - start, 'section': '.text'}
                for start, end in [(base, base + 3), (base + 16, base + 18),
                                   (base + 32, base + len(raw))]}
    translator = FunctionTranslator(raw, database)
    body = '#define RECOMP_GENERATED_CODE\n#include "recomp_types.h"\n'
    body += '\n'.join(translator.translate_function(start, info)
                      for start, info in database.items())
    body, spin_loops = mark_spin_loops(body)
    if 'RECOMP_SPIN_HINT();' not in body:
        raise RuntimeError('Synthetic memory poll was not recognized')
    build = ROOT / 'build/host-workspace'
    source = build / 'cpu-tests/interrupt_functions.c'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(body, encoding='utf-8', newline='\n')
    tools = ws.paths()
    env = ws.vs_environment(tools)
    ws.run([tools['cmake'], '-S', ROOT, '-B', build], name='interrupt-configure', env=env)
    ws.run([tools['cmake'], '--build', build, '--target', 'host_interrupt_probe', '--parallel', '1'],
           name='interrupt-build', env=env)
    executable = build / 'host_interrupt_probe.exe'
    output = subprocess.run([str(executable)], cwd=source.parent, env=env,
                            capture_output=True, timeout=10)
    (ROOT / 'build/logs/interrupt-execution.log').write_bytes(output.stdout + output.stderr)
    print((output.stdout + output.stderr).decode('utf-8', errors='replace'))
    output.check_returncode()
    ws.write_json(source.parent / 'interrupt-manifest.json', {
        'scope': 'Synthetic CPU/scheduler test; no game inputs', 'x86_hex': raw.hex(),
        'source_sha256': ws.digest(source), 'executable_sha256': ws.digest(executable),
        'passed': True,
    })


if __name__ == '__main__':
    main()
