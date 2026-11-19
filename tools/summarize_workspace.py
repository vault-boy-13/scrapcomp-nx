"""Summarize existing build/test evidence; does not run or certify the game."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def log(name):
    return (ROOT / 'build/logs' / name).read_text(encoding='utf-8', errors='replace')


staged = ROOT / 'switch_sd/switch/scrapland-workspace'
manifest = load('switch_sd/switch/scrapland-workspace/manifest.json')
artifacts = []
for record in manifest['files']:
    path = staged / record['name']
    if sha(path) != record['sha256']:
        raise SystemExit(f'Artifact hash mismatch: {path.name}')
    if path.suffix == '.nro':
        assert path.read_bytes()[0x10:0x14] == b'NRO0', path.name
    elif path.suffix == '.elf':
        header = path.read_bytes()[:64]
        assert header[:4] == b'\x7fELF' and struct.unpack_from('<H', header, 18)[0] == 183, path.name
    artifacts.append(record)

profile = ROOT / '.cache/ryubing-workspace/sdcard/switch/scrapland-workspace'
runtime = json.loads((profile / 'runtime-probe-results.json').read_text())
gl = (profile / 'gl-probe.log').read_text()
deko = (profile / 'deko-probe.log').read_text()
tools = log('tool-tests.log')
assert '24 passed' in tools
assert 'ALL PASS' in log('d3d8_smoke.log')
assert '0 FAILURE(S)' in log('d3d8_states_smoke.log')
assert all(runtime.values()), runtime
assert 'presented 60 frames, GL error 0' in gl
assert 'presented 60 frames' in deko
scanner = re.search(r'found (\d+) of (\d+) functions, (\d+) of (\d+) data', log('scan-xdk.log'))
lift = load('generated/14ecbbcf23613a91/lift-report/summary.json')
summary = {
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Workspace/toolchain/probes validation only; Scrapland has not booted',
    'artifact_build_id': manifest['build_id'],
    'artifact_manifest_sha256': sha(staged / 'manifest.json'),
    'dependencies_lock_sha256': sha(ROOT / 'config/dependencies.lock.json'),
    'switch_artifacts_verified': artifacts,
    'native_tools': {name: sha(ROOT / 'build/host-workspace' / name)
                     for name in ['xbe_symbols.exe', 'xbe_recomp.exe', 'workspace_probe.exe']},
    'donor_tool_tests': '24 passed, 2 subtests passed',
    'd3d_format_tests': 'ALL PASS', 'd3d_state_tests': '0 failures',
    'ryubing_runtime_probe': runtime,
    'ryubing_gl_probe': {'sixty_presents': True, 'gl_error': 0, 'log': gl.splitlines()},
    'ryubing_deko_probe': {'sixty_presents': True, 'log': deko.splitlines()},
    'presentation_note': 'GPU probes need a visible window on this emulator; hidden mode did not confirm 60 frames',
    'xdk_signature_scan': {'functions_found': int(scanner[1]), 'database_functions': int(scanner[2]),
                           'data_found': int(scanner[3]), 'database_data': int(scanner[4]),
                           'abi_and_call_site_validation': False},
    'initial_codegen': {key: lift[key] for key in ['total', 'translated', 'failed', 'total_lines', 'unresolved_stubs']},
    'unimplemented_diagnostic_entries': sum(len(values) for values in lift.get('unimplemented', {}).values()),
    'unsupported_mnemonics': {key: len(value) for key, value in lift.get('unimplemented', {}).items()},
    'generated_code_game_build': False,
    'arm64_game_conformance': False,
    'renderdoc_installed_cli_verified': True,
    'renderdoc_capture_replay_verified': False,
    'nvk_sdk_installed': False,
    'switch_hardware_tested': False,
}
(ROOT / 'reports/workspace-validation.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: value for key, value in summary.items()
                  if key not in ['switch_artifacts_verified', 'native_tools', 'unsupported_mnemonics',
                                 'ryubing_gl_probe', 'ryubing_deko_probe']}, indent=2))
