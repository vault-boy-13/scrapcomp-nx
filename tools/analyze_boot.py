"""Report bounded static boot candidates; all game-derived results stay in generated/."""
import argparse
from collections import deque
import json
from pathlib import Path
import sys

import capstone
from capstone.x86_const import X86_OP_IMM
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/xboxrecomp'))
from tools.xbe_parser.xbe_parser import XBEParser


def analyze(depth=2, limit=80):
    path = ws.checked_image()
    image = XBEParser(str(path)).parse()
    raw = path.read_bytes()
    base = ROOT / 'generated' / ws.IMAGE['sha256'][:16]
    directory = base / 'analysis/disasm'
    functions = json.loads((directory / 'functions.json').read_text())
    by_va = {int(f['start'], 16): f for f in functions}
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    decoder.detail = True
    work = deque([(image.header.entry_point, 0, 'XBE header entry')])
    seen = set()
    output = []
    while work and len(output) < limit:
        address, level, provenance = work.popleft()
        if address in seen:
            continue
        seen.add(address)
        function = by_va.get(address)
        if not function:
            output.append({'va': f'0x{address:08X}', 'provenance': provenance,
                           'status': 'missing discovery record'})
            continue
        section = next(s for s in image.sections
                       if s.virtual_addr <= address < s.virtual_addr + s.raw_size)
        offset = section.raw_addr + address - section.virtual_addr
        instructions = list(decoder.disasm(raw[offset:offset + function['size']], address))
        calls, pushed_code = [], []
        for instruction in instructions:
            if instruction.mnemonic == 'call':
                calls.append({'site': f'0x{instruction.address:08X}', 'operand': instruction.op_str,
                              'direct': bool(instruction.operands and instruction.operands[0].type == X86_OP_IMM)})
                if level < depth and instruction.operands and instruction.operands[0].type == X86_OP_IMM:
                    work.append((instruction.operands[0].imm, level + 1,
                                 f'direct call at 0x{instruction.address:08X}'))
            if instruction.mnemonic == 'push' and instruction.operands[0].type == X86_OP_IMM:
                target = instruction.operands[0].imm & 0xFFFFFFFF
                if target in by_va:
                    pushed_code.append({'site': f'0x{instruction.address:08X}', 'value': f'0x{target:08X}',
                                        'interpretation': 'code-valued argument, possible callback; not runtime proof'})
                    if level < depth:
                        work.append((target, level + 1, f'code-valued push at 0x{instruction.address:08X}'))
        output.append({'va': f'0x{address:08X}', 'name': function['name'], 'section': section.name,
                       'provenance': provenance, 'depth': level, 'calls': calls, 'code_arguments': pushed_code,
                       'discovery_method': function['detection_method'],
                       'instructions': [{'va': f'0x{i.address:08X}', 'mnemonic': i.mnemonic,
                                         'operands': i.op_str} for i in instructions]})
    markers = []
    strings = json.loads((directory / 'strings.json').read_text())
    for string in strings:
        if ('python script subsystem' not in string['string'].lower()
                and 'pyinterface' not in string['string'].lower()):
            continue
        refs = []
        for address in string.get('referenced_from', []):
            va = int(address, 16)
            owners = [f['start'] for f in functions if int(f['start'], 16) <= va < int(f['end'], 16)]
            refs.append({'site': address, 'candidate_functions': owners})
        markers.append({'address': string['address'], 'string': string['string'], 'references': refs})
    result = {
        'scope': 'Static candidates from configured disassembly, not reached-path or ABI verification',
        'image_sha256': ws.IMAGE['sha256'], 'functions_db_sha256': ws.digest(directory / 'functions.json'),
        'depth_limit': depth, 'function_limit': limit, 'truncated': bool(work),
        'functions': output, 'python_markers': markers,
    }
    destination = base / 'analysis/boot-path.json'
    ws.write_json(destination, result)
    print(json.dumps({'report': str(destination), 'functions': len(output),
                      'python_marker_count': len(markers)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--depth', type=int, default=2)
    parser.add_argument('--limit', type=int, default=80)
    args = parser.parse_args()
    if not 0 <= args.depth <= 8 or not 1 <= args.limit <= 1000:
        parser.error('depth must be 0..8 and limit 1..1000')
    analyze(args.depth, args.limit)
