import hashlib
import json
import os
import queue
import re
import secrets
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
import requests

from .captions import prompt,validate_caption
from .config import load_config,load_secrets,data_dir,footer_name
from .store import Store,now,instant
from .lumia import Lumia
from .layout import detect_scenes,NeedsLayoutReview


def clip_id(event):
    data=event.get('data',{}); extra=data.get('extraSettings',{})
    candidates=[extra.get('clip_id'),extra.get('id'),extra.get('clipId'),extra.get('clip_url'),extra.get('url'),data.get('dynamic',{}).get('value')]
    for value in candidates:
        value=str(value or '')
        if value.startswith('https://'):
            p=urlparse(value)
            if p.hostname=='clips.twitch.tv': value=p.path.strip('/').split('/')[0]
            elif p.hostname in ('twitch.tv','www.twitch.tv') and '/clip/' in p.path: value=p.path.split('/clip/',1)[1].split('/')[0]
            else: continue
        if re.fullmatch('[A-Za-z0-9_-]{8,200}',value): return value
    return None


def allowed_media(url):
    p=urlparse(url); host=(p.hostname or '').lower()
    return p.scheme=='https' and not p.username and not p.password and (host=='d1ndex63qxojbr.cloudfront.net' or any(host==s or host.endswith('.'+s) for s in ('twitch.tv','twitchcdn.net','jtvnw.net')))


def download(url,target,cancel):
    session=requests.Session(); session.trust_env=False
    for _ in range(4):
        if not allowed_media(url): raise ValueError('Ungültige Twitch-Medienadresse.')
        try: response=session.get(url,stream=True,allow_redirects=False,timeout=(10,30))
        except requests.RequestException: raise RuntimeError('Clip-Download ist momentan nicht erreichbar.') from None
        if response.is_redirect:
            from urllib.parse import urljoin
            url=urljoin(url,response.headers['Location']); response.close(); continue
        break
    else: raise RuntimeError('Zu viele Weiterleitungen beim Clip-Download.')
    if response.status_code!=200: response.close(); raise RuntimeError('Twitch-Download noch nicht verfügbar oder abgelaufen.')
    target=Path(target); tmp=target.with_suffix('.part'); count=0
    try:
        with tmp.open('wb') as out:
            for chunk in response.iter_content(1024*1024):
                if cancel.is_set(): raise RuntimeError('Download abgebrochen.')
                count+=len(chunk)
                if count>512*1024*1024: raise RuntimeError('Clip überschreitet die Downloadgrenze von 512 MB.')
                out.write(chunk)
        if not count: raise RuntimeError('Leere Clipdatei.')
        tmp.replace(target)
    except requests.RequestException: raise RuntimeError('Clip-Download wurde unterbrochen.') from None
    finally: response.close(); tmp.unlink(missing_ok=True)


