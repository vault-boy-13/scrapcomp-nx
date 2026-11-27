#!/usr/bin/env python3
"""Workspace commands for the Original Xbox Scrapland port (native Windows Python).

No command edits reference checkouts or game inputs. Build outputs are local.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime/xboxrecomp'
LOCK = ROOT / 'config/references.lock.json'
IMAGE = json.loads((ROOT / 'config/scrapland/image.json').read_text(encoding='utf-8'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def run(args, *, name, cwd=ROOT, env=None):
    logfile = ROOT / 'build/logs' / (name + '.log')
    logfile.parent.mkdir(parents=True, exist_ok=True)
    print(f'[{name}] {subprocess.list2cmdline([str(a) for a in args])}', flush=True)
    with logfile.open('w', encoding='utf-8') as output:
        result = subprocess.run(['rtk', 'proxy', *map(str, args)], cwd=cwd,
                                env=env, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join(logfile.read_text(encoding='utf-8', errors='replace').splitlines()[-35:]))
        raise RuntimeError(f'{name} failed ({result.returncode}); see {logfile}')
    print(f'[{name}] OK — {logfile.relative_to(ROOT)}', flush=True)


def capture(args, cwd=ROOT, env=None):
    return subprocess.check_output(['rtk', 'proxy', *map(str, args)], cwd=cwd,
                                   env=env, text=True, encoding='utf-8', errors='replace').strip()


def paths():
    custom = ROOT / 'config/workspace.local.json'
    config = json.loads(custom.read_text(encoding='utf-8')) if custom.exists() else {}
    vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    vs = Path(config.get('visual_studio') or capture([vswhere, '-latest', '-products', '*',
                  '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath']))
    dkp = Path(config.get('devkitpro', 'C:/devkitPro'))
    return {
        'vs': vs, 'dkp': dkp,
        'cmake': vs / 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe',
        'ninja': vs / 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe',
        'host_compiler': Path(config.get('host_compiler') or
            sorted((vs / 'VC/Tools/MSVC').glob('*/bin/Hostx64/x64/cl.exe'))[-1]),
        'renderdoc': Path(config.get('renderdoc', ROOT / '.deps/RenderDoc_1.47_64')),
        'ryubing': ROOT / 'emu/Ryubing/Ryujinx.exe',
    }


def vs_environment(p):
    # cmd is used only to obtain the VS compiler environment, never for file operations.
    script = p['vs'] / 'Common7/Tools/VsDevCmd.bat'
    batch = ROOT / 'build/msvc-environment.cmd'
    batch.parent.mkdir(parents=True, exist_ok=True)
    batch.write_text(f'@call "{script}" -arch=amd64 -host_arch=amd64 >nul\n'
                     '@if errorlevel 1 exit /b 1\n@set\n', encoding='utf-8')
    raw = subprocess.check_output(['rtk', 'proxy', 'cmd.exe', '/d', '/c',
                                   'build\\msvc-environment.cmd'], cwd=ROOT)
    env = os.environ.copy()
    for line in raw.decode('utf-8', errors='replace').splitlines():
        if '=' in line and not line.startswith('='):
            key, value = line.split('=', 1)
            # Windows environment names are case-insensitive; remove differently cased aliases.
            for old in list(env):
                if old.lower() == key.lower():
                    env.pop(old)
            env[key] = value
    # Prefer English diagnostics if that language pack exists. CMake separately
    # probes /showIncludes in UTF-8 because localized installations may fall back.
    env['VSLANG'] = '1033'
    return env


def materialize(reference, prefix, target):
    pins = json.loads(LOCK.read_text(encoding='utf-8'))
    commit = pins[reference]['commit']
    marker = target / '.workspace-source.json'
    identity = {'reference': reference, 'commit': commit, 'prefix': prefix}
    if marker.exists():
        if json.loads(marker.read_text()) != identity:
            raise RuntimeError(f'{target} has another source identity; preserve it before changing the pin')
        return
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f'Refusing to overwrite nonempty untracked source directory: {target}')
    archive = subprocess.check_output(['rtk', 'proxy', 'git', '-C', str(ROOT / 'references' / reference),
                                       'archive', '--format=tar', commit, prefix])
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        for member in bundle:
            member_path = Path(member.name)
            if not member_path.is_relative_to(prefix):
                continue  # git archive also emits ancestor directory records
            relative = member_path.relative_to(prefix)
            if not relative.parts:
                continue
            if member.issym() or member.islnk() or '..' in relative.parts:
                raise RuntimeError(f'Unsupported source archive entry: {member.name}')
            destination = target / relative
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(bundle.extractfile(member).read())
    write_json(marker, identity)


def prepare():
    materialize('nfsu2-sw', 'xboxrecomp', RUNTIME)
    materialize('BLACK-NX-PORT', 'XboxXBE-Recomp', ROOT / '.deps/XboxXBE-Recomp')
    materialize('BLACK-NX-PORT', 'third_party/tomlplusplus', ROOT / '.deps/tomlplusplus')
    for category, source in [('hle-tools', ROOT / '.deps/XboxXBE-Recomp'), ('runtime', RUNTIME)]:
        # git apply skips paths outside its working subdirectory, even with
        # --check. Use the repository root and explicitly prefix patch paths.
        directory = f'--directory={source.relative_to(ROOT).as_posix()}'
        for patch in sorted((ROOT / 'patches' / category).glob('*.patch')):
            already = subprocess.run(
                ['rtk', 'proxy', 'git', 'apply', directory, '--reverse', '--check', str(patch)],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if already.returncode:
                run(['git', 'apply', directory, '--check', patch], name=category + '-check-' + patch.stem)
                run(['git', 'apply', directory, patch], name=category + '-apply-' + patch.stem)
    for relative in ['src/game', 'src/platform/host', 'src/platform/switch', 'src/gpu/common',
                     'src/gpu/gl', 'src/gpu/deko3d', 'patches/runtime', 'runs', 'artifacts']:
        (ROOT / relative).mkdir(parents=True, exist_ok=True)
    run([sys.executable, '-m', 'pip', 'check'], name='python-dependencies')
    print('Pinned runtime and HLE tooling sources are materialized; reference trees untouched.')


def checked_image():
    xbe = ROOT / IMAGE['path']
    if digest(xbe) != IMAGE['sha256']:
        raise RuntimeError('Input XBE hash differs from config/scrapland/image.json; audit the new image first')
    return xbe


def analysis_directory():
    return ROOT / 'generated' / IMAGE['sha256'][:16] / 'analysis'


def analyze():
    checked_image()
    run([sys.executable, ROOT / 'tools/analyze_image.py'], name='analyze-image')


def generate():
    checked_image()
    base = analysis_directory()
    env = os.environ.copy()
    env.update(PYTHONPATH=str(RUNTIME), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    out = base.parent / 'c'
    seeds_path = ROOT / 'config/scrapland/seed_functions.json'
    seeds_sha256 = digest(seeds_path)
    seeds = json.loads(seeds_path.read_text())
    detected = {int(item['start'], 16) for item in
                json.loads((base / 'disasm/functions.json').read_text())}
    if any(int(item['start'], 0) not in detected for item in seeds):
        raise RuntimeError('Analysis is missing configured seeds; run analyze before generate')
    recovery = ROOT / IMAGE['coalesce_functions'] if IMAGE.get('coalesce_functions') else None
    recovery_args = ['--coalesce-functions', recovery] if recovery else []
    wrappers = ROOT / IMAGE['manual_wrappers'] if IMAGE.get('manual_wrappers') else None
    wrappers_sha256 = digest(wrappers) if wrappers else None
    wrapper_args = ['--exclude-manual', wrappers] if wrappers else []
    run([sys.executable, '-B', '-m', 'tools.recomp', ROOT / IMAGE['path'],
         '--game-name', 'Scrapland', '--all', '--split', '150', '--gen-dir', out,
         '--output-dir', base.parent / 'lift-report', '--disasm-dir', base / 'disasm',
         '--func-id-dir', base / 'func_id', '--abi-dir', base / 'abi',
         '--mmio-sections', ','.join(IMAGE['mmio_sections']), *recovery_args, *wrapper_args],
        name='generate-c', cwd=RUNTIME, env=env)
    if digest(seeds_path) != seeds_sha256:
        raise RuntimeError('Seeds changed during generation; refusing a mismatched manifest')
    if wrappers and digest(wrappers) != wrappers_sha256:
        raise RuntimeError('Manual wrappers changed during generation; refusing a mismatched manifest')
    files = [p for p in out.iterdir() if p.is_file()]
    write_json(base.parent / 'codegen-manifest.json', {
        'image_sha256': IMAGE['sha256'], 'runtime_source': json.loads((RUNTIME / '.workspace-source.json').read_text()),
        'config_sha256': digest(ROOT / 'config/scrapland/image.json'),
        'coalesce_sha256': digest(recovery) if recovery else None,
        'seeds_sha256': seeds_sha256,
        'manual_wrappers_sha256': wrappers_sha256,
        'files': {p.name: digest(p) for p in sorted(files)},
        'status': 'Generated; not yet CPU conformance or gameplay validated',
    })


def build_host():
    p = paths()
    env = vs_environment(p)
    build = ROOT / 'build/host-workspace'
    run([p['cmake'], '--fresh', '-S', ROOT, '-B', build, '-G', 'Ninja',
         f'-DCMAKE_MAKE_PROGRAM={p["ninja"].as_posix()}', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
         f'-DCMAKE_C_COMPILER={p["host_compiler"].as_posix()}',
         f'-DCMAKE_CXX_COMPILER={p["host_compiler"].as_posix()}'], name='host-configure', env=env)
    run([p['cmake'], '--build', build, '--parallel', '4'], name='host-build', env=env)
    run([build / 'workspace_probe.exe'], name='host-probe', env=env)


def scan_xdk():
    xbe = checked_image()
    out = analysis_directory() / 'hle'
    out.mkdir(parents=True, exist_ok=True)
    run([ROOT / 'build/host-workspace/xbe_symbols.exe', xbe,
         ROOT / '.deps/XboxXBE-Recomp/xdk', '--out', out / 'game.toml', '--name', 'scrapland'],
        name='scan-xdk')


def build_switch():
    p = paths()
    run([p['dkp'] / 'msys2/usr/bin/bash.exe', '--noprofile', '--norc',
         ROOT / 'tools/build-switch.sh'], name='switch-build')


def build_game_switch():
    from game_switch import build
    build()


def stage():
    build = ROOT / 'build/switch-workspace'
    destination = ROOT / 'switch_sd/switch/scrapland-workspace'
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    for stem in ['runtime_probe', 'deko_probe', 'gl_probe', 'deko_game_frame']:
        for extension in ['nro', 'elf', 'map']:
            source = build / (stem + '.' + extension)
            if not source.exists():
                raise RuntimeError(f'Missing artifact: {source}; run build-switch first')
            shutil.copy2(source, destination / source.name)
            files.append({'name': source.name, 'sha256': digest(source), 'size': source.stat().st_size})
    sources = [ROOT / 'CMakeLists.txt', ROOT / 'cmake/switch-toolchain.cmake', ROOT / 'tools/build-switch.sh']
    sources += [p for p in (ROOT / 'probes').rglob('*') if p.is_file()]
    manifest = {
        'purpose': 'Workspace/runtime/GPU probes and captured-frame replay tool',
        'files': files, 'date_utc': datetime.now(timezone.utc).isoformat(),
        'sources': {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(sources)},
        'dependencies_lock_sha256': digest(ROOT / 'config/dependencies.lock.json'),
    }
    build_id = hashlib.sha256(json.dumps({k: v for k, v in manifest.items() if k != 'date_utc'}, sort_keys=True).encode()).hexdigest()[:16]
    manifest['build_id'] = build_id
    write_json(destination / 'manifest.json', manifest)
    archived = ROOT / 'artifacts' / build_id
    archived.mkdir(parents=True, exist_ok=True)
    if not (archived / 'manifest.json').exists():
        for record in files:
            shutil.copy2(destination / record['name'], archived / record['name'])
        write_json(archived / 'manifest.json', manifest)
    print(destination)


def doctor():
    p = paths()
    checks = {key: {'path': str(value), 'exists': value.exists()} for key, value in p.items()}
    checks['runtime'] = {'exists': (RUNTIME / 'CMakeLists.txt').exists()}
    checks['deko3d'] = {'release': (p['dkp'] / 'libnx/lib/libdeko3d.a').exists(),
                       'debug': (p['dkp'] / 'libnx/lib/libdeko3dd.a').exists()}
    checks['switch_gl'] = {name: (p['dkp'] / ('portlibs/switch/lib/' + name)).exists()
                           for name in ['libSDL2.a', 'libEGL.a', 'libglapi.a', 'libdrm_nouveau.a']}
    checks['input_xbe'] = {'sha256_matches': digest(ROOT / IMAGE['path']) == IMAGE['sha256']}
    checks['python_packages'] = json.loads(capture([sys.executable, '-m', 'pip', 'list', '--format=json']))
    checks['zydis_commit'] = capture(['git', '-C', ROOT / '.deps/zydis', 'rev-parse', 'HEAD'])
    checks['zycore_commit'] = capture(['git', '-C', ROOT / '.deps/zydis/dependencies/zycore', 'rev-parse', 'HEAD'])
    checks['devkit_packages'] = capture([p['dkp'] / 'msys2/usr/bin/bash.exe', '--noprofile', '--norc', '-c',
        'rtk proxy pacman -Q devkitA64 libnx deko3d uam switch-mesa switch-sdl2 switch-cmake'])
    write_json(ROOT / 'reports/workspace-environment.json', checks)
    print(json.dumps(checks, indent=2, ensure_ascii=False))


def check():
    p = paths()
    env = vs_environment(p)
    native_llvm = Path('C:/Program Files/LLVM/bin')
    env['PATH'] = str(native_llvm) + os.pathsep + env.get('PATH', env.get('Path', ''))
    env.update(PYTHONPATH=str(RUNTIME), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    tests = ['test_lifter_atomics.py', 'test_mmio_rewrite.py', 'test_translator_xmm_state.py',
             'test_fallthrough.py', 'test_x87_classification.py', 'test_runtime_helpers_defined.py']
    run([sys.executable, '-m', 'pytest', *[RUNTIME / 'tools/recomp' / t for t in tests],
         '-q', '--import-mode=importlib', '-p', 'no:cacheprovider'], name='tool-tests', env=env)
    build = ROOT / 'build/host-workspace'
    run([p['cmake'], '--build', build, '--target', 'd3d8_smoke', 'd3d8_states_smoke', '--parallel', '4'],
        name='format-tests-build', env=env)
    for target in ['d3d8_smoke', 'd3d8_states_smoke']:
        run([build / 'xboxrecomp/src/d3d/d3d8_smoke' / (target + '.exe')], name=target, env=env)


def emu_prepare(stage_probes=True):
    source = Path(os.environ['APPDATA']) / 'Ryujinx'
    destination = ROOT / '.cache/ryubing-workspace'
    destination.mkdir(parents=True, exist_ok=True)
    config_path = destination / 'Config.json'
    if not config_path.exists():
        config = json.loads((source / 'Config.json').read_text(encoding='utf-8-sig'))
        config.update(check_updates_on_start=False, enable_discord_integration=False,
                      enable_file_log=True, graphics_backend='Vulkan', res_scale=1,
                      enable_internet_access=False, game_dirs=[], autoload_dirs=[],
                      show_confirm_exit=False)
        write_json(config_path, config)
    # Reuse only installed system prerequisites, never the user's savedata,
    # game profiles, game-specific settings or writable SD tree. No key values
    # are logged, transformed or added to repository artifacts.
    for relative in ['system', 'bis/system']:
        target = destination / relative
        if not target.exists():
            shutil.copytree(source / relative, target)
    if stage_probes:
        sd = destination / 'sdcard/switch/scrapland-workspace'
        sd.mkdir(parents=True, exist_ok=True)
        staged = ROOT / 'switch_sd/switch/scrapland-workspace'
        for entry in staged.iterdir():
            if entry.is_file():
                shutil.copy2(entry, sd / entry.name)
    print(f'Isolated emulator root: {destination}')


def lock_dependencies():
    p = paths()
    trees = {}
    for name, directory in [('xboxrecomp', RUNTIME), ('XboxXBE-Recomp', ROOT / '.deps/XboxXBE-Recomp'),
                            ('tomlplusplus', ROOT / '.deps/tomlplusplus')]:
        content = {f.relative_to(directory).as_posix(): digest(f)
                   for f in sorted(directory.rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
        trees[name] = {'identity': json.loads((directory / '.workspace-source.json').read_text()),
                       'tree_sha256': hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest(),
                       'file_count': len(content)}
    data = {
        'source_trees_after_patches': trees,
        'zydis': {'repository': 'https://github.com/zyantific/zydis.git',
                  'commit': capture(['git', '-C', ROOT / '.deps/zydis', 'rev-parse', 'HEAD']),
                  'zycore_commit': capture(['git', '-C', ROOT / '.deps/zydis/dependencies/zycore', 'rev-parse', 'HEAD'])},
        'python_requirements_sha256': digest(ROOT / 'config/python-requirements.lock.txt'),
        'patches': {f.relative_to(ROOT).as_posix(): digest(f) for f in sorted((ROOT / 'patches').rglob('*.patch'))},
        'devkit_packages': json.loads((ROOT / 'reports/workspace-environment.json').read_text())['devkit_packages'],
        'tool_binaries': {name: {
            'path': path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name,
            'sha256': digest(path),
        } for name, path in {
            'host_compiler': p['host_compiler'], 'native_cmake': p['cmake'], 'native_ninja': p['ninja'],
            'aarch64_gcc': p['dkp'] / 'devkitA64/bin/aarch64-none-elf-gcc.exe',
            'uam': p['dkp'] / 'tools/bin/uam.exe', 'libnx': p['dkp'] / 'libnx/lib/libnx.a',
            'deko3d': p['dkp'] / 'libnx/lib/libdeko3d.a', 'ryubing': p['ryubing'],
        }.items()},
        'renderdoc': json.loads((ROOT / 'config/renderdoc.lock.json').read_text()),
    }
    write_json(ROOT / 'config/dependencies.lock.json', data)
    print('config/dependencies.lock.json written')


def build_game_host():
    from game_host import build
    build()


def run_game_host():
    from game_host import run
    raise SystemExit(run(15))


def stage_game_emu():
    from game_switch import stage_emulator
    stage_emulator()


def boot_report():
    from analyze_boot import analyze
    analyze()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'doctor', 'analyze', 'generate', 'build-host',
                                           'build-switch', 'scan-xdk', 'stage', 'check',
                                           'emu-prepare', 'lock-dependencies', 'boot-report',
                                           'build-game-host', 'run-game-host', 'build-game-switch', 'stage-game-emu'])
    args = parser.parse_args()
    globals()[args.command.replace('-', '_')]()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
