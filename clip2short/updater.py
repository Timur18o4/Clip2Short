"""Stage Windows releases from GitHub and apply them after the service exits."""
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

REPOSITORY = 'Timur18o4/Clip2Short'
PROGRAM = Path(__file__).resolve().parents[1]
ACTIVE = {'resolving', 'downloading', 'transcribing', 'analyzing', 'rendering', 'uploading', 'dispatching'}
ROOT_FILES = {'VERSION', 'README.md', 'CHANGELOG.md', 'SECURITY.md', 'requirements.txt',
              'requirements-test.txt', 'start_service.py', 'Verwalten.ps1', 'Installieren.ps1',
              'STARTEN.cmd', 'STOPPEN.cmd', 'EINRICHTEN.cmd', 'AUTOSTART AN.cmd', 'AUTOSTART AUS.cmd'}
MAX_ARCHIVE = 16 * 1024 * 1024


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Ungültige Versionsnummer.')
    return tuple(map(int, value.split('.')))


def read_url(url, limit=MAX_ARCHIVE):
    request = urllib.request.Request(url, headers={'User-Agent': 'Clip2Short-Updater'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if url.startswith('http://127.0.0.1:') else None
    open_url = opener.open if opener else urllib.request.urlopen
    with open_url(request, timeout=5 if opener else 15) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Update-Datei ist zu groß.')
    return data


def stage_release(release, current, stage, program=PROGRAM):
    tag = release['tag_name']
    if not tag.startswith('v') or release.get('draft') or release.get('prerelease'):
        return None
    version = tag[1:]
    if version_tuple(version) <= version_tuple(current):
        return None
    name = f'Clip2Short_Windows_{tag}.zip'
    asset = next(a for a in release['assets'] if a['name'] == name)
    digest = asset.get('digest') or ''
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('GitHub liefert keine prüfbare SHA-256-Prüfsumme.')
    archive = read_url(f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}')
    if hashlib.sha256(archive).hexdigest() != digest[7:]:
        raise ValueError('Die Prüfsumme des Updates stimmt nicht.')
    files = set()
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        if sum(entry.file_size for entry in bundle.infolist()) > MAX_ARCHIVE:
            raise ValueError('Entpacktes Update ist zu groß.')
        for entry in bundle.infolist():
            path = PurePosixPath(entry.filename)
            if (path.parts[:1] != ('Clip2Short',) or len(path.parts) < 2
                    or not all(re.fullmatch(r'[a-zA-Z0-9_. -]+', part)
                               and part not in ('.', '..') and not part.endswith(('.', ' '))
                               for part in path.parts)):
                raise ValueError('Das Update enthält einen ungültigen Dateipfad.')
            relative = PurePosixPath(*path.parts[1:])
            module = (len(relative.parts) == 2 and relative.parts[0] in ('clip2short', 'clip_engine')
                      and relative.suffix in ('.py', '.ps1', '.html', '.ico'))
            if not module and relative.as_posix() not in ROOT_FILES and relative.as_posix() != 'lumia/clip2short.js':
                continue
            key = relative.as_posix().casefold()
            if key in files:
                raise ValueError('Das Update enthält doppelte Dateien.')
            files.add(key)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(entry))
    required = {'version', 'requirements.txt', 'clip2short/__main__.py', 'clip2short/server.py'}
    if not required <= files or (stage/'VERSION').read_text().strip() != version:
        raise ValueError('Das Update ist unvollständig.')
    requirements = lambda root: (root/'requirements.txt').read_text(encoding='utf-8').splitlines()
    if requirements(stage) != requirements(program):
        raise ValueError('Dieses Update ändert Abhängigkeiten. Bitte das Windows-Paket manuell einrichten.')
    return version


def request_check(service, manual=False):
    if os.name != 'nt':
        raise ValueError('Automatische Updates sind unter Windows verfügbar.')
    with service.guard:
        if getattr(service, 'update_running', False):
            return
        service.update_running = True
        threading.Thread(target=check, args=(service, manual), daemon=True).start()


def check(service, manual):
    try:
        service.update_status = 'Suche nach Updates …'
        current = (PROGRAM/'VERSION').read_text().strip()
        release = json.loads(read_url(f'https://api.github.com/repos/{REPOSITORY}/releases/latest', 1024*1024))
        failed = service.root/'update-failed.txt'
        if not manual and failed.exists() and failed.read_text().strip() == release['tag_name'][1:]:
            service.update_status = 'Automatische Wiederholung nach fehlgeschlagenem Update ausgesetzt.'
            return
        with tempfile.TemporaryDirectory(prefix='clip2short-update-') as temporary:
            stage = Path(temporary)/'program'
            version = stage_release(release, current, stage)
            if not version:
                service.update_status = 'Clip2Short ist aktuell.'
                return
            service.update_status = f'Version {version} bereit. Warte auf laufende Aufträge …'
            while not service.stop.is_set() and (manual or service.cfg.get('auto_update', True)):
                with service.guard, service.store.lock:
                    if service.stop.is_set():
                        return
                    if not any(job['state'] in ACTIVE or job.get('preview_rendering')
                               for job in service.store.list(-1)):
                        destination = Path(tempfile.mkdtemp(prefix='clip2short-install-'))
                        try:
                            shutil.copytree(stage, destination/'program')
                            shutil.copy2(__file__, destination/'apply.py')
                            with (service.root/'update.log').open('a', encoding='utf-8') as log:
                                subprocess.Popen(
                                    [sys.executable, str(destination/'apply.py'), str(PROGRAM),
                                     str(service.root), str(os.getpid()), str(service.cfg['port']), current, version],
                                    cwd=PROGRAM, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                        except Exception:
                            shutil.rmtree(destination, ignore_errors=True)
                            raise
                        service.stop.set()
                        break
                if service.stop.wait(5):
                    return
            else:
                service.update_status = 'Updateprüfung beendet.'
                return
        service.http.shutdown()
    except Exception as exc:
        service.update_status = f'Update konnte nicht vorbereitet werden: {exc}'
    finally:
        with service.guard:
            service.update_running = False


def loop(service):
    while not service.stop.wait(30):
        if service.cfg.get('auto_update', True) and hasattr(service, 'http'):
            request_check(service)
            if service.stop.wait(6 * 3600):
                return


def replace_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def start_program(program, data):
    env = {**os.environ, 'CLIP2SHORT_CLIP_DATA': str(data)}
    return subprocess.Popen([sys.executable, '-m', 'clip2short', 'run'], cwd=program,
                            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def apply(program, data, parent, port, old, version):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.OpenProcess(0x00100000, False, parent)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 45000) != 0:
                raise RuntimeError('Der laufende Dienst wurde nicht rechtzeitig beendet.')
        finally:
            kernel.CloseHandle(handle)
    workspace = Path(__file__).resolve().parent
    stage = workspace/'program'
    backups = workspace/'backup'
    changed = []
    child = None
    try:
        if (program/'VERSION').read_text().strip() != old:
            raise RuntimeError('Die installierte Version wurde inzwischen geändert.')
        for source in sorted(stage.rglob('*'), key=lambda p: p.name == 'VERSION'):
            if not source.is_file():
                continue
            relative = source.relative_to(stage)
            destination = program/relative
            if destination.resolve() != destination:
                raise ValueError('Programmdatei liegt hinter einem umgeleiteten Pfad.')
            backup = backups/relative
            existed = destination.exists()
            if existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
            replace_file(source, destination)
            changed.append((destination, backup if existed else None))
        child = start_program(program, data)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and child.poll() is None:
            try:
                health = json.loads(read_url(f'http://127.0.0.1:{port}/health', 8192))
                if health.get('version') == version:
                    (data/'update-failed.txt').unlink(missing_ok=True)
                    print(f'Clip2Short {version} gestartet.')
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.5)
        raise RuntimeError('Die neue Version meldet sich nach dem Start nicht.')
    except Exception as exc:
        print(f'Update {version} fehlgeschlagen: {exc}', flush=True)
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        for path, backup in reversed(changed):
            if backup is None:
                path.unlink(missing_ok=True)
            else:
                replace_file(backup, path)
        (data/'update-failed.txt').write_text(version, encoding='utf-8')
        start_program(program, data)


if __name__ == '__main__':
    _, program, data, parent, port, old, version = sys.argv
    helper = Path(__file__).resolve()
    apply(Path(program), Path(data), int(parent), int(port), old, version)
    # Keep backups available if the rollback itself raised an exception.
    if helper.parent.parent == Path(tempfile.gettempdir()).resolve() and helper.parent.name.startswith('clip2short-install-'):
        shutil.rmtree(helper.parent, ignore_errors=True)
