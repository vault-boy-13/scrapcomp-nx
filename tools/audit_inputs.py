#!/usr/bin/env python3
"""Read-only input audit; reports contain metadata, never certificate keys or code.

Uses the local reference XBE parser and its static kernel routing audit.
Python 3.11+, standard library only. Run from any working directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ("manhunt1_nx", "nfsu1-sw", "nfsu2-sw", "BLACK-NX-PORT")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(path: Path, *args: str) -> str:
    # Follow the workspace RTK instruction for subprocess commands too.
    result = subprocess.run(
        ["rtk", "proxy", "git", "-C", str(path), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def reference_lock() -> dict:
    result = {}
    for name in REFERENCES:
        directory = ROOT / "references" / name
        dirty = git(directory, "status", "--porcelain=v1", "--untracked-files=no")
        # Nested vendored SDKs have no independent git identity in these snapshots.
        result[name] = {
            "commit": git(directory, "rev-parse", "HEAD"),
            "commit_date": git(directory, "show", "-s", "--format=%cI", "HEAD"),
            "origin": git(directory, "config", "--get", "remote.origin.url"),
            "tracked_changes": dirty.splitlines(),
        }
    return result


def packed_inventory(path: Path) -> dict:
    """Inspect the observed BFPK v0 directory; never extract or execute payloads."""
    total = path.stat().st_size
    entries = []
    with path.open("rb") as stream:
        def read_exact(size: int) -> bytes:
            value = stream.read(size)
            if len(value) != size:
                raise ValueError(f"Truncated BFPK directory: {path.name}")
            return value

        magic, version, count = struct.unpack("<4sII", read_exact(12))
        if magic != b"BFPK" or version != 0 or count > 100_000:
            raise ValueError(f"Unsupported BFPK directory: {path.name}")
        for _ in range(count):
            length, = struct.unpack("<I", read_exact(4))
            if not 0 < length <= 4096:
                raise ValueError(f"Invalid BFPK name length: {path.name}")
            name = read_exact(length).decode("utf-8", errors="replace")
            size, offset = struct.unpack("<II", read_exact(8))
            entries.append((name, size, offset))
        table_end = stream.tell()
        if entries and min(offset for _, _, offset in entries) < table_end:
            raise ValueError(f"BFPK payload overlaps directory: {path.name}")
        scripts = [(name, size, offset) for name, size, offset in entries
                   if Path(name).suffix.lower() in (".py", ".pyc", ".pyo")]
        bytecode_headers = set()
        for name, size, offset in scripts:
            if Path(name).suffix.lower() in (".pyc", ".pyo") and size >= 4 and offset + size <= total:
                stream.seek(offset)
                bytecode_headers.add(stream.read(4).hex())
    return {
        "format": "BFPK", "version": version, "entry_count": count,
        "directory_end": table_end,
        "all_payload_ranges_in_bounds": all(o + s <= total for _, s, o in entries),
        "external_or_unresolved_ranges": [{"path": n, "size": s, "offset": o}
                                          for n, s, o in entries if o + s > total],
        "extension_counts": dict(sorted(Counter(Path(n).suffix.lower() for n, _, _ in entries).items())),
        "python_script_count": len(scripts),
        "python_script_examples": [n for n, _, _ in scripts[:12]],
        "python_bytecode_magic_hex": sorted(bytecode_headers),
        "scope": "Inferred v0 directory layout only. Out-of-file ranges need investigation; no decompression or asset semantic validation.",
    }


def audit(xbe_path: Path) -> dict:
    toolkit = ROOT / "references/nfsu2-sw/xboxrecomp"
    sys.path.insert(0, str(toolkit))
    from tools.xbe_parser.xbe_parser import XBEParser
    from tools.kernel_audit.coverage import classify

    image = XBEParser(str(xbe_path)).parse()
    raw = xbe_path.read_bytes()
    sections = []
    for section in image.sections:
        if section.raw_addr + section.raw_size > len(raw):
            raise ValueError(f"Section outside file: {section.name}")
        sections.append({
            "name": section.name,
            "va": f"0x{section.virtual_addr:08X}",
            "virtual_size": section.virtual_size,
            "raw_offset": section.raw_addr,
            "raw_size": section.raw_size,
            "flags": f"0x{section.flags:08X}",
        })
    imports = [asdict(item) for item in image.kernel_imports]
    covered, wrap, data, todo, sizes = classify(imports)

    # Same id/address entry layout as XboxXBE-Recomp's Image::Exports().
    # This is only the .XTLID fallback, NOT the tool's full signature matcher.
    xtlid = defaultdict(set)
    for section in image.sections:
        if section.name == ".XTLID":
            length = min(section.virtual_size, section.raw_size)
            for offset in range(0, length - 7, 8):
                ident, va = struct.unpack_from("<II", raw, section.raw_addr + offset)
                if ident and va:
                    xtlid[ident].add(va)
    signatures = ROOT / "references/BLACK-NX-PORT/XboxXBE-Recomp/xdk/5849/signatures.toml"
    sigs = tomllib.loads(signatures.read_text(encoding="utf-8"))
    xtlid_matches = {}
    for group in ("symbols", "data"):
        matched, absent, ambiguous = {}, [], {}
        for name, signature in sigs.get(group, {}).items():
            ident = signature.get("xtlid", 0)
            if not ident:
                continue
            values = sorted(xtlid.get(ident, set()))
            if len(values) == 1:
                va = values[0]
                destination = next((s.name for s in image.sections
                                    if s.virtual_addr <= va < s.virtual_addr + s.virtual_size), None)
                matched[name] = {"id": f"0x{ident:08X}", "va": f"0x{va:08X}", "section": destination}
            elif values:
                ambiguous[name] = [f"0x{va:08X}" for va in values]
            else:
                absent.append(name)
        xtlid_matches[group] = {
            "signature_entries": len(sigs.get(group, {})),
            "entries_with_xtlid": len(matched) + len(absent) + len(ambiguous),
            "matched": matched, "absent_ids": absent, "ambiguous_ids": ambiguous,
        }

    game = xbe_path.parent
    files = sorted((p for p in game.rglob("*") if p.is_file()),
                   key=lambda p: p.relative_to(game).as_posix())
    counts = Counter(p.suffix.lower() for p in files)
    folded = defaultdict(list)
    for path in files:
        relative = path.relative_to(game).as_posix()
        folded[relative.casefold()].append(relative)
    certificate = image.certificate
    strings = re.findall(rb"[ -~]{8,}", raw)
    python_markers = [s.decode("ascii") for s in strings
                      if s in (b"Python script subsystem initialized.",
                               b"Python script subsystem closed.")
                      or b"PyInterface\\PythonInit.cpp" in s]
    return {
        "scope": "Static metadata only. No disassembly, build, or runtime validation.",
        "xbe": {
            "relative_path": xbe_path.relative_to(ROOT).as_posix() if xbe_path.is_relative_to(ROOT) else str(xbe_path),
            "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "title": certificate.title_name, "title_id": f"0x{certificate.title_id:08X}",
            "region_flags": f"0x{certificate.game_region:08X}",
            "allowed_media_flags": f"0x{certificate.allowed_media:08X}",
            "signature_authenticity": "NOT VERIFIED; certificate flags do not prove an unmodified retail dump",
            "base": f"0x{image.header.base_address:08X}",
            "entry_point": f"0x{image.header.entry_point:08X}",
            "kernel_thunks": f"0x{image.header.kernel_thunk_addr:08X}",
            "debug_path": image.debug_pathname,
            "libraries": [asdict(lib) for lib in image.libraries],
            "sections": sections,
            "kernel_imports": imports,
        },
        "xboxrecomp_static_kernel_routing": {
            "toolkit": "references/nfsu2-sw/xboxrecomp",
            "warning": "Routed means a source-level route exists, NOT complete semantic support or a runtime pass.",
            "total": len(imports), "routed": len(covered),
            "wrapper_needed": [{**imp, "source": source} for imp, source in wrap],
            "data_export_needed": data,
            "implementation_not_found": todo,
            "unrouted_functions_without_argument_size": [imp for imp, _ in wrap if imp["ordinal"] not in sizes]
                + [imp for imp in todo if imp["ordinal"] not in sizes],
        },
        "xtlid_probe": {
            "warning": "ID matches only; verify function boundaries, ABI, globals and runtime call sites before hooking. Missing IDs may match by byte signatures.",
            "signatures_sha256": sha256(signatures),
            "distinct_nonzero_ids": len(xtlid), **xtlid_matches,
        },
        "embedded_python_evidence": python_markers,
        "packed_inventory": {p.name: packed_inventory(p) for p in files if p.suffix.lower() == ".packed"},
        "assets": {
            "file_count": len(files), "total_bytes": sum(p.stat().st_size for p in files),
            "extension_counts": dict(sorted(counts.items())),
            "case_collisions": [values for values in folded.values() if len(values) > 1],
            "manifest": [{"path": p.relative_to(game).as_posix(),
                          "size": p.stat().st_size, "sha256": sha256(p)} for p in files],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=ROOT / "original/Default.xbe")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/input-audit.json")
    parser.add_argument("--references-output", type=Path, default=ROOT / "config/references.lock.json")
    args = parser.parse_args()
    result = audit(args.xbe.resolve())
    refs = reference_lock()
    for path, content in ((args.output, result), (args.references_output, refs)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    routing = result["xboxrecomp_static_kernel_routing"]
    probe = result["xtlid_probe"]
    print(json.dumps({
        "xbe_sha256": result["xbe"]["sha256"],
        "title": result["xbe"]["title"],
        "kernel_imports": routing["total"], "kernel_routed": routing["routed"],
        "kernel_gaps": {key: value for key, value in routing.items() if isinstance(value, list)},
        "xtlid": {group: {"matches": len(probe[group]["matched"]),
                          "with_id": probe[group]["entries_with_xtlid"],
                          "all_signatures": probe[group]["signature_entries"]} for group in ("symbols", "data")},
        "assets": {key: value for key, value in result["assets"].items() if key != "manifest"},
        "packs": {name: {"entries": pack["entry_count"],
                         "python_scripts": pack["python_script_count"],
                         "unresolved_ranges": pack["external_or_unresolved_ranges"]}
                  for name, pack in result["packed_inventory"].items()},
        "output": str(args.output),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
