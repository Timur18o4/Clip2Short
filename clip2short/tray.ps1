param([int]$ServicePid, [int]$Port)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$service = [Diagnostics.Process]::GetProcessById($ServicePid)
$null = $service.Handle
$base = "http://127.0.0.1:$Port"
$pipe = [Console]::OpenStandardInput()
$reader = New-Object IO.StreamReader($pipe)
$token = $reader.ReadLine()
if (-not $token) { exit 1 }
$buffer = New-Object byte[] 1
$shutdown = $pipe.ReadAsync($buffer, 0, 1)
$client = New-Object Net.WebClient
$client.Proxy = $null
$client.Encoding = [Text.Encoding]::UTF8
$client.Headers['Authorization'] = 'Bearer ' + $token
$context = New-Object Windows.Forms.ApplicationContext
$icon = New-Object Windows.Forms.NotifyIcon
$artwork = [Drawing.Icon]::new((Join-Path $PSScriptRoot 'tray.ico'), [Windows.Forms.SystemInformation]::SmallIconSize)
$icon.Icon = $artwork
$menu = New-Object Windows.Forms.ContextMenuStrip
$open = $menu.Items.Add('Weboberfläche öffnen')
$stop = $menu.Items.Add('Dienst beenden')
$icon.ContextMenuStrip = $menu
[Threading.SynchronizationContext]::SetSynchronizationContext(
    (New-Object Windows.Forms.WindowsFormsSynchronizationContext))
$openDashboard = { Start-Process "$base/" }
$open.Add_Click($openDashboard)
$icon.Add_MouseDoubleClick({
    param($sender, $eventArgs)
    if ($eventArgs.Button -eq [Windows.Forms.MouseButtons]::Left) { & $openDashboard }
})
$stop.Add_Click({
    if ($client.IsBusy) { $client.CancelAsync() }
    # Notify the owning Python process through its private pipe.
    $stop.Enabled = $false
    [Console]::WriteLine('stop')
    [Console]::Out.Flush()
})

$client.add_DownloadStringCompleted({
    param($sender, $eventArgs)
    if ($eventArgs.Cancelled -or $eventArgs.Error) { return }
    $status = ($eventArgs.Result | ConvertFrom-Json).status
    $tip = ('Clip2Short · ' + ($status -replace '\s+', ' ')).Trim()
    # Windows PowerShell 5 limits NotifyIcon.Text to 63 UTF-16 characters.
    if ($tip.Length -gt 63) { $tip = $tip.Substring(0,62) + '…' }
    $icon.Text = $tip
})

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 1500
$timer.Add_Tick({
    if ($service.HasExited -or $shutdown.IsCompleted) { $context.ExitThread(); return }
    if (-not $client.IsBusy -and $stop.Enabled) { $client.DownloadStringAsync([Uri]"$base/api/tray") }
})
$icon.Text = 'Clip2Short · startet'
$icon.Visible = $true
try {
    $timer.Start()
    [Windows.Forms.Application]::Run($context)
} finally {
    $timer.Dispose()
    $icon.Visible = $false
    $icon.Dispose()
    $artwork.Dispose()
    $menu.Dispose()
    $client.Dispose()
    $reader.Dispose()
    $service.Dispose()
    $context.Dispose()
}
