import argparse
import getpass
import json
import os
import signal
import sys
import threading
import webbrowser
from .config import data_dir,load_config,save_config,save_secrets,channel_name


def main():
    for stream in (sys.stdout,sys.stderr):
        if stream and hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf-8',errors='replace')
    p=argparse.ArgumentParser(description='Clip2Short – neue Twitch-Clips über Lumia')
    p.add_argument('action',choices=['run','setup','configure','dashboard','check','stop'],nargs='?',default='run')
    p.add_argument('--channel',help='Twitch-Kanal beim Einrichten, ohne URL')
    a=p.parse_args(); root=data_dir()
    if a.action=='configure' or (a.action=='run' and not (root/'credentials.dpapi').exists()):
        from .wizard import run
        if not run(root):return
        a.action='run'
    if a.action=='run' and (sys.stdout is None or sys.stderr is None):
        root.mkdir(parents=True,exist_ok=True)
        background_log=(root/'runtime.log').open('a',encoding='utf8',buffering=1)
        if sys.stdout is None:sys.stdout=background_log
        if sys.stderr is None:sys.stderr=background_log
    if a.action=='setup':
        cfg=load_config(root)
        supplied_channel=a.channel or os.environ.get('CLIP2SHORT_TWITCH_CHANNEL') or input('Dein Twitch-Kanal (ohne URL): ')
        cfg['channel']=channel_name(supplied_channel)
        token=os.environ.get('CLIP2SHORT_LUMIA_TOKEN') or getpass.getpass('Lokaler Lumia-API-Token: ')
        if not token.strip():raise ValueError('Der lokale Lumia-API-Token darf nicht leer sein.')
        save_secrets(token,root); save_config(cfg,root)
        from pathlib import Path
        (Path(__file__).resolve().parents[1]/'installation.json').write_text(json.dumps({'data_dir':str(root)},ensure_ascii=False),encoding='utf-8')
        print('Zugangsdaten lokal mit Windows-DPAPI gespeichert.'); return
    if a.action=='dashboard': webbrowser.open('http://127.0.0.1:'+str(load_config(root)['port'])); return
    if a.action=='stop':
        import requests
        from .config import load_secrets
        r=requests.post('http://127.0.0.1:'+str(load_config(root)['port'])+'/api/stop',headers={'Authorization':'Bearer '+load_secrets(root)['bridge_key']},json={},timeout=5)
        r.raise_for_status(); print('Dienst wird beendet.'); return
    if a.action=='check':
        import requests
        from .config import load_secrets
        r=requests.post('http://127.0.0.1:'+str(load_config(root)['port'])+'/api/check',headers={'Authorization':'Bearer '+load_secrets(root)['bridge_key']},json={},timeout=35)
        r.raise_for_status(); print('Lumia-Prüfung ausgelöst.')
        return
    from .service import Service
    service=Service(root)
    from .server import serve
    service.start()
    try: serve(service)
    except KeyboardInterrupt: service.stop.set()
    finally:
        service.close()


if __name__=='__main__':
    try: main()
    except Exception:
        import traceback
        root=data_dir();root.mkdir(parents=True,exist_ok=True)
        (root/'startup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        if sys.stderr: print('Dienststart fehlgeschlagen. Details: '+str(root/'startup-error.log'),file=sys.stderr)
        raise SystemExit(1)
