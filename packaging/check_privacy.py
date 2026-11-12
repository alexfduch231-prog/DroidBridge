"""Inspect uncompressed payload and frozen code filenames for build-host paths."""
import argparse
import json
import types
from pathlib import Path


def inspect(root: Path, forbidden: list[str]) -> dict:
    from PyInstaller.archive.readers import CArchiveReader
    needles = [value.encode(encoding) for value in forbidden for encoding in ('utf-8', 'utf-16le')]
    binary_hits = []
    for path in root.rglob('*'):
        if path.is_file() and any(needle in path.read_bytes() for needle in needles):
            binary_hits.append(path.relative_to(root).as_posix())
    archive = CArchiveReader(str(root / 'DroidBridge.exe'))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    filename_hits = []
    def visit(code, module):
        if not isinstance(code, types.CodeType):
            return
        normalized = code.co_filename.lower().replace('\\', '/')
        if any(value.lower().replace('\\', '/') in normalized for value in forbidden):
            filename_hits.append({'module': module, 'filename': code.co_filename})
        for item in code.co_consts:
            visit(item, module)
    for name in pyz.toc:
        visit(pyz.extract(name), name)
    return {'ok': not binary_hits and not filename_hits, 'binary_hits': binary_hits, 'frozen_filename_hits': filename_hits, 'modules_checked': len(pyz.toc)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('payload', type=Path)
    parser.add_argument('--forbid', action='append', required=True)
    args = parser.parse_args()
    report = inspect(args.payload, args.forbid)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['ok'] else 1)
