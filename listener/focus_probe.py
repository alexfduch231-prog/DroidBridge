"""UIA focus metadata only. Never reads values, names or document text."""
import os
import subprocess
import threading

_PROBE_SLOT = threading.BoundedSemaphore(1)

_SCRIPT = r'''Add-Type -AssemblyName UIAutomationClient
try {
 $e=[System.Windows.Automation.AutomationElement]::FocusedElement
 if ($null -eq $e) { exit 2 }
 if ($e.Current.IsPassword) { Write-Output 'false'; exit 0 }
 $p=$null
 if ($e.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$p)) {
  if (-not $p.Current.IsReadOnly -and $e.Current.IsEnabled -and $e.Current.IsKeyboardFocusable) { Write-Output 'true' } else { Write-Output 'false' }
 } elseif ($e.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit -and $e.Current.IsEnabled) {
  Write-Output 'true'
 } else { Write-Output 'false' }
} catch { exit 2 }
'''

def editable_focus():
    """Return True/False or None on unsupported, denied or slow UIA providers."""
    if not _PROBE_SLOT.acquire(blocking=False):
        return None
    try:
        return _editable_focus()
    finally:
        _PROBE_SLOT.release()


def _editable_focus():
    executable = os.path.join(os.environ.get('SystemRoot', 'C:/Windows'),
                              'System32/WindowsPowerShell/v1.0/powershell.exe')
    try:
        result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-Command', _SCRIPT],
                                capture_output=True, text=True, timeout=1.5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        value = result.stdout.strip().lower()
        if result.returncode == 0 and value in ('true', 'false'):
            return value == 'true'
    except (OSError, subprocess.SubprocessError):
        pass
    return None
