"""Build/run the real generated game on Windows with strict bring-up diagnostics."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import workspace as ws

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/host-workspace'


def input_inventory():
    """Record complete immutable disc input, including unexpected new files."""
    original = ROOT / 'original'
    return {path.relative_to(original).as_posix():
            {'size': path.stat().st_size, 'sha256': ws.digest(path)}
            for path in sorted(original.rglob('*')) if path.is_file()}


def build_inputs(base):
    files = [ROOT / 'CMakeLists.txt', ROOT / 'config/dependencies.lock.json',
             ROOT / 'cmake/RealDsp.cmake', ROOT / 'config/xemu-dsp.lock.json',
             ROOT / 'config/sdl2.lock.json', ROOT / 'probes/host_sampler.c',
             base / 'codegen-manifest.json', base / 'host-strict/unresolved.c',
             base / 'host-strict/scrap_image.h',
             *sorted(p for p in (ROOT / 'src').rglob('*') if p.suffix in ('.c', '.h'))]
    dsp_lock = json.loads((ROOT / 'config/xemu-dsp.lock.json').read_text())
    files.extend(ROOT / '.deps/xemu-dsp' / item['path'] for item in dsp_lock['files'])
    result = {path.relative_to(ROOT).as_posix(): ws.digest(path) for path in files}
    rd_header = ws.paths()['renderdoc'] / 'renderdoc_app.h'
    if rd_header.exists():
        result['renderdoc_api_header'] = ws.digest(rd_header)
    return result


def prepare(platform='host'):
    image = ws.checked_image()
    lock = json.loads((ROOT / 'config/dependencies.lock.json').read_text())
    actual_patches = {p.relative_to(ROOT).as_posix(): ws.digest(p)
                      for p in sorted((ROOT / 'patches').rglob('*.patch'))}
    if lock['patches'] != actual_patches:
        raise RuntimeError('Runtime patch lock differs; validate intentional changes and lock-dependencies first')
    config = json.loads((ROOT / 'config/scrapland/image.json').read_text())
    base = ROOT / 'generated' / config['sha256'][:16]
    manifest = json.loads((base / 'codegen-manifest.json').read_text())
    if manifest['image_sha256'] != config['sha256']:
        raise RuntimeError('Codegen image identity mismatch; run analyze/generate')
    if manifest['config_sha256'] != ws.digest(ROOT / 'config/scrapland/image.json'):
        raise RuntimeError('Codegen configuration is stale; run analyze/generate')
    recovery = ROOT / config['coalesce_functions'] if config.get('coalesce_functions') else None
    wrappers = ROOT / config['manual_wrappers'] if config.get('manual_wrappers') else None
    if manifest.get('manual_wrappers_sha256') != (ws.digest(wrappers) if wrappers else None):
        raise RuntimeError('Manual wrapper scan differs from codegen; run generate')
    if manifest.get('coalesce_sha256') != (ws.digest(recovery) if recovery else None):
        raise RuntimeError('CFG recovery configuration is stale; run generate')
    if manifest.get('seeds_sha256') != ws.digest(ROOT / 'config/scrapland/seed_functions.json'):
        raise RuntimeError('Function seeds differ from codegen; run analyze/generate')
    for name, expected in manifest['files'].items():
        if ws.digest(base / 'c' / name) != expected:
            raise RuntimeError(f'Generated file differs from codegen manifest: {name}')
    # This reusable runtime header is copied by codegen, not lifted from the
    # game. Refresh it after a header-only portability patch without lifting
    # two million lines again; preserve and identify the previous manifest.
    template = ROOT / 'runtime/xboxrecomp/templates/runtime/recomp_types.h'
    header = base / 'c/recomp_types.h'
    if platform == 'host' and ws.digest(header) != ws.digest(template):
        previous = ws.digest(base / 'codegen-manifest.json')
        backup = base / ('codegen-manifest.before-header-' + previous[:16] + '.json')
        if not backup.exists():
            backup.write_bytes((base / 'codegen-manifest.json').read_bytes())
        header.write_bytes(template.read_bytes())
        manifest['files']['recomp_types.h'] = ws.digest(header)
        manifest['runtime_header_refresh'] = {
            'previous_manifest_sha256': previous, 'runtime_header_sha256': ws.digest(template),
            'patches': {p.relative_to(ROOT).as_posix(): ws.digest(p)
                        for p in sorted((ROOT / 'patches/runtime').glob('*.patch'))},
        }
        ws.write_json(base / 'codegen-manifest.json', manifest)
        print('Refreshed reusable runtime header; generated game C bodies unchanged')
    strict = base / (platform + '-strict')
    strict.mkdir(parents=True, exist_ok=True)
    strict_files = ['unresolved.c', 'scrap_image.h']
    if platform == 'switch':
        # Keep the original include order and the macros defined by each
        # generated translation unit. The host retains its generated tree.
        switch_c = strict / 'c'
        switch_c.mkdir(exist_ok=True)
        for name, expected in manifest['files'].items():
            if name == 'recomp_types.h':
                continue
            destination = switch_c / name
            if not destination.exists() or ws.digest(destination) != expected:
                shutil.copyfile(base / 'c' / name, destination)
        switch_header = switch_c / 'recomp_types.h'
        if not switch_header.exists() or ws.digest(switch_header) != ws.digest(template):
            switch_header.write_bytes(template.read_bytes())
        strict_files.extend('c/' + name for name in manifest['files'])
    original = (base / 'c/recomp_stubs_unresolved.c').read_text()
    matches = re.findall(r'void (sub_([0-9A-Fa-f]{8}))\(void\)\s*\{[^{}]*\}', original)
    count = len(re.findall(r'^void sub_', original, re.MULTILINE))
    if not count or len(matches) != count:
        raise RuntimeError('Unrecognized unresolved-stub format; refusing silent fallbacks')
    body = '#include <stdint.h>\nextern void scrap_stop_unresolved(uint32_t va);\n'
    body += '\n'.join(f'void {name}(void) {{ scrap_stop_unresolved(0x{address}u); }}'
                      for name, address in matches) + '\n'
    (strict / 'unresolved.c').write_text(body, encoding='utf-8', newline='\n')
    (strict / 'scrap_image.h').write_text(
        f'#define SCRAP_ENTRY_POINT {config["entry_point"]}u\n'
        f'#define SCRAP_IMAGE_SIZE {image.stat().st_size}L\n'
        f'#define SCRAP_IMAGE_SHA256 "{config["sha256"]}"\n', encoding='utf-8', newline='\n')
    ws.write_json(strict / 'manifest.json', {
        'image_sha256': config['sha256'], 'codegen_manifest_sha256': ws.digest(base / 'codegen-manifest.json'),
        'unresolved_count': count, 'policy': 'terminate with guest VA when reached',
        'files': {name: ws.digest(strict / name) for name in strict_files},
    })
    print(f'Strict {platform} preparation: {count} unresolved calls will terminate')
    return base


def build():
    from fetch_xemu_dsp import fetch as fetch_dsp
    fetch_dsp()
    from fetch_sdl2 import main as fetch_sdl2
    fetch_sdl2()
    base = prepare()
    inputs = build_inputs(base)
    tools = ws.paths()
    env = ws.vs_environment(tools)
    ws.run([tools['cmake'], '-S', ROOT, '-B', BUILD, '-G', 'Ninja',
            f'-DCMAKE_MAKE_PROGRAM={tools["ninja"].as_posix()}',
            f'-DCMAKE_C_COMPILER={tools["host_compiler"].as_posix()}',
            f'-DCMAKE_CXX_COMPILER={tools["host_compiler"].as_posix()}',
            '-DCMAKE_BUILD_TYPE=RelWithDebInfo', '-DSCRAP_BUILD_GAME_HOST=ON',
            '-DXBOXRECOMP_WIN32_OPENGL=ON',
            f'-DSCRAP_RENDERDOC_INCLUDE_DIR={tools["renderdoc"].resolve().as_posix()}',
            f'-DSDL2_DIR={(ROOT / ".deps/SDL2-2.32.10/cmake").as_posix()}',
            f'-DSCRAP_GENERATED_DIR={base.as_posix()}'], name='game-host-configure', env=env)
    ws.run([tools['cmake'], '--build', BUILD, '--target', 'host_numeric_probe', '--parallel', '1'],
           name='game-host-numeric-build', env=env)
    ws.run([BUILD / 'host_numeric_probe.exe'], name='game-host-numeric', env=env)
    ws.run([tools['cmake'], '--build', BUILD, '--target', 'scrapcomp_host', 'host_sampler', '--parallel', '1', '--', '-k', '0'],
           name='game-host-build', env=env)
    # A localized MSVC prefix mismatch can produce successful builds with no
    # header edges. Do not certify an incremental artifact in that state.
    first_chunk = sorted((base / 'c').glob('recomp_[0-9]*.c'))[0]
    obj = 'CMakeFiles/scrapcomp_host.dir/' + first_chunk.relative_to(ROOT).as_posix() + '.obj'
    dependencies = subprocess.check_output(
        ['rtk', 'proxy', str(tools['ninja']), '-C', str(BUILD), '-t', 'deps', obj], env=env)
    if b'recomp_types.h' not in dependencies or b'(VALID)' not in dependencies:
        raise RuntimeError('Missing native header dependencies; clean and rebuild this old build tree')
    if build_inputs(base) != inputs:
        raise RuntimeError('Game build inputs changed during compilation; rebuild before running')
    ws.write_json(BUILD / 'game-build-manifest.json', {
        'inputs': inputs, 'executable_sha256': ws.digest(BUILD / 'scrapcomp_host.exe'),
        'pdb_sha256': ws.digest(BUILD / 'scrapcomp_host.pdb'),
        'sdl2_dll_sha256': ws.digest(BUILD / 'SDL2.dll'),
        'sampler_executable_sha256': ws.digest(BUILD / 'host_sampler.exe'),
    })


def run(seconds, graphics_smoke=False, sample_at=0, pad_script=None, dump_every=60, pvideo_smoke=False,
        profile=False, audio_capture=None, gpu_sync='deferred', apu_trace=False, voice_capture=None, renderdoc_at=None,
        apu_ring_stats=False, gpu_state_at=None, watch_address=None, quiet_gpu=False, dsp_capture=None,
        audio_stream=None, dsp_dma_period=None):
    base = prepare()
    executable = BUILD / 'scrapcomp_host.exe'
    if not executable.exists():
        raise RuntimeError('Build the game host first')
    built = json.loads((BUILD / 'game-build-manifest.json').read_text())
    if built['inputs'] != build_inputs(base) or built['executable_sha256'] != ws.digest(executable):
        raise RuntimeError('Game host build is stale; rebuild before execution')
    if built['pdb_sha256'] != ws.digest(BUILD / 'scrapcomp_host.pdb'):
        raise RuntimeError('Game host symbols differ from matching build')
    if built.get('sdl2_dll_sha256') != ws.digest(BUILD / 'SDL2.dll'):
        raise RuntimeError('Native SDL2 DLL differs from matching build')
    sampler = BUILD / 'host_sampler.exe'
    if sample_at and built.get('sampler_executable_sha256') != ws.digest(sampler):
        raise RuntimeError('Native sampler differs from matching build')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    destination = ROOT / 'runs/host' / stamp
    destination.mkdir(parents=True)
    inputs_before = input_inventory()
    ws.write_json(destination / 'input-inventory-before.json', inputs_before)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('RECOMP_'):
            del env[key]
    env.update(RECOMP_KERNEL_LOG_BUDGET='200', RECOMP_GIL='1',
               RECOMP_WATCHDOG_SECS=str(max(1, seconds - 2)))
    if dump_every:
        env['RECOMP_GL_DUMP'] = f'frame,{dump_every}'
    if quiet_gpu:
        env['RECOMP_QUIET'] = '1'
    else:
        env['RECOMP_GL_TRACE'] = '1'
    if gpu_sync == 'strict':
        env['RECOMP_GL_FINISH'] = '1'
    env.update(RECOMP_USB='1', RECOMP_PB_EXEC='1', RECOMP_VBLANK='1')
    if not graphics_smoke and not pvideo_smoke:
        env['RECOMP_AC97_READY'] = '1'
    if pad_script:
        env['RECOMP_PAD_SCRIPT'] = pad_script
    if profile:
        env['RECOMP_HOST_PROFILE'] = '1'
    if audio_capture:
        env['RECOMP_AUDIO_CAPTURE'] = audio_capture
    if audio_stream:
        env['RECOMP_AUDIO_STREAM'] = str(audio_stream)
    if dsp_capture:
        env['RECOMP_DSP_CAPTURE'] = dsp_capture
    if dsp_dma_period:
        env['RECOMP_DSP_DMA_PERIOD'] = str(dsp_dma_period)
    if apu_trace:
        env['RECOMP_APU_TRACE'] = '1'
    if apu_ring_stats:
        env['RECOMP_APU_RING_STATS'] = '1'
    if watch_address is not None:
        env['RECOMP_WATCH'] = hex(watch_address)
    if gpu_state_at is not None:
        env['RECOMP_GPU_STATE_AT'] = str(gpu_state_at)
    if voice_capture:
        voice, start, duration = voice_capture.split(',')
        env['RECOMP_APU_VOICE_DUMP'] = f'{voice},voice-{voice}.f32,{start},{duration}'
    rd_dll = None
    if renderdoc_at is not None:
        rd_dll = (ws.paths()['renderdoc'] / 'renderdoc.dll').resolve()
        if not rd_dll.is_file(): raise RuntimeError('Configured portable RenderDoc DLL is missing')
        env['RECOMP_RENDERDOC_DLL'] = str(rd_dll)
        env['RECOMP_RENDERDOC_AT'] = str(renderdoc_at)
    command = [str(executable), str(ws.checked_image()), str(ROOT / 'original'), str(destination / 'saves')]
    if graphics_smoke:
        command.append('--graphics-smoke')
        env['RECOMP_GL_DUMP'] = 'frame,1'
    if pvideo_smoke:
        command.append('--pvideo-smoke')
        env['RECOMP_GL_DUMP'] = 'frame,1'
    timed_out = False
    sample_status = None
    launch = {
        'scope': 'Launch identity; completion and exit status are not yet established',
        'command': command, 'executable_sha256': built['executable_sha256'],
        'pdb_sha256': built['pdb_sha256'], 'image_sha256': ws.IMAGE['sha256'],
        'build_manifest_sha256': ws.digest(BUILD / 'game-build-manifest.json'),
        'codegen_manifest_sha256': ws.digest(base / 'codegen-manifest.json'),
        'strict_manifest_sha256': ws.digest(base / 'host-strict/manifest.json'),
        'gpu_synchronization': gpu_sync,
        'diagnostic_environment': {k: v for k, v in env.items() if k.startswith('RECOMP_')},
        'requested_seconds': seconds,
    }
    ws.write_json(destination / 'launch-manifest.json', launch)
    with (destination / 'host.log').open('wb') as output:
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=destination, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        launch['process_id'] = process.pid
        ws.write_json(destination / 'launch-manifest.json', launch)
        try:
            status = process.wait(timeout=sample_at or seconds)
        except subprocess.TimeoutExpired:
            if sample_at:
                with (destination / 'threads.log').open('wb') as threads:
                    try:
                        result = subprocess.run([str(sampler), str(process.pid), str(BUILD)],
                            stdout=threads, stderr=subprocess.STDOUT, timeout=8,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                        sample_status = result.returncode
                    except subprocess.TimeoutExpired:
                        sample_status = 'sampler timed out'
                        # The helper might have been killed between SuspendThread
                        # and ResumeThread. End our bounded diagnostic process;
                        # execution after that point would not be valid evidence.
                        timed_out = True
                        process.kill()
            try:
                status = process.wait(timeout=max(0, seconds - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                status = process.wait()
    inputs_after = input_inventory()
    rd_captures = {p.name: {'bytes': p.stat().st_size, 'sha256': ws.digest(p)} for p in destination.glob('*.rdc')}
    if renderdoc_at is not None and not rd_captures and status == 0:
        status = 84
    changed_inputs = sorted(name for name in inputs_before.keys() | inputs_after.keys()
                            if inputs_before.get(name) != inputs_after.get(name))
    ws.write_json(destination / 'input-inventory-after.json', inputs_after)
    report = {
        'scope': ('Synthetic PVIDEO YUY2 scanout; XBE mapped but not executed' if pvideo_smoke else
                  'Synthetic NV097 clear/readback; XBE mapped but not executed' if graphics_smoke
                  else 'Diagnostic execution, not a gameplay validation'), 'command': command,
        'executable_sha256': ws.digest(executable), 'image_sha256': ws.IMAGE['sha256'],
        'pdb_sha256': built['pdb_sha256'],
        'codegen_manifest_sha256': ws.digest(base / 'codegen-manifest.json'),
        'strict_manifest_sha256': ws.digest(base / 'host-strict/manifest.json'),
        'exit_code': status, 'exit_code_hex': f'0x{status & 0xFFFFFFFF:08X}', 'timed_out': timed_out,
        'process_id': process.pid, 'native_sample_exit_code': sample_status,
        'gpu_synchronization': gpu_sync,
        'original_input_file_count': len(inputs_before),
        'original_inputs_unchanged': not changed_inputs,
        'changed_original_inputs': changed_inputs,
        'diagnostic_environment': {k: v for k, v in env.items() if k.startswith('RECOMP_')},
        'renderdoc_dll_sha256': ws.digest(rd_dll) if rd_dll else None,
        'renderdoc_captures': rd_captures,
    }
    ws.write_json(destination / 'manifest.json', report)
    print(json.dumps(report, indent=2))
    lines = (destination / 'host.log').read_text(encoding='utf-8', errors='replace').splitlines()
    events = [line for line in lines if any(marker in line for marker in
              ['[BOOT]', '[STOP]', '[FAULT]', '[UNIMPL]', '[GL]', '[FRAME]', 'WARNING', 'PsCreate', 'Python'])]
    print('\n'.join(events[-60:]))
    print(f'Run evidence: {destination}')
    return 86 if changed_inputs else (124 if timed_out else (status if 0 <= status <= 255 else 1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'build', 'run', 'graphics-smoke', 'pvideo-smoke'])
    parser.add_argument('--seconds', type=int, default=15)
    parser.add_argument('--sample-at', type=int, default=0, help='Capture native thread stacks after this many seconds')
    parser.add_argument('--pad-script', help='Guest USB pad sequence, e.g. 8000:start:200,12000:a:200')
    parser.add_argument('--dump-every', type=int, default=60, help='Save every Nth presented game frame')
    parser.add_argument('--quiet-gpu', action='store_true',
                        help='Disable verbose GL and periodic runtime logs; errors remain visible')
    parser.add_argument('--profile', action='store_true', help='Record presentation times and audio queue health')
    parser.add_argument('--apu-trace', action='store_true', help='Enable donor APU voice/register diagnostics; affects timing')
    parser.add_argument('--watch-address', type=lambda value: int(value, 0),
                        help='Trace writes to one guest dword using the runtime page trap; affects timing')
    parser.add_argument('--apu-ring-stats', action='store_true', help='Report existing donor ring repetition counters every ten seconds')
    parser.add_argument('--voice-capture', help='Bounded donor voice capture: voice_hex,start_seconds,duration_seconds (1..10)')
    parser.add_argument('--renderdoc-at', type=int, help='Capture one GL frame after this many seconds using portable RenderDoc')
    parser.add_argument('--gpu-state-at', type=int, help='Save at most sixteen reached fixed-function method shadows after this many seconds')
    parser.add_argument('--gpu-sync', choices=['strict','deferred'], default='deferred',
                        help='Strict glFinish per operation, or donor normal deferred submission for controlled comparison')
    parser.add_argument('--audio-capture', help='Capture input/output PCM: start_seconds,duration_seconds (duration 1..30)')
    parser.add_argument('--audio-stream', type=int, help='Stream complete input/output PCM from startup, bounded to 1..900 sample seconds')
    parser.add_argument('--dsp-capture', help='Capture aligned DSP stages: active_start_seconds,duration_seconds (1..10); affects timing')
    parser.add_argument('--dsp-dma-period', type=int, help='Capture 32 APU frames of actual DMA every 5..300 active seconds, for at most 900 seconds')
    args = parser.parse_args()
    if not 3 <= args.seconds <= 900:
        parser.error('--seconds must be between 3 and 900')
    if args.sample_at < 0 or args.sample_at >= args.seconds - 2:
        parser.error('--sample-at must be zero or precede the watchdog deadline')
    if args.renderdoc_at is not None and not 0 <= args.renderdoc_at < args.seconds - 2:
        parser.error('--renderdoc-at must precede the watchdog deadline')
    if args.gpu_state_at is not None and not 0 <= args.gpu_state_at < args.seconds - 2:
        parser.error('--gpu-state-at must precede the watchdog deadline')
    if not 0 <= args.dump_every <= 10000:
        parser.error('--dump-every must be between 0 (off) and 10000')
    if args.watch_address is not None and not (0x10000 <= args.watch_address <= 0xFFFFFFFC and args.watch_address % 4 == 0):
        parser.error('--watch-address requires an aligned guest dword address')
    if args.audio_capture:
        if not re.fullmatch(r'\d+,\d+', args.audio_capture):
            parser.error('--audio-capture expects start_seconds,duration_seconds')
        start, duration = map(int, args.audio_capture.split(','))
        if not 0 <= start <= 300 or not 1 <= duration <= 30:
            parser.error('--audio-capture requires start 0..300 and duration 1..30')
    if args.audio_stream is not None and not 1 <= args.audio_stream <= 900:
        parser.error('--audio-stream requires 1..900 seconds')
    if args.dsp_capture:
        if not re.fullmatch(r'\d+,\d+', args.dsp_capture):
            parser.error('--dsp-capture expects start_seconds,duration_seconds')
        start, duration = map(int, args.dsp_capture.split(','))
        if not 0 <= start <= 600 or not 1 <= duration <= 10:
            parser.error('--dsp-capture requires start 0..600 and duration 1..10')
    if args.dsp_dma_period is not None and not 5 <= args.dsp_dma_period <= 300:
        parser.error('--dsp-dma-period requires 5..300 seconds')
    if args.voice_capture:
        if not re.fullmatch(r'[0-9a-fA-F]{1,2},\d+,\d+', args.voice_capture):
            parser.error('--voice-capture expects voice_hex,start_seconds,duration_seconds')
        voice, start, duration = args.voice_capture.split(',')
        if not 0 <= int(start) <= 300 or not 1 <= int(duration) <= 10:
            parser.error('--voice-capture requires start 0..300 and duration 1..10')
    try:
        if args.command in ('run', 'graphics-smoke', 'pvideo-smoke'):
            raise SystemExit(run(args.seconds, graphics_smoke=args.command == 'graphics-smoke',
                                 sample_at=args.sample_at, pad_script=args.pad_script, dump_every=args.dump_every,
                                  profile=args.profile, audio_capture=args.audio_capture, gpu_sync=args.gpu_sync,
                                  dsp_capture=args.dsp_capture,
                                  dsp_dma_period=args.dsp_dma_period,
                                  audio_stream=args.audio_stream,
                                 apu_trace=args.apu_trace,
                                 apu_ring_stats=args.apu_ring_stats,
                                 voice_capture=args.voice_capture,
                                 renderdoc_at=args.renderdoc_at,
                                 gpu_state_at=args.gpu_state_at,
                                  watch_address=args.watch_address,
                                  quiet_gpu=args.quiet_gpu,
                                 pvideo_smoke=args.command == 'pvideo-smoke'))
        else:
            globals()[args.command]()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
