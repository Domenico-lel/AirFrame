# Local-subnet access only. This setup is invoked by the user from Settings.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$airFrameResult = Join-Path $env:LOCALAPPDATA 'AirFrame\network-setup.txt'
try {
$airFrameEngine = Join-Path $PSScriptRoot 'engine\uxplay.exe'
if (-not (Test-Path -LiteralPath $airFrameEngine)) { throw 'Ricevitore AirFrame non trovato.' }
$airFrameEngine = (Resolve-Path -LiteralPath $airFrameEngine).Path
$airFrameRule = 'AirFrame prototype local network'
Get-NetFirewallRule -DisplayName $airFrameRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $airFrameRule -Direction Inbound -Action Allow -Program $airFrameEngine -Profile Private,Public -RemoteAddress LocalSubnet -Protocol TCP -LocalPort 7100-7102 | Out-Null
New-NetFirewallRule -DisplayName $airFrameRule -Direction Inbound -Action Allow -Program $airFrameEngine -Profile Private,Public -RemoteAddress LocalSubnet -Protocol UDP -LocalPort 5353,7100-7102 | Out-Null
$airFrameMessage = 'Configurazione completata. Torna su iPhone e seleziona AirFrame in Duplica schermo. Accesso limitato alla sottorete locale.'
$airFrameMessage | Set-Content -LiteralPath $airFrameResult
[System.Windows.Forms.MessageBox]::Show($airFrameMessage, 'AirFrame - Rete configurata') | Out-Null
} catch {
    $airFrameMessage = 'Configurazione non completata: ' + $_.Exception.Message
    $airFrameMessage | Set-Content -LiteralPath $airFrameResult
    [System.Windows.Forms.MessageBox]::Show($airFrameMessage, 'AirFrame - Errore di rete') | Out-Null
    exit 1
}
