"""Browser-based first run, isolated from the job database until completion."""
import json
import threading
import webbrowser
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from .config import load_config,load_secrets,save_config,save_secrets,channel_name
from .lumia import Lumia


def lumia_url(value):
    parsed=urlparse(str(value))
    if parsed.scheme not in ('http','https') or parsed.hostname not in ('localhost','127.0.0.1','::1') or parsed.path.rstrip('/')!='/api' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Bitte die lokale Lumia-Adresse verwenden, z. B. http://127.0.0.1:39231/api.')
    return str(value).rstrip('/')


def action(service,path,data):
    if path=='/api/setup/cancel':
        if not getattr(service,'setup_only',False):raise ValueError('Ein laufender Dienst wird durch Abbrechen der Einrichtung nicht beendet.')
        threading.Timer(.3,service.http.shutdown).start()
        return {'ok':True,'message':'Einrichtung abgebrochen. Es wurde kein Clip verarbeitet.'}
    if path=='/api/setup/connect':
        candidate={**service.cfg,'lumia_url':lumia_url(data.get('url',service.cfg['lumia_url']))}
        token=str(data.get('token') or service.credentials.get('lumia_token','')).strip()
        if not token:raise ValueError('Bitte den lokalen API-Token aus Lumia eingeben.')
        credentials={**service.credentials,'lumia_token':token}
        client=Lumia(candidate,credentials);result=client.probe_native()
        # Keep the token only in memory until the explicit finish/save action.
        service.setup_connection={'cfg':candidate,'credentials':credentials,'result':result}
        if getattr(service,'setup_only',False):service.cfg['channel']=channel_name(result['channel'])
        return result
    if path=='/api/setup/models':
        from .ai import models
        return {'models':models(data.get('url','http://127.0.0.1:11434'))}
    if path=='/api/setup/pull-model':
        from .ai import local_url
        import requests
        address=local_url(data.get('url','http://127.0.0.1:11434'))
        if getattr(service,'setup_progress',{}).get('status')=='running':return {'ok':True}
        service.setup_progress={'status':'running','message':'Qwen3 4B wird lokal geladen (Modell ca. 2,5 GB) …'}
        def pull():
            client=requests.Session();client.trust_env=False
            try:
                complete=False
                with client.post(address+'/api/pull',json={'model':'qwen3:4b','stream':True},stream=True,timeout=(5,90)) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:continue
                        result=json.loads(line)
                        if result.get('status')=='success':complete=True
                        if result.get('error'):raise RuntimeError('Modell konnte nicht geladen werden.')
                        percent=round(result.get('completed',0)*100/max(1,result.get('total',1)))
                        service.setup_progress={'status':'running','message':'Lokales Modell: '+str(percent)+' % · '+str(result.get('status',''))[:120]}
                if not complete:raise RuntimeError('Modellübertragung nicht vollständig.')
                service.setup_progress={'status':'done','message':'Qwen3 4B ist bereit.'}
            except Exception:service.setup_progress={'status':'error','message':'Modell konnte nicht geladen werden. Ollama, Internet und freien Speicher prüfen.'}
        threading.Thread(target=pull,daemon=True).start();return {'ok':True}
    if path=='/api/setup/finish':
        from .ai import local_url,models
        if not getattr(service,'setup_only',False) and any(j['state'] in ('resolving','queued','downloading','transcribing','analyzing','rendering','uploading','dispatching') for j in service.store.list()):
            raise ValueError('Bitte die laufende Clip-Verarbeitung abschließen lassen, bevor die Integration umgestellt wird.')
        connection=getattr(service,'setup_connection',None)
        if not connection:raise ValueError('Bitte zuerst die Lumia-Verbindung prüfen.')
        cfg={**service.cfg,'lumia_url':connection['cfg']['lumia_url'],'transport':'native',
             'channel':channel_name(connection['result']['channel']),'broadcaster_id':connection['result'].get('broadcaster_id','')}
        if not getattr(service,'setup_only',False) and service.cfg['channel'].casefold()!=cfg['channel'].casefold():
            raise ValueError('Bei einer vorhandenen Installation darf der Kanal nicht beiläufig gewechselt werden.')
        provider=data.get('ai_provider','lumia')
        if provider not in ('lumia','ollama'):raise ValueError('Unbekannter KI-Anbieter.')
        cfg['ai_provider']=provider
        if provider=='ollama':
            cfg['ollama_url']=local_url(data.get('ollama_url','http://127.0.0.1:11434'))
            cfg['ollama_model']=str(data.get('ollama_model',''))
            if cfg['ollama_model'] not in models(cfg['ollama_url']):raise ValueError('Bitte ein vorhandenes lokales Modell auswählen.')
        else:
            probe=Lumia(connection['cfg'],connection['credentials']).evaluate('{{ai_prompt=Antworte ausschließlich mit CLIP2SHORT_OK.}}',150)
            if probe.strip()!='CLIP2SHORT_OK':raise ValueError('Lumias Text-KI ist noch nicht einsatzbereit. Dort einen Anbieter einrichten oder die lokale KI auswählen.')
        auto=data.get('auto_upload',False)
        if not isinstance(auto,bool):raise ValueError('Ungültige Upload-Auswahl.')
        cfg['auto_upload']=auto
        if data.get('privacy') not in ('SELF_ONLY','PUBLIC_TO_EVERYONE'):raise ValueError('Bitte eine Sichtbarkeit auswählen.')
        cfg['privacy']=data['privacy']
        if data.get('prepare_events',False):
            Lumia(connection['cfg'],connection['credentials']).prepare_clip_events()
        credentials=save_secrets(connection['credentials']['lumia_token'],service.root,bridge_key=service.credentials['bridge_key'])
        save_config(cfg,service.root)
        (getattr(service,'program_root',Path(__file__).resolve().parents[1])/'installation.json').write_text(json.dumps({'data_dir':str(service.root)},ensure_ascii=False),encoding='utf-8')
        service.credentials.update(credentials);service.cfg.update(cfg);service.lumia=Lumia(service.cfg,service.credentials)
        autostart=False;warning=''
        if data.get('autostart',False):
            script=getattr(service,'program_root',Path(__file__).resolve().parents[1])/'Verwalten.ps1'
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Action','AutostartAn'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
            autostart=result.returncode==0
            if not autostart:warning=' Der automatische Windows-Start konnte nicht eingerichtet werden. AUTOSTART AN.cmd kann später erneut ausgeführt werden.'
        service.autostart_registered=autostart
        if getattr(service,'setup_only',False):
            service.finished.set()
            threading.Timer(.5,service.http.shutdown).start()
        return {'ok':True,'message':'Einrichtung gespeichert. Clip2Short verwendet Lumia ohne zusätzlichen Befehl.'+warning,'first_run':getattr(service,'setup_only',False)}
    raise ValueError('Unbekannter Einrichtungsschritt.')


