"""Frozen/source dispatch without installing Python on an end user's PC."""
import importlib.util
import ipaddress
import os
from pathlib import Path
import subprocess
import sys


def data_directory(environment=None):
    env = os.environ if environment is None else environment
    return Path(env.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'VzaimoPult'


def phone_address(value):
    return str(ipaddress.ip_address(value.strip()))


def bundle_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def child_command(component, *arguments):
    if component not in ('server', 'viewer'):
        raise ValueError('Unknown component')
    base = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).with_name('launcher.py'))]
    return base + ['--component', component, *arguments]


def start_child(component, *arguments):
    return subprocess.Popen(child_command(component, *arguments), env=os.environ.copy(),
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def load_component(component):
    if component not in ('server', 'viewer'):
        raise ValueError('Unknown component')
    root = bundle_root()
    relative = 'listener/pc-listener.py' if component == 'server' else 'client/pc-viewer.pyw'
    path = root / relative
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('vzaimopult_' + component, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_component(component, arguments):
    data = data_directory()
    data.mkdir(parents=True, exist_ok=True)
    os.environ['VZAIMOPULT_DATA_DIR'] = str(data)
    module = load_component(component)
    # Compatibility with versions predating the production environment override.
    if component == 'server':
        module.TOKEN_FILE = str(data / 'token.txt')
        module.APPS_FILE = str(data / 'apps.json')
        module.LOG_FILE = str(data / 'listener.log')
        module.CLIENT_PID = str(data / 'client.pid')
        def mirror(ip, port):
            try:
                start_child('viewer', '--connect', phone_address(ip), '--port', str(int(port)))
                return True, ''
            except (OSError, ValueError) as error:
                return False, str(error)
        module.start_mirror_client = mirror
    else:
        module.LOG_PATH = str(data / 'client.log')
        module.PID_PATH = str(data / 'client.pid')
        module.DEFAULT_TOKEN = str(data / 'token.txt')
    sys.argv = [sys.argv[0], *arguments]
    return module.main()
