"""Assemble hash-complete handoff kit only after successful runtime verification."""
from pathlib import Path
import shutil, tarfile, hashlib, json, urllib.request
root=Path(__file__).resolve().parents[1]; work=root/'.build/media-minimal-01'; kit=work/'media-kit'; dl=root/'.build-tools/media/downloads'
assert (kit/'bin/ffmpeg.exe').is_file() and (kit/'bin/ffplay.exe').is_file()
checks=json.loads((work/'verification.json').read_text(encoding='utf8'))
assert len(checks)>=12 and all(item['exit']==0 for item in checks), 'runtime verification incomplete'
inspection=json.loads((work/'runtime-inspection.json').read_text(encoding='utf8'))
assert inspection['runtime'] and not inspection['private_paths'] and not inspection['unresolved_imports']
assert set(inspection['runtime'])=={p.name for p in (kit/'bin').iterdir()}
for name, item in inspection['runtime'].items():
    assert hashlib.sha256((kit/'bin'/name).read_bytes()).hexdigest()==item['sha256'], ('stale inspection',name)
sources=kit/'sources'; licenses=kit/'licenses'; sources.mkdir(exist_ok=True); licenses.mkdir(exist_ok=True)
items=[('FFmpeg','9.0.2','LGPL-2.1-or-later','https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz','ffmpeg-9.0.2.tar.xz',['FFmpeg-LGPL-2.1.txt','FFmpeg-LICENSE.md']),('SDL2','2.32.10','Zlib','https://github.com/libsdl-org/SDL/releases/download/release-2.32.10/SDL2-2.32.10.tar.gz','SDL2-2.32.10.tar.gz',['SDL2-LICENSE.txt']),('nv-codec-headers','13.0.19.0','MIT','https://github.com/FFmpeg/nv-codec-headers/releases/download/n13.0.19.0/nv-codec-headers-13.0.19.0.tar.gz','nv-codec-headers-13.0.19.0.tar.gz',['nv-codec-headers-LICENSE.txt'])]
for _,_,_,_,archive,_ in items: shutil.copy2(dl/archive,sources/archive)
# Include exact SDL development archive too (import libs are part of build inputs).
shutil.copy2(dl/'SDL2-devel-2.32.10-mingw.tar.gz',sources/'SDL2-devel-2.32.10-mingw.tar.gz')
for name in ['build.sh','fetch.sh','verify.py','inspect_runtime.py']:
    shutil.copy2(root/'media-build'/name,sources/name)
ff=work/'ffmpeg-9.0.2'
shutil.copy2(ff/'COPYING.LGPLv2.1',licenses/'FFmpeg-LGPL-2.1.txt'); shutil.copy2(ff/'LICENSE.md',licenses/'FFmpeg-LICENSE.md')
shutil.copy2(ff/'COPYING.GPLv3',licenses/'GCC-GPL-3.0.txt')
with tarfile.open(dl/'SDL2-2.32.10.tar.gz') as t:
    m=next(m for m in t.getmembers() if m.name.endswith('/LICENSE.txt'))
    (licenses/'SDL2-LICENSE.txt').write_bytes(t.extractfile(m).read())
notices=[]
for p in sorted((work/'nv-codec-headers-13.0.19.0/include/ffnvcodec').glob('*.h')):
    header=p.read_text(); notices.append(p.name+'\n'+header[:header.index('*/')+2])
(licenses/'nv-codec-headers-LICENSE.txt').write_text('\n\n'.join(notices),encoding='utf8')
shutil.copy2(root/'.build-tools/media/w64devkit/COPYING.MinGW-w64-runtime.txt',licenses/'COPYING.MinGW-w64-runtime.txt')
# GCC runtime exception document from the matching GCC source mirror is accompanying notice.
url='https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-16.2.0/COPYING.RUNTIME'
(licenses/'GCC-RUNTIME-EXCEPTION.txt').write_bytes(urllib.request.urlopen(url).read())
(sources/'BUILD.md').write_text('''# DroidBridge media build\n\nFFmpeg 9.0.2 built with w64devkit 2.11.0 x64, GCC 16.2.0 (official portable compiler), all external autodetection disabled. FFmpeg shared libraries and SDL2 DLL may be replaced with compatible builds. No GPL components or proprietary codec SDK binaries are bundled. NVENC uses the installed NVIDIA driver at runtime (driver >=570 for headers 13.0); Direct3D DLLs are Windows system components and are not shipped. Native H.264/AAC/PCM decoding is included; no software H.264 encoder is provided. NVENC and Direct3D capabilities do not mean every PC is supported: the NVIDIA driver/GPU is an external runtime prerequisite and desktop capture remains subject to Windows session permissions. Synthetic verification does not certify desktop capture or remote-device playback.\n\nOriginal source and input archives are in this directory; build.sh records the exact configure invocation. Sources are unmodified. For a rebuild, make an empty packaging directory and packaging/media-build subdirectory; place the supplied scripts into packaging/media-build. Install/extract archives into packaging/.build/media-minimal-01; portable compiler into packaging/.build-tools/media/w64devkit. fetch.sh (Git Bash) downloads/checks inputs, then run build.sh through w64devkit/bin/sh.exe. The prebuilt SDL development archive supplies an SDL2 import library and SDL2main entry shim; the matching complete SDL2 source archive is supplied alongside it. Prefix and source paths may be moved by setting ROOT. Preserve the original archives. Build uses no NASM (--disable-x86asm); optimization/performance should be assessed separately.\n\nToolchain: https://github.com/skeeto/w64devkit/releases/tag/v2.11.0 . Binary SHA256 54c2bb9962e8a30c8270e34c5efc3d5fee579f53087fa7d435b95fbba2af7b2b. Toolchain full sources: https://github.com/skeeto/w64devkit/releases/download/v2.11.0/source.tar (237045760 bytes). MinGW runtime notices and GCC runtime exception accompany this kit. Compiler itself is build-only and is not installed with DroidBridge.\n\nVerification details remain separate from sources. FFmpeg licensing reference https://ffmpeg.org/legal.html ; this is technical provenance, not a legal opinion or patent clearance.\n''',encoding='utf8')
components=[]
for name,version,license,url,archive,lic in items:
    paths=['sources/'+archive,'sources/build.sh','sources/BUILD.md']
    if name=='SDL2': paths+=['sources/SDL2-devel-2.32.10-mingw.tar.gz']
    components.append(dict(name=name,version=version,license=license,source_url=url,source_paths=paths,license_paths=['licenses/'+p for p in lic]))
def hashes(folder):
    return {p.relative_to(kit).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*')) if p.is_file()}
manifest=dict(schema_version=1,runtime_sha256=hashes(kit/'bin'),source_sha256=hashes(sources),license_sha256=hashes(licenses),components=components)
(kit/'media-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print('KIT',kit,'runtime_bytes',sum(p.stat().st_size for p in (kit/'bin').iterdir()),'sources_bytes',sum(p.stat().st_size for p in sources.iterdir()))
