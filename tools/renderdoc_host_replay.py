"""Replay an owned host capture using portable RenderDoc's embedded Python."""
import json
import os
from pathlib import Path
import sys


def replay(config):
    import renderdoc as rd
    import traceback
    target = Path(config['output'])
    target.mkdir(parents=True, exist_ok=True)
    result = {'capture': config['capture']}
    capture = controller = None
    try:
        rd.InitialiseReplay(rd.GlobalEnvironment(), [])
        capture = rd.OpenCaptureFile()
        status = capture.OpenFile(config['capture'], '', None)
        result['open_file'] = str(status)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError(str(status))
        status, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        result['open_capture'] = str(status)
        if status != rd.ResultCode.Succeeded:
            raise RuntimeError(str(status))

        def flatten(actions):
            for action in actions:
                yield action
                yield from flatten(action.children)

        actions = list(flatten(controller.GetRootActions()))
        structured = controller.GetStructuredFile()
        result['actions'] = [
            {'event': a.eventId, 'flags': str(a.flags), 'name': a.GetName(structured),
             'indices': a.numIndices, 'outputs': [str(x) for x in a.outputs]}
            for a in actions]
        controller.SetFrameEvent(actions[-1].eventId, True)
        result['textures'] = []
        result['api_docs'] = {name: getattr(controller, name).__doc__ for name in
                              ('PixelHistory', 'GetCBufferVariableContents', 'GetGLPipelineState')}
        for texture in controller.GetTextures():
            entry = {'id': str(texture.resourceId), 'width': texture.width,
                     'height': texture.height, 'format': texture.format.Name(),
                     'creation': str(texture.creationFlags)}
            result['textures'].append(entry)
            if (texture.creationFlags & rd.TextureCategory.ColorTarget and
                    not texture.creationFlags & rd.TextureCategory.DepthTarget):
                save = rd.TextureSave()
                save.resourceId = texture.resourceId
                save.destType = rd.FileType.PNG
                filename = 'target-' + str(texture.resourceId).split('::')[-1] + '.png'
                entry['save_status'] = str(controller.SaveTexture(save, str(target / filename)))
                entry['file'] = filename
                if config.get('pixel') and texture.width == 640 and texture.height == 480:
                    x, y = config['pixel']
                    history = controller.PixelHistory(texture.resourceId, x, y, rd.Subresource(), rd.CompType.Typeless)
                    entry['pixel_history'] = []
                    for modification in history:
                        row = {'event': modification.eventId, 'primitive': modification.primitiveID}
                        for key in ('preMod', 'postMod', 'shaderOut'):
                            row[key] = list(getattr(modification, key).col.floatValue)
                        for key in ('backfaceCulled', 'depthClipped', 'scissorClipped', 'shaderDiscarded',
                                    'depthTestFailed', 'stencilTestFailed', 'predicationSkipped', 'sampleMasked'):
                            row[key] = getattr(modification, key, None)
                        entry['pixel_history'].append(row)
                    shader_events = sorted({m.eventId for m in history})
                    entry['shaders'] = []
                    for event in shader_events:
                        controller.SetFrameEvent(event, True)
                        pipeline = controller.GetPipelineState()
                        reflection = pipeline.GetShaderReflection(rd.ShaderStage.Fragment)
                        if reflection:
                            shader = {'event': event, 'id': str(reflection.resourceId)}
                            def variable(v):
                                return {'name': v.name, 'rows': v.rows, 'columns': v.columns,
                                        'type': str(v.type), 'float': list(v.value.f32v),
                                        'uint': list(v.value.u32v), 'members': [variable(m) for m in v.members]}
                            shader['constants'] = []
                            for slot, block in enumerate(reflection.constantBlocks):
                                if not block.bufferBacked:
                                    values = controller.GetCBufferVariableContents(
                                        pipeline.GetGraphicsPipelineObject(), reflection.resourceId,
                                        rd.ShaderStage.Fragment, pipeline.GetShaderEntryPoint(rd.ShaderStage.Fragment),
                                        slot, rd.ResourceId.Null(), 0, 0)
                                    shader['constants'].append({'block': block.name, 'values': [variable(v) for v in values]})
                            for index, source in enumerate(reflection.debugInfo.files):
                                path = 'fragment-{}-{}.glsl'.format(event, index)
                                (target / path).write_text(source.contents, encoding='utf-8')
                                shader.setdefault('sources', []).append(path)
                            entry['shaders'].append(shader)
                    controller.SetFrameEvent(actions[-1].eventId, True)
        result['passed'] = True
    except BaseException:
        result['error'] = traceback.format_exc()
    finally:
        if controller:
            controller.Shutdown()
        if capture:
            capture.Shutdown()
        try:
            rd.ShutdownReplay()
        except BaseException:
            pass
        (target / 'replay.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result.get('passed', False)


def main():
    import argparse
    import subprocess
    import workspace as ws
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pixel', help='Inspect a pixel in each 640x480 color target, x,y in target coordinates')
    args = parser.parse_args()
    capture = args.capture.resolve(strict=True)
    output = (args.output or capture.parent / 'renderdoc-replay').resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = {'capture': str(capture), 'output': str(output)}
    if args.pixel:
        parts = args.pixel.split(',')
        if len(parts) != 2 or not all(part.isdecimal() for part in parts):
            parser.error('--pixel expects x,y')
        config['pixel'] = list(map(int, parts))
        if not 0 <= config['pixel'][0] < 640 or not 0 <= config['pixel'][1] < 480:
            parser.error('--pixel must lie within 640x480')
    env = os.environ.copy()
    env['SCRAP_RENDERDOC_REPLAY'] = json.dumps(config)
    completed = subprocess.run(
        [str(ws.paths()['renderdoc'] / 'qrenderdoc.exe'), '--python', str(Path(__file__).resolve())],
        env=env, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
    report_path = output / 'replay.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    print(json.dumps({'exit_code': completed.returncode, 'report': str(report_path),
                      'capture_sha256': ws.digest(capture), 'passed': report.get('passed', False),
                      'actions': len(report.get('actions', [])),
                      'textures': len(report.get('textures', [])), 'error': report.get('error')}, indent=2))
    return 0 if completed.returncode == 0 and report.get('passed') else 1


if __name__ == '__main__':
    if 'SCRAP_RENDERDOC_REPLAY' in os.environ:
        # qrenderdoc otherwise proceeds to open its UI after the script returns.
        os._exit(0 if replay(json.loads(os.environ['SCRAP_RENDERDOC_REPLAY'])) else 1)
    raise SystemExit(main())
