import hmac
import json
import copy
import math
import secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,unquote,parse_qs
from .captions import prompt


def serve(service):
    ui_key=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,code,value,content='application/json; charset=utf-8'):
            raw=(json.dumps(value,ensure_ascii=False) if content.startswith('application/json') else value).encode()
            self.send_response(code); self.send_header('Content-Type',content); self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(raw)
        def authorized(self):
            if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'): return False
            supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
            return hmac.compare_digest(supplied,service.credentials['bridge_key']) or hmac.compare_digest(supplied,ui_key)
        def do_GET(self):
            path=urlparse(self.path).path
            if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'): self.reply(403,{'error':'Nur localhost erlaubt.'}); return
            if path in ('/','/studio','/setup'):
                name='studio.html' if path in ('/studio','/setup') or getattr(service,'setup_only',False) else 'dashboard.html'
                html=(Path(__file__).parent/name).read_text(encoding='utf-8').replace('__UI_KEY__',ui_key).replace('__SETUP_MODE__','true' if path=='/setup' or getattr(service,'setup_only',False) else 'false')
                self.reply(200,html,'text/html; charset=utf-8'); return
            if path=='/health': self.reply(200,{'ok':True,'armed_at':service.store.armed_at,'channel':service.cfg['channel']}); return
            if not self.authorized(): self.reply(401,{'error':'Nicht autorisiert.'}); return
            if path=='/api/setup/progress':self.reply(200,getattr(service,'setup_progress',{'status':'idle'}));return
            if path.startswith('/api/studio'):
                try:
                    from . import studio
                    if path=='/api/studio':self.reply(200,studio.state(service));return
                    if path=='/api/studio/frame':
                        query=parse_qs(urlparse(self.path).query);self.reply(200,studio.frame(service,query['source'][0],query.get('at',['0'])[0]));return
                    self.reply(404,{'error':'Nicht gefunden.'})
                except Exception as exc:self.reply(400,{'error':str(exc)})
                return
            if path=='/api/status':
                diagnostic=service.root/'diagnostic.json'
                self.reply(200,{'status':service.status,'diagnostic':json.loads(diagnostic.read_text(encoding='utf-8')) if diagnostic.exists() else {},'armed_at':service.store.armed_at,'config':service.cfg,'jobs':[service.public_job(j['id']) for j in service.store.list()]}); return
            if path.startswith('/api/jobs/'):
                try:
                    job=service.public_job(unquote(path.rsplit('/',1)[1])); job['prompt']=prompt(job)
                    from .editorial import instruction
                    for prefix in ('','preview_'):
                        if job.get(prefix+'editorial_context'):job[prefix+'editorial_prompt']=instruction(job,job[prefix+'editorial_context'])
                    self.reply(200,job)
                except Exception as exc: self.reply(400,{'error':str(exc)})
                return
            if path.startswith('/api/media/') or path.startswith('/api/original/'):
                try:
                    job=service.public_job(unquote(path.rsplit('/',1)[1])); variant='preview_output' if parse_qs(urlparse(self.path).query).get('preview')==['1'] else 'output'
                    if path.startswith('/api/original/'):
                        from .studio import source_path
                        file=source_path(service,'job:'+job['id'])
                    else:
                        file=Path(job[variant]).resolve()
                        if file.parent!=(service.root/'renders').resolve() or not file.is_file(): raise ValueError('Video fehlt.')
                    raw=file.read_bytes(); self.send_response(200);self.send_header('Content-Type','video/mp4')
                    self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
                except Exception as exc: self.reply(400,{'error':str(exc)})
                return
            self.reply(404,{'error':'Nicht gefunden.'})
        def do_POST(self):
            if not self.authorized(): self.reply(401,{'error':'Nicht autorisiert.'}); return
            try:
                length=int(self.headers.get('Content-Length',0))
                path=urlparse(self.path).path
                if path in ('/api/studio/background','/api/studio/reference'):
                    limit=12*1024*1024 if path.endswith('background') else 512*1024*1024
                    if not 0<length<=limit:raise ValueError('Datei ist zu groß oder leer.')
                    from . import studio
                    self.reply(200,studio.background(service,self.rfile.read(length)) if path.endswith('background') else studio.upload_reference(service,self.rfile,length,self.headers.get('X-File-Name','')));return
                if not 0<length<=262144: raise ValueError('Ungültige Nutzlastgröße.')
                data=json.loads(self.rfile.read(length)); path=urlparse(self.path).path
                if path.startswith('/api/setup/'):
                    from .wizard import action
                    self.reply(200,action(service,path,data));return
                if path in ('/api/studio/save','/api/studio/preview'):
                    from . import studio
                    self.reply(200,studio.save(service,data) if path.endswith('save') else studio.preview(service,data));return
                if getattr(service,'setup_only',False):raise ValueError('Bitte zuerst die Einrichtung abschließen.')
                if path=='/api/eligible':
                    ident=data['clip']['id']; ok,reason=service.store.eligible(data['clip'],service.cfg['channel'])
                    if ident not in service.resolving: ok,reason=False,'kein neues Ereignis registriert'
                    self.reply(200,{'eligible':ok,'reason':reason}); return
                if path=='/api/resolved': self.reply(200,service.resolved(data)); return
                if path=='/api/claim': self.reply(200,service.claim_upload(data['id'],data['caption'])); return
                if path=='/api/editorial':self.reply(200,service.accept_editorial(data));return
                if path=='/api/manual-upload':service.request_manual_upload(data['id']);self.reply(200,{'ok':True});return
                if path=='/api/manual-preview':service.manual_preview(data);self.reply(200,{'ok':True});return
                if path=='/api/preview':service.preview(data['id']);self.reply(200,{'ok':True});return
                if path=='/api/confirm':
                    job=service.store.get(data['id'])
                    if not job or job['state'] not in ('submitted','uncertain'):raise ValueError('Kein zu bestätigender Upload.')
                    service.store.update_if(data['id'],job['state'],'uploaded',confirmation='Vom Nutzer bei TikTok bestätigt')
                    self.reply(200,{'ok':True});return
                if path=='/api/result':
                    job=service.store.get(data['id'])
                    if not job or job['state']!='uploading': raise ValueError('Kein laufender Upload.')
                    state='uncertain' if data.get('error') else 'submitted'
                    service.store.put(data['id'],state,error=str(data.get('error',''))[:500],lumia_result=data.get('result'),possible_url=str(data.get('url',''))[:300])
                    service.log('TikTok-Aufruf '+('ungeklärt' if state=='uncertain' else 'durch Lumia abgeschlossen')+': '+data['id'])
                    self.reply(200,{'ok':True}); return
                if path=='/api/diagnostic':
                    service.diagnostic(data); self.reply(200,{'ok':True}); return
                if path=='/api/retry': service.retry(data['id']); self.reply(200,{'ok':True}); return
                if path=='/api/settings':
                    from .config import save_config
                    cfg=copy.deepcopy(service.cfg)
                    for key in ('enabled','auto_upload','vision','require_face'):
                        if key in data:
                            if not isinstance(data[key],bool): raise ValueError('Schalter benötigt true oder false.')
                            cfg[key]=data[key]
                    if 'privacy' in data:
                        if data['privacy'] not in ('SELF_ONLY','PUBLIC_TO_EVERYONE'): raise ValueError('Ungültige Sichtbarkeit.')
                        cfg['privacy']=data['privacy']
                    if 'profiles' in data:
                        for name,profile in data['profiles'].items():
                            if name not in cfg['profiles']: raise ValueError('Unbekanntes Profil.')
                            if set(profile)!=set(cfg['profiles'][name]): raise ValueError('Die erforderlichen Bildausschnitte dürfen nicht entfernt werden.')
                            for rect in profile.values():
                                if any(not isinstance(rect.get(k),(int,float)) or not math.isfinite(rect[k]) for k in ('x','y','width','height')) or min(rect['x'],rect['y'])<0 or min(rect['width'],rect['height'])<=0 or rect['x']+rect['width']>1.000001 or rect['y']+rect['height']>1.000001: raise ValueError('Ausschnitte müssen innerhalb des Quellbilds liegen (Werte 0–1).')
                        cfg['profiles'].update(data['profiles'])
                    save_config(cfg,service.root); service.cfg.update(cfg);self.reply(200,{'ok':True}); return
                if path=='/api/check': self.reply(200,service.check_connection()); return
                if path=='/api/stop':
                    self.reply(200,{'ok':True});service.stop.set()
                    import threading
                    threading.Thread(target=service.http.shutdown,daemon=True).start();return
                self.reply(404,{'error':'Nicht gefunden.'})
            except Exception as exc: self.reply(400,{'error':str(exc)})
    http=ThreadingHTTPServer(('127.0.0.1',service.cfg['port']),Handler)
    service.http=http
    try: http.serve_forever(poll_interval=.5)
    finally: http.server_close()
