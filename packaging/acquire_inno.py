"""Fetch official pinned Inno installer and unpack portable mode, no registry install."""
from pathlib import Path
import hashlib
import subprocess
import urllib.request

URL = 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
SHA256 = '8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0'
root = Path(__file__).resolve().parent / '.build-tools'
root.mkdir(exist_ok=True)
installer = root / 'innosetup-7.1.1-x64.exe'
if not installer.exists():
    urllib.request.urlretrieve(URL, installer)
if hashlib.sha256(installer.read_bytes()).hexdigest() != SHA256:
    raise SystemExit('Inno download SHA256 mismatch')
compiler = root / 'inno-7.1.1' / 'ISCC.exe'
if not compiler.exists():
    subprocess.run([str(installer), '/PORTABLE=1', '/VERYSILENT', '/SUPPRESSMSGBOXES',
                    '/NORESTART', '/SP-', '/DIR=' + str(compiler.parent)], check=True)
if not compiler.exists():
    raise SystemExit('Portable Inno extraction did not produce ISCC.exe')
print(compiler)
