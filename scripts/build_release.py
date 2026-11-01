"""Build a source-based Windows program ZIP from the checked publication set."""
from pathlib import Path
import hashlib
import re
import zipfile
from check_public_tree import ROOT,files_for_release,validate_files


def main():
    version=(ROOT/'VERSION').read_text(encoding='utf8').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('VERSION ist ungültig.')
    files=files_for_release();validate_files(ROOT,files)
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    archive=output/f'CNG_Clip_Dienst_Windows_v{version}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for path in files:
            raw=path.read_bytes()
            if path.suffix.lower() in ('.cmd','.ps1'):raw=raw.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
            bundle.writestr('CNG_Clip_Dienst/'+path.relative_to(ROOT).as_posix(),raw)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:raise ValueError('ZIP-Prüfung fehlgeschlagen.')
        for required in ('STARTEN.cmd','EINRICHTEN.cmd','Verwalten.ps1','lumia/cng-clip-dienst.js'):
            if 'CNG_Clip_Dienst/'+required not in bundle.namelist():raise ValueError('Pflichtdatei fehlt: '+required)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(checksum+'  '+archive.name+'\n',encoding='ascii')
    print(f'Erstellt: {archive.name} ({len(files)} Dateien)')
    print('SHA256: '+checksum)


if __name__=='__main__':main()
