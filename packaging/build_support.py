"""Auditable positive source allowlist. Never copy a project directory wholesale."""
from pathlib import Path
import hashlib
import shutil

SOURCE_FILES = (
    'desktop/launcher.py', 'desktop/runtime.py',
    'desktop/pairing_panel.py', 'desktop/apps_panel.py',
    'listener/pairing.py', 'listener/app_catalog.py',
    'listener/pc-listener.py', 'listener/file_upload.py',
    'listener/remote_input.py', 'listener/lan_discovery.py',
    'client/pc-viewer.pyw', 'client/control_geometry.py',
)

def stage_sources(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError('Staging requires a new empty destination')
    source = source.resolve()
    for relative in SOURCE_FILES:
        file = source / relative
        if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(source):
            raise ValueError('Missing or unsafe allowlisted source: ' + relative)
    target.mkdir(parents=True)
    for relative in SOURCE_FILES:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, destination)

def inventory(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}
