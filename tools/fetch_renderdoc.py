"""Download a pinned portable RenderDoc from the official distribution site."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
version = '1.47'
url = f'https://renderdoc.org/stable/{version}/RenderDoc_{version}_64.zip'
archive = root / '.cache/downloads' / url.rsplit('/', 1)[1]
archive.parent.mkdir(parents=True, exist_ok=True)
if not archive.exists():
    request = urllib.request.Request(url, headers={'User-Agent': 'ScraplandWorkspace/0.1'})
    partial = archive.with_suffix('.zip.partial')
    with urllib.request.urlopen(request, timeout=45) as response, partial.open('wb') as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    partial.replace(archive)
destination = root / '.deps'
with archive.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
expected = 'b51712e58d40066b34ca30c7869d15f72e4b5c001b2d92232f6783a636d5a3c1'
if digest != expected:
    raise SystemExit('RenderDoc archive does not match the pinned SHA-256; archive preserved for inspection')
with zipfile.ZipFile(archive) as bundle:
    for entry in bundle.infolist():
        target = (destination / entry.filename).resolve()
        if not target.is_relative_to(destination.resolve()):
            raise SystemExit('Unsafe archive path')
    bundle.extractall(destination)
metadata = {'version': version, 'url': url, 'archive_sha256': digest,
            'executables': [str(p.relative_to(root)) for p in destination.rglob('renderdoccmd.exe')]}
(root / 'config/renderdoc.lock.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata, indent=2))
