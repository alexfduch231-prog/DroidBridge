"""Build from positive allowlist in an isolated venv; all outputs under packaging/.build.
Run using .venv-build/Scripts/python.exe after installing requirements-build.txt.
A fresh --output is required; never re-use a potentially contaminated payload.
"""
import argparse
import ast
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from build_support import stage_sources, inventory
from media_bundle import stage_media_bundle, validate_media_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--media-root', type=Path, help='Reviewed schema-1 media kit with exact runtime/source/license SHA256 allowlists; omit for slim setup')
    parser.add_argument('--iscc', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Output already exists; choose a fresh build path')
    if sys.prefix == sys.base_prefix:
        raise SystemExit('Use isolated build venv, never the global Python environment')
    # Preserve the supplied path until validation: resolve() would hide a root symlink.
    media_root = args.media_root.absolute() if args.media_root else None
    media_proof = validate_media_bundle(media_root) if media_root else None
    stage = output / 'source'
    stage_sources(args.source.resolve(), stage)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
               '--noupx', '--name', 'DroidBridge', '--distpath', str(output / 'dist'),
               '--workpath', str(output / 'work'), '--specpath', str(output),
               '--paths', str(stage), '--paths', str(stage / 'desktop'), '--paths', str(stage / 'listener'),
               '--paths', str(stage / 'client')]
    # Only positive allowlisted files become source data. Production imports are dynamic.
    for directory in ['listener', 'client']:
        for file in sorted((stage / directory).glob('*')):
            command += ['--add-data', str(file) + os.pathsep + directory]
    # Entry components are source data loaded dynamically, not analyzed by PyInstaller.
    # Freeze their complete static import surface (including imports inside functions).
    hidden = {'PIL.ImageTk', 'PIL.ImageGrab', 'qrcode', 'cryptography', 'ssl'}
    for file in stage.rglob('*'):
        if file.suffix not in {'.py', '.pyw'}:
            continue
        for node in ast.walk(ast.parse(file.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.Import):
                hidden.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                hidden.add(node.module)
    for module in sorted(hidden):
        command += ['--hidden-import', module]
    for module in ['qrcode', 'cryptography']:
        command += ['--collect-all', module]
    for file in (stage / 'desktop').glob('*.py'):
        if file.name not in ['launcher.py', 'runtime.py']:
            command += ['--add-data', str(file) + os.pathsep + 'desktop', '--paths', str(file.parent), '--hidden-import', file.stem]
    command += [str(stage / 'desktop' / 'launcher.py')]
    build_environment = os.environ.copy()
    build_environment.pop('PYTHONPATH', None)
    # Never let ambient project modules or user PYTHONPATH override staged files.
    with (output / 'freeze.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, check=True, cwd=stage, env=build_environment,
                       stdout=log, stderr=subprocess.STDOUT)
    payload = output / 'dist' / 'DroidBridge'
    notices = payload / 'licenses'
    notices.mkdir()
    if media_root:
        staged_proof = stage_media_bundle(media_root, payload / 'media')
        if staged_proof != media_proof:
            raise ValueError('Media kit changed during build')
        components = '\n'.join(f"{c['name']} {c['version']}: {c['license']} ({c['source_url']})"
                               for c in media_proof['components'])
        (notices / 'THIRD-PARTY-NOTICES.txt').write_text(
            'FFmpeg and ffplay are separate subprocess executables, not covered by the app license.\n'
            'The complete hash-verified media kit is installed in media/: runtime executables/DLLs,\n'
            'licenses/, sources/ archives and build recipes, and media-manifest.json.\n'
            + components + '\n'
            'Source hashes prove included-file integrity, not independent legal approval.\n'
            'Python: PSF; Pillow: MIT-CMU; qrcode: BSD; cryptography: Apache-2.0 OR BSD.\n'
            'PyInstaller: GPL-2.0-or-later with bootloader distribution exception.\n', encoding='utf-8')
    if not media_root:
        (notices / 'THIRD-PARTY-NOTICES.txt').write_text(
            'This slim build does NOT distribute FFmpeg or ffplay.\n'
            'Optional media features require a separate user-managed FFmpeg installation.\n'
            'Obtain ffmpeg and ffplay from a trusted distribution, review its license, select their folder in Video and audio setup, then restart the server/viewer.\n'
            'No automatic download occurs. https://ffmpeg.org/download.html\n'
            'Python: PSF license; Pillow: MIT-CMU; qrcode: BSD; cryptography: Apache-2.0 OR BSD.\n'
            'PyInstaller: GPL-2.0-or-later with bootloader distribution exception.\n', encoding='utf-8')
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copyfile(python_license, notices / 'Python-LICENSE.txt')
    for name in ['pillow', 'qrcode', 'cryptography', 'cffi', 'pyinstaller']:
        dist = importlib.metadata.distribution(name)
        destination = notices / name
        destination.mkdir()
        for file in dist.files or []:
            if 'license' in file.name.lower() or file.name.lower().startswith('copying'):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    shutil.copyfile(source, destination / source.name)
    report = output / 'frozen-self-test.json'
    subprocess.run([str(payload / 'DroidBridge.exe'), '--self-test', str(report)], check=True, timeout=45)
    if not report.exists() or not json.loads(report.read_text())['ok']:
        raise SystemExit('Frozen self-test did not return success')
    manifest = {'python': sys.version.split()[0], 'dependencies': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
                'source_sha256': inventory(stage), 'payload_sha256': inventory(payload),
                'self_test': json.loads(report.read_text()), 'contains_ffmpeg': bool(media_root), 'public_release_ready': False,
                'media_bundle': media_proof,
                'release_gate': 'Root release review, isolated payload self-test, installer/upgrade, real pairing and media functional validation required'}
    (output / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if args.iscc:
        artifacts = output / 'artifacts'
        artifacts.mkdir()
        with (output / 'installer.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(args.iscc.resolve()), '/DPayloadDir=' + str(payload), '/DArtifactDir=' + str(artifacts),
                            str(Path(__file__).with_name('installer.iss'))], check=True,
                           stdout=log, stderr=subprocess.STDOUT)
        (artifacts / 'SHA256SUMS.json').write_text(json.dumps(inventory(artifacts), indent=2), encoding='utf-8')
    print(output)

if __name__ == '__main__':
    main()
