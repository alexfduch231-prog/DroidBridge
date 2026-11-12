param([string]$Python = "python", [switch]$SetupFirewall)
$ErrorActionPreference = "Stop"
if ($SetupFirewall) {
    # Administrator rights are required. Never enable remote control on Public profiles.
    New-NetFirewallRule -DisplayName "VzaimoPult HTTP (Private LAN)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private -RemoteAddress LocalSubnet
    New-NetFirewallRule -DisplayName "VzaimoPult Discovery (Private LAN)" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 8766 -Profile Private -RemoteAddress LocalSubnet
    exit
}
& $Python (Join-Path $PSScriptRoot "listener/pc-listener.py")
exit $LASTEXITCODE
