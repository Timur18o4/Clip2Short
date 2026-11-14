"""Windows notification icon owned by the background service."""
import os
from pathlib import Path
import subprocess
import threading


def start(service, http):
    if os.name != 'nt':
        return None
    script = Path(__file__).with_suffix('.ps1')
    process = subprocess.Popen(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA',
         '-File', str(script), '-ServicePid', str(os.getpid()), '-Port', str(http.server_port)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        process.stdin.write((service.credentials['bridge_key'] + '\n').encode('ascii'))
        process.stdin.flush()
    except OSError:
        close(process)
        raise

    def receive():
        with process.stdout as pipe:
            if pipe.readline().strip() == b'stop':
                service.stop.set()
                http.shutdown()

    threading.Thread(target=receive, daemon=True).start()
    return process


def close(process):
    if process is None:
        return
    if process.stdin is not None:
        process.stdin.close()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=3)
