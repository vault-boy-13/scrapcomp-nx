"""Materialize the pinned official native Windows SDL2 development package."""
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    pin = json.loads((ROOT / 'config/sdl2.lock.json').read_text())
    archive = ROOT / '.cache/downloads' / pin['url'].rsplit('/', 1)[1]
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        urllib.request.urlretrieve(pin['url'], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != pin['sha256']:
        raise RuntimeError('SDL2 archive hash differs from the pinned official release')
    with zipfile.ZipFile(archive) as package:
        for name in package.namelist():
            member = Path(name)
            if member.is_absolute() or '..' in member.parts:
                raise RuntimeError('Invalid SDL2 archive path')
        destination = ROOT / pin['directory']
        if destination.exists():
            for member in package.infolist():
                if member.is_dir():
                    continue
                path = ROOT / '.deps' / member.filename
                if not path.exists() or path.read_bytes() != package.read(member):
                    raise RuntimeError(f'Existing SDL2 material differs: {member.filename}')
        else:
            package.extractall(ROOT / '.deps')
    print('Native SDL2 package verified against pinned release digest')


if __name__ == '__main__':
    main()