class SetupSession:
    setup_only=True
    def __init__(self,root):
        import secrets
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.cfg=load_config(root)
        self.credentials=load_secrets(root) if (self.root/'credentials.dpapi').exists() else {'bridge_key':secrets.token_urlsafe(32),'lumia_token':''}
        self.store=SimpleNamespace(list=lambda:[],get=lambda ident:None,armed_at=None)
        self.finished=threading.Event();self.stop=threading.Event();self.cfg['auto_upload']=False
        self.status='Ersteinrichtung · Verarbeitung ist noch nicht gestartet'
        if not (self.root/'credentials.dpapi').exists():self.cfg['brand']=''


def run(root):
    from .server import serve
    session=SetupSession(root)
    import requests
    client=requests.Session();client.trust_env=False
    try:
        current=client.get('http://127.0.0.1:'+str(session.cfg['port'])+'/health',timeout=2)
        if current.ok and current.json().get('channel')==session.cfg['channel']:
            webbrowser.open('http://127.0.0.1:'+str(session.cfg['port'])+'/setup');return False
    except (requests.RequestException,ValueError):pass
    # Bind before opening a browser; no stale dashboard from a second instance.
    thread=threading.Thread(target=serve,args=(session,),daemon=True);thread.start()
    for _ in range(100):
        if hasattr(session,'http'):break
        if not thread.is_alive():raise RuntimeError('Der Einrichtungsport ist bereits belegt. Einen laufenden Clip2Short-Dienst über /setup konfigurieren.')
        threading.Event().wait(.05)
    else:raise RuntimeError('Einrichtung konnte nicht gestartet werden.')
    webbrowser.open('http://127.0.0.1:'+str(session.cfg['port'])+'/setup')
    thread.join()
    if session.finished.is_set() and getattr(session,'autostart_registered',False):
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',"Start-ScheduledTask -TaskName 'Clip2Short'"],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode==0:return False
    return session.finished.is_set()
