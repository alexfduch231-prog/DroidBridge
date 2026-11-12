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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--media-root', type=Path, help='Optional LOCAL-ONLY full Gyan bundle; omit for public slim setup')
    parser.add_argument('--iscc', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Output already exists; choose a fresh build path')
    if sys.prefix == sys.base_prefix:
        raise SystemExit('Use isolated build venv, never the global Python environment')
    media_root = args.media_root.resolve() if args.media_root else None
    if media_root:
        for name in ['bin/ffmpeg.exe', 'bin/ffplay.exe', 'LICENSE', 'README.txt']:
            if not (media_root / name).is_file():
                raise SystemExit('Missing media prerequisite: ' + name)
        readme = (media_root / 'README.txt').read_text(encoding='utf-8')
        if 'License: GPL v3' not in readme or '9.0.2-full_build' not in readme or '946fcce07b' not in readme:
            raise SystemExit('Unreviewed media build; review license/source and update pinned release metadata first')
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
        media = payload / 'media'
        media.mkdir()
        for name in ['ffmpeg.exe', 'ffplay.exe']:
            shutil.copyfile(media_root / 'bin' / name, media / name)
        shutil.copyfile(media_root / 'LICENSE', notices / 'FFmpeg-GPLv3.txt')
        shutil.copyfile(media_root / 'README.txt', notices / 'FFmpeg-upstream-README.txt')
    (notices / 'THIRD-PARTY-NOTICES.txt').write_text(
        'DroidBridge ships FFmpeg and ffplay as separate executables invoked via subprocess.\n'
        'They are NOT covered by the application license. FFmpeg 9.0.2 Gyan full build: GPL v3.\n'
        'Build origin: https://www.gyan.dev/ffmpeg/builds/\n'
        'FFmpeg source: https://github.com/FFmpeg/FFmpeg/commit/946fcce07b\n'
        'Source tarball: https://github.com/FFmpeg/FFmpeg/archive/946fcce07b.tar.gz\n'
        'Full static builds include third-party libraries listed in upstream README.\n'
        'PUBLIC RELEASE GATE: host Corresponding Source including linked dependencies and build scripts,\n'
        'or provide a GPLv3-compliant source offer before redistribution. A bare FFmpeg source URL\n'
        'alone does NOT satisfy every obligation for this static full build.\n'
        'Python: PSF license; Pillow: MIT-CMU; qrcode: BSD; cryptography: Apache-2.0 OR BSD.\n'
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
                'release_gate': ('Corresponding Source for full static FFmpeg required; ' if media_root else '') + 'Integrated pairing and installer validation required'}
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
