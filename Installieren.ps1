param([switch]$Pruefen,[switch]$LokaleKI)
$ErrorActionPreference='Stop'
$clipProgramRoot=$PSScriptRoot
Set-Location -LiteralPath $clipProgramRoot
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12

function Find-ClipPython {
    $clipCandidates=@((Join-Path $clipProgramRoot '.runtime\python\python.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))
    $clipFound=Get-Command python.exe -ErrorAction SilentlyContinue
    if ($clipFound -and $clipFound.Source -notlike '*WindowsApps*') {$clipCandidates+=$clipFound.Source}
    foreach($clipCandidate in $clipCandidates){
        if(Test-Path -LiteralPath $clipCandidate){
            $clipVersion=& $clipCandidate -c 'import sys; print(chr(46).join(map(str,sys.version_info[:2])))' 2>$null
            if($LASTEXITCODE -eq 0 -and $clipVersion -eq '3.12'){return $clipCandidate}
        }
    }
    return $null
}
if($Pruefen){
    [pscustomobject]@{Python=Find-ClipPython;Environment=Test-Path -LiteralPath (Join-Path $clipProgramRoot '.venv\Scripts\python.exe');PortableFFmpeg=Test-Path -LiteralPath (Join-Path $clipProgramRoot '.runtime\ffmpeg\bin\ffmpeg.exe')} | ConvertTo-Json
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$clipForm=New-Object Windows.Forms.Form
$clipForm.Text='Clip2Short einrichten';$clipForm.Size=New-Object Drawing.Size(640,430);$clipForm.StartPosition='CenterScreen';$clipForm.FormBorderStyle='FixedDialog';$clipForm.MaximizeBox=$false
$clipLabel=New-Object Windows.Forms.Label;$clipLabel.Location=New-Object Drawing.Point(24,20);$clipLabel.Size=New-Object Drawing.Size(575,95)
$clipLabel.Text="Clip2Short richtet die benötigten Komponenten in diesem Programmordner ein. Danach öffnet sich die Ersteinrichtung für Lumia und die Gestaltung.`r`n`r`nBeim ersten Start werden mehrere GB Software und Analysemodelle benötigt. Für spätere Starts werden vorhandene Komponenten wiederverwendet."
$clipLabel.Font=New-Object Drawing.Font('Segoe UI',10)
$clipCheck=New-Object Windows.Forms.CheckBox;$clipCheck.Text='Lokale KI ohne OpenAI vorbereiten (Ollama, zusätzlicher Download)';$clipCheck.Location=New-Object Drawing.Point(24,127);$clipCheck.Size=New-Object Drawing.Size(580,40);$clipCheck.Checked=$LokaleKI
$clipProgress=New-Object Windows.Forms.ProgressBar;$clipProgress.Location=New-Object Drawing.Point(24,185);$clipProgress.Size=New-Object Drawing.Size(575,20);$clipProgress.Style='Marquee';$clipProgress.Visible=$false
$clipStatus=New-Object Windows.Forms.Label;$clipStatus.Location=New-Object Drawing.Point(24,223);$clipStatus.Size=New-Object Drawing.Size(575,80);$clipStatus.Text='Bereit. Eine vorhandene Lumia-Einrichtung und deine Clips bleiben erhalten.'
$clipButton=New-Object Windows.Forms.Button;$clipButton.Text='Einrichten';$clipButton.Location=New-Object Drawing.Point(389,321);$clipButton.Size=New-Object Drawing.Size(210,40)
$clipForm.Controls.AddRange(@($clipLabel,$clipCheck,$clipProgress,$clipStatus,$clipButton))
function Set-ClipStatus([string]$clipText){$clipStatus.Text=$clipText;[Windows.Forms.Application]::DoEvents()}
function Get-ClipDownload([string]$clipUrl,[string]$clipPath){
    $clipWeb=New-Object Net.WebClient;$clipWeb.Headers['User-Agent']='Clip2Short-Setup'
    try {
        $clipDownload=$clipWeb.DownloadFileTaskAsync([Uri]$clipUrl,$clipPath)
        $clipTimer=[Diagnostics.Stopwatch]::StartNew()
        while(-not $clipDownload.IsCompleted){
            [Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 150
            if($clipTimer.Elapsed.TotalSeconds -gt 600){$clipWeb.CancelAsync();throw 'Der Download dauert zu lange. Bitte die Internetverbindung prüfen.'}
        }
        $clipDownload.GetAwaiter().GetResult()
    } finally {$clipWeb.Dispose()}
}
function Run-ClipProcess([string]$clipExecutable,[string[]]$clipArguments){
    $clipLogDir=Join-Path $clipProgramRoot '.installation';New-Item -ItemType Directory -Path $clipLogDir -Force | Out-Null
    $clipProcess=Start-Process -FilePath $clipExecutable -ArgumentList $clipArguments -WorkingDirectory $clipProgramRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $clipLogDir 'install-output.log') -RedirectStandardError (Join-Path $clipLogDir 'install-errors.log')
    $clipProcessHandle=$clipProcess.Handle
    while(-not $clipProcess.HasExited){[Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 200;$clipProcess.Refresh()}
    $clipProcess.WaitForExit()
    if($clipProcess.ExitCode -ne 0){throw ('Einrichtungsschritt fehlgeschlagen. Details stehen im Programmordner unter .installation. Rückgabewert: '+$clipProcess.ExitCode)}
}
$clipButton.Add_Click({
    $clipButton.Enabled=$false;$clipCheck.Enabled=$false;$clipProgress.Visible=$true
    try{
        $clipRuntime=Join-Path $clipProgramRoot '.runtime';New-Item -ItemType Directory -Path $clipRuntime -Force | Out-Null
        Set-ClipStatus 'Python wird geprüft …'
        $clipBasePython=Find-ClipPython
        if(-not $clipBasePython){
            Set-ClipStatus 'Eine portable Python-3.12-Laufzeit wird geladen und geprüft …'
            $clipRelease=Invoke-RestMethod -Uri 'https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest' -Headers @{'User-Agent'='Clip2Short-Setup'} -TimeoutSec 45
            $clipAsset=$clipRelease.assets | Where-Object {$_.name -like 'cpython-3.12.*-x86_64-pc-windows-msvc-install_only.tar.gz'} | Select-Object -First 1
            if(-not $clipAsset -or $clipAsset.digest -notmatch '^sha256:[0-9a-f]{64}$'){throw 'Keine prüfbare Windows-Python-Laufzeit beim offiziellen Laufzeitprojekt gefunden.'}
            $clipArchive=Join-Path $clipRuntime 'python.tar.gz';Get-ClipDownload $clipAsset.browser_download_url $clipArchive
            if((Get-FileHash -LiteralPath $clipArchive -Algorithm SHA256).Hash.ToLower() -ne $clipAsset.digest.Substring(7)){throw 'Prüfsumme der Python-Laufzeit stimmt nicht.'}
            $clipTar=Get-Command tar.exe -ErrorAction SilentlyContinue
            if(-not $clipTar){throw 'Das Windows-Entpackprogramm tar.exe fehlt. Windows aktualisieren oder Python 3.12 vorab installieren.'}
            Run-ClipProcess $clipTar.Source @('-xzf',('"'+$clipArchive+'"'),'-C',('"'+$clipRuntime+'"'))
            $clipBasePython=Find-ClipPython
            if(-not $clipBasePython){throw 'Portable Python-Laufzeit wurde nicht korrekt entpackt.'}
        }
        $clipPython=Join-Path $clipProgramRoot '.venv\Scripts\python.exe'
        if(-not(Test-Path -LiteralPath $clipPython)){
            Set-ClipStatus 'Die eigene Programmumgebung wird angelegt …'
            Run-ClipProcess $clipBasePython @('-m','venv',('"'+(Join-Path $clipProgramRoot '.venv')+'"'))
        }
        Set-ClipStatus 'Bibliotheken für Video und Spracherkennung werden eingerichtet. Das kann einige Minuten dauern …'
        Run-ClipProcess $clipPython @('-m','pip','install','--disable-pip-version-check','-r',('"'+(Join-Path $clipProgramRoot 'requirements.txt')+'"'))
        Set-ClipStatus 'Video-Werkzeuge werden geprüft …'
        $clipFFOk=$false
        try { & $clipPython -c "from clip_engine.media import find_binary; from clip_engine.render import _check_ffmpeg; _check_ffmpeg(find_binary('ffmpeg')); find_binary('ffprobe')" 2>$null | Out-Null; $clipFFOk=($LASTEXITCODE -eq 0) } catch {}
        if(-not $clipFFOk){
            Set-ClipStatus 'FFmpeg wird geladen und anhand der veröffentlichten Prüfsumme geprüft …'
            $clipFFZip=Join-Path $clipRuntime 'ffmpeg.zip';$clipFFChecksum=(Invoke-WebRequest -UseBasicParsing -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256' -TimeoutSec 45).Content
            if($clipFFChecksum -is [byte[]]){$clipFFChecksum=[Text.Encoding]::ASCII.GetString($clipFFChecksum)}
            $clipExpected=[regex]::Match([string]$clipFFChecksum,'[a-fA-F0-9]{64}').Value
            if(-not $clipExpected){throw 'FFmpeg-Prüfsumme fehlt.'}
            Get-ClipDownload 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' $clipFFZip
            if((Get-FileHash -LiteralPath $clipFFZip -Algorithm SHA256).Hash -ne $clipExpected){throw 'FFmpeg-Prüfsumme stimmt nicht.'}
            $clipUnpack=Join-Path $clipRuntime 'ffmpeg-unpack';Expand-Archive -LiteralPath $clipFFZip -DestinationPath $clipUnpack -Force
            $clipFFBin=Join-Path $clipRuntime 'ffmpeg\bin';New-Item -ItemType Directory -Path $clipFFBin -Force | Out-Null
            foreach($clipTool in @('ffmpeg.exe','ffprobe.exe')){
                $clipBinary=Get-ChildItem -LiteralPath $clipUnpack -Filter $clipTool -Recurse | Select-Object -First 1
                if(-not $clipBinary){throw 'Das FFmpeg-Paket ist unvollständig.'}
                Copy-Item -LiteralPath $clipBinary.FullName -Destination (Join-Path $clipFFBin $clipTool) -Force
            }
            Run-ClipProcess $clipPython @('-c','"from clip_engine.media import find_binary; from clip_engine.render import _check_ffmpeg; _check_ffmpeg(find_binary(''ffmpeg'')); find_binary(''ffprobe'')"')
        }
        if($clipCheck.Checked){
            Set-ClipStatus 'Lokale KI wird geprüft …'
            $clipOllamaReady=$false
            try{$null=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3;$clipOllamaReady=$true}catch{}
            if(-not $clipOllamaReady){
                $clipOllama=Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
                if(-not(Test-Path -LiteralPath $clipOllama)){
                    Set-ClipStatus 'Ollama wird vom Hersteller geladen. Der signierte Installer wird im Benutzerkonto ausgeführt …'
                    $clipOllamaSetup=Join-Path $clipRuntime 'OllamaSetup.exe';Get-ClipDownload 'https://ollama.com/download/OllamaSetup.exe' $clipOllamaSetup
                    if((Get-AuthenticodeSignature -LiteralPath $clipOllamaSetup).Status -ne 'Valid'){throw 'Die digitale Signatur des Ollama-Installers konnte nicht bestätigt werden.'}
                    Run-ClipProcess $clipOllamaSetup @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-')
                }
                if(Test-Path -LiteralPath $clipOllama){Start-Process -FilePath $clipOllama -ArgumentList 'serve' -WindowStyle Hidden}
            }
        }
        Set-ClipStatus 'Fertig. Die Ersteinrichtung wird im Browser geöffnet …'
        $clipPythonw=Join-Path $clipProgramRoot '.venv\Scripts\pythonw.exe'
        Start-Process -FilePath $clipPythonw -ArgumentList '-m clip2short configure' -WorkingDirectory $clipProgramRoot -WindowStyle Hidden
        $clipForm.Close()
    }catch{
        Set-ClipStatus $_.Exception.Message
        $clipButton.Enabled=$true;$clipCheck.Enabled=$true;$clipProgress.Visible=$false
    }
})
$null=$clipForm.ShowDialog()
