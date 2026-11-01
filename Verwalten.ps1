param([ValidateSet('Start','Setup','Stop','AutostartAn','AutostartAus')][string]$Action='Start')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$clipPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$clipPythonw=Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$clipData=Join-Path $env:LOCALAPPDATA 'CNGClipDienst'
$clipLocation=Join-Path $PSScriptRoot 'installation.json'
if (Test-Path -LiteralPath $clipLocation) { $clipData=(Get-Content -LiteralPath $clipLocation -Raw -Encoding UTF8 | ConvertFrom-Json).data_dir }
$startup=Join-Path ([Environment]::GetFolderPath('Startup')) 'CNG Clip Dienst.vbs'
try {
    if ($Action -eq 'Setup') {
        if (-not (Test-Path -LiteralPath $clipPython)) {
            $base=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
            if (-not (Test-Path -LiteralPath $base)) {
                $found=Get-Command python.exe -ErrorAction SilentlyContinue
                if (-not $found) { throw 'Python 3.12 installieren, dann erneut starten.' }
                $base=$found.Source
            }
            & $base -m venv (Join-Path $PSScriptRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Python-Umgebung konnte nicht angelegt werden.' }
        }
        & $clipPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Bibliotheken konnten nicht installiert werden.' }
        & $clipPython -c "from clip_engine.media import find_binary; find_binary('ffmpeg'); find_binary('ffprobe')"
        if ($LASTEXITCODE -ne 0) { throw 'Vollstaendiges FFmpeg fehlt. winget install --id Gyan.FFmpeg --exact ausfuehren.' }
        & $clipPython -m cng_clip_service setup
        if ($LASTEXITCODE -ne 0) { throw 'Einrichtung der Zugangsdaten fehlgeschlagen.' }
        Write-Host 'Danach den Befehl aus lumia\cng-clip-dienst.js in Lumia als Chat-Befehl cng-clip-dienst anlegen.'
        Write-Host 'STARTEN.cmd oeffnet den Dienststatus.' -ForegroundColor Green
        exit 0
    }
    if (-not (Test-Path -LiteralPath $clipPython)) { throw 'Zuerst EINRICHTEN.cmd ausfuehren.' }
    if ($Action -eq 'AutostartAn') {
        $clipAccount=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        try {
            $taskAction=New-ScheduledTaskAction -Execute $clipPythonw -Argument '-m cng_clip_service run' -WorkingDirectory $PSScriptRoot
            $taskTrigger=New-ScheduledTaskTrigger -AtLogOn -User $clipAccount
            $taskPrincipal=New-ScheduledTaskPrincipal -UserId $clipAccount -LogonType Interactive -RunLevel Limited
            $taskSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            $existingTask=Get-ScheduledTask -TaskName 'CNG Clip Dienst' -ErrorAction SilentlyContinue
            if ($existingTask -and $existingTask.Description -ne 'CNG Clip Dienst: neue Twitch-Clips ueber Lumia') { throw 'Ein anderer Windows-Auftrag verwendet bereits diesen Namen.' }
            Register-ScheduledTask -TaskName 'CNG Clip Dienst' -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description 'CNG Clip Dienst: neue Twitch-Clips ueber Lumia' -Force | Out-Null
            if (Test-Path -LiteralPath $startup) { Remove-Item -LiteralPath $startup }
            Write-Host 'Automatischer Windows-Start mit Neustart nach einem Fehler ist aktiv.' -ForegroundColor Green
            exit 0
        } catch {
            if ($existingTask -and $existingTask.Description -ne 'CNG Clip Dienst: neue Twitch-Clips ueber Lumia') { throw }
            Write-Host 'Windows-Aufgabenplanung nicht verfuegbar. Verwende den Benutzer-Autostart.'
        }
        $escapedRoot=$PSScriptRoot.Replace('"','""')
        $escapedExe=$clipPythonw.Replace('"','""')
        $escapedData=$clipData.Replace('"','""')
        $text='Set clipShell = CreateObject("WScript.Shell")'+"`r`n"+'clipShell.CurrentDirectory = "'+$escapedRoot+'"'+"`r`n"+'clipShell.Environment("PROCESS")("CNG_CLIP_DATA") = "'+$escapedData+'"'+"`r`n"+'clipShell.Run """'+$escapedExe+'"" -m cng_clip_service run", 0, False'+"`r`n"
        [System.IO.File]::WriteAllText($startup,$text,[System.Text.Encoding]::Unicode)
        Write-Host 'Autostart bei deiner Windows-Anmeldung ist aktiv.' -ForegroundColor Green
        exit 0
    }
    if ($Action -eq 'AutostartAus') {
        $existingTask=Get-ScheduledTask -TaskName 'CNG Clip Dienst' -ErrorAction SilentlyContinue
        if ($existingTask -and $existingTask.Description -eq 'CNG Clip Dienst: neue Twitch-Clips ueber Lumia') { Disable-ScheduledTask -TaskName 'CNG Clip Dienst' | Out-Null }
        if (Test-Path -LiteralPath $startup) { Remove-Item -LiteralPath $startup }
        Write-Host 'Autostart deaktiviert.'
        exit 0
    }
    if ($Action -eq 'Stop') { & $clipPython -m cng_clip_service stop; exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath (Join-Path $clipData 'credentials.dpapi'))) { throw 'Zuerst EINRICHTEN.cmd ausfuehren.' }
    $running=$false
    $clipExpectedChannel=(Get-Content -LiteralPath (Join-Path $clipData 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json).channel
    try { $check=Invoke-RestMethod -Uri 'http://127.0.0.1:39242/health' -TimeoutSec 2; $running=($check.channel -eq $clipExpectedChannel) } catch { }
    if (-not $running) {
        $existingTask=Get-ScheduledTask -TaskName 'CNG Clip Dienst' -ErrorAction SilentlyContinue
        if ($existingTask -and $existingTask.Description -eq 'CNG Clip Dienst: neue Twitch-Clips ueber Lumia' -and $existingTask.State -ne 'Disabled') { Start-ScheduledTask -TaskName 'CNG Clip Dienst' }
        else { Start-Process -FilePath $clipPythonw -ArgumentList @('-m','cng_clip_service','run') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden }
    }
    Start-Process 'http://127.0.0.1:39242'
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
