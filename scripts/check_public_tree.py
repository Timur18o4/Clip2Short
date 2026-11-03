"""Check the publication file set without printing potentially sensitive contents."""
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES={'clip2short','clip_engine','lumia','tests','docs','examples','scripts','.github'}
ROOT_FILES={'README.md','CHANGELOG.md','SECURITY.md','VERSION','.gitignore','.gitattributes',
            'requirements.txt','requirements-test.txt','start_service.py','Verwalten.ps1',
            'STARTEN.cmd','STOPPEN.cmd','EINRICHTEN.cmd','AUTOSTART AN.cmd','AUTOSTART AUS.cmd','Installieren.ps1'}
FORBIDDEN_PARTS={'Daten','data','.venv','venv','__pycache__','.test-temp','node_modules','.cache','dist','build','.runtime','.installation'}
FORBIDDEN_EXTENSIONS={'.dpapi','.sqlite','.sqlite3','.db','.log','.lock','.part','.mp4','.mkv','.mov','.webm',
                      '.wav','.mp3','.onnx','.safetensors','.bin','.pt','.pth','.pyc','.zip','.png','.jpg','.jpeg'}
PATTERNS={
    'GitHub-Zugangsdaten':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'KI-Zugangsdaten':re.compile(r'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}\b'),
    'Lumia-Zugangsdaten':re.compile(r'\blumia[0-9]{6,}\b',re.I),
    'Privater Schlüssel':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'Persönlicher Windows-Pfad':re.compile(r'[A-Za-z]:[/\\]+Users[/\\]+[A-Za-z0-9_.-]+',re.I),
}


def files_for_release(root=ROOT):
    root=Path(root).resolve()
    result=subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],capture_output=True,text=True)
    if result.returncode==0 and Path(result.stdout.strip()).resolve()==root:
        listed=subprocess.run(['git','-C',str(root),'ls-files','-z'],capture_output=True,check=True)
        files=[root/name for name in listed.stdout.decode('utf8').split('\0') if name]
        if files:return sorted(files)
    return sorted(p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts
                  and not set(p.relative_to(root).parts)&FORBIDDEN_PARTS
                  and (p.relative_to(root).parts[0] in DIRECTORIES or p.name in ROOT_FILES))


def validate_files(root,files):
    root=Path(root).resolve();problems=[]
    for path in files:
        path=Path(path)
        try:relative=path.resolve().relative_to(root)
        except ValueError:problems.append('Datei liegt außerhalb der Veröffentlichung.');continue
        name=relative.as_posix()
        if set(relative.parts)&FORBIDDEN_PARTS or path.suffix.lower() in FORBIDDEN_EXTENSIONS or path.name in {'installation.json','config.json'} or path.name.startswith(('.env','credentials')):
            problems.append(name+': private Laufzeitdatei oder nicht vorgesehener Dateityp');continue
        if relative.parts[0] not in DIRECTORIES and name not in ROOT_FILES:
            problems.append(name+': Datei steht nicht in der Veröffentlichungsauswahl');continue
        try:content=path.read_text(encoding='utf8')
        except (UnicodeError,OSError):problems.append(name+': nicht lesbare Textdatei');continue
        for label,pattern in PATTERNS.items():
            if pattern.search(content):problems.append(name+': '+label+' erkannt (Inhalt wird nicht ausgegeben)')
    if problems:raise ValueError('\n'.join(problems))
    return len(files)


if __name__=='__main__':
    try:
        count=validate_files(ROOT,files_for_release())
        print(f'Veröffentlichungsauswahl geprüft: {count} Textdateien; keine erkannten Zugangsdaten oder Laufzeitdateien.')
    except ValueError as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
