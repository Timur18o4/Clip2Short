param([ValidateSet('Start','Setup','Stop','AutostartAn','AutostartAus')][string]$Action='Start')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$clipPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$clipPythonw=Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$clipData=Join-Path $env:LOCALAPPDATA 'Clip2Short'
$clipLocation=Join-Path $PSScriptRoot 'installation.json'
if (Test-Path -LiteralPath $clipLocation) { $clipData=(Get-Content -LiteralPath $clipLocation -Raw -Encoding UTF8 | ConvertFrom-Json).data_dir }
$startup=Join-Path ([Environment]::GetFolderPath('Startup')) 'Clip2Short.vbs'
try {
    if ($Action -eq 'Setup') {
        & (Join-Path $PSScriptRoot 'Installieren.ps1')
        exit 0
    }
    if (-not (Test-Path -LiteralPath $clipPython)) { & (Join-Path $PSScriptRoot 'Installieren.ps1'); exit }
    if ($Action -eq 'AutostartAn') {
        $clipAccount=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        try {
            $taskAction=New-ScheduledTaskAction -Execute $clipPythonw -Argument '-m clip2short run' -WorkingDirectory $PSScriptRoot
            $taskTrigger=New-ScheduledTaskTrigger -AtLogOn -User $clipAccount
            $taskPrincipal=New-ScheduledTaskPrincipal -UserId $clipAccount -LogonType Interactive -RunLevel Limited
            $taskSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            $existingTask=Get-ScheduledTask -TaskName 'Clip2Short' -ErrorAction SilentlyContinue
            if ($existingTask -and $existingTask.Description -ne 'Clip2Short: neue Twitch-Clips ueber Lumia') { throw 'Ein anderer Windows-Auftrag verwendet bereits diesen Namen.' }
            Register-ScheduledTask -TaskName 'Clip2Short' -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'Clip2Short: neue Twitch-Clips ueber Lumia' -Force | Out-Null
            if (Test-Path -LiteralPath $startup) { Remove-Item -LiteralPath $startup }
            Write-Host 'Automatischer Windows-Start mit Neustart nach einem Fehler ist aktiv.' -ForegroundColor Green
            exit 0
        } catch {
            if ($existingTask -and $existingTask.Description -ne 'Clip2Short: neue Twitch-Clips ueber Lumia') { throw }
            Write-Host 'Windows-Aufgabenplanung nicht verfuegbar. Verwende den Benutzer-Autostart.'
        }
        $escapedRoot=$PSScriptRoot.Replace('"','""')
        $escapedExe=$clipPythonw.Replace('"','""')
        $escapedData=$clipData.Replace('"','""')
        $text='Set clipShell = CreateObject("WScript.Shell")'+"`r`n"+'clipShell.CurrentDirectory = "'+$escapedRoot+'"'+"`r`n"+'clipShell.Environment("PROCESS")("CLIP2SHORT_CLIP_DATA") = "'+$escapedData+'"'+"`r`n"+'clipShell.Run """'+$escapedExe+'"" -m clip2short run", 0, False'+"`r`n"
        [System.IO.File]::WriteAllText($startup,$text,[System.Text.Encoding]::Unicode)
        Write-Host 'Autostart bei deiner Windows-Anmeldung ist aktiv.' -ForegroundColor Green
        exit 0
    }
    if ($Action -eq 'AutostartAus') {
        $existingTask=Get-ScheduledTask -TaskName 'Clip2Short' -ErrorAction SilentlyContinue
        if ($existingTask -and $existingTask.Description -eq 'Clip2Short: neue Twitch-Clips ueber Lumia') { Disable-ScheduledTask -TaskName 'Clip2Short' | Out-Null }
        if (Test-Path -LiteralPath $startup) { Remove-Item -LiteralPath $startup }
        Write-Host 'Autostart deaktiviert.'
        exit 0
    }
    if ($Action -eq 'Stop') { & $clipPython -m clip2short stop; exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath (Join-Path $clipData 'credentials.dpapi'))) { Start-Process -FilePath $clipPythonw -ArgumentList '-m clip2short configure' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden; exit }
    $running=$false
    $clipSettings=Get-Content -LiteralPath (Join-Path $clipData 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $clipExpectedChannel=$clipSettings.channel
    $clipPort=$clipSettings.port
    try { $check=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$clipPort+'/health') -TimeoutSec 2; $running=($check.channel -eq $clipExpectedChannel) } catch { }
    if (-not $running) {
        $existingTask=Get-ScheduledTask -TaskName 'Clip2Short' -ErrorAction SilentlyContinue
        if ($existingTask -and $existingTask.Description -eq 'Clip2Short: neue Twitch-Clips ueber Lumia' -and $existingTask.State -ne 'Disabled') { Start-ScheduledTask -TaskName 'Clip2Short' }
        else { Start-Process -FilePath $clipPythonw -ArgumentList @('-m','clip2short','run') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden }
    }
    Start-Process ('http://127.0.0.1:'+$clipPort)
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
