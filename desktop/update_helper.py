"""Generate a fixed detached system helper; never load executable commands from disk."""
import base64
import hashlib
import os
from pathlib import Path
import re
import subprocess


def event_name(executable):
    identity = str(Path(executable).resolve()).casefold().encode('utf-8')
    return 'Local\\DroidBridge-update-' + hashlib.sha256(identity).hexdigest()


def _literal(value):
    value = str(value)
    if any(ord(c) < 32 for c in value) or '"' in value:
        raise ValueError('invalid helper path')
    return "'" + value.replace("'", "''") + "'"


def helper_script(executable, installer, sha256, size, *, sequence=None, expires=None):
    executable, installer = Path(executable), Path(installer)
    if not executable.is_absolute() or executable.name != 'DroidBridge.exe' or not installer.is_absolute() or installer.suffix != '.exe':
        raise ValueError('invalid installed executable')
    if not re.fullmatch('[a-f0-9]{64}', sha256) or type(size) is not int or not 1 <= size <= 512 * 1024 * 1024:
        raise ValueError('invalid installer identity')
    exe, setup, directory = map(_literal, (executable, installer, executable.parent))
    event = _literal(event_name(executable))
    state_guard = ''
    if sequence is not None:
        if type(sequence) is not int or not 1 <= sequence <= 9223372036854775807 or not isinstance(expires, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', expires):
            raise ValueError('invalid verified manifest metadata')
        state_guard = f"""
  $stateLock = [IO.File]::Open({_literal(installer.parent.parent / 'update_state.lock')}, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
  $stateLock.Lock(0, 1)
  $state = Get-Content -LiteralPath {_literal(installer.parent.parent / 'update_state.json')} -Raw | ConvertFrom-Json
  if ($state.maxVerifiedSequence -gt {sequence}) {{ throw 'Manifest rollback' }}
  if ([DateTime]::UtcNow -ge [DateTime]::ParseExact('{expires}', 'yyyy-MM-ddTHH:mm:ssZ', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AdjustToUniversal)) {{ throw 'Manifest expired' }}
"""
    # FileShare.Read denies modifications/deletion through hash verification and
    # execution. Process.Handle is acquired before inspecting its image path: PID
    # reuse never targets another process. No termination API is used at all.
    return f"""$ErrorActionPreference = 'Stop'
$exe = {exe}
$setup = {setup}
$directory = {directory}
$locked = $null
$event = $null
$stateLock = $null
$mutex = [System.Threading.Mutex]::new($false, {event} + '-install')
$ownsMutex = $false
try {{
  $ownsMutex = $mutex.WaitOne(0)
  if (-not $ownsMutex) {{ throw 'Another update is already running' }}
{state_guard}
  $locked = [System.IO.File]::Open($setup, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
  if ($locked.Length -ne {size}) {{ throw 'Installer size changed' }}
  $hasher = [System.Security.Cryptography.SHA256]::Create()
  try {{ $hash = ([BitConverter]::ToString($hasher.ComputeHash($locked))).Replace('-', '').ToLowerInvariant() }} finally {{ $hasher.Dispose() }}
  if ($hash -cne '{sha256}') {{ throw 'Installer SHA256 changed' }}
  $event = [System.Threading.EventWaitHandle]::OpenExisting({event})
  $event.Set() | Out-Null
  $deadline = [DateTime]::UtcNow.AddSeconds(90)
  $clear = 0
  while ($clear -lt 2) {{
    $found = $false
    foreach ($process in [System.Diagnostics.Process]::GetProcessesByName('DroidBridge')) {{
      try {{
        $handle = $process.Handle
        if ($process.HasExited) {{ continue }}
        $path = $process.MainModule.FileName
        if ([String]::Equals($path, $exe, [StringComparison]::OrdinalIgnoreCase)) {{
          $found = $true
          if (-not $process.WaitForExit(500)) {{
            if ([DateTime]::UtcNow -ge $deadline) {{ throw 'Application still running; update aborted' }}
          }}
        }}
      }} catch [System.InvalidOperationException] {{
        # Process exited between snapshot and handle acquisition; no PID-based action.
        continue
      }} catch [System.ComponentModel.Win32Exception] {{
        if ($process.HasExited) {{ continue }}
        throw
      }} finally {{ $process.Dispose() }}
    }}
    if ([DateTime]::UtcNow -ge $deadline) {{ throw 'Application shutdown timed out' }}
    if ($found) {{ $clear = 0 }} else {{ $clear++ }}
    Start-Sleep -Milliseconds 250
  }}
  $arguments = @('/CURRENTUSER', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/DIR="' + $directory + '"'))
  $installed = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
  if ($installed.ExitCode -ne 0) {{ throw ('Installer failed: ' + $installed.ExitCode) }}
  $event.Reset() | Out-Null
  Start-Process -FilePath $exe -WorkingDirectory $directory
}} catch {{
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.MessageBox]::Show('DroidBridge update stopped safely. ' + $_.Exception.Message, 'DroidBridge update') | Out-Null
}} finally {{
  if ($event) {{ $event.Reset() | Out-Null; $event.Dispose() }}
  if ($locked) {{ $locked.Dispose() }}
  if ($stateLock) {{ $stateLock.Dispose() }}
  if ($ownsMutex) {{ $mutex.ReleaseMutex() }}
  $mutex.Dispose()
  Remove-Item -LiteralPath $setup -Force -ErrorAction SilentlyContinue
}}
"""


def launch_helper(executable, installer, sha256, size, *, sequence, expires):
    script = helper_script(executable, installer, sha256, size, sequence=sequence, expires=expires)
    # Absolute Windows system binary, not PATH, environment SystemRoot or a staged
    # executable. UTF16 encoded script is generated in memory, never read from disk.
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer)):
        raise OSError('Cannot locate Windows system directory')
    powershell = Path(buffer.value) / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return subprocess.Popen([str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                            close_fds=True, cwd=str(installer.parent))
