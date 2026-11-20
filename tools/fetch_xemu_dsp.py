#!/usr/bin/env python3
"""Materialize pinned, hash-verified upstream DSP interpreter sources."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / '.deps/xemu-dsp'

def fetch():
    lock = json.loads((ROOT/'config/xemu-dsp.lock.json').read_text())
    for item in lock['files']:
        path = DEST/item['path']
        if path.exists():
            data = path.read_bytes()
        else:
            data = urllib.request.urlopen(lock['raw_base']+item['upstream'], timeout=40).read()
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise RuntimeError(f'DSP dependency digest mismatch: {path}')
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(f"Verified {len(lock['files'])} DSP sources/licences at pinned commit {lock['commit']}")
    return DEST

if __name__ == '__main__':
    fetch()
