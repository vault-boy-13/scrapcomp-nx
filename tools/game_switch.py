"""Build the ARM64 Scrapland game NRO and preserve matching local symbols."""
from datetime import datetime, timezone
import json
import os
import shutil

import workspace as ws
from fetch_xemu_dsp import fetch as fetch_dsp
from game_host import input_inventory, prepare

ROOT = ws.ROOT
BUILD = ROOT / 'build/switch-game'
STEM = 'scrapcomp_switch'
OUTPUTS = (STEM + '.nro', STEM + '.elf', STEM + '.map')


def build_inputs(base):
    paths = [ROOT / path for path in (
        'CMakeLists.txt', 'cmake/RealDsp.cmake', 'cmake/SwitchGame.cmake',
        'cmake/switch-toolchain.cmake', 'tools/build-switch.sh',
        'tools/game_switch.py', 'tools/game_host.py', 'tools/workspace.py',
        'config/scrapland/image.json',
        'config/dependencies.lock.json', 'config/xemu-dsp.lock.json',
        'runtime/xboxrecomp/.workspace-source.json', 'runtime/xboxrecomp/CMakeLists.txt',
    )]
    paths += [path for subtree in ('src/runtime', 'src/audio', 'src/platform/switch',
                                  'runtime/xboxrecomp/src', 'runtime/xboxrecomp/include')
              for path in (ROOT / subtree).rglob('*') if path.is_file()]
    strict = base / 'switch-strict'
    prepared = json.loads((strict / 'manifest.json').read_text(encoding='utf-8'))
    paths += [base / 'codegen-manifest.json', strict / 'manifest.json']
    paths += [strict / name for name in prepared['files']]
    return {path.relative_to(ROOT).as_posix(): ws.digest(path) for path in sorted(paths)}


def build():
    fetch_dsp()
    base = prepare('switch')
    inputs = build_inputs(base)
    dkp = ws.paths()['dkp'].resolve()
    env = os.environ.copy()
    env['DEVKITPRO'] = dkp.as_posix()
    trace_xpp = env.get('SCRAP_SWITCH_TRACE_XPP') == '1'
    bash = dkp / 'msys2/usr/bin/bash.exe'
    ws.run([bash, '--noprofile', '--norc', ROOT / 'tools/build-switch.sh',
            base.relative_to(ROOT).as_posix(), 'ON' if trace_xpp else 'OFF'],
           name='switch-game-build', env=env)
    if build_inputs(base) != inputs:
        raise RuntimeError('Switch inputs changed during compilation; rebuild')
    outputs = {name: ws.digest(BUILD / name) for name in OUTPUTS}
    build_id = outputs[STEM + '.nro']
    archive = ROOT / 'artifacts' / 'switch-game' / build_id / outputs[STEM + '.elf']
    archive.mkdir(parents=True, exist_ok=True)
    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'xbe_sha256': ws.IMAGE['sha256'],
        'settings': {'nv2a_backend': 'OpenGL', 'trace_xpp': trace_xpp},
        'inputs': inputs,
        'outputs': outputs,
        'devkitpro': dkp.as_posix(),
        'toolchain': ws.capture([bash, '--noprofile', '--norc', '-c',
                                 'rtk proxy pacman -Q devkitA64 libnx switch-cmake switch-sdl2 switch-mesa']),
        'artifact_directory': archive.relative_to(ROOT).as_posix(),
    }
    for name, expected in outputs.items():
        shutil.copy2(BUILD / name, archive / name)
        if ws.digest(archive / name) != expected:
            raise RuntimeError(f'Artifact changed while archiving: {name}')
    shutil.copy2(ROOT / 'build/logs/switch-game-build.log', archive / 'build.log')
    ws.write_json(archive / 'manifest.json', manifest)
    ws.write_json(BUILD / 'manifest.json', manifest)
    print(json.dumps(outputs, indent=2))


def stage_emulator():
    base = ROOT / 'generated' / ws.IMAGE['sha256'][:16]
    manifest = json.loads((BUILD / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['inputs'] != build_inputs(base):
        raise RuntimeError('Switch build inputs changed; run build-game-switch')
    archive = ROOT / manifest['artifact_directory']
    if any(ws.digest(archive / name) != manifest['outputs'][name] for name in OUTPUTS):
        raise RuntimeError('Archived Switch artifacts differ from the build manifest')

    ws.emu_prepare(stage_probes=False)
    destination = ROOT / '.cache/ryubing-workspace/sdcard/switch/scrapcomp-nx'
    game = destination / 'game'
    game.mkdir(parents=True, exist_ok=True)
    inventory = input_inventory()
    xbe = ws.IMAGE['path'].removeprefix('original/')
    if inventory[xbe]['sha256'] != ws.IMAGE['sha256']:
        raise RuntimeError('Original game XBE does not match the built image')
    staged_paths = {p.relative_to(game).as_posix() for p in game.rglob('*') if p.is_file()}
    unexpected = sorted(staged_paths - inventory.keys())
    if unexpected:
        raise RuntimeError('Unexpected files in emulator game directory: ' + ', '.join(unexpected))
    for relative, entry in inventory.items():
        target = game / relative
        expected = entry['sha256']
        if target.is_file() and target.stat().st_size == entry['size'] and ws.digest(target) == expected:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'original' / relative, target)
        if ws.digest(target) != expected:
            raise RuntimeError(f'Original data changed while staging: {relative}')

    nro = STEM + '.nro'
    shutil.copy2(archive / nro, destination / nro)
    if ws.digest(destination / nro) != manifest['outputs'][nro]:
        raise RuntimeError('Staged NRO hash mismatch')
    ws.write_json(destination / 'manifest.json', {'build': manifest, 'disc_input': inventory})
