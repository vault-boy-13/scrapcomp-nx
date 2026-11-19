"""Analyze only configured code sections; keep all outputs outside SDK sources."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime/xboxrecomp'
sys.path.insert(0, str(RUNTIME))
sys.dont_write_bytecode = True
from tools.xbe_parser.xbe_parser import XBEParser, export_json
from tools.disasm.disasm import Disassembler
from tools.disasm import config as disasm_config

image_config = json.loads((ROOT / 'config/scrapland/image.json').read_text())
xbe = ROOT / image_config['path']
base = ROOT / 'generated' / image_config['sha256'][:16] / 'analysis'
base.mkdir(parents=True, exist_ok=True)
analysis_json = base / 'image.json'
image = XBEParser(str(xbe)).parse()
export_json(image, str(analysis_json))


class ScraplandDisassembler(Disassembler):
    def _get_target_sections(self):
        # Flags alone include .bss_ste and data. An explicit, audited whitelist
        # overrides only target selection, preserving the donor's analysis passes.
        expected = set(image_config['code_sections'])
        selected = [section for section in self.image.sections if section.name in expected]
        if {section.name for section in selected} != expected:
            raise ValueError('The input is missing configured code sections')
        return selected


disasm_config.configure_from_xbe(str(xbe))
seeds = json.loads((ROOT / 'config/scrapland/seed_functions.json').read_text())
seed_addresses = [int(item['start'], 0) for item in seeds]
previous_manifest = base / 'input-manifest.json'
force = (not previous_manifest.exists()
         or json.loads(previous_manifest.read_text()) != image_config)
disassembler = ScraplandDisassembler(str(xbe), analysis_json=str(analysis_json),
    output_dir=str(base / 'disasm'), verbose=True, seed_functions=seed_addresses, force=force)
if not disassembler.run():
    raise SystemExit('Disassembly failed')
# The donor OutputWriter lists every executable-flagged section, including
# sections not selected by this driver. Preserve its list and label the actual
# sweep explicitly so diagnostic metadata cannot imply .bss/DOLBY were analyzed.
summary_path = base / 'disasm/summary.json'
summary = json.loads(summary_path.read_text())
summary['driver_selected_code_sections'] = image_config['code_sections']
summary['section_selection_note'] = 'sections_analyzed is the donor image-wide inventory; only driver_selected_code_sections were swept'
summary_path.write_text(json.dumps(summary, indent=2) + '\n')

env = os.environ.copy()
env.update(PYTHONPATH=str(RUNTIME), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
for module, args in [
    ('tools.func_id', ['--functions', base / 'disasm/functions.json', '--strings', base / 'disasm/strings.json',
                       '--xrefs', base / 'disasm/xrefs.json', '--output', base / 'func_id']),
    ('tools.abi_analysis', ['--disasm-dir', base / 'disasm', '--func-id-dir', base / 'func_id',
                           '--output-dir', base / 'abi']),
]:
    subprocess.run(['rtk', 'proxy', sys.executable, '-B', '-m', module, str(xbe), *map(str, args)],
                   cwd=RUNTIME, env=env, check=True)
(base / 'input-manifest.json').write_text(json.dumps(image_config, indent=2) + '\n')