class Service:
    def __init__(self,root=None,credentials=None):
        self.root=Path(root or data_dir()); self.cfg=load_config(self.root)
        self.credentials=credentials or load_secrets(self.root)
        self.instance=None
        try:
            self.instance=(self.root/'service.lock').open('a+b'); self.instance.seek(0)
            if not self.instance.read(1): self.instance.write(b'0'); self.instance.flush()
            self.instance.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.instance.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.instance.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            if self.instance: self.instance.close()
            raise RuntimeError('Der Clip2Short läuft bereits oder die Dienstsperre ist nicht zugänglich.') from None
        self.store=Store(self.root); self.lumia=Lumia(self.cfg,self.credentials)
        self.stop=threading.Event(); self.work=queue.Queue(); self.threads=[]
        self.status='Startet …'; self.resolving={}; self.guard=threading.RLock()
        for job in self.store.list(10000):
            if job['state']=='resolving': self.resolving[job['id']]=0
        for name in ('clips','renders','reports'): (self.root/name).mkdir(exist_ok=True)

    def close(self):
        self.stop.set()
        for t in self.threads: t.join(timeout=4)
        self.store.close(); self.instance.close()

    def log(self,message):
        self.status=message
        # Messages contain no access tokens, signed download URLs or raw events.
        with (self.root/'service.log').open('a',encoding='utf-8') as f: f.write(now()+' '+message+'\n')

    def start(self):
        for target in (self.listen,self.worker,self.supervise):
            t=threading.Thread(target=target,daemon=True); t.start(); self.threads.append(t)
        for job in self.store.list(10000):
            if job['state']=='queued': self.work.put(job['id'])

    def resolve(self,ident):
        job=self.store.get(ident)
        if not job or job['state']!='resolving': return
        attempts=job.get('resolve_attempts',0)
        if attempts>=5:
            self.store.update_if(ident,'resolving','error',error=job.get('error') or 'Metadaten konnten nach fünf Versuchen nicht geladen werden.')
            with self.guard: self.resolving.pop(ident,None)
            return
        if not self.store.update_if(ident,'resolving',resolve_attempts=attempts+1,next_resolve=time.time()+max(45,30*2**attempts)): return
        try:
            if self.cfg.get('clip_source')=='twitch' or self.cfg.get('transport')=='native':
                from .downloads import resolve_public
                self.resolved(resolve_public(ident,self.cfg['channel'],self.store.armed_at,self.cfg.get('broadcaster_id')))
                self.log('Neuer Twitch-Clip direkt geprüft: '+ident)
                return
            title=job.get('stream_title') or self.lumia.variable('twitch_channel_title')
            if not self.store.update_if(ident,'resolving',stream_title=str(title)): return
            self.lumia.command('resolve',ident,clip2short_stream_title=str(title),clip2short_armed_at=self.store.armed_at)
            self.log('Neuer Twitch-Clip wird durch Lumia geprüft: '+ident)
        except Exception as exc: self.store.update_if(ident,'resolving',error=str(exc)); self.log(str(exc))

    def dispatch(self,ident):
        job=self.store.get(ident)
        if not self.credentials.get('lumia_token'): return
        if not job or job['state']!='ready' or not self.cfg.get('enabled') or not (self.cfg.get('auto_upload') or job.get('manual_upload_requested')): return
        attempts=job.get('dispatch_attempts',0)
        if attempts>=3: return
        # Repeating this command cannot publish twice: /api/claim is atomic and single-use.
        if not self.store.update_if(ident,'ready',dispatch_attempts=attempts+1,next_dispatch=time.time()+120*2**attempts): return
        try:
            if self.cfg.get('transport')=='native':self.publish_native(ident)
            else:self.lumia.command('publish',ident)
        except Exception: self.log('Lumia-Aufruf unbestätigt. Der Upload bleibt durch die einmalige Freigabe geschützt.')

    def check_connection(self):
        if self.cfg.get('clip_source') == 'twitch':
            from .twitch import Twitch
            client = Twitch(self.credentials['twitch_client_id'], self.credentials['twitch_client_secret'])
            client.broadcaster(self.cfg['channel'])
            return {'message': 'Twitch-Direkterkennung erreichbar.'}
        if self.cfg.get('transport')=='native':
            result=self.lumia.probe_native()
            if result['channel'].casefold()!=self.cfg['channel'].casefold():raise ValueError('Der Twitch-Kanal in Lumia stimmt nicht mit Clip2Short überein.')
            self.diagnostic(result)
            return result
        self.lumia.command('check','diagnostic')
        return {'message':'Prüfung des vorhandenen Lumia-Befehls gestartet.'}

    def publish_native(self,ident):
        from .ai import caption as generate_caption
        job=self.store.get(ident);error=''
        for _ in range(2):
            try:
                caption=generate_caption(self.cfg,self.lumia,job,error)
                claim=self.claim_upload(ident,caption);break
            except (ValueError,KeyError,TypeError) as exc:error=str(exc)
        else:raise ValueError(error)
        if not claim['claimed']:return
        try:
            result=self.lumia.run_actions([{'base':'tiktok','type':'uploadAndPublishVideo','value':{
                'media':claim['media'],'title':claim['caption'],'privacy_level':claim['privacy'],
                'disable_comment':False,'disable_duet':False,'disable_stitch':False}}],timeout=600)
            if not isinstance(result.get('message'),dict) or result['message'].get('ran')!=1:
                raise RuntimeError('Lumia hat die Übergabe der Uploadaktion nicht bestätigt.')
            self.store.update_if(ident,'uploading','submitted',lumia_result=result,error='')
            self.log('TikTok-Aufruf an Lumia übergeben; Verarbeitung bei TikTok ist noch nicht bestätigt.')
        except Exception:
            self.store.update_if(ident,'uploading','uncertain',error='Lumia-Upload nicht eindeutig bestätigt. Zuerst TikTok kontrollieren; keine automatische Wiederholung.')
            raise

    def supervise(self):
        while not self.stop.wait(3):
            if not self.cfg.get('enabled'): continue
            for job in self.store.list(10000):
                if self.stop.is_set(): return
                try:
                    if job['state']=='resolving' and job.get('next_resolve',0)<=time.time(): self.resolve(job['id'])
                    elif job['state']=='ready' and job.get('next_dispatch',0)<=time.time(): self.dispatch(job['id'])
                except Exception: self.log('Ein Warteschritt wurde unterbrochen; erneute Prüfung folgt.')

    def retry(self,ident):
        with self.guard:
            job=self.store.get(ident)
            if not job or job.get('preview_rendering') or job['state'] not in ('error','review','ready'): raise ValueError('Dieser Zustand kann nicht erneut gestartet werden.')
            if job['state']=='ready':
                self.store.update_if(ident,'ready',dispatch_attempts=0,next_dispatch=0,error='');return
            self.resolving[ident]=0
            self.store.put(ident,'resolving',resolve_attempts=0,next_resolve=0,error='')

    def diagnostic(self,payload):
        (self.root/'diagnostic.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        ident=payload.get('id');job=self.store.get(ident) if ident else None
        if job and payload.get('stage')=='resolve' and job['state']=='resolving':
            self.store.update_if(ident,'resolving',error=str(payload.get('message',''))[:500])
        elif job and payload.get('stage')=='publish' and job['state']=='ready':
            self.store.update_if(ident,'ready',error=str(payload.get('message',''))[:500])
        elif job and payload.get('stage')=='editorial':
            prefix='preview_' if payload.get('kind')=='preview' else ''
            if not job.get(prefix+'editorial'):self.store.update_if(ident,job['state'],**{prefix+'editorial_error':str(payload.get('message',''))[:500]})
        self.log('Lumia-Diagnose: '+str(payload.get('message',''))[:300])

    def prepare_editorial(self,ident,source,metadata,pages,preview=False):
        if self.cfg.get('ai_provider') == 'none':
            job = self.store.get(ident)
            editorial = {'title': job['clip'].get('title') or job['category'], 'chat_quote': ''}
            self.store.update_fields(ident, **{('preview_' if preview else '')+'editorial': editorial})
            return editorial
        from .editorial import chat_candidates
        prefix='preview_' if preview else ''
        job=self.store.get(ident)
        fingerprint=hashlib.sha256(Path(source).read_bytes()).hexdigest()
        context=job.get(prefix+'editorial_context') or {}
        cached=job.get(prefix+'editorial')
        if (not preview and cached and context.get('pages')==pages
                and context.get('source_sha256',fingerprint)==fingerprint):
            from .editorial import validate
            try:
                checked=validate({k:cached[k] for k in ('title','chat_id','reply_excerpt')},context)
            except (ValueError,KeyError,TypeError):pass
            else:
                context['source_sha256']=fingerprint
                self.store.update_fields(ident,editorial_context=context)
                self.log('Bereits geprüfter Titel und Chatbezug werden wiederverwendet.')
                return checked
        try: candidates=chat_candidates(source,metadata,self.stop,lambda m,f:self.log(m))
        except Exception:
            if self.stop.is_set():raise
            candidates=[];self.log('Chat war nicht sicher lesbar. Der Clip erhält kein Chat-Zitat.')
        context={'key':secrets.token_urlsafe(20),'pages':pages,'candidates':candidates,'source_sha256':fingerprint}
        job=self.store.get(ident)
        self.store.update_if(ident,job['state'],**{prefix+'editorial_context':context,prefix+'editorial':None,prefix+'editorial_error':''})
        if self.cfg.get('transport')=='native':
            from .ai import editorial as generate_editorial
            self.log('KI erstellt einen eigenen Titel und prüft den Chatbezug …')
            error=''
            for _ in range(2):
                result=generate_editorial(self.cfg,self.lumia,job,context,error)
                try:
                    self.accept_editorial({'id':ident,'kind':'preview' if preview else 'main','analysis_key':context['key'],'result':result})
                    return self.store.get(ident)[prefix+'editorial']
                except ValueError as exc:error=str(exc)
            raise ValueError(error or 'KI-Titel konnte nicht geprüft werden.')
        self.log('Lumia erstellt einen eigenen Titel und prüft den Chatbezug …')
        self.lumia.command('editorial',ident,clip2short_analysis_kind='preview' if preview else 'main')
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            if self.stop.wait(.5):raise RuntimeError('Abgebrochen.')
            current=self.store.get(ident)
            if current.get(prefix+'editorial_error'):raise RuntimeError(current[prefix+'editorial_error'])
            if current.get(prefix+'editorial'):return current[prefix+'editorial']
        raise RuntimeError('Lumia hat den eigenen Titel nicht rechtzeitig geliefert. Kein Upload mit einem Platzhalter-Titel.')

    def accept_editorial(self,payload):
        with self.guard:return self._accept_editorial(payload)

    def _accept_editorial(self,payload):
        from .editorial import validate
        ident=payload['id'];job=self.store.get(ident);preview=payload.get('kind')=='preview';prefix='preview_' if preview else ''
        if not job or (not preview and job['state']!='analyzing') or (preview and job['state'] not in ('submitted','uploaded')):
            raise ValueError('Keine laufende Titelprüfung.')
        context=job.get(prefix+'editorial_context',{})
        if payload.get('analysis_key')!=context.get('key'):raise ValueError('Veraltete Titelantwort.')
        if job.get(prefix+'editorial'):return {'ok':True}
        try:result=validate(payload['result'],context)
        except Exception:
            self.store.update_if(ident,job['state'],**{prefix+'editorial_last_response':str(payload['result'])[:6000]})
            raise
        if not self.store.update_if(ident,job['state'],**{prefix+'editorial':result}):raise ValueError('Clipzustand hat sich geändert.')
        return {'ok':True}

    def preview(self,ident):
        with self.guard:self._preview(ident)

    def request_manual_upload(self, ident):
        with self.guard:
            if not self.credentials.get('lumia_token'):
                raise ValueError('Für die automatische Übergabe zuerst Lumia verbinden.')
            job = self.store.get(ident)
            if not job or job['state'] != 'review' or job.get('preview_rendering'):
                raise ValueError('Dieser manuelle Export kann gerade nicht übergeben werden.')
            if not self.cfg.get('enabled'):
                raise ValueError('Dienst ist angehalten.')
            eligible, reason = self.store.eligible(job['clip'], self.cfg['channel'])
            if not eligible:
                raise ValueError(reason)
            output = self.root / 'renders' / f'{ident}-manual.mp4'
            if job.get('preview_output') != str(output) or not output.is_file():
                raise ValueError('Bitte zuerst einen manuellen Export erstellen.')
            pages = (job.get('editorial_context') or {}).get('pages', [])
            transcript = job.get('manual_transcript', job.get('transcript') or ' '.join(p['text'] for p in pages))
            self.store.update_if(
                ident, 'review', 'ready', output=str(output),
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                privacy=self.cfg['privacy'], transcript=transcript,
                scenes=job.get('manual_scenes', []),
                manual_upload_requested=True, dispatch_attempts=0, next_dispatch=0, error='',
            )

    def manual_preview(self, data):
        from .studio import source_path, profiles
        from .design import validate, render_design
        from .layout import pixel_crop
        from clip_engine.media import probe_media
        from clip_engine.transcribe import transcribe_project

        ident = data['id']
        mode = data['mode']
        cfg = dict(self.cfg)
        crops = profiles(data['profiles'], cfg['profiles']).get(mode)
        if crops is None:
            raise ValueError('Unbekanntes Bildprofil.')
        design = render_design({'design': validate(data['design'])}, self.root)
        with self.guard:
            job = self.store.get(ident)
            if not job or job['state'] != 'review' or job.get('preview_rendering'):
                raise ValueError('Der manuelle Export ist nur für angehaltene Clips verfügbar.')
            source = source_path(self, 'job:' + ident)
            self.store.update_fields(ident, preview_rendering=True, preview_error='')

        def run():
            try:
                metadata = probe_media(source)
                output = self.root / 'renders' / f'{ident}-manual.mp4'
                editorial = job.get('editorial') or {}
                project = {
                    'source': str(source), 'output': str(output), 'design': design,
                    'brand': str(data.get('brand', cfg['brand']))[:100],
                    'channel': footer_name(cfg, data), 'accent': '#ffd13f',
                    'fps': cfg['fps'], 'normalize_audio': True,
                    'transcription_model': cfg['model'],
                    'segments': [{'start': 0, 'end': metadata['duration']}],
                    'title': editorial.get('title') or job['clip'].get('title') or job['category'],
                    'chat_quote': editorial.get('chat_quote', ''), 'label': job['category'].upper(),
                }
                pages = (job.get('editorial_context') or {}).get('pages')
                if pages is None:
                    pages = transcribe_project(project, lambda *_: None, self.stop)
                project['captions'] = pages
                scene = {'name': mode, 'start': 0, 'end': metadata['duration'],
                         'crops': {part: pixel_crop(rect, metadata['width'], metadata['height'])
                                   for part, rect in crops.items()}}
                self.render_output(project, [scene], metadata, output)
                self.store.update_fields(ident, preview_output=str(output), preview_rendering=False,
                                         manual_transcript=' '.join(page['text'] for page in pages),
                                         manual_captions=pages, manual_scenes=[scene])
            except Exception as exc:
                self.store.update_fields(ident, preview_error=str(exc), preview_rendering=False)

        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()

    def _preview(self,ident):
        from clip_engine.media import probe_media
        job=self.store.get(ident)
        if not job or job['state'] not in ('submitted','uploaded') or job.get('preview_rendering'):raise ValueError('Für diesen Clip kann gerade keine Vorschau erstellt werden.')
        self.store.update_fields(ident,preview_rendering=True,preview_error='',preview_output='')
        def run():
            try:
                source=self.root/'clips'/f'{ident}.mp4';metadata=probe_media(source)
                report=json.loads((self.root/'reports'/f'{ident}.json').read_text(encoding='utf8'))
                pages=report['captions'];editorial=self.prepare_editorial(ident,source,metadata,pages,preview=True)
                output=self.root/'renders'/f'{ident}-preview.mp4'
                base={'source':str(source),'output':str(output),'brand':self.cfg['brand'],'channel':footer_name(self.cfg),
                      'accent':'#ffd13f','fps':self.cfg['fps'],'normalize_audio':True,'captions':pages,
                      'title':editorial['title'],'chat_quote':editorial['chat_quote'],'label':job['category'].upper()}
                from .design import render_design
                base['design']=render_design(self.cfg,self.root)
                self.render_output(base,job['scenes'],metadata,output)
                self.store.update_fields(ident,preview_output=str(output),preview_rendering=False)
                self.log('KI-Vorschau fertig. Der vorhandene TikTok-Beitrag wurde nicht erneut hochgeladen.')
            except Exception as exc:
                self.store.update_fields(ident,preview_rendering=False,preview_error=str(exc));self.log('KI-Vorschau: '+str(exc))
        t=threading.Thread(target=run,daemon=True);self.threads.append(t);t.start()

    def listen(self):
        if self.cfg.get('clip_source') == 'twitch':
            from .twitch import listen
            listen(self)
        else:
            self.lumia.events(self.stop,self.on_event,self.log)

    def on_event(self,event):
        if not self.cfg.get('enabled'): return
        data=event.get('data',{}); extra=data.get('extraSettings',{})
        if data.get('replay') or data.get('test') or extra.get('isTest'): return
        try:
            stamp=extra.get('timestamp')
            if stamp is None or instant(stamp)<instant(self.store.armed_at): return
        except (ValueError,TypeError): return
        ident=clip_id(event)
        if not ident:
            self.log('Neues Clip-Ereignis ohne verwertbare Clip-ID. Keine alten Clips werden ersatzweise geladen.'); return
        with self.guard:
            if self.store.get(ident) or ident in self.resolving: return
            self.resolving[ident]=time.monotonic()
            self.store.put(ident,'resolving',clip={'id':ident,'title':'Neuer Clip · Metadaten werden geprüft'},event_at=now(),resolve_attempts=0,next_resolve=0)
        self.resolve(ident)

    def resolved(self,payload):
        clip=payload['clip']; ident=clip['id']
        if ident not in self.resolving: raise ValueError('Kein neues Clip-Ereignis für diese ID registriert.')
        media=payload.get('download_url','')
        if media and not allowed_media(media): raise ValueError('Ungültige Downloadadresse.')
        job,reason=self.store.create(clip,self.cfg['channel'],category=payload['category'],stream_title=payload.get('stream_title',''),download_url=media)
        with self.guard: self.resolving.pop(ident,None)
        if job and not reason: self.work.put(ident)
        return {'accepted':bool(job and not reason),'reason':reason}

    def worker(self):
        while not self.stop.is_set():
            try: ident=self.work.get(timeout=.5)
            except queue.Empty: continue
            try: self.process(ident)
            except NeedsLayoutReview as exc: self.store.put(ident,'review',error=str(exc)); self.log(str(exc))
            except Exception as exc:
                current=self.store.get(ident)
                if current and current['state'] not in ('uploading','submitted','uploaded','uncertain','dispatching'):
                    self.store.put(ident,'error',error=str(exc))
                self.log('Clip-Verarbeitung gestoppt: '+str(exc))
            finally: self.work.task_done()

    def process(self,ident):
        from clip_engine.media import probe_media,find_binary,_creation_flags
        from clip_engine.render import render_project
        from clip_engine.transcribe import transcribe_project
        job=self.store.get(ident)
        if not job or job['state']!='queued': return
        ok,reason=self.store.eligible(job['clip'],self.cfg['channel'])
        if not ok: self.store.put(ident,'ignored',error=reason); return
        source=self.root/'clips'/f'{ident}.mp4'; output=self.root/'renders'/f'{ident}.mp4'
        self.store.put(ident,'downloading'); self.log('Neuer Clip wird geladen: '+ident)
        if not source.is_file():
            from .downloads import public_media
            for attempt in range(3):
                try:
                    download(job.get('download_url') or public_media(job['clip']),source,self.stop);break
                except RuntimeError:
                    if attempt==2 or self.stop.wait(5*(attempt+1)): raise
        metadata=probe_media(source)
        if metadata['duration']>180: raise ValueError('Clip ist länger als 180 Sekunden.')
        base={'source':str(source),'output':str(output),'segments':[{'start':0,'end':metadata['duration']}],
              'transcription_model':self.cfg['model'],'brand':self.cfg['brand'],'channel':footer_name(self.cfg),
              'accent':'#ffd13f','fps':self.cfg['fps'],'normalize_audio':True,'cleanup_regions':[],
              'title':str(job['clip'].get('title',''))[:75] or job['category'],'label':job['category'].upper()}
        from .design import render_design
        base['design']=render_design(self.cfg,self.root)
        self.store.put(ident,'transcribing'); pages=transcribe_project(base,lambda m,f:self.log(m),self.stop)
        base['captions']=pages; transcript=' '.join(p['text'] for p in pages)
        self.store.put(ident,'analyzing',transcript=transcript)
        scenes,evidence=detect_scenes(source,metadata,job['category'],self.cfg,lambda m,f:self.log(m),self.stop)
        editorial=self.prepare_editorial(ident,source,metadata,pages)
        base.update(title=editorial['title'],chat_quote=editorial['chat_quote'])
        self.store.put(ident,'rendering')
        self.render_output(base,scenes,metadata,output)
        digest=hashlib.sha256(output.read_bytes()).hexdigest()
        job=self.store.put(ident,'ready',transcript=transcript,output=str(output),sha256=digest,scenes=scenes,privacy=self.cfg['privacy'])
        (self.root/'reports'/f'{ident}.json').write_text(json.dumps({'clip':job['clip'],'category':job['category'],'scenes':scenes,'evidence':evidence,'captions':pages,'editorial':editorial,'design':base['design']},ensure_ascii=False,indent=2),encoding='utf-8')
        self.dispatch(ident)
        self.log('Hochkantclip fertig: '+ident)

    def render_output(self,base,scenes,metadata,output):
        from clip_engine.render import render_project
        from clip_engine.media import find_binary
        pieces=[]
        with tempfile.TemporaryDirectory(prefix='clip2short-scenes-',dir=self.root) as temp:
            for index,scene in enumerate(scenes):
                project={**base,'mode':'just_chatting' if scene['name']=='camera' else 'gameplay','scene_name':scene['name'],
                         'crops':scene['crops'],'segments':[{'start':scene['start'],'end':scene['end']}],
                         'output':str(Path(temp)/f'part{index}.mp4')}
                render_project(project,lambda m,f:self.log(m),self.stop); pieces.append(Path(project['output']))
            if len(pieces)==1: os.replace(pieces[0],output)
            else:
                from clip_engine.render import _run_encoder
                manifest=Path(temp)/'list.txt'
                manifest.write_text('\n'.join("file '"+p.name+"'" for p in pieces),encoding='utf-8')
                staged=Path(temp)/'joined.mp4'
                command=[find_binary('ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y','-progress','pipe:1','-f','concat','-safe','0','-i',str(manifest),'-c','copy','-movflags','+faststart',str(staged)]
                _run_encoder(command,metadata['duration'],lambda m,f:self.log(m),self.stop); os.replace(staged,output)

    def public_job(self,ident):
        job=self.store.get(ident)
        if not job: raise ValueError('Clip nicht gefunden.')
        return {k:v for k,v in job.items() if k!='download_url'}

    def claim_upload(self,ident,caption):
        job=self.store.get(ident)
        if not job: raise ValueError('Clip nicht gefunden.')
        if not self.cfg.get('enabled'): raise ValueError('Dienst ist angehalten.')
        ok,reason=self.store.eligible(job['clip'],self.cfg['channel'])
        if not ok: raise ValueError(reason)
        clean=validate_caption(caption,job['category'])
        path=Path(job['output'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=job['sha256']: raise ValueError('Gerenderte Datei fehlt oder wurde geändert.')
        if job.get('privacy') not in ('SELF_ONLY','PUBLIC_TO_EVERYONE'): raise ValueError('Sichtbarkeit fehlt.')
        if not self.store.claim(ident): return {'claimed':False,'reason':'bereits übergeben oder nicht bereit'}
        self.store.put(ident,'uploading',caption=clean)
        return {'claimed':True,'media':str(path),'caption':clean,'privacy':job['privacy']}
